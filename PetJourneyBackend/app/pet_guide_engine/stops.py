"""PetGuideEngine 停靠点 mixin：停靠点构造、时间/停留规则与文案清洁。"""

from __future__ import annotations

from ..schemas import JourneyPlan, PetGuideStop
from ..storage import PetRecord


class PetGuideStopsMixin:
    def _fallback_title(self, pet: PetRecord, plan: JourneyPlan) -> str:
        if plan.city == "厦门":
            return f"{pet.name} 的厦门山海慢游线"
        return f"{pet.name} 今天想这样过"
    def _fallback_route_theme(self, plan: JourneyPlan) -> str:
        if plan.city == "厦门":
            return "从山上的风，到老城的人间烟火，再到海边的傍晚。"
        return "慢慢走、认真停、按自己的节奏生活。"
    def _fallback_translation(self, pet: PetRecord, plan: JourneyPlan, stops: list[PetGuideStop]) -> str:
        if plan.city == "厦门":
            return (
                "我今天想先在厦门高一点的地方醒来。然后慢慢走进老城，闻一点热闹的味道。"
                "下午去海边，把风和光都收进心里。傍晚的时候，我会找一个安静的位置，"
                "把这一天写成一封小小的信。如果有机会，你也可以沿着这条线来看看。"
            )
        stop_lines = "，".join(stop.name for stop in stops[:4])
        return (
            f"我想在{plan.city}慢慢玩，不想一下子赶很多地方。"
            f"今天我选了这些地方：{stop_lines}。"
            "我会认真停留、休息、看路上的人和光，再把值得你来的地方记下来。"
        )
    def _guide_stop(
        self,
        *,
        place,
        index: int,
        role: str,
        planned_time: str | None,
        dwell_minutes: int,
        pet_reason: str,
        owner_tip: str,
    ) -> PetGuideStop:
        is_visible = self._is_visible_core_place(place, role=role)
        return PetGuideStop(
            id=f"pet-guide-stop-{index + 1}-{place.id}",
            place_id=place.id,
            name=place.name,
            category=place.category,
            role=role,
            is_core=is_visible,
            is_user_visible=is_visible,
            city=place.city,
            lat=place.lat,
            lng=place.lng,
            planned_time=planned_time,
            dwell_minutes=self._clamp_dwell_minutes(place.category, dwell_minutes),
            pet_reason=pet_reason,
            owner_tip=owner_tip,
            rating=place.rating,
            photo_url=place.photo_url,
            distance_meters=place.distance_meters,
            guide_score=place.guide_score,
            source=place.source,
        )
    def _place_for_stop(self, plan: JourneyPlan, stop) -> object:
        for place in plan.places:
            if place.id == stop.id.removeprefix("stop-") or place.name == stop.name:
                return place
        for place in plan.places:
            if place.name == stop.name:
                return place
        return plan.places[0]
    def _planned_time_for_place(self, plan: JourneyPlan, place, fallback: str | None) -> str | None:
        stop = self._matching_stop(plan, place)
        return stop.planned_time if stop and stop.planned_time else fallback
    def _dwell_minutes_for_place(self, plan: JourneyPlan, place, fallback: int) -> int:
        stop = self._matching_stop(plan, place)
        minutes = stop.dwell_minutes if stop else fallback
        return self._clamp_dwell_minutes(place.category, minutes)
    def _clamp_dwell_minutes(self, category: str, minutes: int) -> int:
        bounds = {
            "park": (30, 60),
            "place": (60, 120),
            "beach": (45, 90),
            "cafe": (45, 90),
            "food": (30, 75),
            "shop": (10, 20),
            "netcafe": (35, 90),
            "flower": (15, 40),
        }
        lower, upper = bounds.get(category, (25, 100))
        return max(lower, min(upper, minutes))
    def _matching_stop(self, plan: JourneyPlan, place):
        return next((stop for stop in plan.stops if stop.name == place.name or stop.id.endswith(place.id)), None)
    def _clean_pet_voice(self, text: str) -> str:
        cleaned = " ".join(text.split())
        replacements = {
            "TA 会": "我会",
            "TA 正在": "我正在",
            "TA ": "我",
            "可能会": "会",
            "可能": "",
            "适合攻略型打卡": "我会短暂停留",
            "适合打卡": "我想停一停",
            "打卡": "停留",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned.strip(" ，。；;") or "我会在这里慢慢停一会儿。"
    def _clean_owner_tip(self, text: str) -> str:
        cleaned = " ".join(text.split())
        replacements = {
            "给主人参考：": "",
            "用户": "你",
            "TA 的候选停留点，不是用户命令": "这是我的停留点，不是任务",
            "可能会": "会",
            "可能": "",
            "适合攻略型打卡": "适合短暂停留",
            "打卡": "停留",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned.strip(" ，。；;")
