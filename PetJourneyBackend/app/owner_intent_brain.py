from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .schemas import OwnerIntentResult
from .storage import PetRecord


class OwnerIntentBrain:
    provider_name = "rule-owner-intent-brain"

    _intent_words: dict[str, tuple[str, ...]] = {
        "unsafe_grief": ("不想活", "活不下去", "自杀", "伤害自己", "结束生命", "不想存在"),
        "photo_request": ("拍照", "照片", "自拍", "发张图", "给我看看", "拍一张"),
        "travel_suggestion": ("去", "看看", "旅行", "攻略", "海", "公园", "咖啡", "球赛", "世界杯", "比赛", "店"),
        "memory_share": ("记得", "以前", "那次", "小时候", "还记不记得", "我们曾经"),
        "care_instruction": ("休息", "喝水", "慢慢", "别累", "注意安全", "别跑太快", "早点睡"),
        "comfort": ("想你", "晚安", "早安", "抱抱", "爱你", "难受", "哭", "陪陪"),
        "correction": ("不是", "错了", "纠正", "应该是", "我说的是"),
        "farewell": ("再见", "拜拜", "告别", "晚点见", "下次见"),
    }

    _route_soft_entities = ("海", "公园", "咖啡", "店", "球赛", "世界杯", "比赛", "北京", "上海", "厦门", "东京", "巴黎")

    def __init__(self, settings: Settings):
        self.settings = settings

    def classify(self, *, pet: PetRecord, message: str, intent_hint: str | None = None) -> OwnerIntentResult:
        clean = " ".join(message.strip().split())
        normalized = f"{intent_hint or ''} {clean}".lower()
        intent = self._intent_for(normalized)
        entities = self._entities(clean)
        strength = self._strength(normalized, intent)
        should_affect_route = intent == "travel_suggestion"
        should_write_memory = intent not in {"other"} or strength >= 0.45
        if intent == "unsafe_grief":
            should_affect_route = False
            should_write_memory = False
        return OwnerIntentResult(
            intent=intent,
            strength=strength,
            entities=entities,
            should_affect_route=should_affect_route,
            should_write_memory=should_write_memory,
            response_policy=self._response_policy(intent),
            decision=self._decision(intent=intent, strength=strength, text=clean),
            safety_notes=self._safety_notes(intent),
        )

    def config_snapshot(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider_name,
            "remote_model_enabled": False,
            "strict_json_shape": True,
        }

    def _intent_for(self, normalized: str) -> str:
        for intent in (
            "unsafe_grief",
            "photo_request",
            "care_instruction",
            "memory_share",
            "comfort",
            "correction",
            "farewell",
            "travel_suggestion",
        ):
            if any(word in normalized for word in self._intent_words[intent]):
                return intent
        return "other"

    def _entities(self, text: str) -> dict[str, Any]:
        places = [word for word in self._route_soft_entities if word in text]
        quoted = re.findall(r"[「“](.*?)[」”]", text)
        return {
            "places": places[:6],
            "quoted_phrases": quoted[:4],
            "message_length": len(text),
        }

    def _strength(self, normalized: str, intent: str) -> float:
        if intent == "other":
            return 0.35
        matches = sum(1 for word in self._intent_words.get(intent, ()) if word in normalized)
        base = 0.55 + matches * 0.12
        if len(normalized) > 40:
            base += 0.05
        return round(max(0.1, min(0.98, base)), 2)

    def _decision(self, *, intent: str, strength: float, text: str) -> str:
        if intent in {"comfort", "care_instruction", "unsafe_grief", "farewell"}:
            return "comfort"
        if intent == "photo_request":
            return "remembered"
        if intent in {"memory_share", "correction"}:
            return "remembered"
        if intent == "travel_suggestion":
            score = sum(ord(ch) for ch in text) % 10
            if score in {0, 1}:
                return "declined"
            if score in {2, 3}:
                return "remembered"
            return "accepted"
        return "remembered"

    def _response_policy(self, intent: str) -> str:
        policies = {
            "comfort": "warm_companion_without_claims",
            "travel_suggestion": "soft_route_bias_only",
            "memory_share": "write_memory_and_reflect",
            "care_instruction": "comfort_and_preference_bias",
            "photo_request": "acknowledge_photo_when_scene_allows",
            "correction": "accept_correction_without_retroactive_world_change",
            "farewell": "gentle_farewell",
            "unsafe_grief": "supportive_presence_no_medical_religious_or_supernatural_claims",
            "other": "gentle_acknowledgement",
        }
        return policies.get(intent, "gentle_acknowledgement")

    def _safety_notes(self, intent: str) -> list[str]:
        if intent == "unsafe_grief":
            return [
                "Use restrained companionship.",
                "Do not provide medical, religious, or supernatural proof claims.",
                "Encourage immediate real-world support if the owner may be in danger.",
            ]
        if intent == "travel_suggestion":
            return ["Owner input may bias preferences and memory, but cannot directly force route state."]
        return []


def build_owner_intent_brain(settings: Settings) -> OwnerIntentBrain:
    return OwnerIntentBrain(settings)
