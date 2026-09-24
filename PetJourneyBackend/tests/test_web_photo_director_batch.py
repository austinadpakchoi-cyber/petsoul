"""真实成图批次的金额闸门：校验要能阻断，发送前要真的检查下一笔。

全程离线：这里只做纯计算，不发任何请求。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

from app.web_photo_director import PhotoDirectorError, validate_batch_cost  # noqa: E402
from app.web_photo_director.batch import BatchGuard  # noqa: E402

CNY = {"unit": 0.25, "currency": "CNY"}


class CostValidationTests(unittest.TestCase):
    def test_estimate_over_the_cap_is_blocked(self):
        """估价 2 元、上限 0.01 元：必须进阻塞，不能标成可发送。"""
        checked = validate_batch_cost(CNY, {"amount": 0.01, "currency": "CNY"}, 8)
        self.assertFalse(checked["ok"])
        self.assertEqual(checked["estimated_total"], 2.0)
        self.assertTrue(any("exceeds_cap" in p for p in checked["problems"]))

    def test_mismatched_currency_is_blocked_not_compared_numerically(self):
        """报价 CNY、上限 USD 直接比数值会放行一个实际超支的批次。"""
        checked = validate_batch_cost(CNY, {"amount": 100, "currency": "USD"}, 8)
        self.assertFalse(checked["ok"])
        self.assertTrue(any("currency_mismatch" in p for p in checked["problems"]))

    def test_missing_amount_is_never_treated_as_zero(self):
        checked = validate_batch_cost({"currency": "CNY"}, {"amount": 10, "currency": "CNY"}, 8)
        self.assertFalse(checked["ok"])
        self.assertIn("provider_quote_amount_missing", checked["problems"])

    def test_missing_currency_is_blocked(self):
        checked = validate_batch_cost({"unit": 0.25}, {"amount": 10, "currency": "CNY"}, 8)
        self.assertFalse(checked["ok"])
        self.assertTrue(checked["problems"], "缺币种必须进阻塞")

    def test_non_numeric_amount_is_blocked(self):
        checked = validate_batch_cost({"unit": "便宜", "currency": "CNY"},
                                      {"amount": 10, "currency": "CNY"}, 8)
        self.assertFalse(checked["ok"])

    def test_a_valid_batch_passes(self):
        """正常对照：0.25 x 8 = 2 元，上限 10 元。"""
        checked = validate_batch_cost(CNY, {"amount": 10, "currency": "CNY"}, 8)
        self.assertTrue(checked["ok"])
        self.assertEqual(checked["estimated_total"], 2.0)
        self.assertEqual(checked["problems"], [])


class GuardTests(unittest.TestCase):
    def guard(self, cap=10.0, count=8) -> BatchGuard:
        return BatchGuard.from_spec(CNY, {"amount": cap, "currency": "CNY"}, count)

    def test_a_guard_cannot_be_built_from_an_invalid_cost(self):
        with self.assertRaises(PhotoDirectorError) as caught:
            BatchGuard.from_spec(CNY, {"amount": 0.01, "currency": "CNY"}, 8)
        self.assertIn("batch_cost_invalid", str(caught.exception))

    def test_every_send_is_checked_before_it_happens(self):
        """闸门在**下一笔之后会不会越线**上判断，不是事后才发现超了。

        这里直接构造（绕过 from_spec 的批次级校验）：即便有人这样建出来，
        发送点上的闸门也必须照样挡住。
        """
        guard = BatchGuard(unit=0.25, currency="CNY", cap=0.5, image_count=8)  # 只够两张
        for _ in range(2):
            guard.check_next()
            guard.record("ok")
        with self.assertRaises(PhotoDirectorError) as caught:
            guard.check_next()
        self.assertIn("next_call_would_exceed_cap", str(caught.exception))
        self.assertEqual(guard.sent, 2)

    def test_an_unknown_result_stops_the_batch_immediately(self):
        """结果不明：不补发、不凑张数，并且按最坏情况算进已花。"""
        guard = self.guard()
        guard.check_next()
        guard.record("unknown")
        self.assertEqual(guard.spent, 0.25)
        self.assertEqual(guard.stopped, "unknown_result")
        with self.assertRaises(PhotoDirectorError) as caught:
            guard.check_next()
        self.assertIn("batch_stopped:unknown_result", str(caught.exception))

    def test_a_rejected_call_does_not_count_as_spend(self):
        """当场被拒＝没出图，按公开计费口径不计费。"""
        guard = self.guard()
        guard.check_next()
        guard.record("rejected")
        self.assertEqual(guard.spent, 0.0)
        self.assertIsNone(guard.stopped)

    def test_the_planned_count_is_also_a_ceiling(self):
        guard = self.guard(count=2)
        for _ in range(2):
            guard.check_next()
            guard.record("ok")
        with self.assertRaises(PhotoDirectorError) as caught:
            guard.check_next()
        self.assertIn("batch_image_count_reached", str(caught.exception))

    def test_summary_reports_worst_case_spend(self):
        guard = self.guard()
        for outcome in ("ok", "rejected", "ok"):
            guard.check_next()
            guard.record(outcome)
        summary = guard.summary()
        self.assertEqual(summary["sent"], 3)
        self.assertEqual(summary["spent_worst_case"], 0.5)
        self.assertEqual(summary["remaining"], 9.5)
        self.assertEqual(len(summary["log"]), 3)

    def test_a_full_eight_shot_batch_fits_the_cap(self):
        """正常对照：八张跑满，10 元上限绰绰有余。"""
        guard = self.guard()
        for _ in range(8):
            guard.check_next()
            guard.record("ok")
        self.assertEqual(guard.spent, 2.0)
        self.assertIsNone(guard.stopped)


if __name__ == "__main__":
    unittest.main()
