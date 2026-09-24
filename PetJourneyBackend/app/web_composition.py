"""网页服务装配（组合根的一部分，由 main.py 调用）。

所有跨模块依赖在这里以回调注入，模块之间不互相 import 实现：
身份 → 家/宠物 → 接待（MemoryPolicy 投影）→ 家园快照；旅程世界事件 → 通讯/星球圈/收藏；
交通时间线 → 同行影音会话；旅程到达上下文 → 寻味；意图判断层（默认关闭）→ 通讯回应措辞。
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from .companion_media.sessions import LegContext, WebCompanionMedia
from .config import Settings
from .economy_engine import PetEconomyEngine
from .food_discovery.store import WebFoodService
from .intent_layer import IntentLayer, build_judge
from .reception.store import WebReceptionService
from .schemas.web.common import CoordSystem
from .schemas.web.intent import IntentChannel, IntentContext, IntentLayerMode, IntentProvider
from .schemas.web.pets import PetOrigin, PetPresence, PetPrivateSummary
from .schemas.web.reception import CareNoteSlot, CandidateKind, MemoryPurpose
from .schemas.web.social import ActorKind, ActorRef
from .schemas.web.home import UnreadSignals
from .schemas.web.household import EntryIntentView, EntryKind, HouseholdRole, InvitePreview, InviteStatus, PendingAdoption
from .storage import JourneyStorage
from .transport_world.registry import WorldServiceRegistry
from .utils import utcnow
from .web_character import CharacterService, ImageWorkPump, install_character_service
from .web_collection import WebCollectionService
from .web_agent import MomentBuilder
from .web_agent.life import LifeEngine
from .web_agent.profile import BehaviorProfile
from .web_agent.proactive import ProactiveMessenger
from .web_agent.ticker import WorldTicker
from .web_agent_wiring import wire_agent_world
from .web_agent.wish_wiring import bind_ready_plan, bind_wish_round, bind_wish_tick
from .web_communicator import WebCommunicatorService
from .web_economy import WebEconomy, WebInventory
from .web_farm import WebFarmService
from .web_home import WebHomeService
from .web_household import HouseholdError, HouseholdService
from .web_identity import WebIdentityService
from .web_identity.entry import EntryStore
from .web_residents import ResidentService
from .web_journey import JourneySnapshotBuilder, PostcardService, WebJourneyService, window_of
from .web_travel import TravelServices, install_travel
from .web_journey.guides import TravelGuideService
from .web_journey.illustrations import IllustrationService, IllustrationWorker
from .web_home.place import HomePlaceStore
from .web_pets.dna import PetDNAStore
from .web_journey.service import JourneyError
from .web_market import WebMarket
from .web_pets import WebPetsService
from .web_platform.tasks import WebTaskQueue
from .web_providers import WebProviders, build_web_providers
from .web_social import WebSocialService
from .web_social.friends import FriendService
from .web_credentials import CredentialService
from .web_credentials_wiring import wire_documents
from .web_agent.brain_wiring import wire_brain
from .web_driving import DrivingService

logger = logging.getLogger("petsoul.web.composition")


@dataclass
class WebServices:
    identity: WebIdentityService
    households: HouseholdService
    entries: EntryStore
    residents: ResidentService
    pets: WebPetsService
    homes: WebHomeService
    economy: WebEconomy
    inventory: WebInventory
    market: WebMarket
    farm: WebFarmService
    reception: WebReceptionService
    journeys: WebJourneyService
    snapshots: JourneySnapshotBuilder
    registry: WorldServiceRegistry
    media: WebCompanionMedia
    food: WebFoodService
    social: WebSocialService
    communicator: WebCommunicatorService
    collection: WebCollectionService
    postcards: PostcardService
    intent: IntentLayer
    providers: WebProviders
    illustrations: IllustrationService
    character: CharacterService  # TA 在世界里的专属形象（与旅行照片是两条链路，见 web_character/）
    dna: PetDNAStore
    home_places: HomePlaceStore
    moments: MomentBuilder
    proactive: ProactiveMessenger
    life: LifeEngine
    guides: TravelGuideService
    friends: FriendService
    credentials: CredentialService
    driving: DrivingService
    travel: TravelServices  # 旅行心愿与自动手账（TRV-00 §6 装配）
    ticker: WorldTicker  # 世界线（结算与确定性下游）
    cognition: WorldTicker  # 认知线（可能调模型的表达与回复）
    projector: object | None = None  # 每宠运行投影（只读）
    shadow: object | None = None  # 心跳 shadow（只评估并记录）
    brain_life: object | None = None  # 自主决策生活循环（默认 off，一次模型都不调用）
    worker: IllustrationWorker | None = None
    profile_of: Callable[[str], BehaviorProfile] | None = None  # 统一的 DNA 行为画像（DNA 页面展示“为什么这样理解”）

    def presence(self, pet_id: str) -> PetPresence:
        """宠物唯一位置。家庭里的宠物：家已入住且它自己也住进来了才算“在家”；待领养居民：住在星球居民驿站，照常生活。"""
        home = self.homes.by_pet(pet_id)
        if home is None:
            return self.journeys.presence(pet_id, self.pets.is_resident(pet_id))
        moved_in = home.activated_at is not None and self.homes.join_step(pet_id, home).value == "moved_in"
        return self.journeys.presence(pet_id, moved_in)


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


def build_web_services(storage: JourneyStorage, settings: Settings, economy_engine: PetEconomyEngine, providers: WebProviders | None = None) -> WebServices:
    providers = providers or build_web_providers(settings, storage)
    tasks = WebTaskQueue(storage)
    economy = WebEconomy(storage, economy_engine)
    inventory = WebInventory(storage)
    market = WebMarket(storage, economy, inventory)
    registry = WorldServiceRegistry(storage)
    identity = WebIdentityService(storage)
    households = HouseholdService(storage, settings.auth_secret or "")
    entries = EntryStore(storage)
    residents = ResidentService(storage)
    settings.web_private_media_dir.mkdir(parents=True, exist_ok=True)
    pets = WebPetsService(storage, settings.web_private_media_dir, households)
    pets.on_resident_adopted = residents.on_adopted
    journeys = WebJourneyService(storage, economy, registry)
    reception = WebReceptionService(storage, tasks)
    social = WebSocialService(storage)
    communicator = WebCommunicatorService(storage)
    collection = WebCollectionService(storage)
    postcards = PostcardService(storage, settings.web_private_media_dir, tasks)
    illustrations = IllustrationService(storage, settings.web_private_media_dir, tasks)
    food = WebFoodService(storage)
    intent_provider = _safe_enum(IntentProvider, settings.intent_layer_provider, IntentProvider.rule)
    intent = IntentLayer(_safe_enum(IntentLayerMode, settings.intent_layer_mode, IntentLayerMode.off), intent_provider,
                         judge=build_judge(intent_provider, chat=providers.chat))

    holder: dict[str, WebServices] = {}

    def presence_of(pet_id: str) -> PetPresence:
        return holder["web"].presence(pet_id)

    farm = WebFarmService(storage, economy, presence_of, inventory)
    homes = WebHomeService(storage, economy, farm, households)

    def members_of_pet(pet_id: str) -> list[str]:
        """这只宠物所在家庭的有效成员（待领养居民没有家庭 → 空）。"""
        household_id = households.household_of_pet(pet_id)
        return households.member_ids(household_id) if household_id else []

    def projection_slot(user_id: str, pet_id: str, purpose: MemoryPurpose, slot: CareNoteSlot) -> str | None:
        items = reception.projection(user_id, pet_id, purpose).items
        return next((i.slot_value for i in items if i.slot is slot and i.slot_value), None)

    def slot_for_all_purposes(user_id: str, pet_id: str, slot: CareNoteSlot,
                              *purposes: MemoryPurpose) -> str | None:
        """这个槽位的值，**只有同一条叮嘱把列出的每个用途都授权了**才给出来。

        为什么要"同一条"：分别取每个用途的投影再看"都有值"是不够的——
        可能是甲叮嘱授了 A 用途、乙叮嘱授了 B 用途，恰好落在同一个槽位上。
        那是**两次不同的许可**，拼不成一次。所以按 `(note_id, note_version)` 取交集。

        带上 `note_version`：叮嘱被更正后版本会变，**旧版本那条 grant 记录不会放行新内容**。

        **这句话容易被读宽，所以把实际行为写明**（Q 实测 + 我核 `reception/store.py:276-293`）：
        更正时旧 note 的 grants 全部 `revoked_at`，新 note 以 `version + 1` 落库，
        然后 `for purpose in note.purposes` **为新版本重新插入 grants**——
        也就是**用途集合是继承的，用户不需要重新授权，新文字立即可用**。
        所以这里挡住的是「拿旧版本那条 grant 去放行新内容」，
        **不是**「更正后必须重新授权」。后者是**假的保护**，别当它存在。
        （要不要改成「更正后需重新授权」是产品决定，不在本函数范围内。）

        取不到就返回 None，由调用方省略——CR-IMAGE-MEMORY-PURPOSE：**未明确允许的输入应省略**，
        不是换一个用途再用同一段文本。

        **当前唯一调用方 `keepsake_of` 只传一个用途**（`public_story`，
        C84A-MEMORY-RECIPIENT-01 之后按接收方各自授权，见那处注释）。
        名字里的 "all" 说的是**传进来的那些**要全部满足，不是"系统里所有用途"；
        只传一个时它就是"按这一个用途读"，而 `(note_id, note_version)` 那条版本保护照旧生效。
        多用途的交集逻辑留着——**它挡的是"甲叮嘱授 A、乙叮嘱授 B 恰好同槽位"被拼成一次许可**，
        哪天再有接收方需要双授权，直接多传一个即可。
        """
        if not purposes:
            return None
        allowed: dict[tuple[str, int], str] | None = None
        for purpose in purposes:
            here = {(i.note_id, i.note_version): i.slot_value
                    for i in reception.projection(user_id, pet_id, purpose).items
                    if i.slot is slot and i.slot_value}
            allowed = here if allowed is None else {k: v for k, v in allowed.items() if k in here}
            if not allowed:
                return None
        return next(iter(allowed.values())) if allowed else None

    def quiet_of(pet_id: str) -> bool:
        """路上喜欢安静：任何一位家人确认过、并允许用于“出行偏好”的叮嘱都算（只影响活动选择，不转述叮嘱原文）。"""
        return any(i.slot is CareNoteSlot.travel_mood for user_id in members_of_pet(pet_id)
                   for i in reception.projection(user_id, pet_id, MemoryPurpose.travel_preference).items)

    def wishes_of(user_id: str, pet_id: str) -> list[str]:
        items = reception.projection(user_id, pet_id, MemoryPurpose.travel_preference).items
        return [i.text for i in items if i.kind is CandidateKind.wish or i.slot is CareNoteSlot.wish_place]

    def pet_summary_of(pet_id: str) -> PetPrivateSummary | None:
        profile = pets.profile(pet_id)
        home = homes.by_pet(pet_id)
        if profile is None:
            return None
        return PetPrivateSummary(pet_id=pet_id, home_id=home.home_id if home else None, name=profile.name, species=profile.species,
                                 photo_url=pets.photo_url(profile), origin=profile.origin, owner_title=None, presence=PetPresence.unknown,
                                 photo_generated=pets.photo_generated(pet_id))

    def journey_brief_of(pet_id: str):
        journey = journeys.repo.active_for_pet(pet_id)
        if journey is None:
            return None
        return snapshots.brief(journey, journeys.repo.legs(journey.journey_id), journeys.repo.visit_for_journey(journey.journey_id), utcnow())

    def pet_ref(pet_id: str) -> ActorRef | None:
        profile = pets.profile(pet_id)
        if profile is None:
            return None
        avatar = pets.photo_url(profile) if profile.visibility.value == "public" else None
        return ActorRef(actor_kind=ActorKind.pet, actor_id=pet_id, display_name=profile.name, avatar_url=avatar, is_real_household=True)

    def owner_ref(user_id: str) -> ActorRef | None:
        user = storage.get_user(user_id)
        cared = households.accessible_pets(user_id)
        first = pets.profile(cared[0][0]) if cared else None
        name = f"{first.name}的家人" if first else (user.display_name if user and user.display_name else "一位主人")
        return ActorRef(actor_kind=ActorKind.owner, actor_id=user_id, display_name=name, avatar_url=None, is_real_household=True)

    def leg_lookup(leg_id: str) -> LegContext | None:
        leg = journeys.repo.leg(leg_id)
        if leg is None:
            return None
        journey = journeys.repo.get(leg.journey_id)
        if journey is None:
            return None
        return LegContext(window=window_of(leg), user_id=journey.user_id, pet_id=journey.pet_id, quiet=quiet_of(journey.pet_id))

    media = WebCompanionMedia(storage, leg_lookup)
    snapshots = JourneySnapshotBuilder(registry, quiet_of, media.session_state_override)

    def arrival_context_of(user_id: str, pet_id: str):
        journey = journeys.repo.active_for_pet(pet_id)  # 只读（地图快照在 GET 里调用）
        if journey is None or journey.lifecycle != "active" or not pets.is_member(user_id, pet_id):
            return None
        legs = journeys.repo.legs(journey.journey_id)
        visit = journeys.repo.visit_for_journey(journey.journey_id)
        if visit is None or utcnow() >= visit.ends_at:
            return None
        snapshot = snapshots.map_snapshot(journey, legs, visit)
        area = visit.place.get("food_area")
        return (snapshot.arrival_context, area) if snapshot.arrival_context and area else None

    def recommendation_place(user_id: str, recommendation_id: str, journey) -> dict:
        from .food_discovery.store import FoodError

        try:
            rec, journey_id = food.recommendation(user_id, recommendation_id)
        except FoodError as exc:
            raise JourneyError("not_found", exc.message) from exc
        if journey_id != journey.journey_id or rec.branch.place is None:
            raise JourneyError("not_allowed", "只能选这段旅程里的推荐。")
        if rec.freshness.value != "fresh":
            raise JourneyError("stale_recommendation", "行程已经变了，这条推荐需要重新查看。")
        visit = journeys.repo.visit_for_journey(journey.journey_id)
        tz = visit.place.get("timezone", "Asia/Hong_Kong") if visit else "Asia/Hong_Kong"
        place = rec.branch.place
        return {"provider": place.provider.value, "place_id": place.place_id, "name": place.name, "address": place.address, "lat": place.lat, "lng": place.lng,
                "coord_system": CoordSystem.wgs84.value, "category": place.category, "source_updated_at": None, "attribution": place.attribution,
                "timezone": tz, "food_area": visit.place.get("food_area") if visit else None}

    def shared_listening_of(journey) -> dict[str, int]:
        """这趟旅程里每位家人陪 TA 一起听/看的毫秒数。"""
        leg_ids = [leg.leg_id for leg in journeys.repo.legs(journey.journey_id)]
        members = members_of_pet(journey.pet_id) or [journey.user_id]
        return {user_id: sum(ms for _, ms in media.counted_for_legs(user_id, leg_ids)) for user_id in members}

    def reply_style_of(user_id: str, text: str) -> str | None:
        return intent.reply_style(IntentContext(request_id="-", message_id="-", channel=IntentChannel.communicator), text)

    # ---- 注入 ----
    journeys.pet_name_of = lambda pet_id: (pets.profile(pet_id).name if pets.profile(pet_id) else "TA")
    journeys.wishes_of = wishes_of
    journeys.postcard_maker = postcards.make
    journeys.recommendation_place = recommendation_place
    # 冒险故事里那件"带着你准备的 X"。**按它自己的接收方授权**：
    # `web_communicator` 把 story 写进**家庭频道**（全家可见）→ 所以要的是 `public_story`。
    #
    # **原先这里请求的是 `private_chat`**（CR-IMAGE-MEMORY-PURPOSE-2026-09-24）。
    # `reception/policy.py` 的过滤本身没错——它老老实实按**请求的那个用途**过滤；
    # 错在这个消费端请求了私聊专用的用途，于是私聊叮嘱进了家庭故事，又进了供应商提示词。
    # **这一条我逐环核过可达数据流，不是照抄 CR。**
    #
    # ---- 为什么这不是绕回一个已经被否定的做法（C84A-MEMORY-RECIPIENT-01，00:44 收口增量）----
    #
    # 这里一度要求 `public_story` ∩ `media_generation` **双授权**。当初否定
    # 「把 `private_chat` 换成 `public_story` 就完事」，理由是**那样只挡住家庭频道那一半，
    # 同一段文本照样进生图**——那时 story 确实会流进 `illustrations` 的任务载荷，
    # 再进 `photo_prompts.build_prompt` 的 `Scene (…): {story}`。
    #
    # **那个理由现在不成立了**：A 已把图片那一侧从根上断开——`illustrations.request`
    # 不再存 story，发送时按模板 `render_story(…, None)` **无条件**不带叮嘱
    # （`illustrations.py:341`）。**「同一段文字要给两个接收者」这个前提没有了。**
    # 再要求 `media_generation` 就成了**过度限制**：只授权过「公开故事」的叮嘱
    # 本该能进家庭故事，却因为没授权生图被挡在外面。
    #
    # 所以 CR 禁止的是「换个用途名继续共用同一文本」，**不是**「家庭文字永远绑上图片许可」。
    # 两个接收方各按各的用途授权、互不默认——而图片那一侧本批**一律不用叮嘱**，比任何用途门都严。
    #
    # 仍然走 `slot_for_all_purposes`（即便现在只传一个用途）：它按 `(note_id, note_version)`
    # 取值，**叮嘱被更正后旧版本的许可不延续到新内容**这条保护要留着。
    journeys.keepsake_of = lambda user_id, pet_id: slot_for_all_purposes(
        user_id, pet_id, CareNoteSlot.favorite_object, MemoryPurpose.public_story)
    # 世界事件下游（按 outbox 投递）：家庭来信、公开动态、收藏都只写库，走 fast 通道
    journeys.add_consumer("communicator", communicator)
    journeys.add_consumer("social", social)
    journeys.add_consumer("collection", collection)
    if providers.geo is not None and (providers.geo.configured("amap") or providers.geo.configured("google")):
        journeys.geo = providers.geo
    journeys.demo_catalog = bool(getattr(settings, "web_demo_catalog", False))  # 演示线路只在演示环境
    journeys.on_replanned = lambda journey, trip, text, now: communicator.post_family_note(
        journey.pet_id, text, dedupe_key=f"replan:{journey.journey_id}:{journey.itinerary_version}:{journey.lifecycle}", now=now)
    reception.pet_name_of = journeys.pet_name_of
    reception.chat = providers.chat
    def reception_state(user_id: str, session_id: str, skipped: bool) -> None:
        """接待的进度记到那只宠物的入住进度上（只对还没住进来的宠物有意义）。"""
        with storage.connect() as conn:
            row = conn.execute("SELECT pet_id FROM web_reception_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is not None:
            homes.record_reception(row["pet_id"], session_id, skipped)

    reception.on_state = reception_state
    reception.onboarding_of = homes.onboarding
    homes.presence_of = lambda pet_id, activated: journeys.presence(pet_id, activated)
    homes.journey_brief_of = journey_brief_of
    homes.welcome_of = reception.home_welcome

    homes.owner_title_of = lambda user_id, pet_id: projection_slot(user_id, pet_id, MemoryPurpose.home_interaction, CareNoteSlot.owner_title)
    homes.unread_of = lambda user_id, pet_id: UnreadSignals(
        messages=communicator.unread(user_id, pet_id),
        circle=social.unread_circle(user_id, [p for p, _ in households.accessible_pets(user_id)], utcnow() - timedelta(days=1)))
    homes.pet_summary_of = pet_summary_of

    def entry_view(user_id: str) -> EntryIntentView | None:
        """注册时带来的入口（只恢复、重新校验，不替用户做决定）：选中的伙伴还在不在；邀请有没有过期、是不是已经是成员。"""
        pending = entries.pending(user_id)
        if pending is None:
            return None
        adoption = invite = None
        if pending["kind"] == "adopt" and pending["target_pet_id"]:
            record = pets.profile(pending["target_pet_id"])
            if record is not None:
                adoption = PendingAdoption(pet_id=record.pet_id, name=record.name, species=record.species,
                                           available=pets.candidate_for_pet(record.pet_id) is not None)
        if pending["kind"] == "invite" and pending["invite_id"]:
            try:
                invite = invite_preview(households.invite(pending["invite_id"]), user_id)
            except HouseholdError:
                invite = None
        return EntryIntentView(kind=EntryKind(pending["kind"]), pending_adoption=adoption, pending_invite=invite, created_at=pending["created_at"])

    def invite_preview(view: dict, viewer: str | None) -> InvitePreview:
        household = households.household_row(view["household_id"])
        inviter = storage.get_user(view["created_by"])
        names = [pets.profile(p).name for p in households.pets_of(view["household_id"]) if pets.profile(p)]
        member = viewer is not None and households.access_household(viewer, view["household_id"]) is not None
        return InvitePreview(invite_id=view["invite_id"], status=InviteStatus(view["status"]), role=HouseholdRole(view["role"]),
                             relation_hint=view["relation_hint"], expires_at=view["expires_at"], household_name=household["name"] if household else None,
                             inviter_name=(inviter.display_name if inviter and inviter.display_name else "一位家人"), pet_names=names, already_member=member)

    homes.entry_of = entry_view

    def consume_household_seed(home, crop_key: str) -> str | None:
        """稀有种子是宠物带回来的收藏：从这个家任意一只宠物那里用掉一颗，返回是哪一只（并发失败时退回给它）。"""
        for pet_id in home.all_pets:
            if collection.consume_seed(pet_id, crop_key):
                return pet_id
        return None

    farm.consume_seed = consume_household_seed
    farm.refund_seed = collection.refund_seed
    communicator.household_of = households.household_of_pet
    journeys.can_view_pet = pets.is_member
    media.can_view_pet = pets.is_member
    illustrations.can_view_pet = pets.is_member
    postcards.can_view_pet = pets.is_member
    collection.shared_listening_of = shared_listening_of
    def public_posts_of(pet_id: str) -> bool:
        """这只宠物的新动态是否公开：家庭的公开设置；待领养居民的生活本来就是公开的。"""
        home = homes.by_pet(pet_id)
        return bool(home.public_posts) if home is not None else pets.is_resident(pet_id)

    social.public_posts_of = public_posts_of
    social.members_of_pet = members_of_pet
    social.pet_ref_of = pet_ref
    social.owner_ref_of = owner_ref
    social.on_post_media_public = lambda url: postcards.mark_public(url.rsplit("/", 1)[-1])
    communicator.presence_of = presence_of
    communicator.owner_title_of = lambda user_id, pet_id: projection_slot(user_id, pet_id, MemoryPurpose.private_chat, CareNoteSlot.owner_title)
    communicator.reply_style_of = reply_style_of
    communicator.chat = providers.chat
    communicator.model_replies_of = lambda user_id: identity.prefs(user_id)["model_replies"]

    def character_of(pet_id: str):
        record = pets.profile(pet_id)
        if record is None:
            return None
        return record.species.value, record.name, pets.traits(record)[0]

    def reference_photo_of(pet_id: str):
        """生图用的外貌参考：只用这只宠物自己的照片，不会借用别的宠物或样板照片。"""
        found = pets.photo_path(pet_id)
        return (found[0].read_bytes(), found[1]) if found else None

    def reference_origin_of(pet_id: str) -> str | None:
        """这张参考照**是从哪来的**（A 的 CR-A15）。照片导演要求标注来源，**拿不准一律返回 None → hold**。

        不新开表、不加迁移——用已经存在的两个事实拼：
        - `pets.photo_generated(pet_id)`：`set_portrait` 保存我们自己画的基准照时会在同一条 UPDATE 里置 1；
        - `profile.origin`：`own_pet`＝主人自己带来的伙伴，照片是主人上传的。

        映射（只映射说得清的两种，其余宁可 hold）：
        - 有照片 ＋ `photo_generated` → **original_companion**（我们自己生成并保存的基准照）
        - 有照片 ＋ 非 generated ＋ `own_pet` → **owner_original**（主人上传的原照）
        - 有照片 ＋ 非 generated ＋ `adopted_real_archive` → **real_archive**（真实档案照，词表里有它自己的位置）
        - **其余一律 None**：`adopted_original` 的预置素材既不是主人原照、也不是我们画的基准照、更不是真实档案，
          没有诚实的来源可给，**继续 hold 是对的**——给来源不明的图冒名比 hold 糟得多。
          要不要给它一个来源是产品判断，不在装配里顺手定。

        `real_archive` 这一档曾经走不通——来源词表有两份，上游 `photo_director_bridge.py` 那份少一个值，
        会先把它拦成"来源不明"。**A 已经补齐，两份现在一致**（2026-09-23 10:0X 实测），所以这条映射是通的。
        留这段话是为了记住教训：**同一个概念有两份定义时，谁也不报错，行为会静悄悄变成一次"合理的 hold"。**
        """
        if pets.photo_path(pet_id) is None:
            return None
        if pets.photo_generated(pet_id):
            return "original_companion"
        record = pets.profile(pet_id)
        if record is None:
            return None
        return {PetOrigin.own_pet: "owner_original", PetOrigin.adopted_real_archive: "real_archive"}.get(record.origin)

    illustrations.illustrator = providers.illustrator
    households.prefs_in = identity.prefs_in  # 家庭那边复核授权时，在调用方的连接上读个人设置

    # 【已摘除】`generated_photos_of` 与 `illustrations.opted_in = …` —— 那道家庭级「生成照片」许可。
    # 用户 2026-09-23 决定取消逐次询问（角色与生活/旅行两类都取消）。摘的是**询问**，
    # 身份与成员关系、事实代数、租约、额度预占、`unknown` 不自动重试一条都没动。
    #
    # 摘除顺序（反过来会静默全停）：先去掉 `web_agent_wiring.py` 里 `photo_generation_on`
    # 的 `opted_in` 调用，**再**摘这里和那边的 `consent_in` 接线——先摘接线的话，
    # `opted_in` 会落回 `IllustrationService` 的默认 `lambda …: False`，
    # 到店照片全部停掉且**不报错**。
    #
    # **留给 c84a 的线索**：摘掉这里之后，`households.generated_photos_in`
    # （`web_household/access.py:23`）**已无任何调用方**。它连同 `web_user_prefs` /
    # `web_households` 两张表的 `generated_photos` 列、`PATCH /settings` 的写入口、
    # 以及前端设置页，属于同一批要统筹处置的东西——**不在本窗口范围，我只摘到这里为止**。
    illustrations.character_of = character_of
    illustrations.reference_photo_of = reference_photo_of
    illustrations.reference_origin_of = reference_origin_of

    def event_revision_of(source_key: str) -> int | None:
        """**执行这一刻**的事件代数。按来路分派，谁也不猜。

        - **主人主动拍照**（`photo-request:…`）：事实在按下命令那一刻就固定了
          （在家 / 在列车这一段 / 主人选的虚构主题），**命令型事件没有后续修订**，所以恒为 1。
          这不是"回读 payload 自比"——是这条来路的定义：它本来就不会有第二个版本。
          **但要把话说透：恒为 1 等于这条路上没有代数围栏。** 它是一个诚实的常量，不是伪装的闸；
          主人命令那条的保护来自别处（下命令那一刻的状态核验、写事务里的 `versions_in` 复核、
          A 每次发送前的实时授权复核），**不要以为它也被 revision 保护着**。
        - **到访触发**（`photo:<visit_id>`）：事实来自到访记录，会随主人选座、点饮品、类目被更正而变，
          必须按**进照片的那几个字段**重算（P 给的 `fact_revision_of`，归 B 的 `photo_scene.py`）。
          B 把它接到 `illustrations.visit_revision_of` 上，这里就用；**没接上一律 None → hold**，
          不拿一个假代数把围栏伪装成有效。
        """
        if source_key.startswith("photo-request:"):
            return 1
        hook = getattr(illustrations, "visit_revision_of", None)
        return hook(source_key) if hook is not None else None

    illustrations.event_revision_of = event_revision_of
    communicator.illustration_request = illustrations.request
    food.arrival_context_of = arrival_context_of
    food.current_itinerary_of = lambda journey_id: (journeys.repo.get(journey_id).itinerary_version if journeys.repo.get(journey_id) else None)

    agent = wire_agent_world(storage=storage, settings=settings, providers=providers, identity=identity, pets=pets, homes=homes, farm=farm,
                             economy=economy, journeys=journeys, reception=reception, communicator=communicator, collection=collection,
                             illustrations=illustrations, social=social, presence_of=presence_of, households=households, residents=residents)
    docs = wire_documents(storage=storage, pets=pets, homes=homes, economy=economy, journeys=journeys, registry=registry, dna_store=agent.dna,
                          reception=reception, communicator=communicator, moments=agent.moments, profile_of=agent.profile_of, collection=collection,
                          illustrations=illustrations, activated_pets=agent.activated_pets, households=households)
    agent.ticker.jobs.append(("driving", docs.tick))

    # ---- 旅行心愿与自动手账（TRV-00 合同 §6）----
    # **只接了三样，其余留默认，逐条登记在下面**——默认值都是安全的（少画东西，不是多造事实）。
    travel = install_travel(
        storage, tasks,
        # 合同 §4.5：复用既有暂停谓词，不再读一次那一列
        paused_in=lambda conn, pet_id: agent.projector.runtime.paused(pet_id, conn=conn),
        settings=settings,
        illustrations=illustrations,
    )
    # **没接的，以及后果**（不写的话下一个人会以为已经全接上了）：
    #   research_port  —— TRV-04 适配器还没做。`run_pending` 在没有 port 时 `return 0`，
    #                     任务留在队里、**不造一个「没查到」**（A 的 fail-closed，我核过 research.py:94）。
    #                     心愿会停在 `research_pending`，那是诚实的状态。
    #   ledger         —— ⚠ **它和 research_port 是一对**：`_reserve_in` 在 `ledger is None` 时直接
    #                     `return None`（research.py:207）＝**不预占额度就继续**。今天不出事只因为
    #                     没有 port 就走不到那一行。**接 port 的那一刻必须同时接 ledger**。
    #                     **A 已闭合，两层**：`install_travel` 构造期抛 ValueError（装配时快速失败），
    #                     `_reserve_in` 开头抛 ResearchMisconfigured（**花钱那一步 fail-closed**）。
    #                     **承重的是第二层**（Q 核出）：`port` 是普通属性，事后赋值能绕过构造期检查。
    #                     接法：`install_travel(ledger=BudgetLedger(storage), research_port=...)`，
    #                     **不要事后写 `travel.research.port = adapter`**。
    #   identity_of    —— 默认 None ＝ 手账里不画 TA（仍有文字与画面）。
    #   mood_of        —— 默认心情常量。
    #   visit_of       —— 默认 None ＝ 回忆页不盖到访章。
    # 出发事务内的三个注入位（合同 §4.2，C 的 CR）。**不接这三行，心愿链路最后一段就是断的，
    # 而且断得很安静**：`depart` 传了 plan_id 时会被 `plan_link_unavailable` 当场拒——
    # 闸在正常工作（端口缺席时宁可不出发，也不建一趟没有计划归属的行程），
    # 但**不报错、不崩，只是每次都拒绝**。我上一轮装配时漏了这三行，C 核出。
    journeys.ready_plan_in = travel.wishes.ready_plan_in
    journeys.link_journey_in = travel.wishes.link_journey_in
    journeys.stale_facts_in = travel.wishes.stale_facts_in
    # 世界事件 sink：returned_home 时出回忆页、心愿落定 completed，重放幂等（A 的口径）
    journeys.add_consumer("travel_journals", travel.journals)
    # 心愿这一轮挂在**现有的生活节奏**上，不新建调度器（TRV-01 接入点，I 定）。
    # **在有提案器之前它是空转**：每宠每轮一次只读。接它的理由是 B 那条——
    # 「接线本身是一次独立的验证」，不要等 TRV-04 时把接口改动和新模块放同一批。
    # `activated` 是**按调用传进来的事实、不是谓词**（B 改）：`bind_wish_tick` 本来就在遍历
    # 已入住的宠物，**它知道答案，不需要再查一遍**——上一版那个谓词是每轮 N 次 SQL，
    # 而 ticker 是 30 秒一轮、`activated_pets` 的 SQL 上限 2000 行。现在与 driving tick 同量级。
    agent.ticker.jobs.append(("wishes", bind_wish_tick(
        bind_wish_round(wishes=travel.wishes, projector=agent.projector, economy=economy,
                        journeys=journeys, storage=storage),
        agent.activated_pets)))
    # 链路最后一格：规则生活挑目的地时先看有没有就绪的计划（B 的 CR）。
    # **不接的后果是安静的**：`ready_plan_of` 默认返回 None，规则生活照原样掷骰，
    # **一条用例都不会红**——攒了很久的那个心愿只是永远轮不到。所以 B 专门写了一条行为断言看着它。
    # `_wish_pick` 用的是与 `choose` 同一组判据（不在选项里／钱不够／长途冷却没过 → 都不强推）：
    # **不能因为「有计划」就绕过既有闸**，那会变成第五条出门路径。
    agent.life.ready_plan_of = bind_ready_plan(travel.wishes, storage)

    web = WebServices(identity=identity, households=households, entries=entries, residents=residents, pets=pets, homes=homes, economy=economy, inventory=inventory, market=market, farm=farm, reception=reception, journeys=journeys, snapshots=snapshots,
                      registry=registry, media=media, food=food, social=social, communicator=communicator, collection=collection, postcards=postcards, intent=intent,
                      providers=providers, illustrations=illustrations,
                      # 海象绑定是为了让下面的 worker= 能引用同一个实例：实参按源码顺序求值，
                      # 所以这里绑好之后 worker= 才求值。不另起一行局部变量，是为了把改动收在已释放的实参位置内。
                      character=(character := install_character_service(
                          storage, settings.web_private_media_dir, tasks, pets=pets,
                          illustrator=providers.illustrator, settings=settings, meter=providers.meter)),
                      dna=agent.dna, home_places=agent.home_places, moments=agent.moments,
                      proactive=agent.proactive, life=agent.life, guides=agent.guides, friends=agent.friends, credentials=docs.credentials, driving=docs.driving, travel=travel,
                      ticker=agent.ticker, cognition=agent.cognition, projector=agent.projector, shadow=agent.shadow, profile_of=agent.profile_of,
                      # 进程内那一个线程要同时泵插画与角色：`illustrations.run_pending` 里写死了 kind="illustration"，
                      # 角色任务永远不会被它领取（上传排了队、库里有行，却没人执行）。`ImageWorkPump` 逐个泵、逐个兜异常。
                      worker=IllustrationWorker(ImageWorkPump(illustrations, character)) if providers.illustrator.available else None)
    holder["web"] = web
    wire_brain(web, agent, storage, providers, settings)
    return web
