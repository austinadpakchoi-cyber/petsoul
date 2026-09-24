"""保守计入之后的**回正**：unknown / expired 先按预占全额记账，查清之后按差额补回来。

原来那条更正路径只处理 `not_sent`（整笔退回），"预占 2、查清只用了 1"这种**部分**情况一分钱都回不来，
`used` 永久停在 2。**这一条已经修好**（`BudgetLedger._settle` 的迟到结算分支按差额回正），前 10 项钉住它。

两件事仍然成立，分别钉在下面，不要混读：
  1. **unknown 当场**现在按**已确认发出的次数**计（说不清才退回按预占全额保守计入），
     `actual_units` 落下"本地已按此计量的单位数"。这一条原先是刻意保留的旧语义，
     已在专门的一批里修掉，见 `test_web_budget_partial_unknown`。
  2. **回正是"能力"，不是"正在发生的行为"**：产品里目前没有任何路径会发起查清
     （见 `ReconcileHasNoCallerTests`）。所以多记的量**不会自己回正**，要有人来查清才会。

一次性临时库；不联网、0 次付费调用。
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.image_provider.models import GeneratedImage  # noqa: F401  （替身返回类型，保持与真实适配器一致）
from app.web_journey.illustrations import IllustrationService
from app.web_platform.budget import BudgetLedger, BudgetLimit
from app.web_platform.tasks import WebTaskQueue
from app.web_platform.uow import unit_of_work
from app.web_providers import ImageUnavailable
from task_budget_helpers import open_storage


class TimingOutIllustrator:
    """替身：每次都超时。超时＝可能已经受理，落进 A 的 UNKNOWN_REASONS。"""

    available = True
    provider_label = "测试生图"

    def render(self, prompt, reference=None, size="2048x2048"):
        raise ImageUnavailable("timeout")


NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)
DAILY, PET = "provider:image:daily", "pet:p1:illustration"


class BudgetReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = BudgetLedger(open_storage(str(Path(tmp.name) / "budget.sqlite3")))

    # ---- 辅助 ----
    def reserve(self, operation_id: str = "op-1", units: int = 2, now: datetime = NOW):
        return self.ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope="pet:p1",
                                   units=units, limits=[BudgetLimit(DAILY, 50), BudgetLimit(PET, 50)], now=now)

    def used(self, scope_key: str = DAILY) -> int:
        return self.ledger.usage(scope_key, now=NOW)["used"]

    def inflight(self, scope_key: str = DAILY) -> int:
        return self.ledger.usage(scope_key, now=NOW)["inflight"]

    def row(self, operation_id: str = "op-1"):
        with self.ledger.storage.connect() as conn:
            return conn.execute("SELECT status, outcome, reserved_units, actual_units FROM web_budget_reservations "
                                "WHERE operation_id = ?", (operation_id,)).fetchone()

    # ---- 对照：正常预占→结算，本来就该对 ----
    def test_a_plain_reservation_and_settlement_is_unchanged(self) -> None:
        permit = self.reserve()
        self.assertEqual((self.used(), self.inflight()), (0, 2), "预占之后：在途 2、已用 0")

        self.ledger.settle(permit, "succeeded", actual_units=2, now=NOW)

        self.assertEqual((self.used(), self.inflight()), (2, 0), "两次都用上了：已用 2、在途归零")
        self.assertEqual(self.used(PET), 2, "每一层作用域都要跟着对")

    # ---- 缺陷本体：unknown 先保守记 2，查清只用了 1，却回不来 ----
    def test_a_clarified_partial_use_after_unknown_is_corrected(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        # 口径已变（见 test_web_budget_partial_unknown）：当场按**已发出次数**记 1，不再按预占全额记 2。
        self.assertEqual((self.used(), self.inflight()), (1, 0), "当场按已发出的 1 次记，在途已释放")

        # 之后查清：这次确实只用了 1 个单位
        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=10))

        self.assertEqual(self.used(), 1, "查清之后要按差额回正，不能永久停在 2")
        self.assertEqual(self.used(PET), 1, "每一层作用域都要回正")
        self.assertEqual(self.inflight(), 0, "**不能重复扣在途**——转 unknown 那一步已经释放过了")
        row = self.row()
        self.assertEqual((row["status"], row["outcome"], row["actual_units"]), ("settled", "succeeded", 1))

    def test_a_clarified_partial_use_after_expiry_is_corrected(self) -> None:
        """过期那一档同理：到期没结算先保守计入，之后查清也要回正。"""
        permit = self.reserve()
        self.ledger.expire_stale(now=NOW + timedelta(hours=2))
        self.assertEqual((self.used(), self.inflight()), (2, 0), "过期：保守计入、释放在途")
        self.assertEqual(self.row()["status"], "expired")

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(hours=3))

        self.assertEqual(self.used(), 1)
        self.assertEqual(self.inflight(), 0, "不重复扣在途")

    def test_a_clarified_failure_with_known_units_is_corrected_too(self) -> None:
        """明确失败但已知发出几次：同样按差额回正（失败不等于没发出，费用照记）。"""
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "failed", actual_units=1, now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 1, "确定失败但确实发出过 1 次：记 1，不是 2、也不是 0")

    def test_a_clarified_not_sent_returns_the_whole_reservation(self) -> None:
        """查清一次都没发出：整笔退回（这一条原来就对，作为不回归的对照）。"""
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "not_sent", now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 0, "一次都没发出：归零")
        self.assertEqual(self.inflight(), 0)

    def test_an_unclarified_late_settlement_keeps_what_was_already_charged(self) -> None:
        """查清时仍然说不出用了几个单位：**维持当初已经记下的那个数**，不因"回正"擅自上下调。

        当场就说不清（不给 `actual_units`）→ 按预占全额 2 记；之后查清还是说不清 → 仍是 2。
        """
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", now=NOW)  # 当场也说不清
        self.assertEqual(self.used(), 2, "说不清就按预占全额保守计入")

        self.ledger.settle(permit, "succeeded", now=NOW + timedelta(minutes=5))  # 依然没给 actual_units

        self.assertEqual(self.used(), 2, "还是不知道就不动它")

    # ---- 只调一次：重复结算与并发重复 ----
    def test_repeating_the_same_clarification_adjusts_only_once(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))
        self.assertEqual(self.used(), 1)

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=6))

        self.assertEqual(self.used(), 1, "重复报告同一个结论不能再扣一次")

    def test_concurrent_clarifications_adjust_only_once(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        start = threading.Barrier(2)

        def clarify() -> None:
            start.wait(timeout=10)
            self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))

        threads = [threading.Thread(target=clarify) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "不该卡住")

        self.assertEqual(self.used(), 1, "两个查清同时到，也只调一次")

    # ---- 不碰当天别的操作 ----
    def test_the_correction_does_not_touch_other_operations(self) -> None:
        other = self.reserve("op-other", units=3)
        self.ledger.settle(other, "succeeded", actual_units=3, now=NOW)
        permit = self.reserve("op-1", units=2)
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.assertEqual(self.used(), 4, "3 ＋ 当场按已发出次数记的 1")

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 4, "查清与当场记的一致，不再动；别人的 3 一动不动")

    # ---- 本批**不改**的语义，钉住免得被顺手改掉 ----
    def test_unknown_now_records_what_was_charged(self) -> None:
        """**这条用例的期望是被有意改过的**，不是回归。

        它原来钉的是"unknown 当场留空 `actual_units`、按预占全额记"——那是**上一批**刻意保留的旧语义，
        当时协调单要求"不顺手改列义"。"当场少发多记"随后被单列成自己的一批并已修：
        现在 `actual_units` 记的是**本地已按此计量的单位数**（unknown 时＝已确认发出、是否被受理未知），
        事后查清就对着它算差额。旧行为的证据在 10:39 与 13:38 两条记录里原样保留。
        """
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        row = self.row()
        self.assertEqual((row["status"], row["outcome"]), ("unknown", "unknown"))
        self.assertEqual(row["actual_units"], 1, "落下已记账的那个数，供事后查清算差额")
        self.assertEqual(self.used(), 1, "当场就只记实际发出的 1 次")


class ReconcileHasNoCallerTests(unittest.TestCase):
    """**能力有、调用方无**：回正逻辑本身可用（上面 10 项已证明），但产品里目前**没有任何路径会发起查清**。

    这不是缺陷主张，也不是待办——要不要接线、由谁发起（定时对账作业？运维命令？）是产品判断，
    协调方说过可能本来就计划由后续对账来接。这里只把**当前边界**钉住，
    免得"事后可回正"被读成"多记的量会自己回正"。

    这几条现在是**绿**的：它们描述的是现状。哪天有人接上了查清的调用方，它们会**转红**——
    那正是提醒去更新这里与发布记录的信号，不是回归。
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.storage = open_storage(str(root / "chain.sqlite3"))
        self.queue = WebTaskQueue(self.storage)
        self.ledger = BudgetLedger(self.storage)
        self.illustrations = IllustrationService(self.storage, root / "media", self.queue)
        self.illustrations.illustrator = TimingOutIllustrator()
        self.illustrations.character_of = lambda pet_id: ("cat", "小岚", None)
        self.illustrations.reference_photo_of = lambda pet_id: (b"photo", "image/png")
        self.illustrations.reserve = lambda operation_id, pet_id, units: self.ledger.reserve(
            operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}",
            units=units, limits=[BudgetLimit(DAILY, 50)])
        self.illustrations.settle = lambda permit, outcome, actual_units=None: self.ledger.settle(
            permit, outcome, actual_units=actual_units)

    def rows(self) -> list[tuple]:
        with self.storage.connect() as conn:
            return [(r["status"], r["outcome"], r["actual_units"])
                    for r in conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations ORDER BY rowid")]

    def test_the_normal_chain_never_settles_an_unknown_a_second_time(self) -> None:
        """跑完整条真实链路：落成 unknown 之后，**再跑多少轮都不会有第二次结算**。"""
        with unit_of_work(self.storage) as conn:
            self.illustrations.request_photo_in(conn, "u-1", "p1", "photo:v1", place="信德中心", city="香港", scene="靠窗坐着")
        self.illustrations.run_pending()
        self.assertEqual(self.rows(), [("unknown", "unknown", 1)], "超时：落成 unknown，并记下已发出的 1 次")
        used_after_unknown = self.ledger.usage(DAILY)["used"]

        for _ in range(3):  # 后台再跑几轮，看有没有谁会去查清
            self.illustrations.run_pending()

        self.assertEqual(self.rows(), [("unknown", "unknown", 1)], "没有任何一轮会发起查清")
        self.assertEqual(self.ledger.usage(DAILY)["used"], used_after_unknown, "多记的量不会自己回正")

    def test_the_illustration_chain_skips_settling_once_it_is_no_longer_reserved(self) -> None:
        """机制层面的原因：`illustrations._settle` 只在预占仍是 `reserved` 时才结算。

        所以即便把同一张预占再交给它一次，也什么都不会发生——查清必须由**别人**发起。
        """
        permit = self.ledger.reserve("op-x", provider="image", purpose="illustration", subject_scope="pet:p1",
                                     units=2, limits=[BudgetLimit(DAILY, 50)])
        self.ledger.settle(permit, "unknown", actual_units=1)
        refreshed = self.ledger.get("op-x")
        self.assertEqual(refreshed.status, "unknown")

        self.illustrations._settle(refreshed, "succeeded", 1)  # 把它再交回插画链路

        self.assertEqual(self.rows(), [("unknown", "unknown", 1)], "插画链路不会替你查清")
        self.assertEqual(self.ledger.usage(DAILY)["used"], 1, "当场记的就是已发出的 1 次；没人查清它也就停在这里")

    def test_nothing_expires_a_stale_reservation_on_its_own(self) -> None:
        """`expire_stale` 在 app/ 下零调用方：没有后台作业会主动把过期预占收掉。

        **但不要读大**：过期仍然会发生，只是**顺带**发生——`reserve` 每次会先清一批
        （`_expire_in_tx`）。所以准确说法是"没有独立的到期作业"，不是"过期永远不发生"。
        """
        self.ledger.reserve("op-stale", provider="image", purpose="illustration", subject_scope="pet:p1",
                            units=2, limits=[BudgetLimit(DAILY, 50)], ttl_seconds=0.001)
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        self.assertEqual(self.rows(), [("reserved", None, None)], "光是等，不会有人来收")

        self.ledger.reserve("op-next", provider="image", purpose="illustration", subject_scope="pet:p1",
                            units=1, limits=[BudgetLimit(DAILY, 50)], now=later)  # 下一次预占顺带清

        self.assertEqual(self.rows()[0], ("expired", None, None), "是被下一次 reserve 顺带收掉的，不是定时作业")


if __name__ == "__main__":
    unittest.main()
