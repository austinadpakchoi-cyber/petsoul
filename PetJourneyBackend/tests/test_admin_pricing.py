"""平台调用成本：价格表只追加、没有价格就是未知、币种分开、按调用当时有效的价格估算。

所有调用都用真实的 BudgetLedger 造出来（预占 → 结清 / 未确认 / 没发出 / 过期），估算走后台接口；
选一个与"今天"无关的记账日（2026-09-02/03），不被别的调用混进来。
"""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from admin_base import AdminTestBase

from app.web_platform.budget import BudgetLedger

T0 = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
WINDOW = "?start=2026-09-02&end=2026-09-03"


class PricingBase(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.boss = self.owner()                      # 平台负责人：带 cost.manage
        self.sre = self.staff("cost-sre", ["sre"])    # 能看（provider.read），不能录价
        self.sre.login_ok()
        self.player = self.user("cost-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ledger = BudgetLedger(self.app.state.storage)

    def add_price(self, *, provider="image", purpose="illustration", currency="CNY", unit_price="0.2",
                  effective_from="2026-09-01T00:00:00+00:00", source_note="供应商价目页 2026-09（验收用）", key=None, staff=None):
        return (staff or self.boss).post("/costs/prices", {
            "provider": provider, "purpose": purpose, "currency": currency, "unit_price": unit_price,
            "effective_from": effective_from, "source_note": source_note, "model_note": "验收用模型说明"}, key=key)

    def call(self, operation_id: str, *, at: datetime, units: int = 1, provider="image", purpose="illustration",
             outcome: str | None = "succeeded", actual: int | None = None):
        """造一次调用：outcome=None 表示还在途；'expire' 表示预占过期。"""
        ttl = 5 if outcome == "expire" else 3600
        reservation = self.ledger.reserve(operation_id, provider=provider, purpose=purpose,
                                          subject_scope=f"pet:{self.player.pet_id}", units=units, ttl_seconds=ttl, now=at)
        if outcome == "expire":
            self.ledger.expire_stale(now=at + timedelta(seconds=30))
        elif outcome is not None:
            self.ledger.settle(reservation, outcome, actual_units=actual, now=at)
        return reservation

    def estimate(self, staff=None) -> dict:
        response = (staff or self.sre).get(f"/costs/estimate{WINDOW}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class PriceTableTests(PricingBase):
    def test_without_prices_costs_are_unknown_not_zero(self):
        self.call("est:none:1", at=T0)
        result = self.estimate()
        self.assertFalse(result["price_table_configured"])
        self.assertEqual(result["currencies"], {}, "没有按任何币种计价的调用，就不出现任何币种——不给 0")
        line = result["lines"][0]
        self.assertEqual((line["counted_units"], line["unpriced_units"], line["priced_units"]), (1, 1, 0))
        self.assertFalse(line["complete"])
        self.assertIsNone(result["billed"])

    def test_only_cost_manage_can_add_or_retire_and_everything_is_audited(self):
        self.assert_admin_error(self.add_price(staff=self.sre), 403, "FORBIDDEN")
        self.assertEqual(self.sre.get("/costs/prices").status_code, 200, "有 provider.read 就能看价格")
        created = self.add_price()
        self.assertEqual(created.status_code, 201, created.text)
        price = created.json()["price"]
        self.assertEqual((price["currency"], price["unit_price"], price["unit_price_micros"]), ("CNY", "0.2", 200000))
        self.assertEqual(price["status"], "active")

        self.assert_admin_error(self.sre.post(f"/costs/prices/{price['price_id']}/retire", {"reason": "越权作废"}), 403, "FORBIDDEN")
        retired = self.boss.post(f"/costs/prices/{price['price_id']}/retire", {"reason": "录错了，重新录"})
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()["price"]["status"], "retired")
        again = self.boss.post(f"/costs/prices/{price['price_id']}/retire", {"reason": "再作废一次"})
        self.assert_admin_error(again, 409, "CONFLICT")

        entries = self.boss.get("/audit?target_kind=price").json()["entries"]
        self.assertEqual(sorted(e["action"] for e in entries if e["status"] == "succeeded"), ["cost.price_add", "cost.price_retire"])
        added = next(e for e in entries if e["action"] == "cost.price_add")
        self.assertEqual(added["reason"], "供应商价目页 2026-09（验收用）", "价格的来源进审计")

    def test_price_input_is_validated(self):
        for unit_price in ("1e3", "-1", "0.1234567", "abc", "1,5", "99999999"):
            with self.subTest(unit_price=unit_price):
                error = self.assert_admin_error(self.add_price(unit_price=unit_price), 422, "VALIDATION_FAILED")
                self.assertEqual(error["details"]["field"], "unit_price")
        self.assert_admin_error(self.add_price(currency="EUR"), 422, "VALIDATION_FAILED")
        self.assert_admin_error(self.add_price(provider="Image!"), 422, "VALIDATION_FAILED")
        self.assert_admin_error(self.add_price(source_note="网上"), 422, "VALIDATION_FAILED")
        naive = self.assert_admin_error(self.add_price(effective_from="2026-09-01T00:00:00"), 422, "VALIDATION_FAILED")
        self.assertEqual(naive["details"]["field"], "effective_from")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM admin_provider_prices").fetchone()[0], 0)

    def test_rows_are_append_only_in_the_database(self):
        price_id = self.add_price().json()["price"]["price_id"]
        with self.app.state.storage.connect() as conn:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute("UPDATE admin_provider_prices SET unit_price_micros = 1 WHERE price_id = ?", (price_id,))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute("DELETE FROM admin_provider_prices WHERE price_id = ?", (price_id,))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):  # 作废也必须写清作废人、时间与原因
                conn.execute("UPDATE admin_provider_prices SET status = 'retired' WHERE price_id = ?", (price_id,))

    def test_same_key_replays_and_different_content_is_refused(self):
        first = self.add_price(key="op-price-once")
        self.assertEqual(first.status_code, 201, first.text)
        again = self.add_price(key="op-price-once")
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["replayed"])
        self.assertEqual(again.json()["price"]["price_id"], first.json()["price"]["price_id"])
        self.assert_admin_error(self.add_price(key="op-price-once", unit_price="0.3"), 409, "IDEMPOTENCY_KEY_REUSED")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM admin_provider_prices").fetchone()[0], 1)


class EstimateTests(PricingBase):
    def test_each_call_uses_the_price_in_effect_when_it_was_made(self):
        cheap = self.add_price(unit_price="0.2", effective_from="2026-09-01T00:00:00+00:00").json()["price"]["price_id"]
        dearer = self.add_price(unit_price="0.3", effective_from="2026-09-03T00:00:00+00:00").json()["price"]["price_id"]
        self.call("est:hist:1", at=T0)                                           # 9 月 2 日：0.2 × 1
        self.call("est:hist:2", at=T0 + timedelta(days=1), units=2, actual=2)    # 9 月 3 日：0.3 × 2
        result = self.estimate()
        self.assertEqual(result["currencies"]["CNY"]["estimated"], "0.8")
        self.assertEqual(result["lines"][0]["price_ids"], sorted([cheap, dearer]))
        self.assertTrue(result["lines"][0]["complete"])

    def test_currencies_stay_separate(self):
        self.add_price(provider="image", purpose="illustration", currency="CNY", unit_price="0.2")
        self.add_price(provider="llm", purpose="life_plan", currency="USD", unit_price="0.001")
        self.call("est:cur:img", at=T0)
        self.call("est:cur:llm1", at=T0, provider="llm", purpose="life_plan")
        self.call("est:cur:llm2", at=T0, provider="llm", purpose="life_plan")
        currencies = self.estimate()["currencies"]
        self.assertEqual(set(currencies), {"CNY", "USD"})
        self.assertEqual(currencies["CNY"]["estimated"], "0.2")
        self.assertEqual(currencies["USD"]["estimated"], "0.002")
        self.assertNotIn("total", currencies, "两种币不相加，也没有换算后的合计")

    def test_unconfirmed_unpriced_and_in_flight_are_kept_apart(self):
        self.add_price(unit_price="0.5")
        self.call("est:mix:settled", at=T0)                                            # 已结清 1
        self.call("est:mix:unknown", at=T0, units=2, outcome="unknown", actual=1)      # 未确认：已发出 1
        self.call("est:mix:expired", at=T0, units=2, outcome="expire")                 # 未确认：过期按预占 2
        self.call("est:mix:notsent", at=T0, units=2, outcome="not_sent")               # 确定没发出：不计
        self.call("est:mix:inflight", at=T0 + timedelta(minutes=5), outcome=None)      # 在途：不计
        self.call("est:mix:character", at=T0, purpose="character")                     # 没录价的用途
        result = self.estimate()
        self.assertEqual(result["currencies"]["CNY"]["estimated"], "0.5")
        self.assertEqual(result["currencies"]["CNY"]["unconfirmed"], "1.5", "(1 + 2) × 0.5，与已结清的分开")
        lines = {line["purpose"]: line for line in result["lines"]}
        illustration = lines["illustration"]
        self.assertEqual((illustration["not_counted_calls"], illustration["in_flight_calls"]), (1, 1))
        self.assertEqual(illustration["counted_units"], 4)
        self.assertEqual(lines["character"]["unpriced_units"], 1)
        self.assertFalse(lines["character"]["complete"])
        self.assertEqual(result["unpriced_units"], 1)

    def test_a_star_price_is_only_a_fallback(self):
        self.add_price(purpose="*", unit_price="0.1")
        self.add_price(purpose="illustration", unit_price="0.2")
        self.call("est:star:ill", at=T0)
        self.call("est:star:char", at=T0, purpose="character")
        lines = {line["purpose"]: line for line in self.estimate()["lines"]}
        self.assertEqual(lines["illustration"]["by_currency"]["CNY"]["estimated"], "0.2")
        self.assertEqual(lines["character"]["by_currency"]["CNY"]["estimated"], "0.1")

    def test_retired_price_stops_applying_but_stays_in_history(self):
        price_id = self.add_price(unit_price="0.2").json()["price"]["price_id"]
        self.call("est:retire:1", at=T0)
        self.assertEqual(self.estimate()["currencies"]["CNY"]["estimated"], "0.2")
        self.boss.post(f"/costs/prices/{price_id}/retire", {"reason": "来源核对后发现录错了"})
        after = self.estimate()
        self.assertEqual(after["currencies"], {})
        self.assertEqual(after["unpriced_units"], 1)
        history = {p["price_id"]: p for p in self.sre.get("/costs/prices").json()["prices"]}
        self.assertEqual(history[price_id]["status"], "retired")
        self.assertEqual(history[price_id]["retired_reason"], "来源核对后发现录错了")

    def test_pet_calls_and_user_summary_show_estimates(self):
        self.add_price(unit_price="0.2")
        self.call("est:pet:settled", at=T0)
        self.call("est:pet:unknown", at=T0, units=2, outcome="unknown", actual=2)
        self.call("est:pet:notsent", at=T0, outcome="not_sent")
        rows = {r["operation_id"]: r for r in self.sre.get(f"/pets/{self.player.pet_id}/calls").json()["reservations"]}
        self.assertEqual((rows["est:pet:settled"]["estimated_cost"], rows["est:pet:settled"]["cost_currency"]), ("0.2", "CNY"))
        self.assertEqual(rows["est:pet:unknown"]["cost_state"], "unconfirmed_estimate")
        self.assertEqual(rows["est:pet:notsent"]["cost_state"], "not_counted")
        self.assertIsNone(rows["est:pet:notsent"]["estimated_cost"])

        summary = self.boss.get(f"/users/{self.player.user_id}/ledger-summary").json()
        calls = summary["pets"][0]["calls"]
        self.assertEqual(calls["estimated_cost"], {"CNY": {"estimated": "0.2", "unconfirmed": "0.4"}})
        self.assertEqual(calls["cost_state"], "estimated")

    def test_window_is_bounded_and_dates_are_checked(self):
        self.assert_admin_error(self.sre.get("/costs/estimate?start=2026-09-03&end=2026-09-02"), 422, "VALIDATION_FAILED")
        self.assert_admin_error(self.sre.get("/costs/estimate?start=2026-07-01&end=2026-09-02"), 422, "VALIDATION_FAILED")
        self.assert_admin_error(self.sre.get("/costs/estimate?start=yesterday"), 422, "VALIDATION_FAILED")
        economy = self.staff("cost-economy", ["economy_ops"])
        economy.login_ok()
        self.assert_admin_error(economy.get(f"/costs/estimate{WINDOW}"), 403, "FORBIDDEN")

    def test_reading_costs_writes_nothing(self):
        self.add_price()
        self.call("est:read:1", at=T0)
        tables = ("web_budget_reservations", "web_budget_counters", "admin_provider_prices", "economy_transactions", "pet_wallets")
        before = self.table_counts(tables)
        for _ in range(3):
            self.estimate()
            self.sre.get("/costs/prices")
            self.sre.get(f"/pets/{self.player.pet_id}/calls")
            self.sre.get("/providers/usage")
        self.assertEqual(self.table_counts(tables), before)


class UserLedgerSummaryTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("summary-owner")
        self.player.adopt_and_move_in("adopt-lan")

    def test_sections_follow_permissions(self):
        support = self.staff("summary-support", ["support"])        # user.read + economy.read
        sre = self.staff("summary-sre", ["sre"])                    # user.read + provider.read
        moderator = self.staff("summary-moderator", ["moderator"])  # user.read，两本账都不能看
        for member in (support, sre, moderator):
            member.login_ok()
        path = f"/users/{self.player.user_id}/ledger-summary"

        economy_only = support.get(path).json()
        self.assertEqual(economy_only["sections"], {"economy": True, "calls": False})
        pet = economy_only["pets"][0]
        self.assertIn("economy", pet)
        self.assertNotIn("calls", pet)
        self.assertEqual(pet["economy"]["balance"], self.web.economy.wallet(self.player.pet_id).balance)

        calls_only = sre.get(path).json()
        self.assertEqual(calls_only["sections"], {"economy": False, "calls": True})
        self.assertNotIn("economy", calls_only["pets"][0])
        self.assertEqual(calls_only["pets"][0]["calls"]["cost_state"], "unknown_no_price_table")

        self.assert_admin_error(moderator.get(path), 403, "FORBIDDEN")
        self.assert_admin_error(support.get("/users/no-such-user/ledger-summary"), 404, "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
