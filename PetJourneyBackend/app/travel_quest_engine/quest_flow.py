"""PetTravelQuestEngine 任务流 mixin：创建/出发/赛后选项/纪念品/攻略生成。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import uuid

from ..city_timezones import local_wall_time
from ..config import Settings
from ..providers import JourneyCity
from ..schemas import (
    JourneyPlan,
    SouvenirItem,
    SouvenirItemType,
    TravelBag,
    TravelGuideResearch,
    TravelMode,
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelQuestGuide,
    TravelQuestNextOption,
    TravelQuestStatus,
    TravelQuestStop,
    TravelQuestTransportOutline,
    TravelQuestType,
    TravelWishRequest,
)
from ..storage import PetRecord
from ..travel_research import TravelGuideResearchEngine


class PetTravelQuestFlowMixin:
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
        start_date = request.preferred_start_date or (local_wall_time(now, destination).date() + timedelta(days=1))
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
                owner_tip="适合在通讯器里展示为睡眠/准备态，而不是马上移动。",
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
