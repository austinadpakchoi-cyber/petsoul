from __future__ import annotations

from datetime import date, datetime, timedelta
import re
import uuid

from .config import Settings
from .providers import JourneyCity
from .schemas import (
    ItineraryStop,
    JourneyPlan,
    PlaceSignal,
    RouteSegment,
    SouvenirItem,
    SouvenirItemType,
    TransportDecision,
    TravelAnchor,
    TravelBag,
    TravelGuideResearch,
    TravelMode,
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelQuestGuide,
    TravelQuestNextOption,
    TravelQuestReturnPolicy,
    TravelQuestStatus,
    TravelQuestStop,
    TravelQuestTripType,
    TravelQuestTransportOutline,
    TravelQuestType,
    TravelWishRequest,
)
from .storage import PetRecord
from .souvenir_catalog import build_souvenir_templates
from .travel_research import TravelGuideResearchEngine, build_travel_guide_research_engine


class PetTravelQuestEngine:
    provider_name = "mock-pet-travel-quest-engine"

    def __init__(self, settings: Settings, research_engine: TravelGuideResearchEngine):
        self.settings = settings
        self.research_engine = research_engine

    def create_quest(
        self,
        *,
        pet: PetRecord,
        request: TravelWishRequest,
        current_city: JourneyCity,
        current_plan: JourneyPlan,
        now: datetime,
    ) -> TravelQuest:
        message = " ".join(request.message.strip().split())
        quest_type = self._quest_type(message=message, destination=request.destination, event_name=request.event_name)
        destination = self._destination_for(
            quest_type=quest_type,
            message=message,
            destination=request.destination,
            event_name=request.event_name,
            current_city=current_city,
        )
        event_name = request.event_name or self._event_name_for(message, quest_type)
        start_date = request.preferred_start_date or (now.astimezone().date() + timedelta(days=1))
        research = self.research_engine.research(
            owner_message=message,
            destination=destination,
            quest_type=quest_type,
            current_city=current_city,
            event_name=event_name,
            now=now,
            pet_name=pet.name,
        )
        guide = self._guide_for(
            pet=pet,
            quest_type=quest_type,
            owner_message=message,
            destination=destination,
            event_name=event_name,
            preferred_start_date=start_date,
            current_city=current_city,
            current_plan=current_plan,
            research=research,
            now=now,
        )
        quest_id = f"TQ-{uuid.uuid4().hex[:10].upper()}"
        return TravelQuest(
            id=quest_id,
            pet_id=pet.pet_id,
            quest_type=quest_type,
            status=TravelQuestStatus.guide_ready,
            current_phase=TravelQuestStatus.guide_ready,
            trip_type=self._trip_type_for(quest_type),
            return_policy=self._return_policy_for(quest_type),
            origin_anchor=self._origin_anchor(current_city, current_plan),
            owner_message=message,
            destination=destination,
            event_name=event_name,
            preferred_start_date=start_date,
            autonomy_decision=self._autonomy_decision(pet, quest_type, destination),
            current_phase_message=f"我先把去 {destination} 的小攻略整理好了。看完以后，我再慢慢准备出发。",
            guide=guide,
            journey_plan=None,
            worldcup_event=quest_type == TravelQuestType.worldcup,
            created_at=now,
            updated_at=now,
        )

    def prepare_departure(self, *, pet: PetRecord, quest: TravelQuest, current_city: JourneyCity, now: datetime) -> TravelQuest:
        if quest.status in {TravelQuestStatus.traveling, TravelQuestStatus.arrived, TravelQuestStatus.completed}:
            return quest
        plan = self._journey_plan_for_quest(pet=pet, quest=quest, current_city=current_city, now=now)
        return quest.model_copy(
            update={
                "status": TravelQuestStatus.preparing,
                "current_phase": TravelQuestStatus.preparing,
                "current_phase_message": f"我会先休息一下，检查路线和天气，然后从 {current_city.name} 慢慢出发。",
                "journey_plan": plan,
                "updated_at": now,
            }
        )

    def build_post_event_options(self, *, pet: PetRecord, quest: TravelQuest, now: datetime) -> TravelQuest:
        if quest.post_event_options:
            return quest
        options = self._post_event_options(pet=pet, quest=quest)
        return quest.model_copy(
            update={
                "status": TravelQuestStatus.return_planning,
                "current_phase": TravelQuestStatus.return_planning,
                "current_phase_message": "比赛看完以后，我先休息一下，再认真想想下一步是回去、留下，还是去下一座城市。",
                "post_event_options": options,
                "updated_at": now,
            }
        )

    def select_next_step(
        self,
        *,
        pet: PetRecord,
        quest: TravelQuest,
        request: TravelQuestDecisionRequest,
        now: datetime,
    ) -> TravelQuest:
        options = quest.post_event_options or self._post_event_options(pet=pet, quest=quest)
        selected = self._selected_option(options, request.option_id)
        plan = self._journey_plan_for_next_option(pet=pet, quest=quest, option=selected, now=now)
        status = (
            TravelQuestStatus.return_traveling
            if selected.decision_type == "return_to_origin"
            else TravelQuestStatus.continued_elsewhere
        )
        owner_note = f"我也听见你说「{request.owner_message}」。" if request.owner_message else ""
        return quest.model_copy(
            update={
                "status": status,
                "current_phase": status,
                "current_phase_message": f"{owner_note}{selected.pet_voice}",
                "selected_next_option_id": selected.id,
                "post_event_options": options,
                "journey_plan": plan,
                "updated_at": now,
            }
        )

    def generate_souvenirs(
        self,
        *,
        pet: PetRecord,
        quest: TravelQuest,
        bag: TravelBag | None,
        now: datetime,
    ) -> list[SouvenirItem]:
        destination = quest.destination
        stop = self._souvenir_anchor_stop(quest)
        bag_hint = self._bag_souvenir_hint(bag)
        bag_tags = self._bag_influence_tags(bag)
        templates = self._souvenir_templates(quest, stop=stop, bag_hint=bag_hint, bag_tags=bag_tags)
        souvenirs: list[SouvenirItem] = []
        for index, template in enumerate(templates):
            template_id, item_type, title, subtitle, story, pet_voice, rarity = template
            souvenirs.append(
                SouvenirItem(
                    id=f"SV-{uuid.uuid4().hex[:10].upper()}",
                    pet_id=pet.pet_id,
                    quest_id=quest.id,
                    template_id=template_id,
                    item_type=item_type,
                    title=title,
                    subtitle=subtitle,
                    city=stop.city or destination,
                    place_name=stop.name,
                    story=story,
                    pet_voice=pet_voice,
                    image_prompt=self._souvenir_image_prompt(
                        pet=pet,
                        title=title,
                        item_type=item_type,
                        city=stop.city or destination,
                        place_name=stop.name,
                        story=story,
                        worldcup_event=quest.quest_type == TravelQuestType.worldcup,
                    ),
                    rarity=rarity,
                    obtained_at=now + timedelta(minutes=index),
                    source=self.provider_name,
                    bag_influence_tags=bag_tags,
                    source_photo_mission_id=f"quest-stop-{stop.id}",
                )
            )
        return souvenirs

    def _guide_for(
        self,
        *,
        pet: PetRecord,
        quest_type: TravelQuestType,
        owner_message: str,
        destination: str,
        event_name: str | None,
        preferred_start_date: date,
        current_city: JourneyCity,
        current_plan: JourneyPlan,
        research: TravelGuideResearch,
        now: datetime,
    ) -> TravelQuestGuide:
        if quest_type == TravelQuestType.worldcup:
            return self._worldcup_guide(
                pet=pet,
                destination=destination,
                event_name=event_name,
                preferred_start_date=preferred_start_date,
                current_city=current_city,
                research=research,
                now=now,
            )
        return self._open_destination_guide(
            pet=pet,
            owner_message=owner_message,
            destination=destination,
            preferred_start_date=preferred_start_date,
            current_city=current_city,
            current_plan=current_plan,
            research=research,
            now=now,
        )

    def _worldcup_guide(
        self,
        *,
        pet: PetRecord,
        destination: str,
        event_name: str | None,
        preferred_start_date: date,
        current_city: JourneyCity,
        research: TravelGuideResearch,
        now: datetime,
    ) -> TravelQuestGuide:
        match_text = event_name or "一场世界杯比赛"
        stops = [
            TravelQuestStop(
                id="worldcup-prep-rest",
                city=current_city.name,
                name="出发前安静休息点",
                role="准备",
                planned_time="前一晚",
                dwell_minutes=90,
                pet_voice="我会先睡够，不急着出门。明天要走很远，我想把精神留给赛场的声音。",
                owner_tip="适合在手机里展示为睡眠/准备态，而不是马上移动。",
                source_notes=["pet-life-rhythm"],
            ),
            TravelQuestStop(
                id="worldcup-airport-buffer",
                city=current_city.name,
                name="机场/车站缓冲区",
                role="长途交通前",
                planned_time="出发日早上",
                dwell_minutes=45,
                pet_voice="我会先到交通枢纽旁边等一会儿，确认风、声音和路线都对。",
                owner_tip="这里以后接航班/火车 API，展示真实班次号和预计起飞/到达。",
                source_notes=["transport-provider-needed"],
            ),
            TravelQuestStop(
                id="worldcup-arrival-cafe",
                city=destination,
                name="赛场附近安静咖啡店",
                role="抵达后缓冲",
                planned_time="抵达后",
                dwell_minutes=70,
                pet_voice="我不会一下子冲到人很多的地方。我会先在附近坐一会儿，听听球迷走过的声音。",
                owner_tip="适合生成第一张赛场附近的照片，背景要有城市和球赛氛围。",
                source_notes=["google-places", "social-guide-provider"],
            ),
            TravelQuestStop(
                id="worldcup-stadium-outside",
                city=destination,
                name="世界杯赛场外广场",
                role="看比赛",
                planned_time="比赛前后",
                dwell_minutes=120,
                pet_voice=f"如果是 {match_text}，我想站在不拥挤的地方，把灯光和欢呼声都记下来给你。",
                owner_tip="世界杯视觉彩蛋：球队颜色、人群、赛场外观要进入照片 prompt，但避免官方 logo。",
                source_notes=["worldcup-easter-egg", "photo-mission-brain", research.provider.value],
            ),
        ]
        return TravelQuestGuide(
            id=f"TQG-{uuid.uuid4().hex[:8].upper()}",
            title=f"{pet.name} 的世界杯小攻略",
            summary=f"我会从 {current_city.name} 出发，先查清楚长途交通，再去 {destination} 附近慢慢靠近赛场。",
            pet_voice="我想去看看，但我不想被催着赶路。我会先做攻略，再决定什么时候真的迈出去。",
            route_theme="先休息，后长途交通，抵达后缓冲，最后靠近赛场",
            cities=[current_city.name, destination],
            stops=stops,
            transport_outline=[
                TravelQuestTransportOutline(
                    mode=TravelMode.flight,
                    from_place=current_city.name,
                    to_place=destination,
                    estimated_duration="按真实航班/中转时间推进",
                    reality_level="needs_transport_api",
                    note="第一版可用可信模拟；接入航班/火车查询后替换为真实班次号。",
                ),
                TravelQuestTransportOutline(
                    mode=TravelMode.drive,
                    from_place="抵达机场/车站",
                    to_place="赛场附近",
                    estimated_duration="30-90 分钟",
                    reality_level="map_route_available",
                    note="用 Google/高德路线 API 计算落地后的真实道路路线。",
                ),
                TravelQuestTransportOutline(
                    mode=TravelMode.walk,
                    from_place="赛场附近咖啡店",
                    to_place="世界杯赛场外广场",
                    estimated_duration="10-25 分钟",
                    reality_level="map_route_available",
                    note="最后一段用走路动画和宠物 icon 表达。",
                ),
            ],
            preparation_notes=[
                f"预计 {preferred_start_date.isoformat()} 开始准备。",
                "先生成攻略，不立刻改变当前地图轨迹。",
                f"{pet.name}可以接受、推迟或拒绝，这保留 TA 的自主性。",
                "照片任务由地点、比赛氛围、宠物参考图共同生成。",
                "比赛结束后进入赛后整理，再决定回到出发锚点还是继续旅行。",
            ],
            source_notes=[
                "mock guide now",
                *research.recommended_sources,
                *research.missing_capabilities,
            ],
            research=research,
            generated_at=now,
            provider=self.provider_name,
        )

    def _open_destination_guide(
        self,
        *,
        pet: PetRecord,
        owner_message: str,
        destination: str,
        preferred_start_date: date,
        current_city: JourneyCity,
        current_plan: JourneyPlan,
        research: TravelGuideResearch,
        now: datetime,
    ) -> TravelQuestGuide:
        first_stop = current_plan.stops[0].name if current_plan.stops else f"{current_city.name} 安静街角"
        stops = [
            TravelQuestStop(
                id="open-trip-current-rest",
                city=current_city.name,
                name=first_stop,
                role="准备",
                planned_time="今天",
                dwell_minutes=60,
                pet_voice="我会先把今天这一段过完，不把自己突然拽到很远的地方。",
                owner_tip="当前生活线不被打断，只新增一个旅行愿望。",
                source_notes=["pet-life-rhythm"],
            ),
            TravelQuestStop(
                id="open-trip-city-buffer",
                city=destination,
                name=f"{destination} 抵达后的第一处安静地方",
                role="抵达后缓冲",
                planned_time="抵达后",
                dwell_minutes=80,
                pet_voice="到新地方以后，我会先找不太吵的位置，确认这里的风和声音。",
                owner_tip="用地图 API 找机场/车站附近的咖啡、便利店、公园作为缓冲点。",
                source_notes=["map-provider"],
            ),
            TravelQuestStop(
                id="open-trip-local-walk",
                city=destination,
                name=f"{destination} 本地生活路线",
                role="慢慢玩",
                planned_time="第 1 天下午",
                dwell_minutes=120,
                pet_voice="我不会只去热门景点。我想走进一点真正有人生活的街道。",
                owner_tip="这里以后接豆包/社媒攻略，挑真实体验而不是模板景点。",
                source_notes=["social-guide-provider", research.provider.value],
            ),
            TravelQuestStop(
                id="open-trip-postcard",
                city=destination,
                name=f"{destination} 明信片地点",
                role="给你来信",
                planned_time="傍晚",
                dwell_minutes=50,
                pet_voice="如果这里有好看的光，我会自己拍下来，放进回忆里。",
                owner_tip="照片 prompt 需要结合真实地标、天气、时间和宠物参考图。",
                source_notes=["photo-mission-brain"],
            ),
        ]
        return TravelQuestGuide(
            id=f"TQG-{uuid.uuid4().hex[:8].upper()}",
            title=f"{pet.name} 想去 {destination} 的小攻略",
            summary=f"我先从 {current_city.name} 把路线想清楚，再去 {destination} 找真正适合停下来的地方。",
            pet_voice=f"我听见你说「{owner_message}」。我会先查路线和当地怎么玩，不会马上被推着出发。",
            route_theme="保留当前生活节奏，先做攻略，再决定出发",
            cities=[current_city.name, destination],
            stops=stops,
            transport_outline=[
                TravelQuestTransportOutline(
                    mode=TravelMode.flight,
                    from_place=current_city.name,
                    to_place=destination,
                    estimated_duration="跨城时优先查航班/火车",
                    reality_level="needs_transport_api",
                    note="如果很近，可退化为驾车/公交/步行；如果很远，先查长途交通。",
                ),
                TravelQuestTransportOutline(
                    mode=TravelMode.drive,
                    from_place="抵达交通枢纽",
                    to_place="第一处安静停留点",
                    estimated_duration="按地图路线计算",
                    reality_level="map_route_available",
                    note="到达城市后的本地路线交给高德或 Google。",
                ),
                TravelQuestTransportOutline(
                    mode=TravelMode.walk,
                    from_place="本地停留点",
                    to_place="明信片地点",
                    estimated_duration="按宠物体力慢慢走",
                    reality_level="map_route_available",
                    note="走走停停，允许咖啡店、便利店、公园、网吧等中途事件。",
                ),
            ],
            preparation_notes=[
                f"预计 {preferred_start_date.isoformat()} 开始整理行李和路线。",
                "先把攻略 po 给用户，不马上改当前世界状态。",
                "用户可以收藏攻略或继续聊天，但不能强制 TA 喜欢某个地点。",
                "到达后会再决定是回到出发锚点，还是继续在附近城市生活。",
            ],
            source_notes=[
                "mock guide now",
                *research.recommended_sources,
                *research.missing_capabilities,
            ],
            research=research,
            generated_at=now,
            provider=self.provider_name,
        )

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


def build_pet_travel_quest_engine(settings: Settings) -> PetTravelQuestEngine:
    return PetTravelQuestEngine(
        settings=settings,
        research_engine=build_travel_guide_research_engine(settings),
    )
