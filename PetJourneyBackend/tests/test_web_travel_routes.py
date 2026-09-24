"""旅行心愿的只读路由（TRV-00 §23.4；6c2b 2026-09-24 报 `/travel/wish` 与 `/travel/plans/{id}` 都 404）。

钉的是前端依赖的几件事：
  · 没有心愿是正常状态：200 ＋ null，不是 404；
  · 有心愿时字段按 A 的只读视图原样组装（状态、候选、等待原因），候选 `executable` 字面常假；
  · 别人家的宠物读不到；GET 不写库；
  · 计划那条的用例在 `test_web_travel_plan_route.py`（先挂过占位，A 补齐手账视图字段后已换成实现；
    不存在的计划回带 `plan_not_found` 原因的结构化 404，与路由没挂时的裸 404 分得开）。
"""

from __future__ import annotations

import unittest

from web_base import WebPlatformTestBase

SEA = {"destination_key": "hk-repulse-bay", "name": "浅水湾", "city": "香港"}
PARK = {"destination_key": "hk-victoria-park", "name": "维多利亚公园", "city": "香港"}


class TravelWishRouteTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("wish-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def propose(self) -> None:
        self.web.travel.wishes.propose(pet_id=self.owner.pet_id, user_id=self.owner.user_id, trigger_event_id="evt-wish-1",
                                       candidates=[SEA, PARK], selected=0, interest_tags=[], owner_reason="上次聊到想看海",
                                       funds_goal=None)

    def test_no_wish_is_200_and_null(self) -> None:
        response = self.owner.get("/travel/wish", params={"pet_id": self.owner.pet_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json(), "没有心愿是正常状态，不是 404")

    def test_an_active_wish_is_assembled_from_the_view(self) -> None:
        self.propose()
        body = self.owner.get("/travel/wish", params={"pet_id": self.owner.pet_id}).json()
        view = self.web.travel.wishes.read(self.owner.pet_id)
        self.assertEqual((body["wish_id"], body["status"], body["destination_name"], body["city"]),
                         (view.wish_id, view.status, "浅水湾", "香港"))
        self.assertEqual([c["title"] for c in body["candidates"]], ["浅水湾", "维多利亚公园"])
        self.assertTrue(all(c["executable"] is False for c in body["candidates"]), "候选不能拿去出发（合同 §3）")
        self.assertEqual(body["waiting_reasons"], list(view.waiting_reasons))
        self.assertEqual(body["owner_reason"], "上次聊到想看海")

    def test_pet_id_may_be_omitted_when_there_is_exactly_one_pet(self) -> None:
        self.propose()
        self.assertEqual(self.owner.get("/travel/wish").json()["destination_name"], "浅水湾", "合同 §29.5：沿用 require_pet 的惯例")

    def test_another_household_cannot_read_it(self) -> None:
        self.propose()
        stranger = self.user("wish-stranger")
        response = stranger.get("/travel/wish", params={"pet_id": self.owner.pet_id})
        self.assertIn(response.status_code, (403, 404), response.text)
        self.assertNotIn("浅水湾", response.text)

    def test_reading_writes_nothing(self) -> None:
        self.propose()
        with self.app.state.storage.connect() as conn:
            before = conn.execute("SELECT wish_revision, updated_at FROM web_travel_wishes WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()
        self.owner.get("/travel/wish", params={"pet_id": self.owner.pet_id})
        with self.app.state.storage.connect() as conn:
            after = conn.execute("SELECT wish_revision, updated_at FROM web_travel_wishes WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()
        self.assertEqual(tuple(before), tuple(after))


if __name__ == "__main__":
    unittest.main()
