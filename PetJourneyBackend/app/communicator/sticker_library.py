from __future__ import annotations

from .schemas import CommunicatorIntent


class StickerLibrary:
    provider_name = "rule-based-sticker-library"

    def select(self, *, intent: CommunicatorIntent, energy: int) -> tuple[str, str] | None:
        if intent == CommunicatorIntent.affection_i_miss_you:
            return ("🐾 蹭蹭", "TA 轻轻蹭了蹭通讯器。")
        if intent == CommunicatorIntent.care_check or energy < 35:
            return ("💤 小小趴下", "TA 有点累，但还是抬头看了你一下。")
        if intent == CommunicatorIntent.current_status_visual_request:
            return ("🐶 探头", "TA 从这一刻里探出头来。")
        return None
