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
            # 确认已存在的拍照承诺：回复本身已承载，不再挂卡（≤2 块上限）
            return attachments

        if intent in PHOTO_INTENTS:
            if policy.cooldown_applied:
                # 正文（visible_status）已经说了「刚刚才拍过」，不再挂同义卡
                return attachments
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
                        # 话语由气泡（visible_status）承载，卡不重复同一句话
                        text="",
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
                        text="",
                        state=AttachmentState.planned,
                        location=world.location,
                        metadata={"scene_hash": world.scene_hash},
                    )
                )
            # 位置卡只在用户明确问位置（location_check）时出现，避免三块堆叠
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
        # 「城市 · 地点」去重：地点名已含城市名（如「洛杉矶国际机场」）时不重复前缀
        place_name = world.place_name or ""
        if world.city and world.city not in place_name:
            place = f"{world.city} · {place_name}" if place_name else world.city
        else:
            place = place_name or world.city
        # 气象串不进对话：结构化数值留给地图/状态区，卡上只留 TA 能说出口的体感
        feeling = pet_voice_weather(world.weather)
        text = f"{place}。{feeling}" if feeling else place
        return CommunicatorAttachment(
            type=AttachmentType.location_card,
            title="TA 此刻的位置",
            text=text,
            state=AttachmentState.ready,
            location=world.location,
            metadata={"scene_hash": world.scene_hash},
        )


def pet_voice_weather(weather: str) -> str | None:
    """把气象串转成宠物能说出口的第一人称体感（UI/UX 审计 P1-2）。

    报体感、不报数值：结构化气象（温度/湿度/风力）只用于地图与状态区，
    对话里只出现 TA 的感知。识别不了的天气给一句不暴露机制的兜底。
    """
    text = weather or ""
    if not text.strip():
        return None
    if any(marker in text for marker in ("雨", "rain", "storm")):
        return "外面在下雨，我找了个能躲雨的地方"
    if any(marker in text for marker in ("雪", "snow")):
        return "外面飘着雪，我走得慢了一点"
    if any(marker in text for marker in ("风", "wind")):
        return "风有点大，耳朵一直轻轻动"
    if any(marker in text for marker in ("多云", "cloud")):
        return "云很多，光线软软的"
    if any(marker in text for marker in ("晴", "sun")):
        return "太阳很好，晒得暖暖的"
    if any(marker in text for marker in ("雾", "fog")):
        return "雾有点浓，我走得更小心了"
    return "天气刚刚好，不冷不热"
