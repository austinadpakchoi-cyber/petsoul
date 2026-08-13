"""记忆记录：`_remember_*` 系列——把关键事件安全写入记忆库。

这些方法被生命周期、旅行、经济、照片、主人交互等多个场景复用，统一在此，
底层都走 `_remember_safely`（吞掉记忆写入异常，不打断主流程）。
"""

from __future__ import annotations

from ..schemas import (
    OwnerIntentResult,
    PhotoMission,
    Postcard,
    SouvenirItem,
    TravelBag,
    TravelBagItem,
    TravelQuest,
)
from ..storage import PetRecord


class MemoryRecordingMixin:
    def _remember_identity(self, pet: PetRecord) -> None:
        content = (
            f"{pet.name} 是一只 {pet.pet_type.value}。主人称呼：{pet.dna.owner_title}。"
            f"性格：{pet.dna.personality}。喜欢的地方：{', '.join(pet.dna.favorite_places)}。"
            f"爱做的事：{', '.join(pet.dna.hobby)}。常被记住的一句话：{pet.dna.catchphrase}。"
            f"声音风格：{pet.dna.voice_style}。"
        )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="identity",
            title=f"{pet.name} 的通讯 DNA",
            content=content,
            salience=0.95,
            source="onboarding",
            metadata={"pet_type": pet.pet_type.value, "photo_path": pet.photo_path or ""},
            memory_type="relationship",
            importance=0.96,
            emotional_valence=0.38,
            confidence=0.98,
            structured_payload={"favorite_places": pet.dna.favorite_places, "hobby": pet.dna.hobby},
        )

    def _remember_travel_bag(self, *, pet: PetRecord, bag: TravelBag, new_items: list[TravelBagItem]) -> None:
        if new_items:
            item_text = "、".join(
                f"{item.title}（{item.item_type.value}）" for item in new_items
            )
        else:
            item_text = "你留了一句路上的叮嘱"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="travel_bag",
            title=f"{pet.name} 的旅行小包",
            content=(
                f"你给 {pet.name} 准备了：{item_text}。"
                f"这些物品只影响旅途倾向和情绪，不直接控制目的地。"
                f"小包提示：{bag.pet_visible_note}"
            ),
            salience=0.84,
            source="travel_bag",
            metadata={
                "quest_id": bag.quest_id or "",
                "bag_id": bag.id,
                "item_count": len(bag.items),
                "influence_tags": [tag for item in bag.items for tag in item.influence_tags],
            },
            memory_type="preference",
            importance=0.84,
            emotional_valence=0.34,
            confidence=0.86,
            structured_payload={
                "quest_id": bag.quest_id or "",
                "influence_tags": [tag for item in bag.items for tag in item.influence_tags],
                "soft_influence_only": True,
            },
        )

    def _remember_souvenir(self, *, pet: PetRecord, souvenir: SouvenirItem) -> None:
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="souvenir",
            title=souvenir.title,
            content=(
                f"{pet.name} 从 {souvenir.city} · {souvenir.place_name} 带回 {souvenir.title}。"
                f"故事：{souvenir.story}。TA 的话：{souvenir.pet_voice}"
            ),
            salience=0.82 if souvenir.rarity == "common" else 0.9,
            source="souvenir",
            metadata={
                "souvenir_id": souvenir.id,
                "quest_id": souvenir.quest_id or "",
                "item_type": souvenir.item_type.value,
                "city": souvenir.city,
                "place_name": souvenir.place_name,
                "rarity": souvenir.rarity,
                "bag_influence_tags": souvenir.bag_influence_tags,
            },
            memory_type="souvenir",
            importance=0.82 if souvenir.rarity == "common" else 0.9,
            emotional_valence=0.48,
            confidence=0.85,
            source_event_id=souvenir.source_photo_mission_id,
            structured_payload={
                "souvenir_id": souvenir.id,
                "quest_id": souvenir.quest_id or "",
                "city": souvenir.city,
                "place_name": souvenir.place_name,
                "bag_influence_tags": souvenir.bag_influence_tags,
            },
        )

    def _remember_feedback(self, pet: PetRecord, city: str, liked: bool, message: str) -> None:
        owner_signal = "收藏了这个攻略方向" if liked else "暂时略过了这个攻略方向"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="owner_preference",
            title=f"{city} 的主人反馈",
            content=(
                f"你{owner_signal}。这只是你的旅行参考偏好，"
                f"不会直接决定 {pet.name} 对地点的感受。系统反馈：{message}"
            ),
            salience=0.72,
            source="feedback",
            metadata={"city": city, "liked": liked},
            memory_type="preference",
            importance=0.72,
            emotional_valence=0.28 if liked else -0.08,
            confidence=0.78,
            structured_payload={"city": city, "liked": liked, "soft_route_bias_only": True},
        )

    def _remember_postcard(self, pet: PetRecord, postcard: Postcard, mission: PhotoMission | None = None) -> None:
        metadata: dict[str, object] = {"postcard_id": postcard.id, "image_url": postcard.image_url or ""}
        if mission:
            metadata.update(
                {
                    "photo_mission_id": mission.id,
                    "scene_anchor": mission.scene_anchor,
                    "camera_perspective": mission.camera_perspective.value,
                    "interaction_type": mission.interaction.interaction_type,
                }
            )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="postcard",
            title=f"{postcard.location} 的自拍/明信片",
            content=f"{pet.name} 从 {postcard.location} 发来内容：{postcard.text}",
            salience=0.86,
            source="postcard",
            metadata=metadata,
            memory_type="recent_episodic",
            importance=0.86,
            emotional_valence=0.42,
            confidence=0.82,
            source_event_id=mission.id if mission else None,
            structured_payload=metadata,
        )

    def _remember_safely(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.memory_store.add_memory(
                pet_id=pet_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )
        except Exception:
            return

    def _remember_owner_message(
        self,
        *,
        pet: PetRecord,
        message: str,
        decision: str,
        scene: str,
        city: str,
        owner_intent: OwnerIntentResult | None = None,
    ) -> None:
        memory_type = "owner_intent"
        importance = 0.78 if decision in {"accepted", "comfort"} else 0.66
        emotional_valence = 0.25 if decision in {"accepted", "comfort"} else 0.05
        if owner_intent and owner_intent.intent in {"comfort", "care_instruction", "memory_share"}:
            memory_type = "relationship"
            emotional_valence = 0.42
        elif owner_intent and owner_intent.intent == "travel_suggestion":
            memory_type = "preference"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="owner_message",
            title="你的讯息",
            content=(
                f"你发来：{message}。当前城市：{city}。{pet.name} 的回应：{scene}。"
                f"自主回应状态：{decision}"
            ),
            salience=importance,
            source="owner_message",
            metadata={"decision": decision, "city": city, "intent": owner_intent.intent if owner_intent else ""},
            memory_type=memory_type,
            importance=importance,
            emotional_valence=emotional_valence,
            confidence=owner_intent.strength if owner_intent else 0.75,
            structured_payload=owner_intent.model_dump(mode="json") if owner_intent else {},
        )

    def _remember_travel_quest(self, *, pet: PetRecord, quest: TravelQuest, city: str) -> None:
        guide_title = quest.guide.title if quest.guide else f"去 {quest.destination} 的攻略"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="travel_quest",
            title=guide_title,
            content=(
                f"你提出：{quest.owner_message}。"
                f"{pet.name} 的决定：{quest.autonomy_decision}。"
                f"当前阶段：{quest.current_phase_message}。"
                f"目的地：{quest.destination}。"
            ),
            salience=0.88,
            source="travel_quest",
            metadata={
                "quest_id": quest.id,
                "status": quest.status.value,
                "quest_type": quest.quest_type.value,
                "city": city,
            },
            memory_type="preference",
            importance=0.88,
            emotional_valence=0.32,
            confidence=0.82,
            structured_payload={
                "quest_id": quest.id,
                "destination": quest.destination,
                "status": quest.status.value,
                "soft_influence_only": True,
            },
        )
