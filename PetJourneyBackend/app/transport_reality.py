from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Protocol

from .config import Settings
from .providers import JourneyCity
from .schemas import PlaceSignal, ScheduledTransportLeg, TransportLegStatus, TravelMode
from .storage import PetRecord
from .transport_schedule import (
    MockTransportScheduleProvider,
    TransportScheduleCandidate,
    TransportScheduleProvider,
    TransportScheduleRequest,
    build_transport_schedule_provider,
)


class TransportRealityProvider(Protocol):
    provider_name: str

    def local_life_legs(
        self,
        pet: PetRecord,
        city: JourneyCity,
        places: list[PlaceSignal],
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        ...

    def worldcup_legs(
        self,
        pet: PetRecord,
        origin: PlaceSignal,
        airport: PlaceSignal,
        cafe: PlaceSignal,
        stadium: PlaceSignal,
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        ...


class MockTransportRealityProvider:
    base_provider_name = "mock-scheduled-transport-provider"

    def __init__(self, schedule_provider: TransportScheduleProvider | None = None):
        self.schedule_provider = schedule_provider or MockTransportScheduleProvider()
        self.provider_name = self.base_provider_name
        if self.schedule_provider.provider_name != MockTransportScheduleProvider.provider_name:
            self.provider_name = f"{self.base_provider_name}+{self.schedule_provider.provider_name}"

    def local_life_legs(
        self,
        pet: PetRecord,
        city: JourneyCity,
        places: list[PlaceSignal],
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        if len(places) < 4:
            return []

        base = self._local_day_start(now)
        return [
            self._leg(
                id="local-walk-to-coffee",
                mode=TravelMode.walk,
                title="步行去下一处停留点",
                detail="这段会按真实道路慢慢走，TA 会用自己的节奏靠近下一处停留点。",
                origin=places[0],
                destination=places[1],
                departure=base + timedelta(minutes=90),
                duration=timedelta(minutes=18),
                now=now,
                distance_meters=1250,
                carrier=None,
                service_number=None,
                terminal_or_platform=None,
                reality_level="mock_local_schedule",
                timeline_note=f"{pet.name} 会先走一小段路，像真实散步一样慢慢靠近 {places[1].name}。",
            ),
            self._leg(
                id="local-drive-to-long-stay",
                mode=TravelMode.drive,
                title="短途搭车去长时间停留点",
                detail="距离稍远时不强行步行，交通方式会像真实世界一样切换。",
                origin=places[2],
                destination=places[3],
                departure=base + timedelta(hours=5, minutes=20),
                duration=timedelta(minutes=16),
                now=now,
                distance_meters=3100,
                carrier="本地道路",
                service_number="短途车程",
                terminal_or_platform=None,
                reality_level="mock_local_schedule",
                timeline_note=f"{pet.name} 不是一直走路，远一点的地方会搭一小段车。",
            ),
        ]

    def worldcup_legs(
        self,
        pet: PetRecord,
        origin: PlaceSignal,
        airport: PlaceSignal,
        cafe: PlaceSignal,
        stadium: PlaceSignal,
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        base = self._base_time(pet)
        flight_departure = base + timedelta(hours=2)
        flight_duration = timedelta(hours=12)
        flight_legs = self._worldcup_flight_legs(
            pet=pet,
            origin=origin,
            airport=airport,
            departure=flight_departure,
            duration=flight_duration,
            now=now,
        )
        drive_departure = flight_legs[-1].scheduled_arrival + timedelta(minutes=45)
        return [
            *flight_legs,
            self._leg(
                id="worldcup-airport-to-cafe-drive",
                mode=TravelMode.drive,
                title="落地后短途车程",
                detail="落地后先去赛场附近适应环境，不会立刻跳到打卡点。",
                origin=airport,
                destination=cafe,
                departure=drive_departure,
                duration=timedelta(minutes=36),
                now=now,
                distance_meters=19_600,
                carrier="本地道路",
                service_number="机场至赛场附近",
                terminal_or_platform=None,
                reality_level="mock_local_schedule",
                timeline_note=f"{pet.name} 落地后会先坐一段车，慢慢接近比赛的声音。",
            ),
            self._leg(
                id="worldcup-cafe-to-stadium-walk",
                mode=TravelMode.walk,
                title="步行到赛场外",
                detail="最后一段保留走走停停的节奏，像真的在附近靠近人群。",
                origin=cafe,
                destination=stadium,
                departure=drive_departure + timedelta(minutes=70),
                duration=timedelta(minutes=12),
                now=now,
                distance_meters=650,
                carrier=None,
                service_number=None,
                terminal_or_platform=None,
                reality_level="mock_local_schedule",
                timeline_note=f"{pet.name} 会从咖啡店慢慢走到赛场外。",
            ),
        ]

    def _worldcup_flight_legs(
        self,
        *,
        pet: PetRecord,
        origin: PlaceSignal,
        airport: PlaceSignal,
        departure: datetime,
        duration: timedelta,
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        candidates = self._schedule_itinerary(
            TransportScheduleRequest(
                pet=pet,
                mode=TravelMode.flight,
                origin=origin,
                destination=airport,
                depart_after=departure,
                now=now,
                context=(
                    "World Cup easter egg journey. Need a real public flight reference and time only. "
                    "Direct is preferred, but transfer flights are acceptable if no direct service is clear. "
                    "Travel or ticketing websites can be used as schedule references only. "
                    "Do not need seats, price, booking, or ticket purchase."
                ),
            )
        )
        if candidates:
            return self._legs_from_schedule_candidates(
                pet=pet,
                origin=origin,
                destination=airport,
                candidates=candidates,
                now=now,
            )

        return [
            self._leg(
                id="worldcup-shadow-flight",
                mode=TravelMode.flight,
                title="长途飞行影子段",
                detail="手机会按真实的起降节奏推进这段长途移动，只记录时间、航线和抵达感。",
                origin=origin,
                destination=airport,
                departure=departure,
                duration=duration,
                now=now,
                distance_meters=11_100_000,
                carrier="航班数据源待接入",
                service_number="FLIGHT-DEMO",
                terminal_or_platform="候机中",
                reality_level="mock_flight_schedule",
                timeline_note=f"{pet.name} 会经历候机、起飞、飞行和落地，而不是瞬间到达。",
            )
        ]

    def _schedule_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        best_itinerary = getattr(self.schedule_provider, "best_itinerary", None)
        if callable(best_itinerary):
            return list(best_itinerary(search))
        candidate = self.schedule_provider.best_candidate(search)
        return [candidate] if candidate else []

    def _legs_from_schedule_candidates(
        self,
        *,
        pet: PetRecord,
        origin: PlaceSignal,
        destination: PlaceSignal,
        candidates: list[TransportScheduleCandidate],
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        legs: list[ScheduledTransportLeg] = []
        total = len(candidates)
        for index, candidate in enumerate(candidates):
            segment_origin = self._candidate_endpoint(
                base=origin,
                fallback=destination,
                candidate_name=candidate.origin_name,
                index=index,
                total=total,
            )
            segment_destination = self._candidate_endpoint(
                base=origin,
                fallback=destination,
                candidate_name=candidate.destination_name,
                index=index + 1,
                total=total,
            )
            legs.append(
                self._leg_from_schedule_candidate(
                    id="worldcup-shadow-flight" if total == 1 else f"worldcup-shadow-flight-{index + 1}",
                    title="参考真实航班前往赛场城市" if total == 1 else f"参考真实航班中转段 {index + 1}/{total}",
                    origin=segment_origin,
                    destination=segment_destination,
                    candidate=candidate,
                    now=now,
                    timeline_note=(
                        f"{pet.name} 查到 {candidate.service_number} 的公开时间线，"
                        "会按候机、起飞、飞行、落地的节奏慢慢推进。"
                        if total == 1
                        else f"{pet.name} 查到中转第 {index + 1}/{total} 段 {candidate.service_number}，会把换乘也当成旅程的一部分。"
                    ),
                )
            )
        return legs

    def _candidate_endpoint(
        self,
        *,
        base: PlaceSignal,
        fallback: PlaceSignal,
        candidate_name: str,
        index: int,
        total: int,
    ) -> PlaceSignal:
        if total <= 0:
            total = 1
        fraction = max(0.0, min(1.0, index / total))
        return PlaceSignal(
            id=f"transport-endpoint-{index}-{candidate_name}",
            name=candidate_name,
            category="transport_hub",
            city=fallback.city if fraction >= 1 else base.city,
            lat=base.lat + (fallback.lat - base.lat) * fraction,
            lng=base.lng + (fallback.lng - base.lng) * fraction,
            activity_hint="沿真实交通时间线移动",
            detail_hint="中转点坐标会在接入机场/车站 API 后替换为真实位置。",
            source=self.schedule_provider.provider_name,
        )

    def _leg(
        self,
        *,
        id: str,
        mode: TravelMode,
        title: str,
        detail: str,
        origin: PlaceSignal,
        destination: PlaceSignal,
        departure: datetime,
        duration: timedelta,
        now: datetime,
        distance_meters: int,
        carrier: str | None,
        service_number: str | None,
        terminal_or_platform: str | None,
        reality_level: str,
        timeline_note: str,
    ) -> ScheduledTransportLeg:
        arrival = departure + duration
        return ScheduledTransportLeg(
            id=id,
            mode=mode,
            status=self._status(now=now, departure=departure, arrival=arrival),
            title=title,
            detail=detail,
            origin_name=origin.name,
            destination_name=destination.name,
            origin_lat=origin.lat,
            origin_lng=origin.lng,
            destination_lat=destination.lat,
            destination_lng=destination.lng,
            scheduled_departure=departure,
            scheduled_arrival=arrival,
            carrier=carrier,
            service_number=service_number,
            terminal_or_platform=terminal_or_platform,
            distance_meters=distance_meters,
            duration_seconds=int(duration.total_seconds()),
            route_polyline=f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}",
            progress=self._progress(now=now, departure=departure, arrival=arrival),
            provider=self.provider_name,
            reality_level=reality_level,
            is_simulated=True,
            timeline_note=timeline_note,
        )

    def _leg_from_schedule_candidate(
        self,
        *,
        id: str,
        title: str,
        origin: PlaceSignal,
        destination: PlaceSignal,
        candidate: TransportScheduleCandidate,
        now: datetime,
        timeline_note: str,
    ) -> ScheduledTransportLeg:
        duration = candidate.scheduled_arrival - candidate.scheduled_departure
        detail = candidate.notes or "公开网页只用于参考航班号/车次和时间，不处理余票、价格或购票。"
        return ScheduledTransportLeg(
            id=id,
            mode=candidate.mode,
            status=self._status(
                now=now,
                departure=candidate.scheduled_departure,
                arrival=candidate.scheduled_arrival,
            ),
            title=title,
            detail=detail,
            origin_name=candidate.origin_name or origin.name,
            destination_name=candidate.destination_name or destination.name,
            origin_lat=origin.lat,
            origin_lng=origin.lng,
            destination_lat=destination.lat,
            destination_lng=destination.lng,
            scheduled_departure=candidate.scheduled_departure,
            scheduled_arrival=candidate.scheduled_arrival,
            carrier=candidate.carrier,
            service_number=candidate.service_number,
            terminal_or_platform=candidate.terminal_or_platform,
            distance_meters=None,
            duration_seconds=int(duration.total_seconds()),
            route_polyline=f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}",
            progress=self._progress(
                now=now,
                departure=candidate.scheduled_departure,
                arrival=candidate.scheduled_arrival,
            ),
            provider=self.schedule_provider.provider_name,
            reality_level=candidate.reality_level,
            is_simulated=candidate.is_simulated,
            timeline_note=timeline_note,
            source_urls=list(candidate.source_urls),
            confidence=candidate.confidence,
            search_query=candidate.search_query,
        )

    def _status(self, *, now: datetime, departure: datetime, arrival: datetime) -> TransportLegStatus:
        now = now.astimezone(timezone.utc)
        departure = departure.astimezone(timezone.utc)
        arrival = arrival.astimezone(timezone.utc)
        if now >= arrival:
            return TransportLegStatus.arrived
        if now >= departure:
            return TransportLegStatus.in_transit
        if now >= departure - timedelta(minutes=20):
            return TransportLegStatus.boarding
        if now >= departure - timedelta(minutes=60):
            return TransportLegStatus.waiting
        return TransportLegStatus.scheduled

    def _progress(self, *, now: datetime, departure: datetime, arrival: datetime) -> float:
        total = max(1.0, (arrival - departure).total_seconds())
        elapsed = (now - departure).total_seconds()
        return round(max(0.0, min(1.0, elapsed / total)), 3)

    def _base_time(self, pet: PetRecord) -> datetime:
        return pet.created_at.astimezone(timezone.utc)

    def _local_day_start(self, now: datetime) -> datetime:
        local_now = now.astimezone()
        return datetime.combine(local_now.date(), time(hour=7, minute=20), tzinfo=local_now.tzinfo)


def build_transport_reality_provider(settings: Settings | None = None) -> TransportRealityProvider:
    return MockTransportRealityProvider(build_transport_schedule_provider(settings))
