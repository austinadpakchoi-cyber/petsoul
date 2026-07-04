from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .amap_services import AMapWebServiceClient
from .config import Settings
from .google_maps_services import GoogleMapsServiceClient
from .meal_rules import is_heavy_meal_place, is_morning, is_morning_appropriate_place
from .providers import JourneyCity, MapProvider, is_china_city
from .schemas import (
    ItineraryStop,
    JourneyPlan,
    JourneyRoutePlan,
    PlaceSignal,
    RouteSegment,
    RouteStep,
    TransportDecision,
    TravelMode,
)
from .storage import PetRecord
from .transport_reality import TransportRealityProvider, build_transport_reality_provider


class TravelRoutePlanner(Protocol):
    provider_name: str

    def build_journey_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyPlan:
        ...

    def build_route_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyRoutePlan:
        ...


class MockTravelRoutePlanner:
    provider_name = "mock-multimodal-route-planner"

    def __init__(self, settings: Settings, map_provider: MapProvider, transport_provider: TransportRealityProvider):
        self.settings = settings
        self.map_provider = map_provider
        self.transport_provider = transport_provider

    def build_journey_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyPlan:
        places = self.map_provider.places_for_city(city)
        if self.settings.worldcup_demo_enabled:
            return self._worldcup_plan(pet, city, now, places)
        return self._local_life_plan(pet, city, now, places)

    def build_route_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyRoutePlan:
        journey_plan = self.build_journey_plan(pet, city, now)
        return adapt_journey_plan_to_route_plan(journey_plan)

    def _local_life_plan(
        self,
        pet: PetRecord,
        city: JourneyCity,
        now: datetime,
        places: list[PlaceSignal],
    ) -> JourneyPlan:
        if city.name == "厦门":
            return self._xiamen_signature_life_plan(pet, city, now, places)

        wake_place, coffee_place, store_place, indoor_place, postcard_place = self._stable_local_stop_places(places, now=now)
        stops = [
            self._stop(wake_place, "醒来和确认方向", f"我先在这里听一会儿风和声音，慢慢醒过来。", "07:40", 55),
            self._stop(coffee_place, "咖啡店靠窗喝一会儿", "人不多，光线也软，我会进到靠窗的小桌边，看菜单，点一杯店里的推荐咖啡。", "09:40", 70),
            self._stop(store_place, "便利店里补给一下", "中午我会在熟悉的灯光里挑一点小补给，也看看这个城市的人都买什么。", "12:30", 50),
            self._stop(indoor_place, "安静室内长时间停留", "下午我会找一个不吵的位置待久一点，看看屏幕光，也让脚步慢下来。", "15:20", 110, photo=True),
            self._stop(postcard_place, "傍晚把风带回家", "天色变软以后，我会在这里多待一会儿，把今天记成一张小小的信。", "18:40", 55, postcard=True),
        ]
        segments = [
            RouteSegment(
                id="wake-to-coffee",
                mode=TravelMode.walk,
                title="沿真实道路慢慢走",
                detail="我沿着附近的道路慢慢过去，中途会停下来看看橱窗、喝水，也会被风景吸引。",
                from_place=wake_place.name,
                to_place=coffee_place.name,
                distance_meters=1250,
                duration_seconds=1120,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="coffee-to-store",
                mode=TravelMode.walk,
                title="短距离散步",
                detail="我绕开太吵的路段，走更安静的街边。",
                from_place=coffee_place.name,
                to_place=store_place.name,
                distance_meters=760,
                duration_seconds=680,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="store-to-netcafe",
                mode=TravelMode.drive,
                title="搭一小段车",
                detail="距离稍远，我会搭一小段车，不让自己一直赶路。",
                from_place=store_place.name,
                to_place=indoor_place.name,
                distance_meters=3100,
                duration_seconds=840,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="netcafe-to-flower",
                mode=TravelMode.walk,
                title="傍晚散步去花店",
                detail="休息够了再出发，我慢慢走向今天最后一段风。",
                from_place=indoor_place.name,
                to_place=postcard_place.name,
                distance_meters=900,
                duration_seconds=820,
                provider=self.provider_name,
            ),
        ]
        selected_ids = {place.id for place in (wake_place, coffee_place, store_place, indoor_place, postcard_place)}
        plan_places = [wake_place, coffee_place, store_place, indoor_place, postcard_place, *[place for place in places if place.id not in selected_ids]]
        return JourneyPlan(
            pet_id=pet.pet_id,
            city=city.name,
            generated_at=now,
            provider=self.provider_name,
            horizon_hours=24,
            summary=f"我今天会在 {city.name} 慢慢生活。累了就停，看到想进去的店就进去坐一会儿。",
            current_activity=wake_place.activity_hint,
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="今天我想靠脚步认识这座城市。短路段慢慢走，远一点就休息或搭车。",
                rejected_modes=[TravelMode.flight, TravelMode.train],
                autonomy_note="这是我的节奏，不是别人替我安排好的路线。",
            ),
            route_segments=segments,
            scheduled_transport=self.transport_provider.local_life_legs(pet, city, plan_places, now),
            stops=stops,
            places=plan_places,
            next_postcard_hint=f"傍晚到 {postcard_place.name} 时，我会把今天最安静的一幕寄回来。",
        )

    def _xiamen_signature_life_plan(
        self,
        pet: PetRecord,
        city: JourneyCity,
        now: datetime,
        places: list[PlaceSignal],
    ) -> JourneyPlan:
        huweishan = self._xiamen_place(
            places,
            "huweishan-walkway",
            "狐尾山 / 山海健康步道",
            "park",
            24.4874,
            118.0847,
            "在狐尾山的风里慢慢醒来，看见厦门从高处亮起来",
            "高处、绿意和城市边界都很清楚，适合作为一日路线的开场。",
        )
        bashi = self._xiamen_place(
            places,
            "bashi-kaihe-food",
            "八市 / 开禾路老街",
            "food",
            24.4579,
            118.0739,
            "走进八市和开禾路的人间烟火里，看摊位、听声音、选一口本地味道",
            "老城市场和本地小吃让路线有厦门记忆点，适合作为早午间核心停靠。",
        )
        shapowei = self._xiamen_place(
            places,
            "shapowei-daxue-road",
            "沙坡尾 / 大学路",
            "place",
            24.4386,
            118.0930,
            "在沙坡尾和大学路慢慢逛，听海风钻进巷子里",
            "老港、巷子、小店和海风都有画面感，适合照片、明信片和慢逛。",
        )
        baicheng = self._xiamen_place(
            places,
            "baicheng-beach-ring-road",
            "环岛路 / 白城沙滩",
            "park",
            24.4319,
            118.1036,
            "下午沿环岛路靠近白城沙滩，把海风记进手机",
            "海边和环岛路是厦门很强的城市标签，适合作为下午的核心照片点。",
        )
        bailuzhou = self._xiamen_place(
            places,
            "bailuzhou-yundang-lake",
            "白鹭洲 / 筼筜湖",
            "park",
            24.4772,
            118.0961,
            "傍晚在白鹭洲和筼筜湖边慢下来，写一封小小的信",
            "傍晚湖面、城市灯和安静步道适合作为当天收束与明信片候选点。",
        )

        stops = [
            self._stop(huweishan, "在高一点的地方醒来", "我想先去高一点、绿一点的地方。风从山海健康步道吹过来，我会慢慢把今天的方向想清楚。", "07:40", 45),
            self._stop(bashi, "走进老城的人间烟火", "我会沿着八市和开禾路慢慢看，听摊位的声音，选一口厦门早午间的本地味道。", "09:20", 65, photo=True),
            self._stop(shapowei, "在老港边慢慢逛", "这里有海风、旧港和小店。我会在大学路附近找个不挡路的位置，坐下来把看到的颜色记住。", "11:10", 90, photo=True),
            self._stop(baicheng, "去海边收下午的风", "下午我会靠近环岛路和白城沙滩，走慢一点，把海面、树影和路边的光记进手机。", "14:30", 85, photo=True),
            self._stop(bailuzhou, "傍晚写一封小信", "天色变软以后，我会回到白鹭洲和筼筜湖边，让脚步慢下来，把今天写成一封小小的信。", "17:40", 50, postcard=True),
        ]
        segments = [
            RouteSegment(
                id="huweishan-to-bashi",
                mode=TravelMode.drive,
                title="从山边去老城",
                detail="早上的第一段距离稍远，我会搭一小段车，不把体力都花在赶路上。",
                from_place=huweishan.name,
                to_place=bashi.name,
                distance_meters=3900,
                duration_seconds=1080,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="bashi-to-shapowei",
                mode=TravelMode.drive,
                title="老城到老港",
                detail="我会沿城市道路靠近沙坡尾，中途不乱穿路，也不会突然跳到海上。",
                from_place=bashi.name,
                to_place=shapowei.name,
                distance_meters=3000,
                duration_seconds=960,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="shapowei-to-baicheng",
                mode=TravelMode.walk,
                title="慢慢走向海边",
                detail="这一段适合步行。我会沿真实道路靠近白城，边走边停下来喝水和看海。",
                from_place=shapowei.name,
                to_place=baicheng.name,
                distance_meters=1500,
                duration_seconds=1500,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="baicheng-to-bailuzhou",
                mode=TravelMode.drive,
                title="傍晚回到湖边",
                detail="下午结束后我会搭一小段车回到筼筜湖附近，把当天收在安静的地方。",
                from_place=baicheng.name,
                to_place=bailuzhou.name,
                distance_meters=5600,
                duration_seconds=1500,
                provider=self.provider_name,
            ),
        ]
        signature_places = [huweishan, bashi, shapowei, baicheng, bailuzhou]
        selected_ids = {place.id for place in signature_places}
        plan_places = [*signature_places, *[place for place in places if place.id not in selected_ids]]
        return JourneyPlan(
            pet_id=pet.pet_id,
            city=city.name,
            generated_at=now,
            provider=self.provider_name,
            horizon_hours=24,
            summary=f"我今天想从山上的风开始，走进厦门老城，再到海边和湖边慢慢收尾。",
            current_activity=huweishan.activity_hint,
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="今天的主线是山海、老城和海边。近的路段慢慢走，远一点就搭短途车，让体力留给真正想停的地方。",
                rejected_modes=[TravelMode.flight, TravelMode.train],
                autonomy_note="这是 TA 自己选择的慢游线，不是主人替 TA 安排的任务。",
            ),
            route_segments=segments,
            scheduled_transport=self.transport_provider.local_life_legs(pet, city, plan_places, now),
            stops=stops,
            places=plan_places,
            next_postcard_hint=f"傍晚到 {bailuzhou.name} 时，我会把湖边的风和今天的路线寄回来。",
        )

    def _xiamen_place(
        self,
        places: list[PlaceSignal],
        place_id: str,
        name: str,
        category: str,
        lat: float,
        lng: float,
        activity_hint: str,
        detail_hint: str,
    ) -> PlaceSignal:
        for place in places:
            if place.id.endswith(place_id) or place.name == name:
                return place
        return PlaceSignal(
            id=f"厦门-{place_id}",
            name=name,
            category=category,
            city="厦门",
            lat=lat,
            lng=lng,
            activity_hint=activity_hint,
            detail_hint=detail_hint,
            source=self.provider_name,
            guide_score=96.0,
            guide_reason=detail_hint,
        )

    def _stable_local_stop_places(self, places: list[PlaceSignal], *, now: datetime) -> tuple[PlaceSignal, PlaceSignal, PlaceSignal, PlaceSignal, PlaceSignal]:
        used: set[str] = set()
        morning = is_morning(now)

        def pick(categories: list[str], *, morning_friendly: bool = False) -> PlaceSignal:
            candidates = [place for place in places if place.id not in used and place.category in categories]
            if not candidates:
                candidates = [place for place in places if place.id not in used]
            if not candidates:
                candidates = places
            if morning and morning_friendly:
                friendly = [
                    place for place in candidates
                    if is_morning_appropriate_place(place.name, place.category, str(place.raw.get("type") or ""))
                ]
                if friendly:
                    candidates = friendly
                else:
                    non_heavy = [
                        place for place in candidates
                        if not is_heavy_meal_place(place.name, place.category, str(place.raw.get("type") or ""))
                    ]
                    if non_heavy:
                        candidates = non_heavy
            chosen = sorted(
                candidates,
                key=lambda place: (
                    categories.index(place.category) if place.category in categories else len(categories),
                    -(place.guide_score or 0),
                    place.distance_meters if place.distance_meters is not None else 999_999,
                    place.name,
                ),
            )[0]
            used.add(chosen.id)
            return chosen

        return (
            pick(["park", "shop", "cafe", "food", "place"], morning_friendly=True),
            pick(["cafe", "food"], morning_friendly=True),
            pick(["shop", "food", "cafe"]),
            pick(["netcafe", "cafe", "shop", "food"]),
            pick(["park", "shop", "food", "cafe", "place"]),
        )

    def _worldcup_plan(
        self,
        pet: PetRecord,
        city: JourneyCity,
        now: datetime,
        places: list[PlaceSignal],
    ) -> JourneyPlan:
        stadium = PlaceSignal(
            id="worldcup-los-angeles-stadium",
            name="世界杯赛场外广场",
            category="stadium",
            city="洛杉矶",
            lat=34.0141,
            lng=-118.2879,
            activity_hint="在赛场外听见很远的欢呼声",
            detail_hint="抵达赛场附近前，TA 会先经历一段真实时间感很强的长途移动。",
            source=self.provider_name,
        )
        airport = PlaceSignal(
            id="worldcup-arrival-airport",
            name="洛杉矶机场到达层",
            category="airport",
            city="洛杉矶",
            lat=33.9416,
            lng=-118.4085,
            activity_hint="从到达层慢慢辨认新的空气",
            detail_hint="这里是长途交通后的缓冲停留点。",
            source=self.provider_name,
        )
        cafe = PlaceSignal(
            id="worldcup-stadium-cafe",
            name="赛场附近咖啡店",
            category="cafe",
            city="洛杉矶",
            lat=34.0125,
            lng=-118.2902,
            activity_hint="在赛场附近咖啡店里等球迷经过",
            detail_hint="比赛前可以进店坐一会儿，发回一张带灯光和人群的自拍或小卡片。",
            source=self.provider_name,
        )
        plan_places = [places[0], airport, cafe, stadium]
        stops = [
            self._stop(places[0], "出发前确认气味", "TA 会先在熟悉的城市里慢慢醒来。", "08:10", 40),
            self._stop(airport, "长途交通后的缓冲", "抵达后不会立刻去赛场，会先安静地适应新地方。", "16:30", 70),
            self._stop(cafe, "赛场附近等待", "有饮料、屏幕和人群，但 TA 会选择不太拥挤的角落。", "18:00", 85, photo=True),
            self._stop(stadium, "在赛场外听比赛", "TA 不需要真的进场，也能把热闹的声音寄给你。", "20:00", 120, postcard=True),
        ]
        segments = [
            RouteSegment(
                id="home-city-to-la-flight",
                mode=TravelMode.flight,
                title="长途飞行段",
                detail="这是一段很长的跨城移动，手机会按真实时间慢慢推进。",
                from_place=places[0].name,
                to_place=airport.name,
                distance_meters=11_100_000,
                duration_seconds=43_200,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="airport-to-cafe-drive",
                mode=TravelMode.drive,
                title="落地后前往赛场附近",
                detail="落地后不会立刻跳到赛场，TA 会先沿城市道路靠近附近的停留点。",
                from_place=airport.name,
                to_place=cafe.name,
                distance_meters=19_600,
                duration_seconds=2_200,
                provider=self.provider_name,
            ),
            RouteSegment(
                id="cafe-to-stadium-walk",
                mode=TravelMode.walk,
                title="步行到赛场外",
                detail="最后一段步行，保留 TA 走走停停的电子宠物节奏。",
                from_place=cafe.name,
                to_place=stadium.name,
                distance_meters=650,
                duration_seconds=720,
                provider=self.provider_name,
            ),
        ]
        return JourneyPlan(
            pet_id=pet.pet_id,
            city=stadium.city,
            generated_at=now,
            provider=self.provider_name,
            horizon_hours=48,
            summary=f"{pet.name} 被远处的比赛声吸引，准备去世界杯赛场外看看。",
            current_activity=places[0].activity_hint,
            transport_decision=TransportDecision(
                selected_mode=TravelMode.flight,
                reason="目的地跨洋，步行、驾车和火车都不符合真实世界原则。",
                rejected_modes=[TravelMode.walk, TravelMode.drive, TravelMode.train],
                autonomy_note="这是 TA 自己被比赛氛围吸引后的选择，不是用户下达的命令。",
            ),
            route_segments=segments,
            scheduled_transport=self.transport_provider.worldcup_legs(
                pet=pet,
                origin=places[0],
                airport=airport,
                cafe=cafe,
                stadium=stadium,
                now=now,
            ),
            stops=stops,
            places=plan_places,
            next_postcard_hint="比赛开始前，TA 会从赛场外发回一张有灯光和人群的照片。",
            worldcup_event=True,
        )

    def _stop(
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
            id=f"stop-{place.id}",
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


class RemoteTravelRoutePlanner:
    provider_name = "remote-route-planner-placeholder"

    def __init__(
        self,
        settings: Settings,
        map_provider: MapProvider,
        transport_provider: TransportRealityProvider,
        amap_client: AMapWebServiceClient | None = None,
        google_client: GoogleMapsServiceClient | None = None,
    ):
        self.settings = settings
        self.fallback = MockTravelRoutePlanner(settings, map_provider, transport_provider)
        self.amap_client = amap_client
        self.google_client = google_client
        if settings.map_provider == "amap" and amap_client and amap_client.configured:
            self.provider_name = "amap-enhanced-route-planner"
        if google_client and google_client.configured:
            self.provider_name = "google-enhanced-route-planner"
        if amap_client and amap_client.configured and google_client and google_client.configured:
            self.provider_name = "hybrid-real-route-planner"

    def build_journey_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyPlan:
        plan = self.fallback.build_journey_plan(pet, city, now)
        if not self._has_route_provider():
            return plan
        return plan.model_copy(
            update={
                "provider": self.provider_name,
                "route_segments": self._enrich_route_segments(plan),
            }
        )

    def build_route_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyRoutePlan:
        return adapt_journey_plan_to_route_plan(self.build_journey_plan(pet, city, now))

    def _enrich_route_segments(self, plan: JourneyPlan) -> list[RouteSegment]:
        stops_by_name = {stop.name: stop for stop in plan.stops}
        enriched: list[RouteSegment] = []
        for segment in plan.route_segments:
            origin = stops_by_name.get(segment.from_place)
            destination = stops_by_name.get(segment.to_place)
            if (
                not origin
                or not destination
                or segment.mode not in {TravelMode.walk, TravelMode.drive, TravelMode.transit}
            ):
                enriched.append(segment)
                continue
            route = self._route_between(segment.mode, origin, destination)
            if not route:
                enriched.append(segment)
                continue
            enriched.append(
                segment.model_copy(
                    update={
                        "distance_meters": route.distance_meters or segment.distance_meters,
                        "duration_seconds": route.duration_seconds or segment.duration_seconds,
                        "provider": route.provider,
                        "polyline": route.polyline or segment.polyline,
                        "is_simulated": False,
                    }
                )
            )
        return enriched

    def _has_route_provider(self) -> bool:
        return bool(
            (self.amap_client and self.amap_client.configured)
            or (self.google_client and self.google_client.configured)
        )

    def _route_between(self, mode: TravelMode, origin: ItineraryStop, destination: ItineraryStop):
        if is_china_city_name(origin.city) and self.amap_client and self.amap_client.configured:
            if mode not in {TravelMode.walk, TravelMode.drive}:
                return None
            try:
                return self.amap_client.route_between(
                    mode=mode,
                    origin_lng=origin.lng,
                    origin_lat=origin.lat,
                    destination_lng=destination.lng,
                    destination_lat=destination.lat,
                )
            except Exception:
                return None
        if self.google_client and self.google_client.configured:
            try:
                return self.google_client.route_between(
                    mode=mode,
                    origin_lng=origin.lng,
                    origin_lat=origin.lat,
                    destination_lng=destination.lng,
                    destination_lat=destination.lat,
                )
            except Exception:
                return None
        return None


def adapt_journey_plan_to_route_plan(plan: JourneyPlan) -> JourneyRoutePlan:
    steps: list[RouteStep] = []
    for stop in plan.stops:
        steps.append(
            RouteStep(
                id=f"{stop.id}-stay",
                mode=TravelMode.stay.value,
                title=stop.title,
                detail=stop.detail,
                from_place=stop.name,
            )
        )
    for segment in plan.route_segments:
        steps.append(
            RouteStep(
                id=segment.id,
                mode=segment.mode.value,
                title=segment.title,
                detail=segment.detail,
                start_time=segment.start_time,
                end_time=segment.end_time,
                from_place=segment.from_place,
                to_place=segment.to_place,
            )
        )
    return JourneyRoutePlan(
        pet_id=plan.pet_id,
        city=plan.city,
        generated_at=plan.generated_at,
        provider=plan.provider,
        steps=steps,
        places=plan.places,
    )


def build_route_planner(
    settings: Settings,
    map_provider: MapProvider,
    transport_provider: TransportRealityProvider | None = None,
    amap_client: AMapWebServiceClient | None = None,
    google_client: GoogleMapsServiceClient | None = None,
) -> TravelRoutePlanner:
    transport_provider = transport_provider or build_transport_reality_provider()
    if settings.provider_mode == "remote" or settings.amap_api_key or settings.google_maps_api_key:
        return RemoteTravelRoutePlanner(settings, map_provider, transport_provider, amap_client, google_client)
    return MockTravelRoutePlanner(settings, map_provider, transport_provider)


def is_china_city_name(city_name: str) -> bool:
    return city_name in {"厦门", "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京", "武汉", "西安"}
