from __future__ import annotations

from datetime import datetime, timedelta

from .schemas import CommunicatorIntent, CommunicatorWorldSnapshot, ReplyMode, ReplyPolicy


PHOTO_REQUEST_COOLDOWN_SECONDS = 300
SAME_SCENE_PHOTO_COOLDOWN_SECONDS = 900
PHOTO_INTENTS = {
    CommunicatorIntent.current_status_visual_request,
    CommunicatorIntent.photo_request,
    CommunicatorIntent.confirm_pending_photo,
}


class CommunicatorReplyPolicyEngine:
    provider_name = "rule-based-communicator-reply-policy"

    def resolve(
        self,
        *,
        intent: CommunicatorIntent,
        world: CommunicatorWorldSnapshot,
        now: datetime,
        latest_photo_at: datetime | None = None,
        latest_scene_photo_at: datetime | None = None,
    ) -> ReplyPolicy:
        cooldown = self._photo_cooldown_applies(
            intent=intent,
            now=now,
            latest_photo_at=latest_photo_at,
            latest_scene_photo_at=latest_scene_photo_at,
        )
        if cooldown:
            return ReplyPolicy(
                mode=ReplyMode.no_reply_needed,
                estimated_reply_seconds=0,
                visible_status="刚刚才拍过啦，还在同一个地方。等走到新的地方再给你看。",
                reason_code="photo_request_cooldown",
                cooldown_applied=True,
            )

        if intent == CommunicatorIntent.emotional_distress:
            return ReplyPolicy(
                mode=ReplyMode.immediate,
                estimated_reply_seconds=4,
                visible_status="这句话先轻轻接住。",
                reason_code="owner_emotional_distress",
            )

        if world.is_sleeping:
            return ReplyPolicy(
                mode=ReplyMode.queued_until_morning,
                estimated_reply_seconds=8 * 60 * 60,
                visible_status="TA 现在睡着啦，醒来会看到。",
                reason_code="pet_sleeping",
            )

        if world.is_flying:
            return ReplyPolicy(
                mode=ReplyMode.queued_until_landed,
                estimated_reply_seconds=45 * 60,
                visible_status="现在信号一会儿有一会儿没有，落地后会看到。",
                reason_code="pet_flying",
            )

        if world.energy < 35:
            return ReplyPolicy(
                mode=ReplyMode.delayed if intent == CommunicatorIntent.general_chat else ReplyMode.immediate,
                estimated_reply_seconds=90,
                visible_status="TA 有点累，会轻轻回你。",
                reason_code="pet_low_energy",
            )

        if intent in PHOTO_INTENTS:
            if world.can_generate_photo:
                return ReplyPolicy(
                    mode=ReplyMode.immediate,
                    estimated_reply_seconds=8,
                    visible_status="这一刻可以拍给你。",
                    reason_code="pet_at_photoable_scene",
                )
            if world.is_in_transit:
                return ReplyPolicy(
                    mode=ReplyMode.delayed,
                    estimated_reply_seconds=180,
                    visible_status="等脚步稳一点再拍给你。",
                    reason_code="pet_in_transit",
                )
            return ReplyPolicy(
                mode=ReplyMode.queued_until_photoable_scene,
                estimated_reply_seconds=20 * 60,
                visible_status="现在还没遇到合适画面，到了能拍的地方会补给你。",
                reason_code="waiting_for_photoable_scene",
            )

        if intent == CommunicatorIntent.general_chat and world.is_in_transit:
            return ReplyPolicy(
                mode=ReplyMode.delayed,
                estimated_reply_seconds=180,
                visible_status="还在路上，可能会慢一点回你。",
                reason_code="general_chat_pet_in_transit",
            )

        return ReplyPolicy(
            mode=ReplyMode.immediate,
            estimated_reply_seconds=6,
            visible_status="收到了。",
            reason_code="default_available",
        )

    def _photo_cooldown_applies(
        self,
        *,
        intent: CommunicatorIntent,
        now: datetime,
        latest_photo_at: datetime | None,
        latest_scene_photo_at: datetime | None,
    ) -> bool:
        if intent not in {CommunicatorIntent.current_status_visual_request, CommunicatorIntent.photo_request}:
            return False
        if latest_photo_at and now - latest_photo_at < timedelta(seconds=PHOTO_REQUEST_COOLDOWN_SECONDS):
            return True
        if latest_scene_photo_at and now - latest_scene_photo_at < timedelta(seconds=SAME_SCENE_PHOTO_COOLDOWN_SECONDS):
            return True
        return False
