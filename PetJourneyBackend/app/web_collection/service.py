"""回忆与收藏：旅行带回的纪念品（绑定宠物、不可交易）、稀有种子（可种植、可交换）、共同听看的回忆（私有）、邮局明信片。

明信片（用户 2026-09-22 的方向）：TA 进城或出远门时，在回程路上路过当地邮局，自己写一张、附上写实自拍寄给主人；
散步、喝一杯和打工是日常，不寄。自拍要主人开启“生成照片”才会有，没开启时就是 TA 手写的话。

物品按 (pet_id, source_event_id, kind) 只发放一次；个人照片、荣誉与关系记忆不进入交易。

0.4.0 家庭：物品属于宠物（全家成员看到同一份）；“一起听/看”的回忆属于陪着听的那位家人与 TA（个人层，别的家人看不到）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable

from ..schemas.web.common import DataOrigin
from ..schemas.web.social import CollectionItem, PhotoStatus
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.tasks import redraw_ticket
from ..web_platform.uow import execute_in, unit_of_work
from ..web_journey.photo_display import settled_photo

# 明信片图已经结束、但没有图的两种状态：failed＝确定没画成；unknown＝可能已受理、结果没确认
UNRESOLVED_IMAGE = (PhotoStatus.failed.value, PhotoStatus.unknown.value)
SOUVENIR_SEEDS = {"harbour_cafe": None, "macau_ferry": ("sea_salt_pea", "海盐豌豆种子"), "tokyo_flight": ("sakura_radish", "樱色萝卜种子")}


class WebCollectionService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        # 这趟旅程里每位家人陪 TA 一起听/看的毫秒数：{user_id: ms}
        self.shared_listening_of: Callable[[object], dict[str, int]] = lambda journey: {}
        # 明信片：TA 写的话（模型或模板）、写实自拍任务（返回任务号）、寄出后通知主人
        self.note_writer: Callable[[object, object], str] = lambda journey, visit: "路过邮局，给你寄了一张明信片。"
        self.selfie_request: Callable[[object, object, str], str | None] = lambda journey, visit, source_key: None
        self.on_postcard: Callable[[object, str], None] = lambda journey, title: None
        # 这只宠物有没有家（待领养居民还没有家：不寄明信片，也就不会为它调用模型或生图）
        self.has_family: Callable[[str], bool] = lambda pet_id: True
        # 同连接的终态口径（装配注入 `lambda conn, task_id: illustrations.outcome_of(task_id, conn)`）：
        # 分辨"确定没画成"与"可能已受理、结果没确认"。不能用另开连接的版本（读不到本事务、还会争锁）。
        self.image_outcome_in: Callable[..., str | None] | None = None

    def _grant(self, conn, *, user_id, pet_id, kind, item_key, title, tradable, bound, source_event_id, now) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO web_collection_items (item_id, user_id, pet_id, kind, item_key, title, tradable, bound_to_pet, source_event_id, obtained_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"it-{uuid.uuid4().hex[:12]}", user_id, pet_id, kind, item_key, title, 1 if tradable else 0, 1 if bound else 0, source_event_id, iso(now)),
        )

    def on_world_event(self, event) -> None:  # WorldEventSink
        if event.kind == "adventure":
            journey = event.journey
            with self.storage.connect() as conn:
                self._grant(conn, user_id=journey.user_id, pet_id=journey.pet_id, kind="badge", item_key=event.data["adventure_key"], title=event.data["badge"],
                            tradable=False, bound=True, source_event_id=event.source_event_id, now=event.occurred_at)
            return
        if event.kind == "visit_ended":
            self._post_office(event)
            return
        if event.kind != "returned_home":
            return
        journey = event.journey
        now = event.occurred_at
        listened = self.shared_listening_of(journey)
        with self.storage.connect() as conn:
            seed = SOUVENIR_SEEDS.get(journey.destination_key)
            if seed:
                self._grant(conn, user_id=journey.user_id, pet_id=journey.pet_id, kind="seed", item_key=seed[0], title=seed[1], tradable=True, bound=False,
                            source_event_id=event.source_event_id, now=now)
            for user_id, total_ms in sorted(listened.items()):
                if total_ms < 30_000:
                    continue
                minutes = max(1, round(total_ms / 60000))
                # 每位陪听的家人各一份；发起旅程的那位沿用事件号（与旧数据一致），其他家人加上自己的编号
                source = event.source_event_id if user_id == journey.user_id else f"{event.source_event_id}:{user_id}"
                self._grant(conn, user_id=user_id, pet_id=journey.pet_id, kind="shared_memory", item_key=None,
                            title=f"去{journey.title}的路上，你陪 TA 一起听/看了约 {minutes} 分钟", tradable=False, bound=True,
                            source_event_id=source, now=now)

    @staticmethod
    def sends_postcard(destination_key: str) -> bool:
        return not (destination_key.startswith("work:") or destination_key in ("local:stroll", "local:cafe"))

    def _post_office(self, event) -> None:
        journey, visit = event.journey, event.visit
        if not self.sends_postcard(journey.destination_key) or visit is None or not self.has_family(journey.pet_id):
            return
        with self.storage.connect() as conn:
            exists = conn.execute("SELECT 1 FROM web_collection_items WHERE pet_id = ? AND source_event_id = ? AND kind = 'postcard'",
                                  (journey.pet_id, event.source_event_id)).fetchone()
        if exists:
            return
        note = self.note_writer(journey, visit)
        task_id = self.selfie_request(journey, visit, f"postcard:{journey.journey_id}")
        title = f"来自{journey.city}的明信片"
        with unit_of_work(self.storage) as conn:
            self.postcard_in(conn, user_id=journey.user_id, pet_id=journey.pet_id, source_event_id=event.source_event_id, title=title, note=note,
                             place=visit.place["name"], city=journey.city, task_id=task_id, now=event.occurred_at)
        self.on_postcard(journey, title)

    def postcard_in(self, conn, *, user_id: str, pet_id: str, source_event_id: str, title: str, note: str, place: str | None, city: str | None,
                    task_id: str | None, now: datetime) -> bool:
        """在**调用方的写事务里**寄一张明信片（回程邮局明信片、到站明信片共用这一份）；按 (pet_id, source_event_id, kind) 只寄一次。

        task_id：写实自拍的生图任务，没有就是一张手写明信片（image_status 为空，页面显示纸质卡片）。
        任务可能先入队、这里后插行，中间 worker 已经跑完：同一个写事务里先读一次终态（见 photo_display）。
        """
        settled = settled_photo(conn, task_id, self.image_outcome_in) if task_id else None
        status, url = settled if settled is not None else ("processing" if task_id else None, None)
        return conn.execute(
            "INSERT OR IGNORE INTO web_collection_items (item_id, user_id, pet_id, kind, item_key, title, tradable, bound_to_pet, source_event_id, obtained_at, "
            "note, image_status, image_task_id, place, city, image_url) VALUES (?, ?, ?, 'postcard', NULL, ?, 0, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"it-{uuid.uuid4().hex[:12]}", user_id, pet_id, title, source_event_id, iso(now), note, status, task_id, place, city, url),
        ).rowcount == 1

    def image_ready(self, task_id: str, url: str, conn=None) -> None:
        execute_in(self.storage, conn, "UPDATE web_collection_items SET image_url = ?, image_status = 'ready' WHERE image_task_id = ?", (url, task_id))

    def image_failed(self, task_id: str, conn=None, outcome: str = "failed") -> None:
        """outcome：`failed`＝确定没画成；`unknown`＝可能已经受理、结果没确认（明信片上如实显示“还没确认”）。"""
        status = outcome if outcome in UNRESOLVED_IMAGE else PhotoStatus.failed.value
        execute_in(self.storage, conn, "UPDATE web_collection_items SET image_status = ? WHERE image_task_id = ? AND image_status = 'processing'", (status, task_id))

    def image_retry_started(self, task_id: str, conn=None) -> None:
        """重画真的排上队了（由插画服务在重排事务里回调）：明信片回到“处理中”，与重排一起提交或一起作废。"""
        marks = ",".join("?" for _ in UNRESOLVED_IMAGE)
        execute_in(self.storage, conn, f"UPDATE web_collection_items SET image_status = 'processing' WHERE image_task_id = ? AND image_status IN ({marks})",
                   (task_id, *UNRESOLVED_IMAGE))

    def image_retrying(self, user_id: str, pet_id: str, item_id: str) -> str | None:
        """主人点明信片上的“重画”：只认这位家人看得到的、这只宠物名下、已经结束又没出图的那一件；
        返回**重画凭据** `<任务号>#<当时看到的失败尝试次数>`，交给 `illustrations.retry`。

        可见性与 `items()` 一致（“一起听/看”的回忆只有本人看得到），另外挡掉已经用掉的藏品。
        **只做归属与状态判断、不写库**：展示状态由 `illustrations.retry` 在重排的同一个事务里改（见 `image_retry_started`）。
        这道查询挡的是顺序连点；**并发与迟到的重复请求由凭据里的失败版本 ＋ 重排事务里的条件更新挡**。
        历史尝试的账本记录原样保留，不在这里回写或删除。
        """
        marks = ",".join("?" for _ in UNRESOLVED_IMAGE)
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT i.image_task_id, t.attempts FROM web_collection_items i LEFT JOIN web_tasks t ON t.task_id = i.image_task_id "
                "WHERE i.item_id = ? AND i.pet_id = ? AND i.consumed_at IS NULL "
                f"AND (i.kind != 'shared_memory' OR i.user_id = ?) AND i.image_status IN ({marks})",
                (item_id, pet_id, user_id, *UNRESOLVED_IMAGE)).fetchone()
        return redraw_ticket(row, "image_task_id")

    def image_state_for(self, user_id: str, pet_id: str, item_id: str) -> str | None:
        """这位家人看得到的那件藏品，图现在是什么状态；看不到、不存在、或根本没有图时返回 None。

        给路由分辨用：`None` 才是"找不到可重画的对象"（404）；拿到 `processing` / `ready` 说明对象在、只是这一刻不能重画，
        应当回当前状态而不是 404。**可见性判断和 `image_retrying` 用的是同一套条件，权限不会因为走这条路被绕过。**
        """
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT image_status FROM web_collection_items WHERE item_id = ? AND pet_id = ? AND consumed_at IS NULL "
                "AND (kind != 'shared_memory' OR user_id = ?) AND image_task_id IS NOT NULL",
                (item_id, pet_id, user_id)).fetchone()
        return row["image_status"] if row is not None else None

    def items(self, user_id: str, pet_id: str) -> list[CollectionItem]:
        """这只宠物的收藏（全家同一份）＋这位家人自己和 TA 的“一起听/看”回忆（别的家人的看不到）。调用方已检查成员关系。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_collection_items WHERE pet_id = ? AND consumed_at IS NULL AND (kind != 'shared_memory' OR user_id = ?) "
                                "ORDER BY obtained_at DESC", (pet_id, user_id)).fetchall()
        return [CollectionItem(item_id=r["item_id"], kind=r["kind"], item_key=r["item_key"], title=r["title"], obtained_at=parse_dt(r["obtained_at"]), tradable=bool(r["tradable"]),
                               bound_to_pet=bool(r["bound_to_pet"]), source_event_id=r["source_event_id"], data_origin=DataOrigin.live,
                               note=r["note"], image_url=r["image_url"] if r["image_status"] == "ready" else None,
                               image_status=PhotoStatus(r["image_status"]) if r["image_status"] else None, place=r["place"], city=r["city"]) for r in rows]

    def consume_seed(self, pet_id: str, item_key: str, now: datetime | None = None) -> bool:
        """用掉这只宠物带回来的一颗种子（种进家里的菜园）。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT item_id FROM web_collection_items WHERE pet_id = ? AND kind = 'seed' AND item_key = ? AND consumed_at IS NULL "
                               "ORDER BY obtained_at LIMIT 1", (pet_id, item_key)).fetchone()
            if row is None:
                return False
            return conn.execute("UPDATE web_collection_items SET consumed_at = ? WHERE item_id = ? AND consumed_at IS NULL",
                                (iso(now or utcnow()), row["item_id"])).rowcount == 1

    # ---- 驾校：借车券与领证合影（在调用方事务里写入；同一来源只发一次）----
    @staticmethod
    def keepsake(conn, *, user_id: str, pet_id: str, kind: str, title: str, note: str, source_event_id: str, now: datetime) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO web_collection_items (item_id, user_id, pet_id, kind, item_key, title, tradable, bound_to_pet, source_event_id, obtained_at, note) "
            "VALUES (?, ?, ?, ?, NULL, ?, 0, 1, ?, ?, ?)",
            (f"it-{uuid.uuid4().hex[:12]}", user_id, pet_id, kind, title, source_event_id, iso(now), note),
        )

    def has(self, pet_id: str, kind: str) -> bool:
        with self.storage.connect() as conn:
            return conn.execute("SELECT 1 FROM web_collection_items WHERE pet_id = ? AND kind = ? AND consumed_at IS NULL", (pet_id, kind)).fetchone() is not None

    def consume(self, pet_id: str, kind: str, now: datetime | None = None) -> bool:
        """用掉一件（例如借车券）；没有就返回 False。自己开一个写事务——核销之外没有别的写入时用这个。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self.consume_in(conn, pet_id, kind, now)

    @staticmethod
    def consume_in(conn, pet_id: str, kind: str, now: datetime | None = None) -> bool:
        """同事务版本（CR-I-to-A2）：在**调用方已经开好的写事务**里核销一件，不自己 BEGIN、不自己提交。

        用在"券换来的东西"与"券本身"必须同生共死的地方（借车券 ↔ 这趟行程）：调用方须已 `BEGIN IMMEDIATE`
        （例如 `web_platform.uow.unit_of_work`），后面任何一步失败，核销跟着一起回滚，不会出现"券没了、车也没借到"。
        选中与核销用的是同一个条件（`consumed_at IS NULL`）并且要求 `rowcount == 1`：
        同一张券被两处同时用时，只有一方能拿到 True，另一方拿到 False 走原价路径。
        """
        row = conn.execute("SELECT item_id FROM web_collection_items WHERE pet_id = ? AND kind = ? AND consumed_at IS NULL ORDER BY obtained_at LIMIT 1",
                           (pet_id, kind)).fetchone()
        if row is None:
            return False
        return conn.execute("UPDATE web_collection_items SET consumed_at = ? WHERE item_id = ? AND consumed_at IS NULL",
                            (iso(now or utcnow()), row["item_id"])).rowcount == 1

    def attach_image(self, pet_id: str, kind: str, source_event_id: str, task_id: str) -> None:
        """把生图任务号贴到藏品上。**贴的这一刻图可能已经画完了**（任务先入队、这里后贴号）：
        同一个写事务里先读一次终态，读到了就直接写终态，否则才写"正在画"。
        读完另开事务再写就还留着那条缝——结果会被丢掉、藏品永远停在"正在画"（C 在领证合影上复现过）。"""
        with unit_of_work(self.storage) as conn:
            settled = settled_photo(conn, task_id, self.image_outcome_in)
            status, url = settled if settled is not None else ("processing", None)
            conn.execute("UPDATE web_collection_items SET image_status = ?, image_url = COALESCE(?, image_url), image_task_id = ? "
                         "WHERE pet_id = ? AND kind = ? AND source_event_id = ?", (status, url, task_id, pet_id, kind, source_event_id))

    def item_of(self, user_id: str, pet_id: str, kind: str) -> CollectionItem | None:
        return next((item for item in self.items(user_id, pet_id) if item.kind == kind), None)

    def refund_seed(self, pet_id: str, item_key: str) -> None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT item_id FROM web_collection_items WHERE pet_id = ? AND kind = 'seed' AND item_key = ? AND consumed_at IS NOT NULL "
                               "ORDER BY consumed_at DESC LIMIT 1", (pet_id, item_key)).fetchone()
            if row is not None:
                conn.execute("UPDATE web_collection_items SET consumed_at = NULL WHERE item_id = ?", (row["item_id"],))
