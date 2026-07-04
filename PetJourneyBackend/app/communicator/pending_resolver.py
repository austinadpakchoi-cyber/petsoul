from __future__ import annotations

from datetime import datetime, timedelta

from .attachment_planner import CommunicatorAttachmentPlanner
from .message_store import CommunicatorMessageStore, new_message_id
from .moment_generator import CommunicatorMomentGenerator
from .schemas import (
    AttachmentType,
    CommunicatorIntent,
    CommunicatorMessage,
    CommunicatorWorldSnapshot,
    MessageSender,
    MomentSourceType,
    PendingPhotoRequest,
    PendingStatus,
    PetReplyState,
    ReplyMode,
    ReplyPolicy,
)


class CommunicatorPendingResolver:
    provider_name = "communicator-pending-resolver"

    def __init__(
        self,
        *,
        message_store: CommunicatorMessageStore,
        attachment_planner: CommunicatorAttachmentPlanner,
        moment_generator: CommunicatorMomentGenerator,
    ):
        self.message_store = message_store
        self.attachment_planner = attachment_planner
        self.moment_generator = moment_generator

    def resolve_due_requests(self, *, pet_id: str, world: CommunicatorWorldSnapshot, now: datetime) -> list[CommunicatorMessage]:
        fulfilled: list[CommunicatorMessage] = []
        for pending in self.message_store.list_due_pending(pet_id, now):
            if pending.expires_at <= now:
                self.message_store.update_pending(pending.model_copy(update={"status": PendingStatus.expired}))
                continue
            if not self._condition_met(pending, world):
                attempts = pending.attempt_count + 1
                status = PendingStatus.failed if attempts >= pending.max_attempts else PendingStatus.pending
                next_available = now + timedelta(minutes=20)
                self.message_store.update_pending(
                    pending.model_copy(update={
                        "attempt_count": attempts,
                        "status": status,
                        "available_after": next_available,
                    })
                )
                continue

            policy = ReplyPolicy(
                mode=ReplyMode.immediate,
                estimated_reply_seconds=4,
                visible_status="TA 终于遇到能拍给你的这一刻。",
                reason_code="pending_request_fulfilled",
            )
            attachments = self.attachment_planner.plan(
                intent=CommunicatorIntent.current_status_visual_request,
                world=world,
                policy=policy,
                now=now,
            )
            text = self._fulfilled_text(world)
            message = CommunicatorMessage(
                id=new_message_id(),
                pet_id=pet_id,
                sender=MessageSender.pet,
                text=text,
                intent=pending.intent,
                scene_hash=world.scene_hash,
                message_state=PetReplyState.sent,
                reply_policy=policy,
                attachments=attachments,
                related_message_id=pending.source_message_id,
                created_at=now,
            )
            self.message_store.add_message(message)
            self.message_store.update_pending(
                pending.model_copy(update={
                    "status": PendingStatus.fulfilled,
                    "fulfilled_message_id": message.id,
                })
            )
            self.moment_generator.maybe_create_moment(
                pet_id=pet_id,
                source_type=MomentSourceType.photo_request_fulfilled,
                text="刚好遇到这一刻，就发到朋友圈里。大家路过的话，可以一起看看。",
                world=world,
                now=now,
                attachments=[item for item in attachments if item.type == AttachmentType.photo],
                force=False,
            )
            fulfilled.append(message)
        return fulfilled

    def _condition_met(self, pending: PendingPhotoRequest, world: CommunicatorWorldSnapshot) -> bool:
        if pending.pending_type == ReplyMode.queued_until_landed:
            return not world.is_flying and world.can_generate_photo
        if pending.pending_type == ReplyMode.queued_until_morning:
            return not world.is_sleeping
        if pending.pending_type == ReplyMode.queued_until_photoable_scene:
            return world.can_generate_photo
        if pending.pending_type == ReplyMode.delayed:
            return not world.is_flying and not world.is_sleeping
        return world.can_generate_photo

    def _fulfilled_text(self, world: CommunicatorWorldSnapshot) -> str:
        place = f"{world.city}{' · ' + world.place_name if world.place_name else ''}"
        return f"我到{place}这边了。刚好能拍一张，给你看。"
