"""到期结算与事件投递：打工/旅程到期 → 业务与账本同一个事务 → 世界事件与 outbox → 家庭消息等下游。

结算（settle）：已到期、还没登记的事实——出发、到站、到店、收工、回家——在一个写事务里提交：
  工资（按 web:job:<journey> 幂等）、世界事件（journey + 事件键唯一）、回家时的行程完成、每个下游一行 outbox。
  任何一步失败整体回滚，下次读取或下一轮再补；不会出现“钱到了、事件没记”或“消息发了、事件没记”。
  事件的有效时间是原本应发生的时刻（occurred_at），晚恢复只影响登记时间（applied_at），不改有效时间。
投递（deliver_outbox）：提交之后按 outbox 逐个下游投递。某个下游失败只让它自己退避重试，已经成立的事实不撤销，其他下游照常。
  fast 通道：只写库的下游（家庭来信、公开动态、收藏、证件），结算后立即投递，任务进程每轮再补一次；
  slow 通道：可能调模型的下游（攻略、朋友相遇的新鲜事），只由任务进程投递，网页请求不等模型。
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..schemas import EconomyTransactionType
from ..utils import utcnow
from ..web_platform.lease import LeaseLost
from ..web_platform.outbox import OutboxItem
from ..web_platform.runtime_epochs import bump_in
from ..web_platform.uow import unit_of_work
from .events import WorldEvent

logger = logging.getLogger("petsoul.web.journey")

FAST, SLOW = "fast", "slow"
ACTIVITY_EVENTS = ("departed", "visit_started", "visit_ended", "returned_home")  # 改变主活动的事实：语义版本换代
MAX_ROUNDS = 12  # 同一旅程同一下游按顺序一条条投递；一次最多推进这么多轮，剩下的交给下一轮


class JourneySettlementMixin:
    def add_consumer(self, name: str, sink, lane: str = FAST) -> None:
        """登记一个世界事件下游（名字写进 outbox，改名等于换一个下游）。"""
        self.consumers[name] = (sink, lane)

    def _apply_due(self, journey, now: datetime) -> None:
        # 下游读状态可能又触发补齐：同一线程里正在结算这段旅程时不重入
        busy = self._applying.__dict__.setdefault("journeys", set())
        if journey.journey_id in busy:
            return
        busy.add(journey.journey_id)
        try:
            recorded = self._settle(journey, now)
        finally:
            busy.discard(journey.journey_id)
        if recorded:
            self.deliver_outbox(now, lanes=(FAST,), aggregate_id=journey.journey_id)

    def _settle(self, journey, now: datetime) -> list[str]:
        """把已到期、还没登记的事件在一个写事务里登记；返回这次新登记的事件键。"""
        due = sorted(self._due_events(journey, now), key=lambda e: e[2])
        if not due:
            return []
        recorded: list[str] = []
        with unit_of_work(self.storage) as conn:
            applied = self.repo.applied_events(journey.journey_id, conn=conn)  # 拿到写锁之后再读：并发的另一方已经登记的不会重复
            for key, kind, occurred_at, data in due:
                if key not in applied:
                    if kind == "work_done":
                        self.economy.apply_in(conn, journey.pet_id, data["pay"], EconomyTransactionType.web_job_income, f"web:job:{journey.journey_id}",
                                              reason=f"{data['label']}的工钱", source="web.journey.work", now=occurred_at)
                    if self._record_in(conn, journey.journey_id, key, kind, occurred_at, data, now):
                        recorded.append(key)
                if kind == "returned_home":
                    self.repo.complete(journey.journey_id, occurred_at, conn=conn)
            if any(key in ACTIVITY_EVENTS for key in recorded):
                # 主活动变了：思考中的提案、在途的表达要按新版本复核（同一事务里换代，不留窗口）
                bump_in(conn, journey.pet_id, "activity_epoch", now)
        return recorded

    def due_summary(self, pet_id: str, now: datetime | None = None) -> dict | None:
        """只读：这只宠物进行中的旅程里最早一个还没登记的事件（给心跳当“到期事项”）。没有就返回 None。

        整段旅程只给一项：由旅程服务按顺序补齐，工钱在其中只入账一次。commitment=True 表示这批里有对家人的承诺（工钱、到家）。
        """
        journey = self.repo.active_for_pet(pet_id)
        if journey is None:
            return None
        now = now or utcnow()
        applied = self.repo.applied_events(journey.journey_id)
        pending = [(key, kind, at) for key, kind, at, _ in self._due_events(journey, now) if key not in applied]
        if not pending:
            return None
        earliest = min(pending, key=lambda item: item[2])
        return {"ref": f"journey:{journey.journey_id}", "due_at": earliest[2], "kinds": [kind for _, kind, _ in pending],
                "commitment": any(kind in ("work_done", "returned_home") for _, kind, _ in pending),
                "itinerary_version": journey.itinerary_version}

    def catching_up(self, pet_id: str, now: datetime | None = None) -> bool:
        """只读：这只宠物有没有已经到期、还没登记的世界事件（后台还没结算到）。GET 用它显示“世界正在更新”，不写库。"""
        journey = self.repo.active_for_pet(pet_id)
        if journey is None:
            return False
        applied = self.repo.applied_events(journey.journey_id)
        return any(key not in applied for key, *_ in self._due_events(journey, now or utcnow()))

    def _record_in(self, conn, journey_id: str, key: str, kind: str, occurred_at: datetime, data: dict, now: datetime) -> bool:
        """在调用者事务里登记一个世界事件，并为每个下游写一行 outbox；已登记过返回 False、不重复写。"""
        if not self.repo.record_event(journey_id, key, kind, occurred_at, now, conn=conn):
            return False
        self.outbox.add_in(conn, event_id=f"{journey_id}:{key}", aggregate_id=journey_id, kind=kind, effective_at=occurred_at,
                           payload={"key": key, "data": data}, consumers=list(self.consumers), now=now)
        return True

    def deliver_outbox(self, now: datetime | None = None, *, lanes: tuple[str, ...] = (FAST,), aggregate_id: str | None = None,
                       limit: int = 50) -> int:
        """把到期的 outbox 行投递给对应下游；返回投递成功的行数。同一线程里已经在投递时不重入（剩下的交给外层或下一轮）。"""
        if getattr(self._applying, "delivering", False):
            return 0
        now = now or utcnow()
        names = [name for name, (_, lane) in self.consumers.items() if lane in lanes]
        self._applying.delivering = True
        delivered = 0
        try:
            for _ in range(MAX_ROUNDS):
                items = self.outbox.claim(names, now, limit=limit, aggregate_id=aggregate_id)
                if not items:
                    break
                progress = sum(self._deliver_one(item, now) for item in items)
                delivered += progress
                if progress == 0:
                    break
        finally:
            self._applying.delivering = False
        return delivered

    def _deliver_one(self, item: OutboxItem, now: datetime) -> int:
        sink = self.consumers[item.consumer][0]
        event = self._event_of(item)
        try:
            if event is not None:
                sink.on_world_event(event)
        except LeaseLost:
            # 租约没了＝这一轮的世界已经不归本进程推进了。下游内部走 unit_of_work，租约失效是在那里抛出来的，
            # **不是这个下游有毛病**：记成失败会白写一条失败、白耗一次重试次数，甚至把行投进退避。
            # 原样抛出去中止本轮（`ticker.tick` 有专门的 LeaseLost 分支），这一行保持未投递，新任期照原样再投。
            raise
        except Exception as exc:  # noqa: BLE001 - 这个下游自己退避重试，已成立的事实与其他下游不受影响
            logger.exception("world event consumer failed consumer=%s event=%s", item.consumer, item.event_id)
            self.outbox.failed(item, f"{type(exc).__name__}: {exc}", now)
            return 0
        return 1 if self.outbox.delivered(item, now) else 0

    def _event_of(self, item: OutboxItem) -> WorldEvent | None:
        """按 outbox 行重建世界事件：旅程与到访读当前记录，事件数据用登记时的快照（晚投递也是同一份事实）。"""
        journey = self.repo.get(item.aggregate_id)
        if journey is None:
            return None
        return WorldEvent(journey, item.payload.get("key", item.event_id.split(":", 1)[-1]), item.kind, item.effective_at,
                          self.pet_name_of(journey.pet_id), self.repo.visit_for_journey(journey.journey_id), item.payload.get("data") or {})
