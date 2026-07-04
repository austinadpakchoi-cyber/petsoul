from __future__ import annotations

from datetime import datetime, timedelta

from .schemas import (
    AttachmentState,
    AttachmentType,
    CommunicatorAttachment,
    CommunicatorIntent,
    CommunicatorWorldSnapshot,
    ReplyMode,
    ReplyPolicy,
)
from .sticker_library import StickerLibrary

PHOTO_INTENTS = {
    CommunicatorIntent.current_status_visual_request,
    CommunicatorIntent.photo_request,
    CommunicatorIntent.confirm_pending_photo,
}


class CommunicatorAttachmentPlanner:
    provider_name = "rule-based-communicator-attachment-planner"

    def __init__(self, sticker_library: StickerLibrary | None = None):
        self.sticker_library = sticker_library or StickerLibrary()

    def plan(
        self,
        *,
        intent: CommunicatorIntent,
        world: CommunicatorWorldSnapshot,
        policy: ReplyPolicy,
        now: datetime,
        photo_mission_id: str | None = None,
    ) -> list[CommunicatorAttachment]:
        attachments: list[CommunicatorAttachment] = []

        if intent == CommunicatorIntent.location_check:
            attachments.append(self._location_card(world))
            return attachments

        if intent == CommunicatorIntent.postcard_request:
            attachments.append(
                CommunicatorAttachment(
                    type=AttachmentType.postcard_candidate,
                    title="明信片在路上",
                    text="TA 会等一个更适合写给你的画面，不把这件事做得太匆忙。",
                    state=AttachmentState.planned,
                    location=world.location,
                    available_after=now + timedelta(hours=2),
                    metadata={"scene_hash": world.scene_hash},
                )
            )
            return attachments

        if intent == CommunicatorIntent.confirm_pending_photo:
            attachments.append(self._location_card(world))
            return attachments

        if intent in PHOTO_INTENTS:
            if policy.cooldown_applied:
                attachments.append(
                    CommunicatorAttachment(
                        type=AttachmentType.photo_status_card,
                        title="刚刚才拍过",
                        text="TA 还在同一个地方，等走到新的地方再拍给你。",
                        state=AttachmentState.planned,
                        location=world.location,
                        metadata={"scene_hash": world.scene_hash},
                    )
                )
            elif policy.mode == ReplyMode.immediate and world.can_generate_photo:
                attachments.append(
                    CommunicatorAttachment(
                        type=AttachmentType.photo_placeholder,
                        title="正在拍给你",
                        text=f"TA 现在在{world.city}{' · ' + world.place_name if world.place_name else ''}，画面准备好后会发来。",
                        state=AttachmentState.placeholder,
                        location=world.location,
                        photo_mission_id=photo_mission_id,
                        available_after=now + timedelta(seconds=max(20, policy.estimated_reply_seconds)),
                        metadata={"scene_hash": world.scene_hash},
                    )
                )
            elif policy.mode in {
                ReplyMode.queued_until_landed,
                ReplyMode.queued_until_morning,
                ReplyMode.queued_until_photoable_scene,
                ReplyMode.delayed,
            }:
                attachments.append(
                    CommunicatorAttachment(
                        type=AttachmentType.pending_photo_request,
                        title="晚点拍给你",
                        text=policy.visible_status,
                        state=AttachmentState.planned,
                        location=world.location,
                        available_after=now + timedelta(seconds=max(60, policy.estimated_reply_seconds)),
                        metadata={"scene_hash": world.scene_hash},
                    )
                )
            else:
                attachments.append(
                    CommunicatorAttachment(
                        type=AttachmentType.photo_status_card,
                        title="现在不方便拍",
                        text=policy.visible_status,
                        state=AttachmentState.planned,
                        location=world.location,
                        metadata={"scene_hash": world.scene_hash},
                    )
                )
            attachments.append(self._location_card(world))
            return attachments

        sticker = self.sticker_library.select(intent=intent, energy=world.energy)
        if sticker:
            label, text = sticker
            attachments.append(
                CommunicatorAttachment(
                    type=AttachmentType.sticker,
                    title=label,
                    text=text,
                    state=AttachmentState.ready,
                    metadata={"sticker_id": label},
                )
            )
        return attachments

    def _location_card(self, world: CommunicatorWorldSnapshot) -> CommunicatorAttachment:
        place = f"{world.city}{' · ' + world.place_name if world.place_name else ''}"
        return CommunicatorAttachment(
            type=AttachmentType.location_card,
            title="TA 此刻的位置",
            text=f"{place}。{world.weather}",
            state=AttachmentState.ready,
            location=world.location,
            metadata={"scene_hash": world.scene_hash},
        )
