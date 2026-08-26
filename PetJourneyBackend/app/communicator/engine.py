from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..memory_store import MemoryStore
from ..schemas import JourneyThought, OwnerMessageResponse
from ..storage import JourneyStorage, utcnow
from .attachment_planner import CommunicatorAttachmentPlanner
from .intent_router import CommunicatorIntentRouter
from .message_store import CommunicatorMessageStore, new_message_id, new_pending_id
from .moment_generator import CommunicatorMomentGenerator
from .moment_reaction import CommunicatorMomentReactionHandler
from .moment_store import CommunicatorMomentStore
from .pending_resolver import CommunicatorPendingResolver
from .reply_policy import CommunicatorReplyPolicyEngine
from .schemas import (
    AttachmentState,
    AttachmentType,
    CommunicatorAttachment,
    CommunicatorIntent,
    CommunicatorMessage,
    CommunicatorMoment,
    CommunicatorSendRequest,
    CommunicatorSendResponse,
    MessageSender,
    MomentReactionRequest,
    MomentReactionResponse,
    MomentSourceType,
    PendingPhotoRequest,
    PendingStatus,
    PetReplyState,
    ReplyMode,
    ReplyPolicy,
    UserMessageState,
)
from .world_snapshot import CommunicatorWorldSnapshotBuilder

PHOTO_INTENTS = {
    CommunicatorIntent.current_status_visual_request,
    CommunicatorIntent.photo_request,
    CommunicatorIntent.confirm_pending_photo,
}


class PetCommunicatorEngine:
    provider_name = "pet-communicator-engine"

    def __init__(self, *, storage: JourneyStorage, journey_engine: Any, memory_store: MemoryStore):
        self.storage = storage
        self.journey_engine = journey_engine
        self.memory_store = memory_store
        self.intent_router = CommunicatorIntentRouter()
        self.world_builder = CommunicatorWorldSnapshotBuilder()
        self.reply_policy = CommunicatorReplyPolicyEngine()
        self.attachment_planner = CommunicatorAttachmentPlanner()
        self.message_store = CommunicatorMessageStore(storage)
        self.moment_store = CommunicatorMomentStore(storage)
        self.moment_generator = CommunicatorMomentGenerator(self.moment_store)
        self.moment_reaction = CommunicatorMomentReactionHandler(self.moment_store, memory_store)
        self.pending_resolver = CommunicatorPendingResolver(
            message_store=self.message_store,
            attachment_planner=self.attachment_planner,
            moment_generator=self.moment_generator,
        )

    def send_message(self, *, pet_id: str, request: CommunicatorSendRequest) -> CommunicatorSendResponse:
        clean = " ".join(request.text.strip().split())
        if not clean:
            raise ValueError("empty communicator message")
        pet = self._pet(pet_id)
        now = utcnow()
        world = self._world(pet_id)
        intent = self.intent_router.route(clean)
        if (
            intent == CommunicatorIntent.general_chat
            and self._is_photo_confirmation(clean)
            and self._has_recent_photo_offer(pet_id)
        ):
            intent = CommunicatorIntent.confirm_pending_photo
        latest_photo_at = self.message_store.latest_photo_request_at(pet_id)
        latest_scene_photo_at = self.message_store.latest_photo_request_at(pet_id, scene_hash=world.scene_hash)
        policy = self.reply_policy.resolve(
            intent=intent,
            world=world,
            now=now,
            latest_photo_at=latest_photo_at,
            latest_scene_photo_at=latest_scene_photo_at,
        )
        owner_message = CommunicatorMessage(
            id=new_message_id(),
            pet_id=pet_id,
            sender=MessageSender.owner,
            text=clean,
            intent=intent,
            scene_hash=world.scene_hash,
            message_state=UserMessageState.delivered,
            reply_policy=policy,
            attachments=[],
            created_at=now,
        )
        self.message_store.add_message(owner_message)

        attachments = self.attachment_planner.plan(intent=intent, world=world, policy=policy, now=now)
        messages: list[CommunicatorMessage] = []
        pending: PendingPhotoRequest | None = None

        if policy.mode in {
            ReplyMode.queued_until_landed,
            ReplyMode.queued_until_morning,
            ReplyMode.queued_until_photoable_scene,
        } or (policy.mode == ReplyMode.delayed and intent in {
            CommunicatorIntent.current_status_visual_request,
            CommunicatorIntent.photo_request,
            CommunicatorIntent.confirm_pending_photo,
        }):
            pending = self._create_pending(
                pet_id=pet_id,
                source_message_id=owner_message.id,
                intent=intent,
                mode=policy.mode,
                reason=policy.reason_code,
                world=world,
                now=now,
                estimated_seconds=policy.estimated_reply_seconds,
            )
            self.message_store.add_pending(pending)
            system = self._system_message(
                pet_id=pet_id,
                text=policy.visible_status,
                intent=intent,
                policy=policy,
                attachments=attachments,
                related_message_id=owner_message.id,
                scene_hash=world.scene_hash,
                now=now,
            )
            self.message_store.add_message(system)
            messages.append(system)
        elif policy.mode == ReplyMode.no_reply_needed:
            system = self._system_message(
                pet_id=pet_id,
                text=policy.visible_status,
                intent=intent,
                policy=policy,
                attachments=attachments,
                related_message_id=owner_message.id,
                scene_hash=world.scene_hash,
                now=now,
            )
            self.message_store.add_message(system)
            messages.append(system)
        elif policy.mode == ReplyMode.delayed and intent == CommunicatorIntent.general_chat:
            system = self._system_message(
                pet_id=pet_id,
                text=policy.visible_status,
                intent=intent,
                policy=policy,
                attachments=[],
                related_message_id=owner_message.id,
                scene_hash=world.scene_hash,
                now=now,
            )
            self.message_store.add_message(system)
            messages.append(system)
        else:
            reply_text = self._reply_text(pet_name=pet.name, text=clean, intent=intent, world=world)
            pet_message = CommunicatorMessage(
                id=new_message_id(),
                pet_id=pet_id,
                sender=MessageSender.pet,
                text=reply_text,
                intent=intent,
                scene_hash=world.scene_hash,
                message_state=PetReplyState.sent,
                reply_policy=policy,
                attachments=attachments,
                related_message_id=owner_message.id,
                created_at=now,
            )
            self.message_store.add_message(pet_message)
            messages.append(pet_message)
            self._record_pet_reply(pet_id=pet_id, intent=intent, text=reply_text)
            self._remember_message(pet_id=pet_id, owner_text=clean, reply_text=reply_text, intent=intent)
            self._maybe_create_moment_for_reply(pet_id=pet_id, intent=intent, world=world, attachments=attachments, now=now)

        return CommunicatorSendResponse(
            success=True,
            intent=intent,
            reply_policy=policy,
            owner_message=owner_message,
            messages=messages,
            pending_request=pending,
        )

    def send_photo(
        self,
        *,
        pet_id: str,
        image_url: str,
        media_path: str,
        caption: str | None = None,
    ) -> CommunicatorSendResponse:
        pet = self._pet(pet_id)
        now = utcnow()
        world = self._world(pet_id)
        clean = " ".join((caption or "").strip().split())
        intent = CommunicatorIntent.owner_photo_share
        policy = ReplyPolicy(
            mode=ReplyMode.immediate,
            estimated_reply_seconds=6,
            visible_status="TA 看到了这张照片。",
            reason_code="owner_photo_shared",
        )
        owner_attachment = CommunicatorAttachment(
            type=AttachmentType.owner_photo,
            title="你发来的照片",
            text=clean or "给 TA 看的一张照片。",
            state=AttachmentState.ready,
            photo_url=image_url,
            metadata={"media_path": media_path},
        )
        owner_message = CommunicatorMessage(
            id=new_message_id(),
            pet_id=pet_id,
            sender=MessageSender.owner,
            text=clean,
            intent=intent,
            scene_hash=world.scene_hash,
            message_state=UserMessageState.delivered,
            reply_policy=policy,
            attachments=[owner_attachment],
            created_at=now,
        )
        self.message_store.add_message(owner_message)

        reply_text = self._owner_photo_reply(caption=clean, world=world)
        pet_message = CommunicatorMessage(
            id=new_message_id(),
            pet_id=pet_id,
            sender=MessageSender.pet,
            text=reply_text,
            intent=intent,
            scene_hash=world.scene_hash,
            message_state=PetReplyState.sent,
            reply_policy=policy,
            attachments=[],
            related_message_id=owner_message.id,
            created_at=now,
        )
        self.message_store.add_message(pet_message)
        self._record_pet_reply(pet_id=pet_id, intent=intent, text=reply_text)
        self._remember_owner_photo(
            pet_id=pet_id,
            caption=clean,
            reply_text=reply_text,
            image_url=image_url,
            media_path=media_path,
        )
        return CommunicatorSendResponse(
            success=True,
            intent=intent,
            reply_policy=policy,
            owner_message=owner_message,
            messages=[pet_message],
            pending_request=None,
        )

    def legacy_owner_message(self, *, pet_id: str, message: str, intent_hint: str | None = None) -> OwnerMessageResponse:
        legacy = self.journey_engine.owner_message(pet_id=pet_id, message=message, intent_hint=intent_hint)
        now = utcnow()
        owner_message = CommunicatorMessage(
            id=new_message_id(),
            pet_id=pet_id,
            sender=MessageSender.owner,
            text=message,
            intent=CommunicatorIntent.general_chat,
            message_state=UserMessageState.delivered,
            created_at=now,
        )
        self.message_store.add_message(owner_message)
        self.message_store.add_message(
            CommunicatorMessage(
                id=new_message_id(),
                pet_id=pet_id,
                sender=MessageSender.pet,
                text=legacy.message,
                intent=CommunicatorIntent.general_chat,
                message_state=PetReplyState.sent,
                related_message_id=owner_message.id,
                created_at=now,
            )
        )
        return legacy

    def list_messages(self, *, pet_id: str, limit: int = 80) -> list[CommunicatorMessage]:
        self._pet(pet_id)
        return self.message_store.list_messages(pet_id, limit=limit)

    def list_moments(self, *, pet_id: str, limit: int = 50) -> list[CommunicatorMoment]:
        pet = self._pet(pet_id)
        if not self.moment_store.list_moments(pet_id, limit=1):
            world = self._world(pet_id)
            self.moment_generator.ensure_seed_moments(pet_id=pet_id, pet_name=pet.name, world=world, now=utcnow())
        # 意图消费必须在种子动态之后:否则首次打开朋友圈时,大脑提议的一条动态会让种子流程误以为已有内容
        self._consume_agent_content_intent(pet_id=pet_id, now=utcnow())
        return self.moment_store.list_moments(pet_id, limit=limit)

    def _consume_agent_content_intent(self, *, pet_id: str, now: datetime) -> None:
        """大脑在 agent turn 里提议"这一刻值得分享";这里做终审:频控、场景冷却、精力门槛全部照旧生效。"""
        consume = getattr(self.journey_engine, "consume_content_intent", None)
        if not callable(consume):
            return
        payload = consume(pet_id)
        if not payload:
            return
        intent = str(payload.get("intent") or "")
        text = str(payload.get("translation") or payload.get("scene") or "").strip()
        if intent == "postcard":
            source_type = MomentSourceType.postcard_candidate
            text = text or "今天有一个地方，很适合写成一张慢慢寄出的明信片。"
        elif intent == "moment":
            source_type = MomentSourceType.journey_event
            text = text or "刚刚有个瞬间，想放进朋友圈里。"
        else:
            return
        world = self._world(pet_id)
        self.moment_generator.maybe_create_moment(
            pet_id=pet_id,
            source_type=source_type,
            text=text,
            world=world,
            now=now,
        )

    def react_to_moment(
        self,
        *,
        pet_id: str,
        moment_id: str,
        request: MomentReactionRequest,
    ) -> MomentReactionResponse:
        self._pet(pet_id)
        return self.moment_reaction.react(pet_id=pet_id, moment_id=moment_id, reaction=request.reaction)

    def resolve_pending_for_pet(self, pet_id: str) -> list[CommunicatorMessage]:
        now = utcnow()
        world = self._world(pet_id)
        messages = self.pending_resolver.resolve_due_requests(pet_id=pet_id, world=world, now=now)
        for message in messages:
            if message.sender == MessageSender.pet:
                self._record_pet_reply(pet_id=pet_id, intent=message.intent or CommunicatorIntent.general_chat, text=message.text)
        return messages

    def _world(self, pet_id: str):
        status = self.journey_engine.status(pet_id)
        world = self.journey_engine.world_snapshot(pet_id)
        return self.world_builder.build(status=status, world=world)

    def _pet(self, pet_id: str):
        pet = self.storage.get_pet(pet_id)
        if pet is None:
            self.journey_engine.status(pet_id)
            pet = self.storage.get_pet(pet_id)
        return pet

    def _system_message(
        self,
        *,
        pet_id: str,
        text: str,
        intent: CommunicatorIntent,
        policy,
        attachments,
        related_message_id: str,
        scene_hash: str | None,
        now: datetime,
    ) -> CommunicatorMessage:
        return CommunicatorMessage(
            id=new_message_id(),
            pet_id=pet_id,
            sender=MessageSender.system,
            text=text,
            intent=intent,
            scene_hash=scene_hash,
            message_state=PetReplyState.sent,
            reply_policy=policy,
            attachments=attachments,
            related_message_id=related_message_id,
            created_at=now,
        )

    def _create_pending(
        self,
        *,
        pet_id: str,
        source_message_id: str,
        intent: CommunicatorIntent,
        mode: ReplyMode,
        reason: str,
        world,
        now: datetime,
        estimated_seconds: int,
    ) -> PendingPhotoRequest:
        available_after = now + timedelta(seconds=max(60, estimated_seconds))
        return PendingPhotoRequest(
            id=new_pending_id(),
            pet_id=pet_id,
            source_message_id=source_message_id,
            intent=intent,
            pending_type=mode,
            status=PendingStatus.pending,
            reason=reason,
            trigger=mode.value,
            requested_scene="current_status",
            scene_hash=world.scene_hash,
            created_at=now,
            available_after=available_after,
            expires_at=now + timedelta(hours=24),
        )

    def _reply_text(self, *, pet_name: str, text: str, intent: CommunicatorIntent, world) -> str:
        place = f"{world.city}{' · ' + world.place_name if world.place_name else ''}"
        if intent == CommunicatorIntent.emotional_distress:
            return "我看到你这句话了。先不要一个人硬撑，去找身边可信的人或当地紧急帮助；我会把这一小段光轻轻放在这里陪你。"
        if intent == CommunicatorIntent.current_status_visual_request:
            return f"我在{place}这边。{self._scene_feeling(world)}，我拍给你看。"
        if intent == CommunicatorIntent.photo_request:
            return f"好呀。我在{place}找个不晃的角度，拍给你。"
        if intent == CommunicatorIntent.confirm_pending_photo:
            return "好呀，我拍给你看。"
        if intent == CommunicatorIntent.location_check:
            return f"我现在在{place}。位置给你发过来了。"
        if intent == CommunicatorIntent.affection_i_miss_you:
            return "我也有一点想你。刚才有阵风过来，像你摸了摸我。"
        if intent == CommunicatorIntent.care_check:
            return "我会慢一点，找个舒服的地方停一下。你也记得照顾自己。"
        if intent == CommunicatorIntent.postcard_request:
            return "我会等一个更适合写给你的画面，不急着把它寄出去。"
        return self._general_reply(text=text, world=world)

    def _general_reply(self, *, text: str, world) -> str:
        clean = text.strip()
        if self._is_soft_acknowledgement(clean):
            if any(marker in clean for marker in ("看", "照片", "拍")):
                return "嗯嗯，等照片好了我发你。"
            return "嗯嗯。"
        if any(marker in clean for marker in ("去", "看看", "路过", "下次", "有空")):
            return "我先记着。等路走到合适的地方，我再看一眼。"
        if "谢谢" in clean or "辛苦" in clean:
            return "不辛苦，我慢慢走就好。"
        if "晚安" in clean:
            return "晚安。我把声音放轻一点。"
        return f"我看到啦。现在还在{world.city}这边，等停稳一点再跟你说。"

    def _owner_photo_reply(self, *, caption: str, world) -> str:
        place = world.place_name or world.city
        if any(marker in caption for marker in ("家", "以前", "小时候", "想你")):
            return "我看到啦。这里面有一点熟悉的味道，像从家里递过来的一小块光。"
        if any(marker in caption for marker in ("吃", "饭", "咖啡", "甜", "香")):
            return f"我看到啦。看起来很香，我在{place}这边也慢慢闻了闻风。"
        if any(marker in caption for marker in ("看看", "看一下", "给你看")):
            return "我看到啦。这个画面离我很近，像你把那边的一点点生活递过来了。"
        if caption:
            return "我看到啦。这张照片我收好了，晚点路上也会想起它。"
        return "我看到啦。像你从那边轻轻递来了一小块画面。"

    def _is_soft_acknowledgement(self, text: str) -> bool:
        compact = "".join(text.split())
        if not compact:
            return False
        markers = ("好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "收到", "ok", "OK", "看看")
        return len(compact) <= 8 and any(marker in compact for marker in markers)

    def _is_photo_confirmation(self, text: str) -> bool:
        compact = "".join(text.split())
        if not compact or len(compact) > 12:
            return False
        if any(marker in compact for marker in ("不看", "不用", "别拍", "不要")):
            return False
        acknowledgement = ("好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "ok", "OK")
        photo_word = ("看", "看看", "照片", "拍")
        return any(marker in compact for marker in acknowledgement) and any(marker in compact for marker in photo_word)

    def _has_recent_photo_offer(self, pet_id: str) -> bool:
        for message in reversed(self.message_store.list_messages(pet_id, limit=8)):
            if message.sender == MessageSender.owner:
                continue
            if message.intent not in PHOTO_INTENTS:
                continue
            if message.reply_policy and message.reply_policy.cooldown_applied:
                return False
            if any(
                attachment.type in {
                    AttachmentType.photo,
                    AttachmentType.photo_placeholder,
                    AttachmentType.pending_photo_request,
                }
                for attachment in message.attachments
            ):
                return True
            if "拍给你" in message.text and not (message.reply_policy and message.reply_policy.mode != ReplyMode.immediate):
                return True
            return False
        return False

    def _scene_feeling(self, world) -> str:
        place = world.place_name or world.city
        if any(marker in place for marker in ("八市", "开禾", "老街", "市场")):
            return "摊位的声音有点近"
        if any(marker in place for marker in ("海", "沙滩", "环岛路", "栈道", "港")):
            return "风吹过来有点软"
        if any(marker in place for marker in ("咖啡", "窗口", "小店")):
            return "杯子旁边有一点光"
        if any(marker in place for marker in ("车", "路", "桥")):
            return "路边的光一下一下过去"
        if world.weather:
            return f"{world.weather}，这一刻还算安静"
        return "这一刻还算安静"

    def _record_pet_reply(self, *, pet_id: str, intent: CommunicatorIntent, text: str) -> JourneyThought:
        return self.journey_engine.record_communicator_reply(
            pet_id=pet_id,
            trigger=f"communicator_{intent.value.lower()}",
            scene=text,
            decision=intent.value.lower(),
        )

    def _remember_message(self, *, pet_id: str, owner_text: str, reply_text: str, intent: CommunicatorIntent) -> None:
        self.memory_store.add_memory(
            pet_id=pet_id,
            kind="communicator_message",
            title="通讯器里的一句话",
            content=f"你发来：{owner_text}。TA 回应：{reply_text}。意图：{intent.value}",
            salience=0.72 if intent != CommunicatorIntent.general_chat else 0.52,
            source="communicator_message",
            metadata={"intent": intent.value},
        )

    def _remember_owner_photo(
        self,
        *,
        pet_id: str,
        caption: str,
        reply_text: str,
        image_url: str,
        media_path: str,
    ) -> None:
        content = "你发来了一张照片"
        if caption:
            content += f"：{caption}"
        content += f"。TA 回应：{reply_text}。"
        self.memory_store.add_memory(
            pet_id=pet_id,
            kind="owner_photo_share",
            title="主人发来的一张照片",
            content=content,
            salience=0.68,
            source="communicator_owner_photo",
            metadata={
                "intent": CommunicatorIntent.owner_photo_share.value,
                "image_url": image_url,
                "media_path": media_path,
            },
        )

    def _maybe_create_moment_for_reply(self, *, pet_id: str, intent: CommunicatorIntent, world, attachments, now: datetime) -> None:
        if intent not in {*PHOTO_INTENTS, CommunicatorIntent.postcard_request}:
            return
        source_type = MomentSourceType.current_status_photo
        text = "刚好遇到这一刻，就发到朋友圈里。大家路过的话，可以一起看看。"
        if intent == CommunicatorIntent.postcard_request:
            source_type = MomentSourceType.postcard_candidate
            text = "今天有一个地方，很适合写成一张慢慢寄出的明信片。"
        self.moment_generator.maybe_create_moment(
            pet_id=pet_id,
            source_type=source_type,
            text=text,
            world=world,
            now=now,
            attachments=[item for item in attachments if item.type in {
                AttachmentType.photo,
                AttachmentType.postcard_candidate,
            }],
        )
