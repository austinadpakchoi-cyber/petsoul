"""PetTravelQuestEngine 计划 mixin：旅程计划、赛后选项、纪念品模板与解析辅助。"""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from ..providers import JourneyCity
from ..schemas import (
    ItineraryStop,
    JourneyPlan,
    PlaceSignal,
    RouteSegment,
    SouvenirItemType,
    TransportDecision,
    TravelAnchor,
    TravelBag,
    TravelMode,
    TravelQuest,
    TravelQuestNextOption,
    TravelQuestReturnPolicy,
    TravelQuestStop,
    TravelQuestTransportOutline,
    TravelQuestTripType,
    TravelQuestType,
)
from ..souvenir_catalog import build_souvenir_templates
from ..storage import PetRecord


class PetTravelQuestPlanningMixin:
    def _journey_plan_for_quest(self, *, pet: PetRecord, quest: TravelQuest, current_city: JourneyCity, now: datetime) -> JourneyPlan:
        destination = quest.destination
        origin = self._place(
            id="quest-origin",
            name=current_city.name,
            category="origin",
            city=current_city.name,
            lat=current_city.lat,
            lng=current_city.lng,
            activity_hint="准备出发前安静待着",
            detail_hint="这里是旅行愿望进入准备阶段的起点。",
        )
        arrival = self._place(
            id="quest-arrival",
            name=f"{destination} 抵达点",
            category="airport" if quest.quest_type == TravelQuestType.worldcup else "station",
            city=destination,
            lat=current_city.lat + 0.42,
            lng=current_city.lng + 0.72,
            activity_hint="抵达后先慢慢适应",
            detail_hint="抵达后不会立刻去热闹地点，会先缓冲。",
        )
        anchor = self._place(
            id="quest-main-place",
            name="世界杯赛场外广场" if quest.quest_type == TravelQuestType.worldcup else f"{destination} 本地生活街区",
            category="stadium" if quest.quest_type == TravelQuestType.worldcup else "place",
            city=destination,
            lat=arrival.lat + 0.03,
            lng=arrival.lng + 0.02,
            activity_hint="慢慢靠近想看的地方",
            detail_hint="这里会成为照片和明信片任务的主要场景。",
        )
        mode = TravelMode.flight if destination != current_city.name else TravelMode.drive
        stops = [
            self._itinerary_stop(origin, "出发前先休息", "我会先把精神留好，再开始这段路。", "08:00", 70),
            self._itinerary_stop(arrival, "抵达后缓冲", "我会先找安静的位置，不立刻钻进人群。", "抵达后", 80),
            self._itinerary_stop(anchor, "把这一刻寄回来", "如果光和声音都刚好，我会拍一张照片给你。", "傍晚", 120, postcard=True, photo=True),
        ]
        segments = [
            RouteSegment(
                id="quest-long-distance",
                mode=mode,
                title="前往目的地",
                detail="这段路会按真实世界的交通逻辑推进，后续接航班/火车 API 后替换为真实班次。",
                from_place=origin.name,
                to_place=arrival.name,
                distance_meters=None,
                duration_seconds=None,
                provider=self.provider_name,
                start_time=now + timedelta(hours=8),
                end_time=now + timedelta(hours=18),
                is_simulated=True,
            ),
            RouteSegment(
                id="quest-local-route",
                mode=TravelMode.drive,
                title="抵达后的本地路线",
                detail="落地后先去安静停留点，再慢慢靠近主要地点。",
                from_place=arrival.name,
                to_place=anchor.name,
                distance_meters=18_000,
                duration_seconds=2_400,
                provider=self.provider_name,
                is_simulated=True,
            ),
        ]
        return JourneyPlan(
            pet_id=pet.pet_id,
            city=destination,
            generated_at=now,
            provider=self.provider_name,
            horizon_hours=48,
            summary=f"我准备从 {current_city.name} 出发，先去 {destination} 看看。",
            current_activity=origin.activity_hint,
            transport_decision=TransportDecision(
                selected_mode=mode,
                reason="我先按真实距离选择长途交通，再在当地慢慢走。",
                rejected_modes=[TravelMode.walk] if mode != TravelMode.walk else [],
                autonomy_note="这是我接受建议后自己的出发计划，仍会按体力和天气调整。",
            ),
            route_segments=segments,
            scheduled_transport=[],
            stops=stops,
            places=[origin, arrival, anchor],
            next_postcard_hint=f"到 {anchor.name} 后，我会寄回第一张照片。",
            worldcup_event=quest.quest_type == TravelQuestType.worldcup,
        )
    def _journey_plan_for_next_option(
        self,
        *,
        pet: PetRecord,
        quest: TravelQuest,
        option: TravelQuestNextOption,
        now: datetime,
    ) -> JourneyPlan:
        origin_anchor = quest.origin_anchor or TravelAnchor(
            city="原来的地方",
            place_name="出发前的位置",
            lat=24.4798,
            lng=118.0894,
            note="旧版本 quest 没有保存出发锚点，使用默认锚点兜底。",
        )
        from_place = self._place(
            id="quest-post-event-origin",
            name=quest.destination,
            category="event_city",
            city=quest.destination,
            lat=origin_anchor.lat + 0.42,
            lng=origin_anchor.lng + 0.72,
            activity_hint="赛后找地方休息",
            detail_hint="看完比赛以后，先从热闹里退出来。",
        )
        to_place = self._place(
            id=f"quest-next-{option.id}",
            name=option.destination,
            category="return_anchor" if option.decision_type == "return_to_origin" else "next_city",
            city=option.destination,
            lat=origin_anchor.lat if option.decision_type == "return_to_origin" else from_place.lat + 0.28,
            lng=origin_anchor.lng if option.decision_type == "return_to_origin" else from_place.lng + 0.31,
            activity_hint="下一段旅程开始",
            detail_hint=option.owner_visible_reason,
        )
        mode = option.transport_outline[0].mode if option.transport_outline else TravelMode.flight
        return JourneyPlan(
            pet_id=pet.pet_id,
            city=option.destination,
            generated_at=now,
            provider=self.provider_name,
            horizon_hours=48,
            summary=option.pet_voice,
            current_activity=from_place.activity_hint,
            transport_decision=TransportDecision(
                selected_mode=mode,
                reason=option.owner_visible_reason,
                rejected_modes=[TravelMode.walk] if mode != TravelMode.walk else [],
                autonomy_note="这是赛后整理后的下一步，不是主人强制切换地图。",
            ),
            route_segments=[
                RouteSegment(
                    id=f"quest-next-route-{option.id}",
                    mode=mode,
                    title=option.title,
                    detail=option.pet_voice,
                    from_place=from_place.name,
                    to_place=to_place.name,
                    provider=self.provider_name,
                    start_time=now + timedelta(hours=4),
                    end_time=now + timedelta(hours=12),
                    is_simulated=True,
                )
            ],
            scheduled_transport=[],
            stops=[
                self._itinerary_stop(from_place, "赛后先休息", "我先从热闹里退出来，喝点水，睡一小会儿。", "赛后", 90),
                self._itinerary_stop(
                    to_place,
                    "下一段旅程",
                    option.pet_voice,
                    "休息后",
                    120,
                    postcard=option.decision_type != "return_to_origin",
                    photo=True,
                ),
            ],
            places=[from_place, to_place],
            next_postcard_hint=f"下一段到 {to_place.name} 后，我会再发一张照片告诉你。",
            worldcup_event=quest.quest_type == TravelQuestType.worldcup,
        )
    def _post_event_options(self, *, pet: PetRecord, quest: TravelQuest) -> list[TravelQuestNextOption]:
        origin = quest.origin_anchor or TravelAnchor(
            city="原来的地方",
            place_name="出发前的位置",
            lat=24.4798,
            lng=118.0894,
            note="旧版本 quest 没有保存出发锚点，使用默认锚点兜底。",
        )
        nearby_city = self._nearby_next_city(quest.destination)
        return [
            TravelQuestNextOption(
                id="return-home-anchor",
                title=f"回到 {origin.city}",
                decision_type="return_to_origin",
                destination=origin.city,
                pet_voice=f"我想把这次比赛的声音带回 {origin.place_name}，先回到熟悉的地方睡一觉。",
                owner_visible_reason="支线旅行默认应该能回到出发锚点，这样主生活线不会断掉。",
                transport_outline=[
                    TravelQuestTransportOutline(
                        mode=TravelMode.flight,
                        from_place=quest.destination,
                        to_place=origin.city,
                        estimated_duration="按真实航班/中转时间推进",
                        reality_level="needs_transport_api",
                        note="后续由航班/火车 provider 查真实班次。",
                    )
                ],
                recommended=True,
            ),
            TravelQuestNextOption(
                id="stay-one-more-day",
                title=f"在 {quest.destination} 多待一天",
                decision_type="stay_local",
                destination=quest.destination,
                pet_voice="我还有点舍不得走。明天我想在附近找一条安静的街，慢慢散步。",
                owner_visible_reason="如果赛后体力还可以，保留当地生活感会让旅程更像真实旅行。",
                transport_outline=[
                    TravelQuestTransportOutline(
                        mode=TravelMode.walk,
                        from_place="赛场附近",
                        to_place="当地生活街区",
                        estimated_duration="按本地步行和短途交通规划",
                        reality_level="map_route_available",
                        note="由地图 provider 找附近咖啡店、公园、便利店等停留点。",
                    )
                ],
            ),
            TravelQuestNextOption(
                id="continue-nearby-city",
                title=f"顺路去 {nearby_city}",
                decision_type="continue_journey",
                destination=nearby_city,
                pet_voice=f"如果路线顺，我也想去 {nearby_city} 看一看。不是赶路，只是把旅程轻轻接下去。",
                owner_visible_reason="适合把世界杯彩蛋自然扩展成多城市旅行，而不是一次性结束。",
                transport_outline=[
                    TravelQuestTransportOutline(
                        mode=TravelMode.train,
                        from_place=quest.destination,
                        to_place=nearby_city,
                        estimated_duration="按城际火车/汽车/短途航班查询",
                        reality_level="needs_transport_api",
                        note="后续由交通 provider 查真实存在的线路。",
                    )
                ],
            ),
        ]
    def _souvenir_anchor_stop(self, quest: TravelQuest) -> TravelQuestStop:
        if quest.guide and quest.guide.stops:
            photo_stop = next((stop for stop in reversed(quest.guide.stops) if "明信片" in stop.role or "看比赛" in stop.role), None)
            return photo_stop or quest.guide.stops[-1]
        return TravelQuestStop(
            id="souvenir-fallback-stop",
            city=quest.destination,
            name=quest.destination,
            role="带回物",
            planned_time=None,
            dwell_minutes=30,
            pet_voice="我在这里停了一会儿，想带一点小东西回去。",
            owner_tip="旧版本旅程没有 guide，使用目的地兜底。",
        )
    def _bag_souvenir_hint(self, bag: TravelBag | None) -> str:
        if not bag or not bag.items:
            return "路上没有额外小包物品，所以 TA 会凭自己的好奇心挑选带回物。"
        titles = "、".join(item.title for item in bag.items[-3:])
        tags = sorted({tag for item in bag.items for tag in item.influence_tags})
        tag_text = f"；倾向：{'、'.join(tags[:4])}" if tags else ""
        return f"TA 的小包里有 {titles}{tag_text}，带回物会带一点主人准备过的回声。"
    def _bag_influence_tags(self, bag: TravelBag | None) -> list[str]:
        if not bag or not bag.items:
            return []
        return sorted({tag for item in bag.items for tag in item.influence_tags if tag})[:8]
    def _souvenir_templates(
        self,
        quest: TravelQuest,
        *,
        stop: TravelQuestStop,
        bag_hint: str,
        bag_tags: list[str],
    ) -> list[tuple[str, SouvenirItemType, str, str, str, str, str]]:
        return build_souvenir_templates(quest=quest, stop=stop, bag_hint=bag_hint, bag_tags=bag_tags)
    def _souvenir_image_prompt(
        self,
        *,
        pet: PetRecord,
        title: str,
        item_type: SouvenirItemType,
        city: str,
        place_name: str,
        story: str,
        worldcup_event: bool,
    ) -> str:
        event_constraint = (
            "If the scene suggests a football match, use generic team-color atmosphere and crowds, "
            "but avoid official tournament logos, club crests, readable trademarks, or real ticket branding. "
            if worldcup_event
            else ""
        )
        return (
            f"Create a warm realistic keepsake photo from a parallel-world pet travel app. "
            f"The keepsake is '{title}', type '{item_type.value}', brought back by a {pet.pet_type.value} named {pet.name}. "
            f"Place context: {city}, near {place_name}. Story context: {story}. "
            f"Show the object as a small travel souvenir on a soft cloth or cafe table, with subtle hints of the local place in the background. "
            f"The pet can appear partially in frame as a paw, feather, nose, or soft shadow if natural, but do not make it look like a pasted cutout. "
            f"{event_constraint}"
            f"Low-saturation emotional companion style, gentle morning or evening light, tactile details, no UI text, no watermark."
        )
    def _selected_option(self, options: list[TravelQuestNextOption], option_id: str | None) -> TravelQuestNextOption:
        if option_id:
            for option in options:
                if option.id == option_id:
                    return option
        return next((option for option in options if option.recommended), options[0])
    def _origin_anchor(self, current_city: JourneyCity, current_plan: JourneyPlan) -> TravelAnchor:
        if current_plan.stops:
            stop = current_plan.stops[0]
            return TravelAnchor(
                city=stop.city,
                place_name=stop.name,
                lat=stop.lat,
                lng=stop.lng,
                note="这次支线旅程的出发锚点；赛后可以回到这里继续主生活线。",
            )
        return TravelAnchor(
            city=current_city.name,
            place_name=current_city.name,
            lat=current_city.lat,
            lng=current_city.lng,
            note="这次支线旅程的城市锚点；赛后可以回到这里继续主生活线。",
        )
    def _trip_type_for(self, quest_type: TravelQuestType) -> TravelQuestTripType:
        if quest_type == TravelQuestType.worldcup:
            return TravelQuestTripType.round_trip
        return TravelQuestTripType.open_ended
    def _return_policy_for(self, quest_type: TravelQuestType) -> TravelQuestReturnPolicy:
        if quest_type == TravelQuestType.worldcup:
            return TravelQuestReturnPolicy.ask_after_event
        return TravelQuestReturnPolicy.ask_after_event
    def _nearby_next_city(self, destination: str) -> str:
        if "洛杉矶" in destination or "世界杯" in destination:
            return "圣地亚哥"
        if "厦门" in destination:
            return "泉州"
        if "上海" in destination:
            return "杭州"
        if "北京" in destination:
            return "天津"
        return "下一座安静城市"
    def _quest_type(self, *, message: str, destination: str | None, event_name: str | None) -> TravelQuestType:
        text = f"{message} {destination or ''} {event_name or ''}".lower()
        if "世界杯" in text or "world cup" in text or "worldcup" in text:
            return TravelQuestType.worldcup
        if destination:
            return TravelQuestType.city_trip
        return TravelQuestType.open_destination
    def _destination_for(
        self,
        *,
        quest_type: TravelQuestType,
        message: str,
        destination: str | None,
        event_name: str | None,
        current_city: JourneyCity,
    ) -> str:
        if destination:
            return destination.strip()
        if quest_type == TravelQuestType.worldcup:
            return "世界杯赛场城市"
        extracted = self._extract_destination(message)
        return extracted or current_city.name
    def _event_name_for(self, message: str, quest_type: TravelQuestType) -> str | None:
        if quest_type != TravelQuestType.worldcup:
            return None
        match = re.search(r"(看|去看)(?P<event>[^，。,.!?]{2,30}?比赛)", message)
        if match:
            return match.group("event").strip()
        return "世界杯比赛"
    def _extract_destination(self, message: str) -> str | None:
        patterns = [
            r"去(?P<destination>[^，。,.!?]{2,18}?)(?:玩|旅行|看看|看|逛|走走|做攻略|$)",
            r"想让.*?去(?P<destination>[^，。,.!?]{2,18})",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group("destination").strip()
        return None
    def _autonomy_decision(self, pet: PetRecord, quest_type: TravelQuestType, destination: str) -> str:
        if quest_type == TravelQuestType.worldcup:
            return f"我听见了。我想先查清楚去 {destination} 的路，再决定什么时候真的出发。"
        return f"我会先把去 {destination} 的路线和停留点想清楚。你可以看攻略，但我会按自己的节奏走。"
    def _place(
        self,
        *,
        id: str,
        name: str,
        category: str,
        city: str,
        lat: float,
        lng: float,
        activity_hint: str,
        detail_hint: str,
    ) -> PlaceSignal:
        return PlaceSignal(
            id=id,
            name=name,
            category=category,
            city=city,
            lat=lat,
            lng=lng,
            activity_hint=activity_hint,
            detail_hint=detail_hint,
            source=self.provider_name,
        )
    def _itinerary_stop(
        self,
        place: PlaceSignal,
        title: str,
        detail: str,
        planned_time: str,
        dwell_minutes: int,
        postcard: bool = False,
        photo: bool = False,
    ) -> ItineraryStop:
        return ItineraryStop(
            id=f"travel-quest-stop-{place.id}",
            name=place.name,
            category=place.category,
            city=place.city,
            lat=place.lat,
            lng=place.lng,
            title=title,
            detail=detail,
            planned_time=planned_time,
            dwell_minutes=dwell_minutes,
            postcard_candidate=postcard,
            photo_candidate=photo,
            source=place.source,
        )
