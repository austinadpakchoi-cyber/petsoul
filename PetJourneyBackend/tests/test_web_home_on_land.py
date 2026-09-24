"""家与「星球内」去处不落在海面上（6c2b 2026-09-24 巡检 P1：「香港·西贡的海边」的家落在海里、宠物在水里走；中环出门的路线直通维港）。

根因：家原先在片区参考点周围随机偏移最多 900 米，而中环北边是维港、西贡东南边是海；没有地图服务时，「星球内」的去处
一律放在家北边约 500 米。改法：有陆地锚点的片区（`LAND_ANCHORS`，逐个用 OpenStreetMap 反查核过）只在锚点 40 米内取点。

钉的是：新家、没选过环境的家、旧库里已落库的家（迁移 0415）、家附近的去处，都落在某个陆地锚点 40 米内；
而且落点稳定（同一个家每次同一点）、不同的家不全叠在一起。
"""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from app.web_home.place import ANCHOR_FUZZ_METERS, AREAS, LAND_ANCHORS, HomePlace, HomePlaceStore, land_point, nearby_spot
from app.web_platform.migrations import m0415_home_places_on_land as m0415
from web_base import WebPlatformTestBase

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = math.radians(b[0] - a[0])
    dlng = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return 6_371_000 * math.hypot(dlat, dlng)


def near_an_anchor(area_key: str, point: tuple[float, float]) -> bool:
    return min(meters(anchor, point) for anchor in LAND_ANCHORS[area_key]) <= ANCHOR_FUZZ_METERS + 1  # 1 米是坐标取 5 位小数的舍入


class HomeOnLandTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.places = HomePlaceStore(self.app.state.storage)

    def test_new_homes_in_coastal_areas_land_near_a_verified_anchor(self) -> None:
        for habitat, area_key in (("seaside", "hk_saikung"), ("city", "hk_central")):
            for n in range(20):
                with self.subTest(habitat=habitat, home=n):
                    place = self.places.assign(f"home-land-{habitat}-{n}", habitat, NOW, open_only=True)
                    self.assertEqual(place.area_key, area_key)
                    self.assertTrue(near_an_anchor(area_key, (place.lat, place.lng)), (place.lat, place.lng))

    def test_a_home_that_never_chose_lands_near_a_central_anchor_and_stays_put(self) -> None:
        first, again = self.places.get("home-no-choice-1"), self.places.get("home-no-choice-1")
        self.assertTrue(near_an_anchor("hk_central", (first.lat, first.lng)))
        self.assertEqual((first.lat, first.lng), (again.lat, again.lng), "同一个家每次同一点，地图上不会自己漂")
        spread = {(self.places.get(f"home-no-choice-{n}").lat, self.places.get(f"home-no-choice-{n}").lng) for n in range(12)}
        self.assertGreater(len(spread), 3, "不同的家不全叠在一个点上")

    def test_stored_homes_in_the_sea_are_moved_onto_land(self) -> None:
        """旧库里按旧算法落库的家（这里放一个维港正中的点）：迁移按同一个种子挪到陆地锚点附近。"""
        owner = self.user("land-migrate")
        owner.adopt_and_move_in("adopt-lan")
        home_id = self.web.homes.by_pet(owner.pet_id).home_id
        chosen_at = "2026-09-20T00:00:00+00:00"
        with self.app.state.storage.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO web_home_places (home_id, habitat, area_key, lat, lng, chosen_at) VALUES (?, 'city', 'hk_central', ?, ?, ?)",
                         (home_id, 22.2900, 114.1640, chosen_at))  # 维港里
            m0415._apply(conn)
        place = self.places.get(home_id)
        self.assertTrue(near_an_anchor("hk_central", (place.lat, place.lng)), (place.lat, place.lng))
        self.assertEqual((place.lat, place.lng), land_point("hk_central", f"{home_id}:city:{chosen_at}"), "与新家同一个算法、同一个种子")

    def test_nearby_spots_are_on_another_land_anchor(self) -> None:
        for habitat, area_key in (("seaside", "hk_saikung"), ("city", "hk_central")):
            for n in range(10):
                home = self.places.assign(f"home-spot-{area_key}-{n}", habitat, NOW, open_only=True)
                with self.subTest(area=area_key, home=n):
                    spot = nearby_spot(home, f"spot-{n}")
                    self.assertTrue(near_an_anchor(area_key, spot), spot)
                    self.assertGreater(meters((home.lat, home.lng), spot), 20, "去处不是家门口本身")

    def test_areas_without_anchors_keep_the_old_offset(self) -> None:
        """没有锚点的片区还没开放、家分不到那里，所以直接用纯函数核：照旧按原来的固定偏移。"""
        habitat, area = AREAS["xm_huandao"]
        home = HomePlace(habitat, "海边", area.key, area.label, area.city, area.lat, area.lng, area.timezone, True)
        self.assertEqual(nearby_spot(home, "x"), (round(area.lat + 0.0045, 5), round(area.lng + 0.003, 5)))
        self.assertIsNone(land_point("xm_huandao", "x"))

    def test_the_world_state_puts_a_new_home_on_land(self) -> None:
        owner = self.user("land-world")
        owner.adopt_and_move_in("adopt-lan")
        home = owner.get("/world/state").json()["pets"][0]["home"]["center"]
        self.assertTrue(near_an_anchor("hk_central", (home["lat"], home["lng"])), home)


if __name__ == "__main__":
    unittest.main()
