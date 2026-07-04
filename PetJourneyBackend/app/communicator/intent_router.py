from __future__ import annotations

from .keyword_triggers import match_keyword_intent
from .schemas import CommunicatorIntent


class CommunicatorIntentRouter:
    provider_name = "rule-based-communicator-intent-router"

    def route(self, text: str) -> CommunicatorIntent:
        matched = match_keyword_intent(text)
        if matched is not None:
            return matched

        clean = text.strip()
        if any(word in clean for word in ("那边", "那里", "过得怎么样", "看一眼")):
            return CommunicatorIntent.current_status_visual_request
        if any(word in clean for word in ("海", "咖啡", "公园", "去", "看看")):
            return CommunicatorIntent.general_chat
        return CommunicatorIntent.general_chat

