"""主人交互编排：主人讯息的意图理解、回应决策与手机侧回复落库。"""

from __future__ import annotations

from ..schemas import (
    JourneyThought,
    OwnerIntentResult,
    OwnerMessageResponse,
)
from ..storage import PetRecord, utcnow


class OwnerInteractionMixin:
    def owner_message(self, pet_id: str, message: str, intent_hint: str | None = None) -> OwnerMessageResponse:
        trace_started = utcnow()
        steps: list = []
        pet = self._pet(pet_id)
        cleaned = " ".join(message.strip().split())
        if not cleaned:
            raise ValueError("empty owner message")
        try:
            now = utcnow()
            city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
            owner_intent = self.owner_intent_brain.classify(pet=pet, message=cleaned, intent_hint=intent_hint)
            decision = owner_intent.decision or self._owner_message_decision(cleaned, intent_hint=intent_hint)
            steps.append(
                self._trace_step(
                    "owner_intent",
                    inputs={"intent_hint": intent_hint or ""},
                    outputs=owner_intent.model_dump(mode="json"),
                    fallback="rule_owner_intent" if self.owner_intent_brain.provider_name.startswith("rule") else None,
                )
            )
            scene = self._owner_message_scene(pet, cleaned, decision, owner_intent=owner_intent)
            steps.append(
                self._trace_step(
                    "action_validation",
                    outputs={
                        "should_affect_route": owner_intent.should_affect_route,
                        "route_forced": False,
                        "decision": decision,
                    },
                )
            )
            self._append_agent_thought(
                pet=pet,
                city=city,
                trigger=f"owner_message_{decision}",
                scene=scene,
                status=self._status_for(now),
                timestamp=now,
            )
            steps.append(self._trace_step("agent_speech", outputs={"response_policy": owner_intent.response_policy}))
            self.storage.append_event(
                pet.pet_id,
                self._owner_message_event_title(decision),
                self._owner_message_event_detail(pet=pet, message=cleaned, decision=decision),
                timestamp=now,
            )
            if owner_intent.should_write_memory:
                self._remember_owner_message(
                    pet=pet,
                    message=cleaned,
                    decision=decision,
                    scene=scene,
                    city=city.name,
                    owner_intent=owner_intent,
                )
                steps.append(self._trace_step("memory_write", outputs={"kind": "owner_message", "intent": owner_intent.intent}))
            else:
                steps.append(self._trace_step("memory_write", status="skipped", outputs={"reason": owner_intent.response_policy}))
            latest = self.storage.list_thoughts(pet.pet_id, limit=1)[-1]
            response = OwnerMessageResponse(
                success=True,
                decision=decision,
                message=scene,
                thought=JourneyThought.model_validate(latest),
                updated_status=self.status(pet.pet_id),
                owner_intent=owner_intent,
            )
            self._save_trace(
                pet_id=pet.pet_id,
                operation="owner_message",
                started_at=trace_started,
                steps=steps,
                state_after={"decision": decision, "intent": owner_intent.intent, "should_affect_route": owner_intent.should_affect_route},
            )
            return response
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="owner_message", started_at=trace_started, steps=steps, error=exc)
            raise

    def record_communicator_reply(
        self,
        *,
        pet_id: str,
        trigger: str,
        scene: str,
        decision: str,
    ) -> JourneyThought:
        pet = self._pet(pet_id)
        now = utcnow()
        city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger=trigger,
            scene=scene,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 在手机里回应了你",
            scene,
            timestamp=now,
        )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="communicator_reply",
            title="手机回应",
            content=f"TA 在手机里回应：{scene}。决策：{decision}",
            salience=0.64,
            source="communicator_reply",
            metadata={"decision": decision},
        )
        latest = self.storage.list_thoughts(pet.pet_id, limit=1)[-1]
        return JourneyThought.model_validate(latest)

    def _owner_message_decision(self, message: str, intent_hint: str | None = None) -> str:
        normalized = f"{intent_hint or ''} {message}".lower()
        travel_words = ("去", "看看", "想去", "咖啡", "海", "公园", "店", "球赛", "世界杯", "比赛", "攻略")
        care_words = ("想你", "晚安", "早安", "抱抱", "注意", "休息", "爱你")
        if any(word in normalized for word in care_words):
            return "comfort"
        if any(word in normalized for word in travel_words):
            score = sum(ord(ch) for ch in message) % 10
            if score in {0, 1, 2}:
                return "declined"
            if score in {3, 4}:
                return "remembered"
            return "accepted"
        return "remembered"

    def _owner_message_scene(
        self,
        pet: PetRecord,
        message: str,
        decision: str,
        owner_intent: OwnerIntentResult | None = None,
    ) -> str:
        owner = self._owner_reference(pet.dna.owner_title)
        if owner_intent and owner_intent.intent == "unsafe_grief":
            return (
                f"我听见{owner}说「{message}」。我会在这里陪你一小会儿，但我不是医生，也不能证明另一个世界。"
                "如果你现在可能伤害自己，请立刻联系身边可信的人或当地紧急电话。你不需要一个人扛过这一刻。"
            )
        if owner_intent and owner_intent.intent == "photo_request":
            return f"我听见{owner}说「{message}」。等当前位置适合拍照时，我会把这一刻发给你；路线还是按真实时间慢慢走。"
        if owner_intent and owner_intent.intent == "care_instruction":
            return f"我听见{owner}说「{message}」。我会把这句话当成小包里的叮嘱，累的时候慢一点，但不会突然改路。"
        if owner_intent and owner_intent.intent == "memory_share":
            return f"我听见{owner}说「{message}」。这段旧记忆我收好了，之后遇到相似的光和地方会更容易想起。"
        if decision == "accepted":
            return f"我听见{owner}说「{message}」。这句话我收好了，等路线和天气合适时，我自己靠近看看。"
        if decision == "declined":
            return f"我听见{owner}说「{message}」。今天我先不往那里走，我想按自己的节奏把眼前这段路走完。"
        if decision == "comfort":
            return f"我听见{owner}说「{message}」。这句话我收好了，像把一小块暖光放进手机里。"
        return f"我听见{owner}说「{message}」。我先记住它，不急着决定，下一段路我自己慢慢判断。"

    def _owner_message_event_title(self, decision: str) -> str:
        titles = {
            "accepted": "TA 收到一个旅行建议",
            "declined": "TA 温柔地保留了自己的路线",
            "comfort": "TA 收到了你的想念",
            "remembered": "TA 先记住了你的想法",
        }
        return titles.get(decision, "TA 收到一条讯息")

    def _owner_message_event_detail(self, *, pet: PetRecord, message: str, decision: str) -> str:
        response = {
            "accepted": "我会把这句建议先放进口袋里，等路线和天气合适时自己靠近看看。",
            "declined": "我先把这句话收好，但今天还是想按自己的节奏走完眼前这段路。",
            "comfort": "我把这句话收好了，像把一小块暖光放进手机里。",
            "remembered": "我先记住它，不急着决定，下一段路我会自己慢慢判断。",
        }.get(decision, "我收到了，会按自己的节奏慢慢回应。")
        return f"你发来：「{message}」。{response}"

    def _owner_reference(self, owner_title: str | None) -> str:
        clean = " ".join((owner_title or "").strip().split())
        if not clean:
            return "你"
        if clean in {"宝宝", "宝贝", "儿子", "女儿", "毛孩子", "家人", "朋友"}:
            return "你"
        return clean
