"""出发站地点模板：文案与旅费可发布，路线与场所身份不可发布。

最要紧的一条：**已经出发的行程按出发时的那一版**。出发那一刻 title / city / fee 就被写进
`web_journeys` 行里、各段时间写进 `web_journey_legs`，所以改模板只影响此后新出发的。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, FakeClock


class DestinationContentTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.publisher = self.staff("dest-publisher", ["content_publisher"])
        self.publisher.login_ok()
        self.player = self.user("dest-owner")
        self.player.adopt_and_move_in("adopt-lan")

    def options(self) -> dict[str, dict]:
        response = self.player.get("/journey/destinations")
        self.assertEqual(response.status_code, 200, response.text)
        return {row["destination_key"]: row for row in response.json()}

    def publish(self, slug: str, body: dict, *, reason: str = "地点模板验收") -> dict:
        created = self.publisher.post("/content", {"content_type": "destination", "slug": slug,
                                                   "title": body["title"], "body": body})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        published = self.publisher.post(f"/content/{item['item_id']}/publish",
                                        {"revision": 1, "expected_version": item["version"], "reason": reason})
        self.assertEqual(published.status_code, 200, published.text)
        return item

    def test_published_copy_and_fee_reach_the_departure_list(self):
        before = self.options()["harbour_cafe"]
        self.assertEqual(before["title"], "海边咖啡馆")
        self.assertEqual(before["fee"], 8)

        self.publish("harbour_cafe", {"title": "海边咖啡馆（春日特惠）", "city": "香港",
                                      "summary": "春天到了，走几分钟去海边坐坐，这周旅费减半。", "fee": 4})

        after = self.options()["harbour_cafe"]
        self.assertEqual(after["title"], "海边咖啡馆（春日特惠）", "出发站列表必须读到已发布的那一版")
        self.assertEqual(after["fee"], 4)
        self.assertIn("春天", after["summary"])
        # 不可发布的两项由各段时长与承运人算出，保持不变
        self.assertEqual(after["total_minutes"], before["total_minutes"])
        self.assertEqual(after["modes"], before["modes"])

    def test_a_journey_already_underway_keeps_the_fee_and_title_it_departed_with(self):
        balance_before = self.web.economy.wallet(self.player.pet_id).balance
        departed = self.player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(departed.status_code, 200, departed.text)
        charged = balance_before - self.web.economy.wallet(self.player.pet_id).balance
        self.assertEqual(charged, 8, "出发时按当时的旅费扣")

        self.publish("harbour_cafe", {"title": "海边咖啡馆（改名了）", "city": "香港",
                                      "summary": "改了文案也涨了价。", "fee": 60})

        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT title, city, fee FROM web_journeys WHERE pet_id = ? ORDER BY departed_at DESC LIMIT 1",
                               (self.player.pet_id,)).fetchone()
        self.assertEqual(row["title"], "海边咖啡馆", "已经出发的这趟保留出发时的名字")
        self.assertEqual(row["fee"], 8, "已经出发的这趟不会被补收差价")
        self.assertEqual(self.web.economy.wallet(self.player.pet_id).balance, balance_before - 8,
                         "发布新旅费不会再从钱包里扣一次")

        snapshot = self.player.get("/journey/map").json()
        self.assertEqual(snapshot["destination_title"], "海边咖啡馆", "玩家在路上看到的还是出发时那一版")

    def test_routes_and_venue_cannot_be_published(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "destination", "slug": "harbour_cafe", "title": "x",
            "body": {"title": "海边咖啡馆", "city": "香港", "summary": "改一下", "fee": 8,
                     "outbound": [], "venue": {"name": "假的"}, "wish_keywords": ["假"]}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual({i["field"] for i in check["issues"]}, {"outbound", "venue", "wish_keywords"})
        self.assertTrue(any("世界事实" in i["message"] for i in check["issues"]), check)

    def test_fee_bounds_and_unknown_destination_are_rejected(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "destination", "slug": "harbour_cafe", "title": "x",
            "body": {"title": "海边咖啡馆", "city": "香港", "summary": "涨过头了", "fee": 99999}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual([i["field"] for i in check["issues"]], ["fee"])
        invented = self.publisher.post("/content", {"content_type": "destination", "slug": "moon-base",
                                                    "title": "月球基地",
                                                    "body": {"title": "月球基地", "city": "月球", "summary": "凭空造的", "fee": 10}})
        self.assertEqual(invented.status_code, 422, invented.text)

    def test_withdraw_returns_to_the_builtin_copy(self):
        item = self.publish("macau_ferry", {"title": "坐船去澳门（限时）", "city": "澳门",
                                            "summary": "限时活动文案。", "fee": 20})
        self.assertEqual(self.options()["macau_ferry"]["title"], "坐船去澳门（限时）")
        latest = self.publisher.get(f"/content/{item['item_id']}").json()["item"]
        withdrawn = self.publisher.post(f"/content/{item['item_id']}/withdraw",
                                        {"expected_version": latest["version"], "reason": "活动结束"})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        restored = self.options()["macau_ferry"]
        self.assertEqual(restored["title"], "坐船去澳门")
        self.assertEqual(restored["fee"], 40, "撤下之后旅费回到内置值")


if __name__ == "__main__":
    unittest.main()
