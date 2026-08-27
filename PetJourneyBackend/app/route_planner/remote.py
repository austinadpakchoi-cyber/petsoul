"""远端路线规划器（架构审计 P1-2 包化）。"""

from __future__ import annotations

from datetime import datetime

from ..amap_services import AMapWebServiceClient
from ..config import Settings
from ..google_maps_services import GoogleMapsServiceClient
from ..providers import JourneyCity, MapProvider
from ..schemas import ItineraryStop, JourneyPlan, JourneyRoutePlan, PlaceSignal, RouteSegment, RouteStep, TransportDecision, TravelMode
from ..storage import PetRecord
from ..transport_reality import TransportRealityProvider
from .mock import MockTravelRoutePlanner
from .protocol import TravelRoutePlanner, adapt_journey_plan_to_route_plan, enforce_transport_reality

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
        return enforce_transport_reality(
            plan.model_copy(
                update={
                    "provider": self.provider_name,
                    "route_segments": self._enrich_route_segments(plan),
                }
            )
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
