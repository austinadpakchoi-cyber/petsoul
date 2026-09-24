"""网页“宠物自主世界”的装配（组合根的一部分，由 web_composition 调用；可以 import 任何模块）。

从 web_composition 拆出来，避免组合根文件过大：TA 的家在哪、DNA、此刻状态与扮演人设、
按状态回复与主动消息、自己决定出门、菜园守护通知、写实照片与邮局明信片、世界定时器。

0.4.0 家庭与待领养居民：
- 扮演人设分两种：对某位家人（带这位家人的称呼、确认过的私信叮嘱与个人层 DNA）与对全家/无人（只用共用 DNA，不带任何个人内容）；
- 世界事件、明信片、攻略、菜园守护与遇到朋友发到家庭频道；早安晚安这类主动私聊按每位家人自己的偏好各发各的；
- 自己决定出门的是“住进家的宠物”（每只一次）与“还在驿站生活的待领养居民”；居民不会触发模型或生图。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from zoneinfo import ZoneInfo
from typing import Callable

from .schemas.web.home import HabitatKind, HomePlaceSummary
from .schemas.web.pets import PetOrigin
from .schemas.web.reception import CareNoteSlot, MemoryPurpose
from .storage import JourneyStorage
from .utils import utcnow
from .web_agent import MomentBuilder
from .web_agent.moment import is_sleep_time
from .web_agent.decision.commitments import commitment_gate
from .web_agent.decision.service_reader import STAY_HOME_HOURS
from .web_agent.life import LifeEngine, decide_window
from .web_agent.profile import BehaviorProfile, derive_profile, profile_sources
from .web_agent.proactive import OwnerPrefs, ProactiveMessenger
from .web_agent.ticker import WorldTicker
from .web_platform.lease import WorkerLease
from .web_communicator.persona import PetPersona, build_proactive, clean_reply
from .web_communicator.service import FAMILY
from .web_home.place import HomePlaceStore
from .web_residents import SYSTEM_USER
from .web_runtime.heartbeat_policy import HeartbeatPolicy
from .web_agent.life import expire_suggestions
from .web_agent.photo_wiring import bind_photo_request, bind_visit_revision
from .web_agent.runtime_view import HeartbeatShadow, RuntimeProjector
from .web_journey.guides import TravelGuideService
from .web_journey.settlement import FAST, SLOW
from .web_social.friends import FriendService
from .web_pets.dna import DNARecord, PetDNAStore, draft as draft_dna

WATCH_TEXT = {
    "caught_awake": "刚才{thief}想来摘咱家的{crop}，被我发现赶跑啦！",
    "caught_resting": "刚才我在打盹，迷迷糊糊听到动静，睁眼一看是{thief}想摘{crop}，被我赶跑啦。",
    "stolen_while_resting": "刚才我睡着了，好像有谁摘走了一颗{crop}……下次我警醒点。",
}


@dataclass
class AgentWorld:
    home_places: HomePlaceStore
    dna: PetDNAStore
    moments: MomentBuilder
    persona_of: Callable[[str, str], PetPersona | None]
    guides: TravelGuideService
    friends: FriendService
    proactive: ProactiveMessenger
    life: LifeEngine
    ticker: WorldTicker  # 世界线：结算、投递确定性下游、出门前复核、规则生活
    cognition: WorldTicker  # 认知线：可能调模型的事（攻略与相遇的表达、到点回复、主动消息）；各自一份租约
    projector: RuntimeProjector  # 每宠运行投影（只读）
    shadow: HeartbeatShadow | None  # 心跳 shadow：只评估并记录，不执行
    profile_of: Callable[[str], BehaviorProfile]
    activated_pets: Callable[[], list[tuple[str, str]]]
    living_pets: Callable[[], list[tuple[str, str]]]


def wire_agent_world(*, storage: JourneyStorage, settings, providers, identity, pets, homes, farm, economy, journeys, reception,
                     communicator, collection, illustrations, social, presence_of, households, residents) -> AgentWorld:
    home_places = HomePlaceStore(storage)

    def home_tz_of(pet_id: str) -> str:
        home = homes.by_pet(pet_id)
        if home is not None:
            return home_places.get(home.home_id).timezone
        return residents.timezone_of(pet_id) or "Asia/Hong_Kong"

    dna_store = PetDNAStore(storage)
    profile_cache: dict[str, tuple[float, BehaviorProfile]] = {}

    def members_of(pet_id: str) -> list[str]:
        household_id = households.household_of_pet(pet_id)
        return households.member_ids(household_id) if household_id else []

    def is_member(user_id: str | None, pet_id: str) -> bool:
        return bool(user_id) and user_id not in (FAMILY, SYSTEM_USER) and households.access_pet(user_id, pet_id) is not None

    def behavior_sources(pet_id: str) -> list[tuple[str, str]]:
        """行为画像读哪些原话（逐栏保留出处）：家人确认过的共用 DNA；还没确认时用领养资料/简介与梦想；
        再加上每位家人允许用于“家中互动”“出行偏好”的接待叮嘱。只用于私信的叮嘱与小暗号不参与行为（沿用用途限制）。"""
        record = pets.profile(pet_id)
        if record is None:
            return []
        saved = dna_store.saved(pet_id)
        if saved is not None:
            sources, known = profile_sources(dna=saved.dna), set(saved.dna.habits)
        else:
            personality, dream = pets.traits(record)
            sources, known = profile_sources(personality=personality) + ([("dream", dream)] if dream else []), set()
        used: set[str] = set()
        for user_id in members_of(pet_id):
            for purpose in (MemoryPurpose.home_interaction, MemoryPurpose.travel_preference):
                for item in reception.projection(user_id, pet_id, purpose).items:
                    if item.text and item.note_id not in used and item.text[:40] not in known:
                        used.add(item.note_id)
                        sources.append(("note", item.text))
        return sources

    def profile_of_pet(pet_id: str) -> BehaviorProfile:
        """统一的 DNA 行为画像（作息、出门、路线与工作倾向、话多话少、学得快慢）：同一只宠物 60 秒内复用，
        保存 DNA 后立即按新的来。作息判断、自主生活、主动消息与 DNA 页面展示都读这一份。"""
        cached = profile_cache.get(pet_id)
        now_ts = monotonic()
        if cached and now_ts - cached[0] < 60:
            return cached[1]
        profile = derive_profile(behavior_sources(pet_id))
        profile_cache[pet_id] = (now_ts, profile)
        return profile

    moments = MomentBuilder(journeys, presence_of, home_tz_of, sleep_window_of=lambda pet_id: (profile_of_pet(pet_id).sleep_start, profile_of_pet(pet_id).wake))
    journeys.home_place_of = home_places.get

    def awake_at(pet_id: str, at) -> bool:
        """TA 在 at 时刻（按家的时区）是不是醒着：DNA 作息（夜猫子、早起、爱睡）决定。"""
        profile = profile_of_pet(pet_id)
        return not is_sleep_time(at.astimezone(ZoneInfo(home_tz_of(pet_id))), (profile.sleep_start, profile.wake))

    journeys.awake_at = awake_at

    def dna_draft(user_id: str | None, pet_id: str) -> DNARecord | None:
        """还没保存过 DNA 时的草稿。给某位家人看时带上这位家人确认过的私信叮嘱；给全家/居民时只用领养资料与简介。"""
        record = pets.profile(pet_id)
        if record is None:
            return None
        personal = is_member(user_id, pet_id)
        if user_id not in (None, FAMILY, SYSTEM_USER) and not personal:
            return None
        personality, dream = pets.traits(record)
        items = reception.projection(user_id, pet_id, MemoryPurpose.private_chat).items if personal else []
        return draft_dna(personality=personality if record.origin is not PetOrigin.own_pet else None, dream=dream,
                         bio=record.bio if record.origin is PetOrigin.own_pet else None,
                         notes=[(i.slot.value if i.slot else None, i.slot_value, i.text) for i in items])

    def recent_of(pet_id: str, now) -> list[str]:
        journey = journeys.repo.latest_for_pet(pet_id)
        if journey is None:
            return []
        if journey.lifecycle == "active":
            return [f"这次出门去{journey.title}（{journey.city}）"]
        if journey.completed_at and now - journey.completed_at < timedelta(days=3):
            days = (now - journey.completed_at).days
            return [f"{'今天' if days == 0 else f'{days} 天前'}刚从{journey.title}回来"]
        return []

    def persona_of(user_id: str | None, pet_id: str) -> PetPersona | None:
        """扮演人设。user_id 是这只宠物的一位家人：带上这位家人的称呼、确认过的私信叮嘱与个人层 DNA（小暗号）；
        user_id 为空、'*'（家庭频道）或居民身份：只用全家共用的 DNA，不带任何人的个人内容。不是家人 → None。"""
        record = pets.profile(pet_id)
        if record is None:
            return None
        personal = is_member(user_id, pet_id)
        if user_id not in (None, FAMILY, SYSTEM_USER) and not personal:
            return None
        personality, dream = pets.traits(record)
        items = reception.projection(user_id, pet_id, MemoryPurpose.private_chat).items if personal else []
        title = next((i.slot_value for i in items if i.slot is CareNoteSlot.owner_title and i.slot_value), None)
        now = utcnow()
        moment = moments.build(pet_id, now)
        if personal:
            dna = dna_store.record(user_id, pet_id)
        else:
            dna = dna_store.saved(pet_id) or dna_draft(None, pet_id)
        in_dna = set(dna.dna.habits) if dna else set()
        return PetPersona(name=record.name, species=record.species.value, origin=record.origin.value, personality=personality, dream=dream,
                          owner_title=title, notes=[i.text for i in items if i.text[:40] not in in_dna], status=moment.doing, place=moment.place,
                          dna=dna.dna if dna else None, local_clock=moment.local_time.strftime("%H:%M"), recent=recent_of(pet_id, now))

    def place_summary(home_id: str) -> HomePlaceSummary:
        place = home_places.get(home_id)
        return HomePlaceSummary(habitat=HabitatKind(place.habitat), habitat_label=place.habitat_label, city=place.city, area_label=place.area_label,
                                display=place.display, timezone=place.timezone, chosen=place.chosen)

    homes.place_of = place_summary
    dna_store.draft_of = dna_draft
    original_save = dna_store.save

    def save_and_refresh(user_id: str, pet_id: str, dna, now, expected_version: int | None = None):
        try:
            return original_save(user_id, pet_id, dna, now, expected_version)
        finally:
            profile_cache.pop(pet_id, None)  # 主人改了 DNA：作息与倾向立刻按新的来

    dna_store.save = save_and_refresh
    for name in ("confirm", "correct"):  # 接待时确认、更正或撤回叮嘱后，行为画像也立刻按新的来
        def refreshed(*args, _original=getattr(reception, name), **kwargs):
            try:
                return _original(*args, **kwargs)
            finally:
                profile_cache.clear()

        setattr(reception, name, refreshed)
    communicator.moment_of = moments.build
    communicator.on_owner_activity = identity.touch_active
    communicator.persona_of = persona_of

    # ---- 攻略手账 ----
    guides = TravelGuideService(storage)
    guides.chat = providers.chat
    guides.geo = providers.geo
    guides.model_enabled = lambda user_id: user_id != SYSTEM_USER and identity.prefs(user_id)["model_replies"]
    guides.persona_of = persona_of
    guides.image_request = illustrations.request_journal
    guides.journey_of = journeys.repo.get
    guides.visit_of = journeys.repo.visit_for_journey
    guides.on_created = lambda journey, title: communicator.post_family_note(
        journey.pet_id, f"我给这次出门写了一份攻略：「{title}」，在攻略手账里能看到，你们也可以照着走。", dedupe_key=f"guide:{journey.journey_id}", now=utcnow())
    journeys.add_consumer("guides", guides, lane=SLOW)  # 写攻略会调模型：只由任务进程投递

    # ---- 写实照片与邮局明信片 ----
    def on_image_ready(task_id: str, url: str, conn=None) -> None:
        # conn：插画任务的领取围栏事务——图好了、消息/收藏/攻略里的图与“任务完成”一起提交，旧领取的结果一起作废
        communicator.illustration_ready(task_id, url, conn=conn)
        collection.image_ready(task_id, url, conn=conn)
        guides.image_ready(task_id, url, conn=conn)

    def on_image_failed(task_id: str, conn=None, outcome: str = "failed") -> None:
        # outcome="unknown"：供应商那边可能已经受理了，三处展示都要如实写“结果未确认”，
        # 不能和“确认没画成”长一个样——前者还能重画对账，后者是终态（CR-A3 / Q-C10）。
        communicator.illustration_failed(task_id, conn=conn, outcome=outcome)
        collection.image_failed(task_id, conn=conn, outcome=outcome)
        guides.image_failed(task_id, conn=conn, outcome=outcome)

    def on_image_retrying(task_id: str, conn=None) -> None:
        # conn：重画的那个事务（任务重排 ＋ 插画记录 ＋ 展示状态一起提交）。主人点了“重画”，
        # 页面必须当场进入“处理中”，不能还写着“没画成”（CR-Q15 / Q-C11）。
        communicator.illustration_retry_started(task_id, conn=conn)
        collection.image_retry_started(task_id, conn=conn)
        guides.image_retry_started(task_id, conn=conn)

    # 【已摘除】`illustrations.consent_in` —— 写事务里的最后一次**生成授权**复核。
    # 用户 2026-09-23 决定取消逐次询问（角色与生活/旅行两类都取消），这道许可不再存在，
    # 所以复核它的读口也一并摘掉。摘除顺序：**先**去掉上方 `photo_generation_on` 里的
    # `opted_in` 调用，**再**摘这两处接线——反过来会让 `opted_in` 落回服务里的默认
    # `lambda …: False`，到店照片**全部静默停掉**（不报错、不崩，就是什么都不生成）。
    #
    # **随之取消的只有「这家开没开生成照片」这一个判断。** 同一段注释里原先记着的另外两件事
    # 仍然成立、也仍在别处生效，不要因为这段被删而以为它们没了：
    #   · 「必须走调用方那个 conn」——撤权/成员变更的同事务可见性，仍由 `can_view_pet`
    #     与 `visit_revision_of` 各自在自己的写事务里保证；
    #   · 「成员被移出家庭立刻失效」本来就属于 membership_epoch 那条线，**从来不是这个开关**。
    # 展示层分辨"确认没画成"与"结果未确认"：**必须用调用方那个 conn**。
    # 另开连接读到的是事务外的旧值——晚到的 unknown 会被当成 failed 写进页面，
    # 主人看到"没画成"，而实际上那次调用可能已经被受理、也已经计费。
    # **三个消费端同一个口径、同一个 conn**：分辨"确定没画成"与"可能已受理、结果没确认"。
    # 另开连接读到的是事务外的旧值——晚到的 unknown 会被当成 failed 写进页面，
    # 主人看到"没画成"，而那次调用其实可能已被受理、也已计费。
    outcome_in = lambda conn, task_id: illustrations.outcome_of(task_id, conn=conn)  # noqa: E731
    communicator.illustration_outcome_in = outcome_in
    collection.image_outcome_in = outcome_in
    guides.image_outcome_in = outcome_in
    # 到访照片的事实代数：**执行那一刻重新读**。回读 payload 里那个值两边永远相等，是伪装的围栏，比没有更坏。
    # 只接这个**分支口**；总入口 `event_revision_of` 由组合根按来路分派（命令型事件没有后续修订），
    # 两边都赋值同一个属性会互相覆盖，后写的那个把另一条路整条打成 hold。
    illustrations.visit_revision_of = bind_visit_revision(journeys)
    illustrations.portrait_saver = pets.set_portrait
    illustrations.on_ready = on_image_ready
    illustrations.on_failed = on_image_failed
    illustrations.on_unknown = lambda task_id, conn=None: on_image_failed(task_id, conn, outcome="unknown")
    illustrations.on_retrying = on_image_retrying
    # 出发闸要的那个谓词（TRV-02 合同 15 节）：此刻有没有**拦住出行**的有效承诺。
    # 谓词是 C 写的（`decision/commitments.py`），数据源是 A 的 `owner_asked_stay_home_in`；
    # 决策包不 import 通讯器，所以两边由**这里**接上——组合根是唯一同时认识两边的地方。
    #
    # **不接就等于没有闸**：服务里默认 None，谁要是传了 `honor_commitments=True` 会当场
    # 被 `commitment_gate_unavailable` 拒绝出发（明确要闸却没有闸可用时**拒绝，而不是当成没有承诺放行**）。
    journeys.active_commitment_in = commitment_gate(communicator)
    journeys.photo_request_in = bind_photo_request(illustrations, households)
    # 这次到店该不该真的去生成照片：**只看供应商可用**。**只读、无副作用**——
    # C 在提交事务之前用它决定走不走拍照这条路，这里不能顺手预占、也不能写任何东西。
    # 它在服务里的默认值是 False，所以**不接就等于一张照片都不生成**；接上之前 photo_not_wired 那条守卫也用不上。
    #
    # 原先这里还要 `illustrations.opted_in(...)`，即那道家庭级「生成照片」许可。
    # 用户 2026-09-23 决定**取消逐次询问**（角色与生活/旅行两类都取消），所以这半边摘掉。
    # A 已先摘掉主人主动拍照那条路；**这一行是最后一处半边闸**——在它摘掉之前，
    # 到店事件仍被旧开关挡在「创建拍照请求之前」，根本走不到 A 摘过的地方。
    #
    # **摘的是「询问」，不是保护**：身份与成员关系（`can_view_pet`）、事实代数
    # （`visit_revision_of`）、租约、额度预占、`unknown` 不自动重试——一条都没动。
    # 写事务里的最终授权复核（`consent_in`）也随之取消，它的注释见下方摘除说明。
    journeys.photo_generation_on = lambda visit, journey: bool(illustrations.available())

    def postcard_note(journey, visit) -> str:
        """明信片上 TA 写的话（寄给全家）：发起这趟出门的家人开启“模型回信”时由模型按共用 DNA 写；否则用模板。只写真实发生的地点。"""
        persona = persona_of(FAMILY, journey.pet_id)
        place = visit.place["name"]
        chat = providers.chat
        if persona is not None and chat.available and journey.user_id != SYSTEM_USER and identity.prefs(journey.user_id)["model_replies"]:
            try:
                messages = build_proactive(persona, [], "postcard")
                messages[0]["content"] += f"\n真实情况：你今天在{journey.city}的{place}。"
                text = clean_reply(chat.complete(messages, max_tokens=120, temperature=0.9).text)
                if text:
                    return text
            except Exception:  # noqa: BLE001 - 模型不可用时用模板
                pass
        return f"今天在{journey.city}的{place}待了一会儿，回来的路上路过邮局，就想给家里寄一张。"

    collection.note_writer = postcard_note
    collection.selfie_request = lambda journey, visit, source_key: illustrations.request_photo(
        journey.user_id, journey.pet_id, source_key, place="街边", city=journey.city,
        scene=f"刚在{visit.place['name']}玩完，坐在街边一个老式邮筒旁边，准备寄明信片")
    collection.on_postcard = lambda journey, title: communicator.post_family_note(
        journey.pet_id, f"路过{journey.city}的邮局，给家里寄了一张明信片～在收藏里能看到。", dedupe_key=f"postcard:{journey.journey_id}", now=utcnow())
    collection.has_family = lambda pet_id: households.household_of_pet(pet_id) is not None  # 居民还没有家，不寄明信片

    # ---- 主动消息、自己决定出门、菜园守护 ----
    def owner_prefs(user_id: str) -> OwnerPrefs:
        prefs = identity.prefs(user_id)
        return OwnerPrefs(pet_messages=prefs["pet_messages"], timezone=prefs["timezone"], last_active_at=prefs["last_active_at"])

    def activated_pets() -> list[tuple[str, str]]:
        """住进家的宠物（每只一次）：(记账用的家人＝家庭的第一位管理员, pet_id)。家庭里还没住进来的宠物不算。"""
        with storage.connect() as conn:
            rows = conn.execute(
                "SELECT p.pet_id, p.household_id FROM web_household_pets p JOIN web_homes h ON h.household_id = p.household_id "
                "JOIN web_pet_onboarding o ON o.pet_id = p.pet_id WHERE h.activated_at IS NOT NULL AND o.moved_in_at IS NOT NULL "
                "ORDER BY o.moved_in_at, p.pet_id LIMIT 2000").fetchall()
        result = []
        for row in rows:
            admin = households.primary_admin(row["household_id"])
            if admin:
                result.append((admin, row["pet_id"]))
        return result

    def living_pets() -> list[tuple[str, str]]:
        """自己过日子的全部宠物：住进家的宠物 + 还在驿站生活的待领养居民（记账身份是星球居民驿站）。"""
        return activated_pets() + [(SYSTEM_USER, pet_id) for pet_id in residents.living()]

    def member_pets() -> list[tuple[str, str]]:
        """(家人, 住进家的宠物)：主动私聊按每位家人自己的偏好各发各的。"""
        result = []
        for _, pet_id in activated_pets():
            result += [(user_id, pet_id) for user_id in members_of(pet_id)]
        return result

    proactive = ProactiveMessenger(communicator, moments, persona_of=persona_of, prefs_of=owner_prefs, activated_pets=member_pets,
                                   model_enabled=lambda user_id: user_id not in (FAMILY, SYSTEM_USER) and identity.prefs(user_id)["model_replies"])

    def family_news_allowed(pet_id: str) -> bool:
        """家庭频道里的新鲜事（菜园守护、遇到朋友）：家庭设置；没设置过沿用建立者当初的个人选择。"""
        household_id = households.household_of_pet(pet_id)
        if household_id is None:
            return False
        value = households.setting(household_id, "pet_messages")
        if value is not None:
            return bool(value)
        row = households.household_row(household_id)
        return bool(identity.prefs(row["created_by"])["pet_messages"]) if row else True

    proactive.family_allowed = family_news_allowed

    def family_model_enabled(pet_id: str) -> bool:
        """家庭频道的措辞用不用模型：跟随家庭第一位管理员的“模型回信”选择（默认关闭，不产生模型费用）。"""
        household_id = households.household_of_pet(pet_id)
        admin = households.primary_admin(household_id) if household_id else None
        return bool(admin) and identity.prefs(admin)["model_replies"]

    proactive.family_model_enabled = family_model_enabled

    def on_watch_event(victim, thief, crop: str, outcome: str, now) -> None:
        text = WATCH_TEXT.get(outcome)
        if text:
            proactive.share_news(FAMILY, victim.pet_id, now, f"farm:{outcome}:{thief.pet_id}:{now:%Y%m%d%H}",
                                 text.format(thief=thief.pet_name, crop=crop))

    def life_home_of(pet_id: str):
        return homes.by_pet(pet_id) or residents.home_of(pet_id)

    life = LifeEngine(storage, journeys, economy, moments, persona_of=persona_of, home_of=life_home_of, activated_pets=living_pets,
                      # 回看多久算“主人说了留在家”：与 `decision/service_reader.py:92` 是**同一个判断**，
                      # 所以用同一个常量。先前这里写字面量 12、那边写具名 12，**将来只会有一处被改**（Q 提）。
                      owner_said_stay_home=lambda user_id, pet_id, now: communicator.owner_asked_stay_home(user_id, pet_id, now - timedelta(hours=STAY_HOME_HOURS)))
    life.profile_of = profile_of_pet
    proactive.profile_of = profile_of_pet

    def on_life_departed(user_id: str, pet_id: str, key: str, suggested_by: list[str], now) -> None:
        """TA 采纳了家人的建议：分别回给提建议的那几位家人（私聊）。"""
        journey = journeys.repo.active_for_pet(pet_id)
        for member in suggested_by:
            communicator.post_pet_note(member, pet_id, f"听你的，我去{journey.title if journey else '那里'}啦～",
                                       dedupe_key=f"suggest-go:{pet_id}:{member}:{now:%Y%m%d%H%M}", now=now)

    life.on_departed = on_life_departed

    # ---- 遇到朋友 ----
    friends = FriendService(storage)
    friends.allowed_social = social.public_posts_of  # 家庭开了公开动态（或本来就公开生活的居民），视为允许 TA 自主社交

    def blocked_between(a: str, b: str) -> bool:
        with storage.connect() as conn:
            return conn.execute("SELECT 1 FROM web_blocks WHERE (user_id = ? AND blocked_user_id = ?) OR (user_id = ? AND blocked_user_id = ?)",
                                (a, b, b, a)).fetchone() is not None

    def pet_brief(pet_id: str):
        record = pets.profile(pet_id)
        return (record.name, record.species.value) if record else None

    friends.blocked_between = blocked_between
    friends.pet_brief = pet_brief
    friends.on_meet = lambda meeting, text, now, key: proactive.share_news(FAMILY, meeting.pet_id, now, key, text)
    journeys.add_consumer("friends", friends, lane=SLOW)  # 相遇的新鲜事可能调模型：只由任务进程投递
    farm.resting_of = lambda pet_id: moments.build(pet_id, utcnow()).asleep
    farm.on_watch_event = on_watch_event
    # 每宠运行投影 + 心跳 shadow：只读投影 → 纯策略评估 → 写运行记录（下次检查、安静原因）；不出门、不发消息、不调模型
    projector = RuntimeProjector(storage=storage, journeys=journeys, households=households, residents=residents, homes=homes,
                                 home_places=home_places, dna=dna_store, communicator=communicator, profile_of=profile_of_pet,
                                 realm=getattr(settings, "web_environment", "dev"))
    projector.model_enabled = family_model_enabled
    projector.model_available = lambda: bool(getattr(providers.chat, "available", False))
    projector.decide_window = lambda pet_id: decide_window(profile_of_pet(pet_id))
    # 规则生活与模型生活共用同一本“谁在什么时候替这只宠物做了决定”的账：两条线不会在同一个时段各安排一次
    # 暂停闸：用 `RuntimeStore.paused` 这个**唯一口径**（与 `due_pets` 同一列同一条件）。
    # 不在这里就地读列——那就成了第二份实现，正是今天在别处吃过的漂移。
    # 到点回复与主动消息那两处（I 持有）调同一个谓词，三处一份实现。
    life.paused = projector.runtime.paused
    life.recently_decided = lambda pet_id, now: projector.runtime.decided_within(pet_id, now, HeartbeatPolicy().min_decision_interval)
    life.record_decision = lambda pet_id, now, by: projector.runtime.record_decision(pet_id, now, by=by, next_review_at=None)

    def living_pet_ids() -> list[str]:
        return sorted({pet_id for _, pet_id in activated_pets()} | {pet_id for _, pet_id in living_pets()})

    # 按到期取宠物（CR-B6）：心跳自己排的 next_check_at 已经把可预测的边界算进去了，
    # 再补上五个唤醒来源与看门狗兜底（见 RuntimeStore.due_pets），就不必每 30 秒把所有宠物重算一遍。
    # 先只用在 shadow 这条对照线上；真实调度切过来要等对照跑满一个完整昼夜（世界运行方案的前置条件）。
    due_of = lambda now, after: projector.runtime.due_pets(  # noqa: E731
        now, watchdog=HeartbeatPolicy().max_check_interval, roster=living_pet_ids(), after=after)
    shadow = (HeartbeatShadow(projector, living_pet_ids, due_of=due_of)
              if getattr(settings, "web_heartbeat_mode", "shadow") == "shadow" else None)

    # 两条线各跑各的：世界线只做确定性的事，认知线做可能调模型的事——模型卡住不会拖住到期结算与家庭来信
    role = "worker" if getattr(settings, "web_world_runner", "embedded") == "worker" else "embedded"
    tick_seconds = settings.web_world_tick_seconds
    ticker = WorldTicker([("journeys", lambda now: journeys.advance_all(now)), ("outbox", lambda now: journeys.deliver_outbox(now, lanes=(FAST,))),
                          ("transport_refresh", journeys.refresh_scheduled), ("life", life.run),
                          ("suggestions", lambda now: expire_suggestions(storage, now)),
                          ("outbox_prune", lambda now: journeys.outbox.prune_delivered(now))]
                         + ([("heartbeat_shadow", shadow.run)] if shadow is not None else []),
                         interval_seconds=tick_seconds)
    cognition = WorldTicker([("outbox_slow", lambda now: journeys.deliver_outbox(now, lanes=(SLOW,), limit=10)),
                             ("replies", communicator.deliver_due), ("proactive", proactive.run)],
                            interval_seconds=tick_seconds)
    # 同一时刻每条线只有一个进程在跑（API 内嵌线程或独立任务进程）；租约期限是 3 轮（至少 90 秒）
    ticker.lease = WorkerLease(storage, "world", timedelta(seconds=max(90.0, 3 * tick_seconds)), role=role)
    # 认知线的租期更长：一次模型调用可能要几十秒，不能因为还没跑完就被别的进程接手
    cognition.lease = WorkerLease(storage, "cognition", timedelta(seconds=max(300.0, 6 * tick_seconds)), role=role)
    return AgentWorld(home_places=home_places, dna=dna_store, moments=moments, persona_of=persona_of, guides=guides, friends=friends, proactive=proactive, life=life,
                      ticker=ticker, cognition=cognition, projector=projector, shadow=shadow, profile_of=profile_of_pet,
                      activated_pets=activated_pets, living_pets=living_pets)
