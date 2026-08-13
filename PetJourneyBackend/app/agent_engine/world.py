"""世界模拟编排：世界快照、生活心跳、街区排行与静态地图。"""

from __future__ import annotations

from ..schemas import LifeTickResult, StaticMapAsset, StreetRankResponse, WorldSimulationSnapshot
from ..storage import utcnow


class WorldSimulationMixin:
    def world_snapshot(self, pet_id: str) -> WorldSimulationSnapshot:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        plan = self._journey_plan_for(pet, city, now)
        return self._life_snapshot(pet=pet, city=city, plan=plan, now=now)

    def life_tick(self, pet_id: str) -> LifeTickResult:
        snapshot = self.world_snapshot(pet_id)
        if snapshot.life_tick is None:
            raise RuntimeError("life tick unavailable")
        return snapshot.life_tick

    def street_rank(self, pet_id: str, theme: str) -> StreetRankResponse:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        return self.street_rank_engine.rank(pet=pet, city=city, theme=theme, weather=city.weather, now=now)

    def static_map_for_pet(self, pet_id: str, zoom: int = 14) -> StaticMapAsset:
        pet = self._pet(pet_id)
        elapsed = (utcnow() - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed)
        return self.amap_client.static_map_asset(center_lat=city.lat, center_lng=city.lng, zoom=zoom)
