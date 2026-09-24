"""统一世界状态（/api/v1/web/world/state，CR-6C2B-MAP W1）。

**纯读**：按服务器时间投影**已提交的事实**，不推进世界、不补齐到期事件、不调任何供应商。
底层用的是 `WebJourneyService.peek()`——它的 docstring 明写「不推进世界、不写任何事件、
不触发任何外部调用」，所以这条路由的纯读性是**继承**来的，不是我在这里声明的。

路线几何取**出发时已缓存**的那份（`geo_plan` 在出发时取回并落库），读时不再调地图。

三条硬规则的落点：
  · **计划 ≠ 正在做**：`phase` 由时间线推，去打工的路上是 `going`，`visit` 开始了才是 `there`；
  · **从没出过门也要有 `home.center`**：家在入住时就落进片区了，不依赖任何旅程记录；
  · **家的位置只给家里人**：本接口 `scope=household` 只返回请求者所在家庭的宠物，
    所以这里每只都是成员；**非成员的可见性属于 W2（显示范围），不在本单**。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, LatLng
from ...schemas.web.home import PetPresence
from ...schemas.web.world import (
    WorldActivity, WorldActivityKind, WorldHome, WorldJob, WorldLeg, WorldPetState,
    WorldPhase, WorldPlace, WorldPose, WorldPosition, WorldPositionBasis, WorldRelation, WorldState,
)
from ...utils import utcnow
from ...web_home.place import FUZZ_METERS
from ...web_journey.local import job_of
from ...web_journey.snapshot import current_leg
from ...web_platform import WebPrincipal, require_principal
from ._shared import cap, require_pet, web_of, web_router

router = web_router("world")

CACHE_SECONDS = 15

# destination_key → 活动种类。`local:` 前缀是家附近的短行程。
_LOCAL_KINDS = {"stroll": WorldActivityKind.stroll}


def capabilities(settings) -> list[Capability]:
    return [cap("world.state", "world", CapabilityStatus.available,
                "家里每只宠物此刻在哪、在做什么、还要多久；纯读，按服务器时间投影已提交的事实")]


def _kind_of(destination_key: str | None) -> WorldActivityKind:
    if not destination_key:
        return WorldActivityKind.home
    if job_of(destination_key) is not None:
        return WorldActivityKind.job
    if destination_key.startswith("local:"):
        return _LOCAL_KINDS.get(destination_key.split(":", 1)[1], WorldActivityKind.stroll)
    return WorldActivityKind.cafe if "cafe" in destination_key else WorldActivityKind.trip


def _phase_of(presence: PetPresence, journey, visit, now: datetime) -> WorldPhase:
    """**只从时间线推，推不出就是 unknown，绝不猜成 home**——猜成 home 会让「在外面」被显示成「在家」。"""
    if presence is PetPresence.at_home or journey is None:
        return WorldPhase.home
    if presence is PetPresence.visiting:
        return WorldPhase.there
    if presence is PetPresence.returning:
        return WorldPhase.returning
    if presence is PetPresence.in_transit:
        # 去程还是回程：visit 尚未开始就是去程；没有 visit 记录时读不出来，如实 unknown。
        if visit is None:
            return WorldPhase.unknown
        return WorldPhase.going if now < visit.starts_at else WorldPhase.returning
    return WorldPhase.unknown


def _home_of(web, home_id: str, label: str) -> WorldHome:
    """家的模糊中心。坐标在入库时已按片区中心偏移过（约 900 米），这里**不再二次模糊**，
    也不把 `precision_m` 写小——写小等于谎报精度。"""
    place = web.home_places.get(home_id)
    return WorldHome(center=LatLng(lat=place.lat, lng=place.lng),
                     precision_m=int(FUZZ_METERS), label=place.display or label)


def _place_of(visit) -> WorldPlace | None:
    if visit is None or not visit.place:
        return None
    p = visit.place
    if p.get("lat") is None or p.get("lng") is None:
        return None
    return WorldPlace(name=p.get("name") or "", lat=float(p["lat"]), lng=float(p["lng"]),
                      attribution=p.get("attribution"))


def _leg_of(web, journey, phase: WorldPhase, now: datetime) -> WorldLeg | None:
    """只在 going / returning 给。`route` 用出发时缓存的几何，**没有就 []**，读时不调地图。

    给的是 **TA 此刻实际在的那一段**，用 `web_journey.snapshot.current_leg`——**与行程详情页同一份判断**。

    2026-09-24 改（6c2b 报，C 导出函数）：原先取的是 `kind == "main"` 的第一段，
    **多段行程里那永远是主段**——打车 → 飞机 → 火车时，TA 还在打车去机场，
    这里却报飞机那段，地图会把位置点画在航线上、`mode` 显示成飞机。

    **不自己抄那三行**：换乘间隙取哪一段是**有产品含义的判断**，两处一旦漂开，
    地图和行程详情页会各说一套，**而这种不一致不会报错**。

    **也不再按 `direction` 过滤**（C 提醒）：去程回程本来就藏在时间里，
    两个筛选叠着用会把当前段筛掉。`current_leg` 的回退依赖 legs 按 `sequence` 有序——
    `JourneyRepository.legs()` 是 `ORDER BY sequence`，**这一条我自己核过**。
    """
    if journey is None or phase not in (WorldPhase.going, WorldPhase.returning):
        return None
    leg = current_leg(web.journeys.repo.legs(journey.journey_id), now)
    if leg is None:
        return None
    raw = leg.route if isinstance(getattr(leg, "route", None), list) else []
    route = [LatLng(lat=float(p["lat"]), lng=float(p["lng"]))
             for p in raw if isinstance(p, dict) and p.get("lat") is not None and p.get("lng") is not None]
    return WorldLeg(mode=leg.mode, route=route, departs_at=leg.starts_at, arrives_at=leg.ends_at)


def _position_of(home: WorldHome | None, place: WorldPlace | None, leg: WorldLeg | None,
                 phase: WorldPhase) -> WorldPosition | None:
    """**每个坐标都要说明来路**；说不清就返回 None，不给一个没有出处的点。"""
    if phase in (WorldPhase.there,) and place is not None:
        return WorldPosition(lat=place.lat, lng=place.lng, basis=WorldPositionBasis.place, precision_m=50)
    if leg is not None and leg.route:
        head = leg.route[0]
        return WorldPosition(lat=head.lat, lng=head.lng, basis=WorldPositionBasis.route, precision_m=200)
    if phase is WorldPhase.home and home is not None:
        return WorldPosition(lat=home.center.lat, lng=home.center.lng,
                             basis=WorldPositionBasis.home_area, precision_m=home.precision_m)
    return None


def _pose_of(web, pet_id: str, phase: WorldPhase, kind: WorldActivityKind,
             leg: WorldLeg | None, now: datetime) -> WorldPose:
    """地图上画成什么样。**每一支都由事实推出，推不出就 idle／unknown，不猜。**

    `sleeping` 只来自作息判定（`journeys.awake_at`，就是 `/journey/depart` 抛 `pet_asleep`
    用的那个回调）。**它没接上时给 `idle` 而不是 `sleeping`——「不知道」不等于「睡着了」**，
    把未知画成睡觉会让每只作息未接入的宠物在地图上一直睡。

    `eating`／`sunbathing` 本批一次都不会产出：现在没有事实来源，**枚举里留着位置不等于可以猜**。
    """
    if phase is WorldPhase.home:
        awake_at = getattr(web.journeys, "awake_at", None)
        if awake_at is None:
            return WorldPose.idle
        return WorldPose.idle if awake_at(pet_id, now) else WorldPose.sleeping
    if phase in (WorldPhase.going, WorldPhase.returning):
        if leg is None:
            return WorldPose.unknown  # 在路上但读不出这一段的交通方式：不默认成走路
        return WorldPose.walking if leg.mode == "walk" else WorldPose.riding
    if phase is WorldPhase.there:
        if kind is WorldActivityKind.job:
            return WorldPose.working
        if kind is WorldActivityKind.cafe:
            return WorldPose.cafe
        return WorldPose.exploring
    return WorldPose.unknown


def _relation_of(web, pet_id: str, user_id: str) -> WorldRelation:
    """谁的宠物：`web_homes` 那行的 `user_id` 就是它的主人（`homes.by_pet` 按宠物反查）。

    查不到归属时算 `household` 而不是 `mine`——**两者只差在 UI 强调，错判成 mine 会把别人的宠物
    说成"你的"**，所以不确定时取弱的那个。
    """
    row = web.homes.by_pet(pet_id)
    return WorldRelation.mine if row is not None and row.user_id == user_id else WorldRelation.household


def _state_of(web, pet_id: str, relation: WorldRelation, home_id: str | None, label: str, now: datetime) -> WorldPetState:
    presence, journey, visit = web.journeys.peek(pet_id, now)
    phase = _phase_of(presence, journey, visit, now)
    kind = _kind_of(journey.destination_key if journey else None)
    home = _home_of(web, home_id, label) if home_id else None
    place = _place_of(visit)
    leg = _leg_of(web, journey, phase, now)
    job_def = job_of(journey.destination_key) if journey else None
    job = WorldJob(title=job_def.label, pay=job_def.pay,
                   paid=phase is WorldPhase.returning or presence is PetPresence.at_home) if job_def else None
    profile = web.pets.profile(pet_id)
    # **`since`/`until` 是「这一阶段」的起止，不是整趟的。** 在路上时给的是这一段的出发与
    # 预计到达——给整趟结束会让「还要多久」答非所问：主面板要说的是「再走 6 分钟就到」，
    # 不是「这趟一共 32 分钟」。
    since, until = (None, None)
    if journey is not None:
        if phase is WorldPhase.there and visit is not None:
            since, until = visit.starts_at, visit.ends_at
        elif leg is not None:
            since, until = leg.departs_at, leg.arrives_at
        else:
            since, until = journey.departed_at, journey.completes_at
    activity = WorldActivity(
        kind=kind, phase=phase, pose=_pose_of(web, pet_id, phase, kind, leg, now),
        title=(place.name if place and phase is WorldPhase.there else ("在家" if phase is WorldPhase.home else "在路上")),
        doing=None,  # moment 文字接入前一律 None——**没有就是没有，不编**
        place=place, since=since, until=until, job=job,
        journey_id=journey.journey_id if journey else None,
        visit_id=visit.visit_id if visit else None)
    return WorldPetState(
        pet_id=pet_id, name=profile.name if profile else "TA",
        species=profile.species if profile else "",
        # 服务端裁好的头部小图（256×256），A 2026-09-24 交付、我核过 docstring 的三条前提：
        # **纯读绝不触发生成**、**没有就返回 None 且不回退到任何别的图**、尺寸 256×256。
        #
        # 先前这里给过 `profile.photo_url`（整张照片），**那是错的**（6c2b 指出）：前端拿到非空的
        # `avatar_url` 就会当头像渲染，而整图的比例与构图都不对——**给一张不合适的图，
        # 比明说「没有」更糟**。所以宁可 None，让前端画爪印占位。
        #
        # **已知的 N+1**：这个方法每次自己开一个连接。本接口按家庭聚合，一个家的宠物数通常是个位数，
        # 所以没有先做批量版本；**哪天这里成为热点，A 那边可以加批量版，不是改这里的结构**。
        avatar_url=web.character.id_photo.avatar_url_of(pet_id),
        relation=relation, home=home, activity=activity, leg=leg,
        position=_position_of(home, place, leg, phase))


@router.get("/world/state", response_model=WorldState)
def world_state(request: Request, pet_id: str | None = None,
                principal: WebPrincipal = Depends(require_principal)) -> WorldState:
    """家里每只宠物此刻的状态。默认且当前仅支持 `scope=household`。"""
    web = web_of(request)
    now = utcnow()
    # **W1 返回的是「这个家」的全部宠物，`pet_id` 只用来定位是哪个家。**
    # 所以一家养两只时不该要求指明——两只属于同一个家，没有歧义可消（6c2b 报的 P0：
    # 第二只入住后 /map 整页 409 pet_required，玩家被困在报错页）。
    # 只有**跨多个家**时才真的需要指明，那时照 `require_pet` 原样抛 409。
    # 不绕过 require_pet 的任何校验：这里只是替它选出一只用来定位，成员关系仍由它查。
    if pet_id is None:
        reachable = web.households.accessible_pets(principal.user_id)
        if len({household_id for _, household_id in reachable}) == 1:
            pet_id = reachable[0][0]
    home = require_pet(request, principal, pet_id)
    pets = web.households.pets_of(home.household_id) if home.household_id else [home.pet_id]
    states = [_state_of(web, p, _relation_of(web, p, principal.user_id), home.home_id, "家", now)
              for p in pets]
    return WorldState(server_time=now, cache_seconds=CACHE_SECONDS, pets=states)
