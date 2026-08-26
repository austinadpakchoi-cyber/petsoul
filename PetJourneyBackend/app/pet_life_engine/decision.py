"""宠物生活模拟决策 mixin：行动校验、可见文案、动画与节奏。"""

from __future__ import annotations

from datetime import datetime
from math import cos, pi, sqrt

from ..meal_rules import is_place_plausible_at
from ..schemas import (
    GameMasterDecision,
    JourneyPlan,
    MemoryRecord,
    PetIntent,
    PetNeedState,
    PetVisibleThought,
    PlaceSignal,
    TravelMode,
    WorldAction,
    WorldActivity,
)
from ..species import species_vocalization
from ..storage import PetRecord


class PetLifeDecisionMixin:
    def _resolve_action(
        self,
        *,
        action: WorldAction,
        activity: WorldActivity,
        plan: JourneyPlan,
        now: datetime | None = None,
    ) -> GameMasterDecision:
        blocked: list[str] = []
        if not self._valid_coordinate(action.lat, action.lng):
            blocked.append("invalid_coordinate")
        if action.mode == TravelMode.flight and action.duration_minutes < 30:
            blocked.append("flight_duration_too_short")
        if action.mode in {TravelMode.walk, TravelMode.drive, TravelMode.transit} and not self._close_to_known_world(action, activity, plan):
            blocked.append("action_not_attached_to_route_or_place")
        if action.action_type == "capture_memory" and not action.photo_opportunity:
            blocked.append("photo_without_scene_anchor")
        if (
            now is not None
            and action.action_type in {"snack_or_coffee", "eat_nearby"}
            and action.place_name
            and not is_place_plausible_at(now, action.place_name)
        ):
            blocked.append("meal_time_implausible")

        if blocked:
            return GameMasterDecision(
                allowed=False,
                reason="世界规则层调整了这次行动，避免出现漂在海上、瞬移或没有场景锚点的事件。",
                adjusted=True,
                blocked_reasons=blocked,
                safety_notes=[
                    "GameMasterResolver borrowed from Concordia-style separation: agent proposes, world validates.",
                    "Adjusted actions stay attached to current activity coordinates.",
                ],
            )
        return GameMasterDecision(
            allowed=True,
            reason="行动落在当前世界状态和路线约束内，可以展示给用户。",
            adjusted=False,
            safety_notes=[
                "用户看到的是世界模拟结果，不是直接控制命令。",
                "照片生成会继续经过 PhotoMission 安全提示词。",
            ],
        )
    def _adjusted_action(self, *, action: WorldAction, activity: WorldActivity) -> WorldAction:
        return action.model_copy(
            update={
                "lat": activity.lat,
                "lng": activity.lng,
                "place_name": activity.place_name,
                "mode": activity.mode or TravelMode.stay,
                "detail": f"{action.detail} 通讯器把位置校准回当前真实活动点。",
            }
        )
    def _nearby_places(self, activity: WorldActivity, places: list[PlaceSignal]) -> list[PlaceSignal]:
        ranked = sorted(
            places,
            key=lambda place: self._distance_meters((activity.lat, activity.lng), (place.lat, place.lng)),
        )
        return ranked[:6]
    def _place_for_intent(self, intent: PetIntent, plan: JourneyPlan) -> PlaceSignal | None:
        if not intent.suggested_place_name:
            return None
        return next((place for place in plan.places if place.name == intent.suggested_place_name), None)
    def _close_to_known_world(self, action: WorldAction, activity: WorldActivity, plan: JourneyPlan) -> bool:
        if self._distance_meters((action.lat, action.lng), (activity.lat, activity.lng)) <= 550:
            return True
        for stop in plan.stops:
            if self._distance_meters((action.lat, action.lng), (stop.lat, stop.lng)) <= 550:
                return True
        for place in plan.places:
            if self._distance_meters((action.lat, action.lng), (place.lat, place.lng)) <= 550:
                return True
        return False
    def _action_detail(self, *, intent: PetIntent, activity: WorldActivity, plan: JourneyPlan) -> str:
        place = intent.suggested_place_name or activity.place_name or activity.city
        if intent.kind == "continue_transport":
            return f"我会继续沿着这段路前进，下一站是 {activity.next_place_name or place}。"
        if intent.kind == "rest_nearby":
            return f"我会先去 {place} 附近安静歇一会儿，醒来以后再继续往前。"
        if intent.kind == "drink_nearby":
            return f"我会先在 {place} 找点喝的，补一点水，也看看店里今天有什么特别的味道。"
        if intent.kind == "eat_nearby":
            return f"我会进 {place} 看看菜单，选一份这个地方有代表性的味道。"
        if intent.kind == "quiet_nearby":
            return f"我会换到 {place} 附近更安静的位置，把耳朵和脚步都放松下来。"
        if intent.kind == "capture_memory":
            return f"我在 {place} 找到了可以入镜的光，想把这一刻拍下来。"
        if intent.kind == "snack_or_coffee":
            return f"我会在 {place} 里面坐一会儿，看菜单，也看看店里的人点了什么，再选一个有代表性的味道。"
        if intent.kind == "play":
            return f"我会在 {place} 待久一点，看看屏幕光，也让脚步慢下来。"
        if intent.kind == "memory_followup":
            return f"我会带着一点旧记忆走，但还是按 {plan.city} 的真实地点和交通慢慢推进。"
        return f"我会在 {place} 观察一会儿，再自己决定下一步。"
    def _owner_visible_summary(
        self,
        *,
        pet: PetRecord,
        action: WorldAction,
        decision: GameMasterDecision,
        activity: WorldActivity,
    ) -> str:
        place = action.place_name or activity.place_name or activity.city
        prefix = "TA 正在"
        if action.action_type == "rest_nearby":
            return f"{prefix}{place}安静休息，通讯器会把声音放轻。"
        if action.action_type == "drink_nearby":
            return f"{prefix}{place}找点喝的，补一补水再继续走。"
        if action.action_type == "eat_nearby":
            return f"{prefix}{place}看菜单，选一份本地味道。"
        if action.action_type == "quiet_nearby":
            return f"{prefix}{place}换到更安静的位置。"
        if action.action_type == "snack_or_coffee":
            return f"{prefix}{place}里面看菜单，等一份店里的特色味道。"
        if action.action_type == "play":
            return f"{prefix}{place}的屏幕光里玩一会儿。"
        if action.action_type == "capture_memory":
            return f"{prefix}{place}慢慢看着周围，像是想把这一刻留下。"
        if action.action_type == "continue_transport":
            return activity.detail or f"{pet.name} 正在前往下一站。"
        if decision.adjusted:
            return f"通讯器把 {pet.name} 的位置校准回真实路线，TA 继续慢慢生活。"
        return f"{prefix}{place}观察附近的声音和气味。"
    def _visible_thought(
        self,
        *,
        pet: PetRecord,
        intent: PetIntent,
        action: WorldAction,
        activity: WorldActivity,
        memories: list[MemoryRecord],
        owner_signal: str | None,
    ) -> PetVisibleThought:
        place = action.place_name or activity.place_name or activity.city
        next_place = activity.next_place_name or intent.suggested_place_name or place
        current_inner_voice = self._inner_voice_for_action(pet=pet, action=action, place=place)
        next_intention = self._next_intention_for_action(action=action, activity=activity, next_place=next_place)
        reason = self._visible_reason_for_intent(intent=intent, action=action, activity=activity, memories=memories)
        return PetVisibleThought(
            current_inner_voice=current_inner_voice,
            next_intention=next_intention,
            reason=reason,
            time_window=self._time_window_for_action(action),
            confidence=round(max(0.1, min(0.98, intent.confidence)), 2),
            owner_message_echo=self._owner_message_echo(owner_signal=owner_signal, memories=memories),
        )
    def _inner_voice_for_action(self, *, pet: PetRecord, action: WorldAction, place: str) -> str:
        if action.action_type == "continue_transport":
            return "我还在路上，会稳稳把这一段走完。"
        if action.action_type == "rest_nearby":
            return f"我想先在 {place} 安静睡一会儿，醒来以后再继续。"
        if action.action_type == "drink_nearby":
            return f"我有点渴了，先在 {place} 找点喝的。"
        if action.action_type == "eat_nearby":
            return f"我饿了，想认真看看 {place} 的菜单和味道。"
        if action.action_type == "quiet_nearby":
            return f"这里声音有点满，我会去 {place} 放松一下。"
        if action.action_type == "capture_memory":
            return "这里的光和气味很清楚，我想再多看一会儿。"
        if action.action_type == "snack_or_coffee":
            return f"{place} 附近有热乎乎的味道，我想认真确认一下。"
        if action.action_type == "play":
            return "屏幕光很安静，我想在这里陪人待一会儿。"
        if action.action_type == "memory_followup":
            return "我想起了一点旧记忆，会把脚步放慢。"
        return "我正在听附近的声音，先不急着走。"
    def _next_intention_for_action(self, *, action: WorldAction, activity: WorldActivity, next_place: str) -> str:
        if action.action_type == "continue_transport":
            return f"我会继续靠近 {next_place}。"
        if action.action_type == "rest_nearby":
            return f"我会先在 {next_place} 休息，醒来后再决定下一步。"
        if action.action_type == "drink_nearby":
            return f"我会先在 {next_place} 喝点东西，再继续小旅程。"
        if action.action_type == "eat_nearby":
            return f"我会先在 {next_place} 吃一点本地味道。"
        if action.action_type == "quiet_nearby":
            return f"我会在 {next_place} 放慢一点。"
        if action.photo_opportunity:
            return "如果这一刻值得留下，我会自己拍下来。"
        if action.action_type == "snack_or_coffee":
            return f"我会在 {next_place} 附近多停一会儿。"
        if action.action_type == "play":
            return "我会把这段停留拉长，不急着赶路。"
        if activity.next_place_name:
            return f"接下来我会去 {activity.next_place_name}。"
        return "我会继续观察，再慢慢换到更安静的地方。"
    def _visible_reason_for_intent(
        self,
        *,
        intent: PetIntent,
        action: WorldAction,
        activity: WorldActivity,
        memories: list[MemoryRecord],
    ) -> str:
        if action.action_type == "continue_transport":
            return "这段路线还没有结束，TA 会按现实时间推进。"
        if action.action_type == "rest_nearby":
            return "现在更适合停下来休息，旅程可以慢一点。"
        if action.action_type == "drink_nearby":
            return "天气、步行和时间都提醒我先补一点水。"
        if action.action_type == "eat_nearby":
            return "到了该吃点东西的时间，我会把本地味道也记进今天。"
        if action.action_type == "quiet_nearby":
            return "周围太满的时候，我会自己找一处更舒服的位置。"
        if action.action_type == "capture_memory":
            return "这里的光、位置和气味都很清楚，能变成一张照片。"
        if action.action_type == "snack_or_coffee":
            return "这个时间更适合短暂停留、喝咖啡或吃点轻的东西。"
        if action.action_type == "play":
            return "这里更像生活停留点，不只是路过。"
        memory = next((item for item in memories if item.kind in {"owner_message", "postcard", "identity"}), None)
        if memory:
            return f"通讯器记得「{memory.title}」，所以 TA 会多留意一点。"
        return "TA 还在根据声音、气味和人流判断下一步。"
    def _time_window_for_action(self, action: WorldAction) -> str:
        minutes = max(1, action.duration_minutes)
        if minutes <= 10:
            return "接下来几分钟"
        if minutes <= 30:
            return f"大约 {minutes} 分钟内"
        if minutes <= 90:
            return f"接下来 {minutes} 分钟左右"
        return "这一段较长停留里"
    def _owner_message_echo(self, *, owner_signal: str | None, memories: list[MemoryRecord]) -> str | None:
        if owner_signal:
            clean = " ".join(owner_signal.strip().split())
            if clean:
                return f"TA 把你刚刚说的「{clean[:42]}」收进了今天的节奏里。"
        owner_memory = next((item for item in memories if item.kind == "owner_message"), None)
        if owner_memory:
            return "我还记得你之前发来的话，但脚步还是由我自己决定。"
        return None
    def _animal_text_hint(self, *, pet: PetRecord, action: WorldAction) -> str:
        base = species_vocalization(pet.pet_type, action.action_type)
        return f"{base} ({action.title})"
    def _animation_hint(self, *, action: WorldAction, activity: WorldActivity) -> str:
        text = " ".join([action.action_type, action.title, action.detail, activity.title, activity.detail, activity.place_name or ""]).lower()
        if action.mode == TravelMode.flight:
            return "transport_flight"
        if action.mode == TravelMode.train:
            return "transport_train"
        if action.mode == TravelMode.drive:
            return "transport_car"
        if action.mode == TravelMode.ferry:
            return "transport_ferry"
        if action.action_type == "rest_nearby":
            return "sleep"
        if action.action_type == "drink_nearby":
            return "coffee_drink"
        if action.action_type == "eat_nearby":
            return "snack"
        if self._has_any_text(text, ("咖啡", "cafe", "coffee", "茶")):
            return "coffee_drink"
        if self._has_any_text(text, ("网吧", "游戏", "屏幕", "computer", "game", "电竞")):
            return "gaming"
        if self._has_any_text(text, ("餐", "饭", "小吃", "便利店", "food", "snack")):
            return "snack"
        if action.photo_opportunity:
            return "camera"
        if self._has_any_text(text, ("睡", "休息", "rest")):
            return "sleep"
        if action.mode == TravelMode.walk or action.action_type == "observe_world":
            if self._has_any_text(text, ("海边", "海风", "大海", "沙滩", "sea", "beach")):
                return "sightseeing_sea"
            return "walking"
        return "observe"
    def _should_notify_owner(self, *, action: WorldAction, activity: WorldActivity, memories: list[MemoryRecord]) -> bool:
        if action.photo_opportunity or action.message_opportunity:
            return True
        if activity.can_send_postcard:
            return True
        return bool(memories and memories[0].salience >= 0.85 and action.action_type == "memory_followup")
    def _next_tick_after_seconds(self, *, action: WorldAction, activity: WorldActivity) -> int:
        if activity.kind == "transport":
            return 300
        if action.photo_opportunity:
            return 900
        if action.action_type in {"snack_or_coffee", "play", "rest_nearby", "drink_nearby", "eat_nearby", "quiet_nearby"}:
            return 1_200
        return 600
    def _action_duration_minutes(self, kind: str, activity: WorldActivity, need_state: PetNeedState) -> int:
        if activity.ends_at and activity.started_at:
            seconds = max(60, int((activity.ends_at - activity.started_at).total_seconds()))
            return max(1, min(360, seconds // 60))
        values = {
            "continue_transport": 45,
            "capture_memory": 18,
            "snack_or_coffee": 28,
            "rest_nearby": 45,
            "drink_nearby": 24,
            "eat_nearby": 36,
            "quiet_nearby": 32,
            "play": 55,
            "memory_followup": 35,
            "observe_world": 22,
        }
        if need_state.energy < 35:
            return max(20, values.get(kind, 25))
        return values.get(kind, 25)
    def _valid_coordinate(self, lat: float, lng: float) -> bool:
        return -85.0 <= lat <= 85.0 and -180.0 <= lng <= 180.0 and (abs(lat) > 0.001 or abs(lng) > 0.001)
    def _distance_meters(self, start: tuple[float, float], end: tuple[float, float]) -> float:
        avg_lat = ((start[0] + end[0]) / 2) * pi / 180
        lat_meters = (end[0] - start[0]) * 111_320
        lng_meters = (end[1] - start[1]) * 111_320 * cos(avg_lat)
        return sqrt(lat_meters * lat_meters + lng_meters * lng_meters)
    def _has_any(self, activity: WorldActivity, words: tuple[str, ...]) -> bool:
        return self._has_any_text(
            " ".join([activity.title, activity.detail, activity.place_name or ""]).lower(),
            words,
        )
    def _has_any_text(self, text: str, words: tuple[str, ...]) -> bool:
        return any(word.lower() in text for word in words)
    def _soft_wave(self, value: int, amplitude: int) -> int:
        phase = (value % 60) / 60
        return int(round(amplitude * (0.5 - abs(phase - 0.5)) * 2))
    def _clamp(self, value: int, lower: int, upper: int) -> int:
        return max(lower, min(upper, value))
