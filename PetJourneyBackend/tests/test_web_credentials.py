"""证件卡包（对齐说明 §5）：编号稳定、签发时间持久、同一事件只签发一次；护照纪念章；登机牌随行程变化；跨账号隔离。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from app.schemas import EconomyTransactionType
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class CredentialWalletTests(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("card-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def cards(self, owner=None) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for card in (owner or self.owner).get("/credentials").json():
            result.setdefault(card["kind"], []).append(card)
        return result

    def test_move_in_issues_identity_bank_and_care_once_with_persistent_dates(self) -> None:
        cards = self.cards()
        for kind in ("identity_card", "bank_card", "care_profile"):
            self.assertEqual(cards[kind][0]["status"], "active")
            self.assertTrue(cards[kind][0]["number"])
        self.assertTrue(cards["care_profile"][0]["private"])
        for kind in ("passport", "driver_license", "boarding_pass", "hotel_key"):
            self.assertEqual((cards[kind][0]["status"], cards[kind][0]["credential_id"]), ("not_obtained", None))
            self.assertTrue(cards[kind][0]["condition"])
        first = cards["identity_card"][0]
        self.assertEqual(datetime.fromisoformat(first["issued_at"]), LUNCH_UTC, "签发时间就是入住时间")
        self.clock.advance(days=3)
        again = self.cards()["identity_card"][0]
        self.assertEqual((again["number"], again["issued_at"]), (first["number"], first["issued_at"]), "刷新、隔几天都不重新签发")
        timeline = [i for i in self.owner.get("/timeline").json() if i["kind"] == "credential"]
        self.assertEqual(sorted(i["title"] for i in timeline), sorted(["拿到星球身份证", "开通星球银行卡", "建立照护档案"]), "入住时的证件进时间线，只记一次")

    def test_numbers_are_unique_and_cards_are_private_to_the_owner(self) -> None:
        other = self.user("card-other")
        other.adopt_and_move_in("adopt-pudding")
        mine, theirs = self.cards()["identity_card"][0], self.cards(other)["identity_card"][0]
        self.assertNotEqual(mine["number"], theirs["number"])
        self.assert_envelope(other.get(f"/credentials/{mine['credential_id']}"), 404, "NOT_FOUND")

    def test_bank_card_is_the_existing_wallet_with_its_ledger(self) -> None:
        bank = self.cards()["bank_card"][0]
        detail = self.owner.get(f"/credentials/{bank['credential_id']}").json()
        self.assertEqual(detail["balance"], self.owner.home()["wallet"]["balance"], "同一个账户，不另建余额")
        self.assertTrue(any(entry["delta"] > 0 for entry in detail["ledger"]), "入住欢迎旅费在流水里")
        care = self.owner.get(f"/credentials/{self.cards()['care_profile'][0]['credential_id']}").json()
        self.assertTrue(care["summary"]["private"])

    def test_formal_trip_issues_passport_once_tickets_follow_the_legs_and_arrival_stamps(self) -> None:
        self.web.economy.apply(self.owner.pet_id, 300, EconomyTransactionType.web_reward, "test:tokyo", reason="测试", source="test")
        legs = self.owner.post("/journey/depart", {"destination_key": "tokyo_flight"}).json()["legs"]
        cards = self.cards()
        passport = cards["passport"][0]
        self.assertEqual(passport["status"], "active")
        self.assertEqual(len(cards["boarding_pass"]), 2, "去程与回程两张登机牌")
        self.assertEqual(len(cards["transport_ticket"]), 2, "来回两张火车票")
        flight = next(l for l in legs if l["mode"] == "flight" and l["kind"] == "main")
        boarding = next(c for c in cards["boarding_pass"] if flight["leg_id"] in [link["ref_id"] for link in c["links"]])
        self.assertEqual(boarding["status"], "active")
        self.clock.now = datetime.fromisoformat(flight["times"]["planned_departure_utc"]) + timedelta(minutes=10)
        self.assertEqual(next(c for c in self.cards()["boarding_pass"] if c["credential_id"] == boarding["credential_id"])["status"], "in_progress")
        self.clock.now = datetime.fromisoformat(flight["times"]["planned_arrival_utc"]) + timedelta(minutes=1)
        self.owner.get("/journey/map")
        self.assertEqual(next(c for c in self.cards()["boarding_pass"] if c["credential_id"] == boarding["credential_id"])["status"], "used")
        detail = self.owner.get(f"/credentials/{passport['credential_id']}").json()
        self.assertEqual([s["city"] for s in detail["stamps"]], ["东京"], "到达后盖纪念章")
        self.clock.advance(days=2)
        self.owner.get("/journey/map")
        self.owner.post("/journey/depart", {"destination_key": "macau_ferry"})
        passports = self.cards()["passport"]
        self.assertEqual(len(passports), 1)
        self.assertEqual(passports[0]["number"], passport["number"], "护照只签发一次")
        self.assertEqual(len(passports[0]["links"]), 2, "第二次出远门关联到同一本护照")


if __name__ == "__main__":
    unittest.main()
