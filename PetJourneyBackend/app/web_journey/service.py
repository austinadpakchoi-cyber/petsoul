"""旅程服务：出发、宠物唯一位置、世界事件（幂等）、到访与店内活动、改选寻味推荐。

- 出发时从统一账本扣旅费；同一宠物同时只有一段进行中的旅程（数据库唯一索引）。
- 时间线按真实经过时间推进；任何读取都只“补齐已到期的事件”，不会加速。
- 0.4.0 真实体验：正式环境里没有演示线路（demo_catalog 只在演示环境打开）。远行走真实交通（web_transport：已核验船期 +
  高德接驳估时，从开船时间反推出门，出门前 TA 在家收拾、不算出发）；家附近的活动用真实地点，地图不可用时去星球内的地方，
  需要真实地点的活动则明确不成立。每段交通都记下时间从哪来（参考班次 / 路线估算 / 世界规则）。
- 世界事件（出发、到港、到店、离店、拍照、回家）按 (journey_id, event_key) 只生效一次，与工资、行程完成、outbox 同一个写事务
  （settlement.py）；通讯/动态/收藏/证件/朋友/攻略这些下游提交后按 outbox 各自投递，并以 source_event_id 去重。
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from ..schemas import EconomyTransactionType
from ..schemas.web.journey import VisitActivityKind
from ..schemas.web.pets import PetPresence
from ..schemas.web.transport import TransportMode
from ..storage import JourneyStorage
from ..transport_world.registry import WorldServiceRegistry
from ..transport_world.timeline import world_service_key
from ..utils import parse_dt, utcnow
from ..web_economy import InsufficientFunds, WebEconomy
from ..web_home.place import default_place
from ..web_platform.outbox import Outbox
from ..web_platform.runtime_epochs import bump_in, versions_in
from ..web_platform.uow import unit_of_work
from .adventures import ADVENTURES, MODE_ADVENTURE, render_story
from .catalog import Destination
from .errors import JourneyError
from .events import WorldEvent, WorldEventSink
from .geo_plan import GeoPlan
from .local import NEEDS_LICENSE, is_local, job_of
from .planner import plan_timeline
from .planning import REAL_TRIPS, JourneyPlanningMixin, Resolved
from ..web_transport.daytrip import PlanUnavailable, plan_macau_day_trip
from .repository import JourneyRecord, JourneyRepository, LegRecord, VisitRecord
from .settlement import FAST, JourneySettlementMixin


@dataclass(frozen=True)
class PlanChoice:
    """按哪一版预研计划出发。**两个一起给，或者都不给。**

    先前这是 `depart` 上两个各自可选的参数，于是「给了 `plan_id`、忘了 `expected_plan_revision`」
    是写得出来的——而那一漏，版本闸会**整个跳过**（`if expected_plan_revision is not None` 才比），
    **跳过时什么都不报**：出发照样成功，只是绑的可能已经是另一版计划了。
    并成一个值之后，**那个错写不出来**——比"写错了会被挡住"更彻底（B 提的改法，这是它那条原则的更强版本）。

    没有"只认编号、不管版本"的正当用法：调用方读到计划到真正出发之间，A 随时可能重查、改版，
    **而"我不会漏传"正是这类规则失效的典型前提**。

    两个字段都来自调用方**事务外**那一次读（用来"选"）；
    到底能不能用，由 `depart` 在写事务里拿同一个 `conn` 重新核一遍。
    """

    plan_id: str
    plan_revision: int


def stable_journey_id(user_id: str, pet_id: str, operation_key: str) -> str:
    """由“谁、替哪只宠物、哪一次请求”算出固定的行程编号：同一次请求重试多少次都是同一趟。"""
    digest = hashlib.sha256(f"{user_id}|{pet_id}|{operation_key}".encode("utf-8")).hexdigest()
    return f"jn-{digest[:12]}"


DEFAULT_ACTIVITIES = [
    ("choose_seat", "选个座位"),
    ("order_drink", "点一杯游戏饮品"),
    ("take_photo", "拍一张合影"),
    ("greet_resident", "和店里的居民打招呼"),
]
ACTIVITY_RESULTS = {
    "choose_seat": "{pet} 挑了靠窗的位置，尾巴搭在椅背上。",
    "order_drink": "{pet} 点了一杯“云朵奶泡”（动物世界的游戏饮品，不是这家店的真实菜单）。",
    "greet_resident": "店里的鹦鹉居民点了点头——它是星球居民，不是真实玩家。",
}
# 其他场景的活动（kind 沿用同一组枚举，只换说法）
TEMPLATE_ACTIVITIES = {
    "park": [("choose_seat", "找块地方躺一会儿"), ("take_photo", "拍一张照片"), ("greet_resident", "和路过的居民打招呼")],
    "generic": [("choose_seat", "找个地方歇歇脚"), ("take_photo", "拍一张照片"), ("greet_resident", "和当地居民打招呼")],
    "work": [("choose_seat", "换上工作围裙"), ("greet_resident", "和一起干活的居民打招呼"), ("take_photo", "干活时拍一张照片")],
}
TEMPLATE_RESULTS = {
    "park": {"choose_seat": "{pet} 找了块晒得到太阳的地方躺下，眯起了眼睛。", "greet_resident": "路过的星球居民跟 {pet} 点了点头——它是星球居民，不是真实玩家。"},
    "generic": {"choose_seat": "{pet} 找了个阴凉处歇脚，看来来往往的居民。", "greet_resident": "当地的星球居民给 {pet} 指了条好走的小路——它是星球居民，不是真实玩家。"},
    "work": {"choose_seat": "{pet} 换好了工作围裙，干劲十足。", "greet_resident": "一起干活的星球居民夸 {pet} 手脚麻利——它是星球居民，不是真实玩家。"},
}


class WebJourneyService(JourneyPlanningMixin, JourneySettlementMixin):
    def __init__(self, storage: JourneyStorage, economy: WebEconomy, registry: WorldServiceRegistry) -> None:
        self.storage = storage
        self.repo = JourneyRepository(storage)
        self.economy = economy
        self.registry = registry
        # 世界事件下游：名字 → (下游, 通道)；fast 结算后立即投递，slow（可能调模型）只由任务进程投递。装配时 add_consumer
        self.consumers: dict[str, tuple[WorldEventSink, str]] = {}
        self.outbox = Outbox(storage)
        self.pet_name_of: Callable[[str], str] = lambda pet_id: "TA"
        self.wishes_of: Callable[[str, str], list[str]] = lambda user_id, pet_id: []
        # 纸质卡片：也用调用方写事务的那个连接写（CR-C11）。captured_at＝按下那一刻，日期按 TA 当时所在地换算。
        self.postcard_maker: Callable[..., str] | None = None
        # 预研计划（TRV-02，合同 4.2）：两个都必须用调用方写事务的那个连接。
        # `ready_plan_in` 纯读；`link_journey_in` 条件更新（版本不符或状态非 ready 就抛，整笔回滚）。
        # 没装配时**不静默放行**：调用方传了 plan_id 却没有绑定端口 → 在动业务数据之前拒绝，
        # 否则会建出一趟没有计划归属的行程（和 CR-C9／CR-C12 同一类残留）。
        self.ready_plan_in: Callable[..., tuple | None] | None = None
        self.link_journey_in: Callable[..., None] | None = None
        self.stale_facts_in: Callable[..., tuple[str, ...]] | None = None
        # 承诺闸（TRV-02，合同 15 节）：`active_commitment_in(conn, pet_id, now) -> Commitment | None`。
        # 数据源是 `communicator.owner_asked_stay_home` 的同事务版（归 A）。
        # **只在调用方显式要闸时才问**——`depart` 三个调用方里有"主人自己点出发"那一条，无差别的闸会把主人也拦掉。
        self.active_commitment_in: Callable[..., object | None] | None = None
        # 写实照片（主人开启“生成照片”且供应商可用时）：返回生图任务号；不可用时退回纸质卡片
        # 拍照登记：**必须用调用方写事务的那个连接**，和 visit 更新、photo_taken 事件同生共死（COORD-C-ATOMIC 方案 B）。
        # captured_at＝主人按下"拍一张"的那一刻（不是到店时刻，也不是任务执行时刻）；
        # source_key 与 photo_taken 的事件键同源，去重靠它。远端调用仍由任务进程在事务之外发，事务里只有本地登记与写入。
        # 没装配就是 None：走拍照的那条路会在动业务数据之前被拒，不退回"先排队再写库"的两段写。
        self.photo_request_in: Callable[..., str | None] | None = None
        # "这次拍照会不会真的去生成照片"——只读判断、无副作用（装配接到"供应商可用且这家开了生成照片"）。
        # 为真却没装配 `photo_request_in` ＝ 本该原子登记却做不到，那就明确拒绝；为假走纸质卡片，那条路不排队，也就没有残留问题。
        self.photo_generation_on: Callable[[VisitRecord, JourneyRecord], bool] = lambda visit, journey: False
        # 旧的事务外登记（自己开连接排队）。提交路径已经不用它——它会在版本冲突／租约被接手时留下没有事件的孤儿任务。
        # 保留这个属性只是让现有装配的赋值有个落点；`photo_request_in` 接上之后可以由装配方删掉。
        self.photo_request: Callable[[VisitRecord, JourneyRecord], str | None] = lambda visit, journey: None
        self.recommendation_place: Callable[[str, str, JourneyRecord], dict] | None = None
        self.keepsake_of: Callable[[str, str], str | None] = lambda user_id, pet_id: None
        self.geo = None  # web_providers.GeoService：可用时出发用真实地点与路线估时
        self._applying = threading.local()
        self._scan_cursor: str | None = None  # 世界线分页扫描的游标（公平轮转；进程内即可）
        # TA 的家（web_home.place.HomePlace）：日常出门的出发地；默认香港·中环
        self.home_place_of: Callable[[str], object] = lambda home_id: default_place()
        # 是否有驾驶证（驾考模块）：没有就不能自己开车，但仍可以步行、坐车、坐火车和飞机
        self.can_drive: Callable[[str], bool] = lambda pet_id: False
        # 驾校借车券：waiver_available 只查看（规划页也用它标“这趟免费”）
        self.waiver_available: Callable[[str, str], bool] = lambda pet_id, key: False
        # 核销一张券。**必须用调用方给的这个连接**，和写行程、递增代数、扣旅费同生共死（CR-C9）。
        # 没装配就是 None：depart 会在动任何业务数据之前拒掉用券那条路，不会留下没付钱的行程，也不会闷声按原价扣钱。
        self.fee_waiver_in: Callable[[sqlite3.Connection, str, str], bool] | None = None
        # 旧的独立写法（自己开连接、自己提交）。提交路径已经不用它了——在写事务里调它会和自己争锁。
        # 保留这个属性只是让现有装配的赋值有个落点；`fee_waiver_in` 接上之后可以由装配方删掉。
        self.fee_waiver: Callable[[str, str], bool] = lambda pet_id, key: False
        # 演示环境才有的演示线路（海边咖啡馆/坐船去澳门/飞去东京的演示版）；正式环境关闭（装配时按配置注入）
        self.demo_catalog = False
        # TA 在某个时刻是不是醒着（按 DNA 作息与家的时区；装配时注入）；没注入时不限制
        self.awake_at: Callable[[str, datetime], bool] | None = None
        # 出门前改签/取消后通知（装配时注入：发到家庭频道）
        self.on_replanned: Callable[[JourneyRecord, object | None, str, datetime], None] = lambda journey, trip, text, now: None
        # 这位用户能不能看这只宠物的旅程（家庭成员关系，装配时注入）；没注入时退回“旅程是不是这位用户发起的”
        self.can_view_pet: Callable[[str, str], bool] | None = None

    # ---- 出发站 ----
    def depart(self, user_id: str, pet_id: str, home_id: str, destination_key: str, now: datetime | None = None,
               operation_key: str | None = None, expected_versions=None, valid_until: datetime | None = None,
               plan: PlanChoice | None = None, honor_commitments: bool = False) -> JourneyRecord:
        """operation_key：这次“出发”请求的稳定标识（HTTP 层的 Idempotency-Key）。

        给了它，行程编号就由它算出来，而不是每次现生成——同一次请求无论重试几次、什么时候重试，
        指向的都是同一趟行程，旅费的幂等键也跟着稳定。**不能只靠“同时只有一段行程”这道领域约束**：
        原来那趟结束之后它就不拦了，那时若回执还没写成，重试会变成第二趟、第二次扣费（验收 CR-Q5 / 合同 C3a、C3c）。

        expected_versions / valid_until：需要时间的决定（自主决策、排队的提案）在**提交的那个写事务里**再核一遍——
        语义版本没变、机会还没过期、TA 还没在路上，三样都用事务里的同一个连接读（验收 CR-C1）。
        解析地点、算路线这些外部调用都在事务之外完成，事务里只有读校验与写入。

        这趟的钱也在**同一个写事务**里结清（CR-C9）：核销一张券或者扣旅费，和行程、代数一起成功或一起回滚。
        分两段写的话，进程死在中间就会留下一趟没付钱的行程，或者券已经核销而行程没建。

        plan（`PlanChoice`，编号＋版本一起）：这趟来自一份预研计划（TRV-02）。计划绑定与行程、旅费**同一个事务**；
        版本对不上就整笔不做。**不传就完全不走这条路**——今天的旅程本来就没有计划，老路径一个字不受影响。
        并成一个值是有意的：分开两个可选参数时，漏传版本号会让版本闸整个跳过**而且不报**（见 `PlanChoice`）。

        honor_commitments：要不要问"主人有没有说过今天待在家"。**默认不问**：这个方法同时服务
        `routers/web/journey.py`（主人自己点出发）、`brain_life`（自主）与 `life`（规则生活）三条路；
        主人自己说了待在家又自己点出发，那是改主意，拦他没道理。自主那两条由调用方显式传 True（合同 15 节）。
        """
        now = now or utcnow()
        journey_id = f"jn-{uuid.uuid4().hex[:12]}"
        if operation_key:
            journey_id = stable_journey_id(user_id, pet_id, operation_key)
            done = self.repo.get(journey_id)
            if done is not None and done.pet_id == pet_id and done.user_id == user_id:
                return done  # 同一次操作的重试：还是原来那一趟，不再重新出发、不再扣费
        home = self.home_place_of(home_id)
        if destination_key in NEEDS_LICENSE and not self.can_drive(pet_id):
            raise JourneyError("no_license", "还没有驾照，不能自己开车；可以打车、坐公共交通或者走路。")
        self.advance_pet(pet_id, now)
        if self.repo.active_for_pet(pet_id):
            raise JourneyError("already_traveling", "TA 已经在路上了。")
        if is_local(destination_key) and self.awake_at is not None and not self.awake_at(pet_id, now):
            # 附近的活动是马上出门的：TA 在睡觉就不叫醒（家人可以先留建议，TA 醒了自己决定）；远行会把出门时间排在 TA 醒着的时候
            raise JourneyError("pet_asleep", "TA 正在睡觉，醒了再出门吧；可以先留个建议，TA 醒来会看到。")
        resolved = self.resolve(home, pet_id, destination_key, now)
        dest = resolved.destination
        trip = resolved.trip
        balance = self.economy.wallet(pet_id).balance
        waivable = dest.fee > 0 and self.waiver_available(pet_id, destination_key)
        if waivable and self.fee_waiver_in is None:
            # 券的核销必须和行程、扣费在同一个事务里。同事务版本还没接上之前，这条路宁可不走：
            # 退回两段写会留下"券用了、行程没建"或"行程建了、钱没扣"；按原价扣钱又是替家人做了主（CR-C9）
            raise JourneyError("waiver_unavailable", "借车券这会儿用不了，稍后再试。", destination_key=destination_key)
        if balance < dest.fee and not waivable:
            raise JourneyError("insufficient_funds", "旅费还不够，先去菜园收获一些吧。", balance=balance, fee=dest.fee)
        if plan is not None and self.link_journey_in is None:
            # 计划绑定必须和行程同事务。端口没接上就宁可不出发——否则会留下一趟没有计划归属的行程（同 CR-C9 的形态）
            raise JourneyError("plan_link_unavailable", "这份计划这会儿用不了，稍后再试。", plan_id=plan.plan_id)
        if honor_commitments and self.active_commitment_in is None:
            # 调用方**明确要闸**却没有闸可用：拒绝，不能当作"没有承诺"放行。静默跳过保护比拒绝危险得多
            raise JourneyError("commitment_gate_unavailable", "这会儿查不到家里的约定，稍后再试。")
        journey, legs, visit = self._materialize(journey_id, user_id, pet_id, home_id, resolved.final, now, resolved.geo_plan,
                                                 template=resolved.template, real_place=resolved.real_place, trip=trip, basis=resolved.basis)
        try:
            with unit_of_work(self.storage) as conn:  # 后台线的进程租约围栏也在这里生效（CR-A4）
                self._assert_still_valid(conn, pet_id, expected_versions, valid_until, honor_commitments=honor_commitments, now=now)
                # 先结钱、再写行程：**用没用券要等核销那一下的返回值才知道**（事务外算出来的 `waivable`
                # 只是"看起来能用"，券可能已经被别处用掉），而这个事实要跟着行程一起落库（m1701）。
                # 两件事仍在同一个事务里，先后不改变"一起成功或一起回滚"。
                journey.fare_waived = self._settle_fare(conn, journey_id, pet_id, destination_key, dest, waivable, now)
                self.repo.insert(conn, journey, legs, visit, now)
                bump_in(conn, pet_id, "activity_epoch", now)  # 定了新行程：旧的提案与表达要按新版本复核
                if plan is not None:
                    self._link_plan(conn, plan, pet_id, journey_id, destination_key, now)
        except InsufficientFunds as exc:  # 整笔已经回滚：行程没写进去，券没核销，钱也没扣，不需要事后 cancel
            raise JourneyError("insufficient_funds", "旅费还不够，先去菜园收获一些吧。", balance=exc.balance, fee=dest.fee) from exc
        except sqlite3.IntegrityError as exc:
            raced = self.repo.get(journey_id) if operation_key else None  # 同一次操作被两个进程同时接手：谁先写谁算数
            if raced is not None and raced.pet_id == pet_id and raced.user_id == user_id:
                return raced
            raise JourneyError("already_traveling", "TA 已经在路上了。") from exc
        self._apply_due(journey, now)
        return journey

    def _link_plan(self, conn, chosen: PlanChoice, pet_id: str, journey_id: str,
                   destination_key: str, now: datetime) -> None:
        """把这趟行程绑到那份预研计划上，**就在写行程的同一个事务里**（合同 4.2）。

        版本在事务内读、在事务内写：先 `ready_plan_in(conn, pet_id)` 读出此刻的 plan/wish 版本，
        对不上调用方报的就整笔不做；对得上再 `link_journey_in(conn, …)` 条件更新。
        **不在事务外先读一遍**——那样读到的是事务开始前的旧快照，等于没核（这批 0.1 节那条硬约束）。

        `chosen` 是调用方事务外那次读的结果（编号＋版本一起，`PlanChoice` 保证不会只给一半）。
        """
        plan_id = chosen.plan_id
        plan = self.ready_plan_in(conn, pet_id) if self.ready_plan_in is not None else None
        # 按**字段名**取，不按位置解：A 的 `PlanRef` 比合同 4.2 的元组多一个 `pet_id`、有效期也拆成了两个字段，
        # 按位置第 6 位拿到的会是 `destination_key`。字段名是稳定的，位置不是。
        if plan is None or plan.plan_id != plan_id:
            raise JourneyError("plan_not_ready", "这份计划现在不能用了，重新看一遍再决定。", plan_id=plan_id)
        if plan.plan_revision != chosen.plan_revision:
            raise JourneyError("plan_revision_changed", "这段时间里这份计划又改过，重新看一遍再出发。",
                               plan_id=plan_id, current_revision=plan.plan_revision)
        if plan.destination_key != destination_key:
            # 这份计划是去**别处**的。不核的话，一份「去浅水湾」的计划会被绑到一趟去咖啡馆的旅程上，
            # 旅程结束时那个心愿落定为 completed——**手账上出现一次根本没去过的旅行**，
            # 而且没有任何东西会报错：两个编号都是真的、版本也都对得上。
            raise JourneyError("plan_destination_mismatch", "这份计划不是去这儿的，换一份再出发。",
                               plan_id=plan_id, plan_destination_key=plan.destination_key)
        self._assert_facts_fresh(plan, now)
        self._assert_preconditions_fresh(conn, plan, now)
        self.link_journey_in(conn, plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, journey_id, now)

    def _assert_preconditions_fresh(self, conn, plan, now: datetime) -> None:
        """逐条前置事实的有效期：**用出发事务里的这个连接**问 A 的端口（合同 0.1、4.2）。

        `plan.valid_window` 是**这版计划**的边界；真正会过期的是它依据的那些事实
        （几点关门、今天有没有活动、票还有没有），各有各的有效期，住在 A 的 `web_travel_facts` 里。
        **旅程包不读别人的表**，只拿 fact_id 去问。

        没有前置事实就不问——端口缺席也照常出发：否则「缺端口就拒绝」会把没有事实要核的计划一起拦掉，
        那是把一道保护扩大成一道故障。
        有前置事实却没有端口时**拒绝**，不当作"都还新鲜"放行：静默跳过保护之后，
        没有任何东西会提示这次根本没核过（同 `waiver_unavailable` / `plan_link_unavailable`）。
        """
        if not plan.preconditions:
            return
        if self.stale_facts_in is None:
            raise JourneyError("fact_check_unavailable", "这会儿核不了攻略里的资料，稍后再试。", plan_id=plan.plan_id)
        stale = self.stale_facts_in(conn, plan.preconditions, now)
        if stale:
            raise JourneyError("fact_stale", "这份攻略里有资料过期了，重新查一遍再出发。",
                               plan_id=plan.plan_id, fact_ids=",".join(stale))

    @staticmethod
    def _assert_facts_fresh(plan, now: datetime) -> None:
        """资料有效期：等钱那段时间里资料可能已经过期，**出发这一刻**按 `now` 再判一次（TRV-02 工作单第 63 行）。

        读 `PlanRef.valid_window`＝`(valid_from, valid_until)`，两个都是 **ISO 字符串、都可能是 None**
        （没核验到带时效的关键事实时，这版计划就没有有效期边界——A 不会编一个出来）。
        判定只用 `ready_plan_in` 在**同一个写事务里**读出来的值，不另查库。
        原因码用合同 5.2 全集里的 `fact_stale`，不新增码。

        **逐条事实的有效期不在这里查**：`plan.preconditions` 是 A 那边 `web_travel_facts` 的 fact_id，
        旅程包不去读别人的表；要逐条看得由 A 给一个 `*_in(conn, …)` 的端口（已去信）。
        """
        valid_from, valid_until = plan.valid_window
        if valid_until is not None and now >= parse_dt(valid_until):
            raise JourneyError("fact_stale", "这份攻略的资料过期了，重新查一遍再出发。", plan_id=plan.plan_id, valid_until=valid_until)
        if valid_from is not None and now < parse_dt(valid_from):
            raise JourneyError("fact_stale", "这份攻略还没到能用的时候。", plan_id=plan.plan_id, valid_from=valid_from)

    def _settle_fare(self, conn, journey_id: str, pet_id: str, destination_key: str, dest: Destination, waivable: bool, now: datetime) -> bool:
        """这趟的钱在**写行程的同一个写事务里**结清：核销一张券，或者扣旅费。回传**这趟是不是用券抵掉的**。

        分两个事务写的话，进程在两步之间死掉就会留下一趟没付钱的行程，或者券已经核销而行程没建——
        幂等键能防“扣两次”，防不了“根本没扣”。这里抛任何异常，行程、代数、券、扣费一起回滚。
        `waivable` 为真时 `fee_waiver_in` 一定已经装配：没装配的用券路径在动业务数据之前就被 depart 拒掉了。
        券在这中间被别处用掉了 → 返回 False → 照既定费用规则付钱；付不起就整笔回滚。
        幂等键绑定行程编号：同一次操作重试指向同一趟、同一笔，不会扣两次。
        不花钱的出门（散步、打工）不在银行卡流水里记一笔 0。

        回传的这个布尔要落进 `web_journeys.fare_waived`：账本里**没有那一笔**既可能是用了券，
        也可能是散步本来就不花钱，两者在流水上分不开（m1701）。
        """
        if waivable and self.fee_waiver_in(conn, pet_id, destination_key):
            return True  # 驾校借车券：第一次自驾不用租车费（用一次）
        if dest.fee > 0:
            self.economy.apply_in(conn, pet_id, -dest.fee, EconomyTransactionType.web_travel_fee, f"web:travel_fee:{journey_id}",
                                  reason=f"「{dest.title}」的旅费", source="web.journey.depart", now=now)
        return False

    def _assert_still_valid(self, conn, pet_id: str, expected_versions, valid_until: datetime | None,
                            *, honor_commitments: bool = False, now: datetime | None = None) -> None:
        """在写事务内、写业务之前的最后一道复核。用的是事务里的这个连接，不另开（另开会读到旧快照，还会和自己争锁）。

        `honor_commitments` 为真时多问一句"主人有没有说过今天待在家"。**默认不问**：
        主人自己点出发也走这条路，无差别的闸会把他自己拦掉（合同 15 节）。
        """
        if honor_commitments:
            blocking = self.active_commitment_in(conn, pet_id, now or utcnow())
            if blocking is not None:
                raise JourneyError("commitment_active", "家里说好今天待在家，这次就不出门了。", commitment=str(blocking))
        if expected_versions is not None:
            stale = expected_versions.stale_fields(versions_in(conn, pet_id))
            if stale:
                raise JourneyError("versions_changed", "这段时间里情况变了，这次先不出门。", fields=",".join(stale))
        if valid_until is not None and utcnow() >= valid_until:
            raise JourneyError("offer_expired", "这个打算已经过了时效，重新看一遍再决定。")
        if self.repo.active_for_pet(pet_id, conn) is not None:
            raise JourneyError("already_traveling", "TA 已经在路上了。")

    def _materialize(self, journey_id, user_id, pet_id, home_id, dest: Destination, now, geo_plan: GeoPlan | None = None,
                     template: str = "cafe", real_place=None, trip=None, basis: str = "demo_fixture"):
        """trip：真实交通的一日行（从开船反推的出门时间、每段的来源）；basis：地点与路程依据（real / world_rule / demo_fixture）。"""
        departed_at = trip.leave_home_at if trip is not None else now
        routes = trip.routes if trip is not None else (geo_plan.routes if geo_plan else None)
        timeline = plan_timeline(dest, departed_at, routes)
        resolved = Resolved(destination=dest, local=None, trip=trip, geo_plan=geo_plan, basis=basis, template=template)
        legs: list[LegRecord] = []
        index_in_direction: dict[str, int] = {}
        for planned in timeline.legs:
            plan = planned.plan
            index = index_in_direction.get(planned.direction, 0)
            index_in_direction[planned.direction] = index + 1
            reference = self._leg_reference(resolved, planned.direction, index, plan.mode, now)
            service_id = None
            if plan.carrier and plan.code_prefix and reference.get("kind") == "verified_timetable":
                # 同一班船上的所有宠物共用同一个动物世界编号；编号追溯到参考班次
                sailing = trip.outbound if planned.direction == "outbound" else trip.inbound
                self._record_reference_trip(trip.timetable, sailing, now)
                key = world_service_key("ref", sailing.reference_id, sailing.service_date, plan.origin["node_id"], plan.destination["node_id"], 0)
                service_id = self.registry.get_or_create(key, plan.carrier, plan.code_prefix, TransportMode(plan.mode),
                                                         reference_id=sailing.reference_id).world_service_id
            elif plan.carrier and plan.code_prefix:
                key = world_service_key("demo", f"{dest.key}:{planned.direction}", now.date(), plan.origin["node_id"], plan.destination["node_id"], planned.sequence)
                service_id = self.registry.get_or_create(key, plan.carrier, plan.code_prefix, TransportMode(plan.mode)).world_service_id
            kind = reference.get("kind")
            # time_basis 只有四个大类（兼容旧客户端）：星球内的路程记为“估算”，精确来源在 reference.kind（→ time_source）
            time_basis = {"verified_timetable": "verified_timetable", "routed_estimate": "routed_estimate", "operator_rule": "verified_timetable",
                          "world_rule": "routed_estimate"}.get(kind, "demo_fixture")
            legs.append(
                LegRecord(
                    leg_id=f"lg-{uuid.uuid4().hex[:10]}",
                    journey_id=journey_id,
                    sequence=planned.sequence,
                    direction=planned.direction,
                    kind=plan.kind,
                    mode=plan.mode,
                    role=plan.role,
                    world_service_id=service_id,
                    origin=plan.origin,
                    destination=plan.destination,
                    starts_at=planned.starts_at,
                    ends_at=planned.ends_at,
                    time_basis=time_basis,
                    freshness="verified" if kind in ("verified_timetable", "operator_rule", "routed_estimate") else "unavailable",
                    position_basis="schematic" if plan.schematic or plan.kind == "wait" else "simulated_route",
                    route=planned.route,
                    reference=reference,
                )
            )
        place = self.visit_place(dest, (geo_plan.real_place if geo_plan else None) or real_place, basis, now)
        visit = VisitRecord(
            visit_id=f"vs-{uuid.uuid4().hex[:10]}",
            journey_id=journey_id,
            pet_id=pet_id,
            user_id=user_id,
            place=place,
            template="generic" if template == "work" else template,
            starts_at=timeline.visit_starts_at,
            ends_at=timeline.visit_ends_at,
            recommendation_id=None,
            activities=[{"activity_id": f"va-{kind}", "kind": kind, "label": label, "state": "available", "result_text": None}
                        for kind, label in TEMPLATE_ACTIVITIES.get(template, DEFAULT_ACTIVITIES)],
            version=1,
        )
        journey = JourneyRecord(journey_id, user_id, pet_id, home_id, dest.key, dest.title, dest.city, "active", 1, dest.fee, departed_at, timeline.completes_at, None)
        return journey, legs, visit

    # ---- 出门前复核：按最新路况重新规划（改坐下一班 / 来不及就取消并退回旅费） ----
    def refresh_scheduled(self, now: datetime | None = None, window: timedelta = timedelta(minutes=45), stale_after: timedelta = timedelta(hours=2)) -> int:
        """定时任务：还没出门、45 分钟内要出门的真实远行，如果去码头的路线估算已经超过 2 小时，就按最新路况复核一次（每个行程版本一次）。"""
        now = now or utcnow()
        changed = 0
        for journey in self.repo.active_journeys(200):
            if journey.destination_key not in REAL_TRIPS or not (now < journey.departed_at <= now + window):
                continue
            key = f"refresh:{journey.itinerary_version}"
            if key in self.repo.applied_events(journey.journey_id):
                continue
            first = next(iter(self.repo.legs(journey.journey_id)), None)
            fetched = (first.reference or {}).get("fetched_at") if first else None
            if fetched and parse_dt(fetched) > now - stale_after:
                continue
            self.repo.record_event(journey.journey_id, key, "refresh", now, now)
            if self.replan(journey.journey_id, now, road_max_age=timedelta(minutes=30)) != "unchanged":
                changed += 1
        return changed

    def replan(self, journey_id: str, now: datetime | None = None, road_max_age: timedelta | None = None) -> str:
        """还没出门的真实远行按最新资料重新规划：unchanged / replanned（改了出门时间或船班，行程版本 +1）/ cancelled（来不及了，退回旅费）。"""
        now = now or utcnow()
        journey = self.repo.get(journey_id)
        if journey is None or journey.lifecycle != "active" or now >= journey.departed_at or journey.destination_key not in REAL_TRIPS:
            return "unchanged"
        home = self.home_place_of(journey.home_id)
        try:
            awake = (lambda t, _pet=journey.pet_id: self.awake_at(_pet, t)) if self.awake_at is not None else None
            trip = plan_macau_day_trip(home, self.geo, now, fee=journey.fee, road_max_age=road_max_age, awake=awake)
        except PlanUnavailable as exc:
            self.repo.cancel(journey_id)
            if journey.fee > 0:
                self.economy.apply(journey.pet_id, journey.fee, EconomyTransactionType.web_reward, f"web:travel_refund:{journey_id}",
                                   reason=f"「{journey.title}」来不及成行，旅费退回", source="web.journey.replan", now=now)
            self.on_replanned(journey, None, f"今天去不成{journey.title}了（{exc.message}），旅费已经退回银行卡。", now)
            return "cancelled"
        old_legs = self.repo.legs(journey_id)
        old_sailings = [(l.reference or {}).get("reference_id") for l in old_legs if l.kind == "main" and l.mode == "ferry"]
        new_sailings = [trip.outbound.reference_id, trip.inbound.reference_id]
        if trip.leave_home_at == journey.departed_at and old_sailings == new_sailings:
            return "unchanged"
        resolved = Resolved(destination=trip.destination, local=None, trip=trip, geo_plan=None, basis="real", template="cafe")
        _, legs, visit = self._materialize(journey_id, journey.user_id, journey.pet_id, journey.home_id, resolved.final, now, None,
                                           template="cafe", real_place=trip.venue_place, trip=trip, basis="real")
        self.repo.replace_plan(journey_id, legs, visit, trip.leave_home_at, legs[-1].ends_at, trip.destination.title)
        updated = self.repo.get(journey_id)
        self.on_replanned(updated, trip, f"出门前看了下路况，改成 {trip.outbound.departure_local} 的船去澳门（{trip.leave_home_at.astimezone(ZoneInfo('Asia/Hong_Kong')):%H:%M} 出门），"
                                         f"回程坐 {trip.inbound.departure_local} 的船。", now)
        return "replanned"

    # ---- 位置与事件 ----
    def advance_pet(self, pet_id: str, now: datetime | None = None) -> JourneyRecord | None:
        now = now or utcnow()
        journey = self.repo.active_for_pet(pet_id)
        if journey is None:
            return None
        self._apply_due(journey, now)
        return self.repo.get(journey.journey_id)

    def advance_all(self, now: datetime | None = None, limit: int = 200) -> int:
        """补齐进行中旅程已到期的世界事件（不依赖主人打开页面）。

        一轮最多处理 limit 段，并记下停在哪里：下一轮从游标之后接着扫，走完一圈回到开头。
        这样旅程多于一页时，后排的也轮得到，不会永远只处理最早的那一批。
        """
        now = now or utcnow()
        journeys = self.repo.active_journeys(limit, after=self._scan_cursor)
        if not journeys and self._scan_cursor:
            self._scan_cursor = None  # 走完一圈，从头再来
            journeys = self.repo.active_journeys(limit)
        for journey in journeys:
            self._apply_due(journey, now)
        self._scan_cursor = journeys[-1].journey_id if len(journeys) == limit else None
        return len(journeys)

    def due_lag_seconds(self, now: datetime | None = None, limit: int = 200) -> int:
        """只读运维指标：最老一件“已经到期但还没登记”的事实等了多少秒。持续变大说明世界线卡住了。"""
        now = now or utcnow()
        worst = 0
        for journey in self.repo.active_journeys(limit):
            due = self.due_summary(journey.pet_id, now)
            if due is not None:
                worst = max(worst, int((now - due["due_at"]).total_seconds()))
        return worst

    def peek(self, pet_id: str, now: datetime | None = None) -> tuple[PetPresence, JourneyRecord | None, VisitRecord | None]:
        """只读（访客页用）：按已经写入的行程推算此刻位置，不推进世界、不写任何事件、不触发任何外部调用。"""
        now = now or utcnow()
        journey = self.repo.active_for_pet(pet_id)
        if journey is None or now >= journey.completes_at or now < journey.departed_at:
            return PetPresence.at_home, None, None
        visit = self.repo.visit_for_journey(journey.journey_id)
        if visit and visit.starts_at <= now < visit.ends_at:
            return PetPresence.visiting, journey, visit
        if visit and now >= visit.ends_at:
            return PetPresence.returning, journey, visit
        return PetPresence.in_transit, journey, visit

    def presence(self, pet_id: str, activated: bool, now: datetime | None = None) -> PetPresence:
        """只读：按已写入的行程与此刻时间推算位置，不补齐事件、不写库（GET 纯读；结算由任务进程或命令完成）。
        出门前在家收拾（从开船时间反推的出门时间还没到）、已过回家时间但后台还没结算，都算在家。"""
        if not activated:
            return PetPresence.not_activated
        return self.peek(pet_id, now)[0]

    def _due_events(self, journey: JourneyRecord, now: datetime) -> list[tuple[str, str, datetime, dict]]:
        events: list[tuple[str, str, datetime, dict]] = [("departed", "departed", journey.departed_at, {})]
        legs = self.repo.legs(journey.journey_id)
        last_of = {direction: max((l.sequence for l in legs if l.direction == direction), default=None) for direction in ("outbound", "return")}
        for leg in legs:
            if leg.kind == "main" and leg.ends_at <= now:
                # 到达店门口 / 回到家的那一段由 visit_started / returned_home 表达，不再重复“到站”。
                terminal = leg.sequence == last_of.get(leg.direction)
                events.append((f"leg_arrived:{leg.sequence}", "leg_arrived", leg.ends_at,
                               {"leg_id": leg.leg_id, "mode": leg.mode, "place": leg.destination["name"], "terminal": terminal}))
                adventure = MODE_ADVENTURE.get(leg.mode)
                if adventure and leg.direction == "outbound":
                    events.append((f"adventure:{adventure}", "adventure", leg.ends_at, self._adventure_data(journey, adventure)))
        visit = self.repo.visit_for_journey(journey.journey_id)
        if visit and visit.starts_at <= now:
            events.append(("visit_started", "visit_started", visit.starts_at, {}))
        if visit and visit.ends_at <= now:
            events.append(("visit_ended", "visit_ended", visit.ends_at, {}))
            job = job_of(journey.destination_key)
            if job is not None:
                events.append(("work_done", "work_done", visit.ends_at, {"pay": job.pay, "label": job.label, "hours": job.hours}))
        if journey.completes_at <= now:
            events.append(("returned_home", "returned_home", journey.completes_at, {}))
        return [e for e in events if e[2] <= now]

    def _adventure_data(self, journey: JourneyRecord, key: str) -> dict:
        template = ADVENTURES[key]
        story = render_story(template, self.pet_name_of(journey.pet_id), self.keepsake_of(journey.user_id, journey.pet_id))
        return {"adventure_key": key, "title": template.title, "badge": template.badge, "story": story}

    # ---- 到访 ----
    def visit_for_user(self, user_id: str, visit_id: str, now: datetime | None = None, *, settle: bool = True) -> tuple[VisitRecord, JourneyRecord]:
        """settle=False 给 GET 用：只读，不补齐到期事件；店内动作等命令先结算再判断。"""
        visit = self.repo.visit(visit_id)
        allowed = visit is not None and (self.can_view_pet(user_id, visit.pet_id) if self.can_view_pet else visit.user_id == user_id)
        if not allowed:
            raise JourneyError("not_found", "没有找到这次到访。")
        journey = self.repo.get(visit.journey_id)
        assert journey is not None
        if settle and journey.lifecycle == "active":
            self._apply_due(journey, now or utcnow())
        return visit, journey

    def visit_state(self, visit: VisitRecord, journey: JourneyRecord, now: datetime) -> str:
        if journey.lifecycle == "cancelled":
            return "cancelled"
        if now < visit.starts_at:
            return "travelling"
        if now < visit.ends_at:
            return "active"
        return "completed"

    def act(self, user_id: str, visit_id: str, activity_id: str, now: datetime | None = None) -> VisitRecord:
        now = now or utcnow()
        visit, journey = self.visit_for_user(user_id, visit_id, now)
        if self.visit_state(visit, journey, now) != "active":
            raise JourneyError("not_in_venue", "TA 现在不在店里。")
        target = next((a for a in visit.activities if a["activity_id"] == activity_id), None)
        if target is None:
            raise JourneyError("not_found", "没有这个活动。")
        if target["state"] == "done":
            return visit
        pet_name = self.pet_name_of(visit.pet_id)
        pending: list[WorldEvent] = []
        photo_key, task_id = f"photo:{visit.visit_id}", None
        taking_photo = target["kind"] == VisitActivityKind.take_photo.value
        generating = taking_photo and self.photo_generation_on(visit, journey)
        if generating and self.photo_request_in is None:
            # 这次本该真的去生成照片，却没有同事务登记可用：宁可不走。退回"先排队、再写库"会在版本冲突或租约被接手时
            # 留下一张没有 photo_taken 事件的孤儿任务——镜头没响，队列里却多了一张要画的照片。
            raise JourneyError("photo_not_wired", "拍照暂时不可用，稍后再试。")
        if not taking_photo:
            scene = "work" if job_of(journey.destination_key) else visit.template
            results = TEMPLATE_RESULTS.get(scene, ACTIVITY_RESULTS)
            target.update(state="done", result_text=results.get(target["kind"], ACTIVITY_RESULTS.get(target["kind"], "{pet} 玩得很开心。")).format(pet=pet_name))
            if target["kind"] == VisitActivityKind.greet_resident.value and visit.template == "cafe":
                target["result_text"] += f" 还顺手当了一回小侦探——{ADVENTURES['cafe_detective'].badge}已放进回忆柜。"
                pending.append(WorldEvent(journey, "adventure:cafe_detective", "adventure", now, pet_name, visit, self._adventure_data(journey, "cafe_detective")))
        # 活动结果与它引出的世界事件、outbox 同一个事务提交；提交后再投递给通讯/收藏等下游（各自按事件号去重）
        with unit_of_work(self.storage) as conn:
            if generating:
                # 排队／插画登记就在这个连接、这个事务里：版本冲突或租约被接手时，它跟着一起回滚（COORD-C-ATOMIC 方案 B）
                task_id = self.photo_request_in(conn, visit, journey, captured_at=now, source_key=photo_key)
                if task_id:
                    target.update(state="done", result_text=f"{pet_name} 对着镜头拍了一张照片，正在冲洗，好了就发到通讯。")
                    pending.append(WorldEvent(journey, photo_key, "photo_taken", now, pet_name, visit, {"photo_task_id": task_id}))
            if pending or not taking_photo:
                self._commit_activity(conn, visit, journey, pending, now)
        if taking_photo and task_id is None:
            # 没开启"生成照片"或供应商不可用：走纸质卡片。卡片记录同样写在这一个事务里（CR-C11），
            # 日期按 TA 当时所在地换算——拍摄时刻由这里传进去，不让渲染时刻冒充。
            if self.postcard_maker is None:
                raise JourneyError("unavailable", "拍照暂时不可用。")
            with unit_of_work(self.storage) as conn:
                photo_url = self.postcard_maker(conn, visit, journey, pet_name, captured_at=now)
                target.update(state="done", result_text="还没开启“生成照片”，先写了一张纸质卡片（没有照片），已送到通讯。", photo_url=photo_url)
                pending.append(WorldEvent(journey, photo_key, "photo_taken", now, pet_name, visit, {"photo_url": photo_url}))
                self._commit_activity(conn, visit, journey, pending, now)
        if pending:
            self.deliver_outbox(now, lanes=(FAST,), aggregate_id=journey.journey_id)
        return self.repo.visit(visit_id)  # type: ignore[return-value]

    def _commit_activity(self, conn, visit: VisitRecord, journey: JourneyRecord, pending: list[WorldEvent], now: datetime) -> None:
        """活动结果 ＋ 它引出的世界事件，在调用方的写事务里一起落库。版本对不上就整笔回滚。"""
        if not self.repo.update_visit(visit, visit.version, conn=conn):
            raise JourneyError("version_conflict", "店里的状态刚更新过，请刷新。")
        for event in pending:
            self._record_in(conn, journey.journey_id, event.key, event.kind, event.occurred_at, event.data, now)

    def choose_recommendation(self, user_id: str, visit_id: str, recommendation_id: str, expected_version: int, now: datetime | None = None) -> JourneyRecord:
        now = now or utcnow()
        visit, journey = self.visit_for_user(user_id, visit_id, now)
        if journey.itinerary_version != expected_version:
            raise JourneyError("version_conflict", "行程已更新，请刷新后再选。", current=journey.itinerary_version)
        if now >= visit.starts_at:
            raise JourneyError("too_late", "TA 已经到店了，这次不能再换。")
        if self.recommendation_place is None:
            raise JourneyError("unavailable", "寻味暂时不可用。")
        place = self.recommendation_place(user_id, recommendation_id, journey)
        visit.place = place
        visit.recommendation_id = recommendation_id
        if not self.repo.rechoose_venue(visit, expected_version):
            raise JourneyError("version_conflict", "行程已更新，请刷新后再选。")
        return self.repo.get(journey.journey_id)  # type: ignore[return-value]
