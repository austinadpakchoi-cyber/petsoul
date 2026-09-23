"""工作包 A：供应商日上限的原子预计（ProviderMeter.allow/record），以及操作级预算预占（BudgetLedger）。

临时库 + 真实迁移（额度表来自迁移 0050）；缺表场景在一次性临时库里显式构造；注入时钟与真实多进程；不联网、不调用任何供应商。
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app.schemas.runtime_internal import BudgetDenied, BudgetReservation
from app.storage import JourneyStorage
from app.web_platform.budget import CONCURRENT, BudgetLedger, BudgetLimit
from app.web_providers import meter as meter_mod
from app.web_providers.meter import ProviderMeter
from task_budget_helpers import (BUDGET_TABLES, CountingProvider, TaskTestBase, block_network_hook, open_storage, provider_error,
                                 reserve_then_call, tables_in)

T0 = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def child_meter_call(db: str, cap: int, barrier, out) -> None:  # noqa: ANN001
    """每个进程：检查额度 → 等所有进程都检查完 → “调用供应商” → 记录。"""
    sys.addaudithook(block_network_hook)
    meter = ProviderMeter(open_storage(db), {"llm": cap})
    allowed = meter.allow("llm")
    barrier.wait(timeout=60)
    if allowed:
        time.sleep(0.05)
        meter.record("llm", True)
    out.put(allowed)


def child_reserve(db: str, n: int, barrier, out) -> None:  # noqa: ANN001
    sys.addaudithook(block_network_hook)
    ledger = BudgetLedger(open_storage(db))
    barrier.wait(timeout=60)
    result = ledger.reserve(f"op-proc-{n}", provider="llm", purpose="brain", limits=[BudgetLimit("purpose:brain", 3)])
    out.put(isinstance(result, BudgetReservation))


class BudgetTestBase(TaskTestBase):
    budget_tables = True

    def setUp(self) -> None:
        super().setUp()
        saved_status = dict(meter_mod._STATUS)  # 供应商最近状态是进程级的：测完恢复，不影响其他测试
        self.addCleanup(lambda: (meter_mod._STATUS.clear(), meter_mod._STATUS.update(saved_status)))

    def usage_row(self, provider: str) -> tuple[int, int]:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT calls, failures FROM web_provider_usage WHERE provider = ?", (provider,)).fetchone()
        return (0, 0) if row is None else (row["calls"], row["failures"])


class ProviderMeterAtomicTests(BudgetTestBase):
    def test_interleaved_checks_from_two_processes_cannot_exceed_the_cap(self) -> None:
        first, second = ProviderMeter(self.storage, {"llm": 1}), ProviderMeter(self.storage, {"llm": 1})
        self.assertEqual([first.allow("llm"), second.allow("llm")], [True, False], "上限检查与计数是同一个原子操作")
        first.record("llm", True)
        self.assertEqual(self.usage_row("llm"), (1, 0), "record 不再重复计数")

    def test_real_processes_racing_for_the_last_calls(self) -> None:
        ctx = mp.get_context("spawn")
        barrier, out = ctx.Barrier(5), ctx.Queue()
        procs = [ctx.Process(target=child_meter_call, args=(self.db, 2, barrier, out)) for _ in range(5)]
        for proc in procs:
            proc.start()
        allowed = [out.get(timeout=120) for _ in procs]
        for proc in procs:
            proc.join(timeout=60)
        self.assertEqual(([p.exitcode for p in procs], sorted(allowed)), ([0] * 5, [False, False, False, True, True]))
        self.assertEqual(self.usage_row("llm"), (2, 0), "5 个进程抢 2 个名额：恰好 2 次")

    def test_failures_are_counted_once_and_reported(self) -> None:
        meter = ProviderMeter(self.storage, {"llm": 5}, secrets=["sk-secret"])
        self.assertTrue(meter.allow("llm"))
        meter.record("llm", False, "http 500 with sk-secret")
        self.assertEqual(self.usage_row("llm"), (1, 1))
        self.assertNotIn("sk-secret", str(meter_mod.provider_status("llm")))
        with self.storage.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT last_failure_at FROM web_provider_health WHERE provider = 'llm'").fetchone()[0])
        self.assertTrue(meter.allow("llm"))
        meter.record("llm", True)
        self.assertEqual(meter.snapshot()["llm"], {"calls": 2, "failures": 1, "cap": 5})

    def test_record_without_allow_keeps_the_old_behaviour(self) -> None:
        meter = ProviderMeter(self.storage, {"llm": 1})
        meter.record("llm", False, "http 401")
        self.assertEqual(self.usage_row("llm"), (1, 1))
        self.assertFalse(meter.allow("llm"), "旧写法记过的次数照样算进上限")

    def test_allow_without_record_is_counted_conservatively(self) -> None:
        meter = ProviderMeter(self.storage, {"image": 2})
        self.assertTrue(meter.allow("image"))  # 放行后调用方在发出前就出错，没有 record
        self.assertEqual(meter.calls_today("image"), 1)
        with mock.patch.object(meter_mod, "_PENDING_MAX_AGE_SECONDS", -1.0):
            meter.record("image", True)  # 过旧的 allow 不再认领：这次按旧写法另计一次
        self.assertEqual(meter.calls_today("image"), 2)
        self.assertFalse(meter.allow("image"))

    def test_pending_allows_are_per_thread(self) -> None:
        meter = ProviderMeter(self.storage, {"amap": 10})
        self.assertTrue(meter.allow("amap"))
        other = threading.Thread(target=lambda: meter.record("amap", True))
        other.start()
        other.join()
        self.assertEqual(meter.calls_today("amap"), 2, "别的线程的 record 不能认领本线程的 allow")
        meter.record("amap", True)
        self.assertEqual(meter.calls_today("amap"), 2)

    def test_uncapped_providers_are_still_counted(self) -> None:
        meter = ProviderMeter(self.storage, {})
        for _ in range(3):
            self.assertTrue(meter.allow("google"))
            meter.record("google", True)
        self.assertEqual(self.usage_row("google"), (3, 0))


class BudgetLedgerTests(BudgetTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.ledger = BudgetLedger(self.storage)

    def reserve(self, op: str, *limits: BudgetLimit, now: datetime = T0, **kwargs):
        return self.ledger.reserve(op, provider="llm", purpose="brain", limits=list(limits), now=now, **kwargs)

    def test_daily_quota_is_atomic_and_not_sent_releases(self) -> None:
        quota = BudgetLimit("pet:p1:brain", 2)
        first, second = self.reserve("op-1", quota, subject_scope="pet:p1"), self.reserve("op-2", quota)
        self.assertEqual((first.status, first.accounting_window, first.subject_scope, second.subject_scope), ("reserved", "2026-09-22", "pet:p1", "global"))
        denied = self.reserve("op-3", quota)
        self.assertEqual(denied, BudgetDenied("op-3", "pet:p1:brain", "limit_reached", retry_after=datetime(2026, 9, 23, tzinfo=timezone.utc)))
        self.assertEqual(self.ledger.settle(first, "succeeded", actual_units=1, now=T0).status, "settled")
        self.assertEqual(self.ledger.settle(second, "not_sent", now=T0).status, "released")
        self.assertEqual(self.ledger.usage("pet:p1:brain", now=T0), {"used": 1, "inflight": 0})
        reopened = self.reserve("op-2", quota)
        self.assertEqual((reopened.reservation_id, reopened.status), (second.reservation_id, "reserved"), "确定没发出的操作可以原样重试")
        self.assertIsInstance(self.reserve("op-3", quota), BudgetDenied)
        self.assertEqual(self.ledger.usage("usage:llm:brain", now=T0), {"used": 1, "inflight": 1}, "不设上限的用量也有记录")

    def test_concurrency_limit_counts_only_inflight(self) -> None:
        one_at_a_time = BudgetLimit("inflight:brain", 1, kind=CONCURRENT)
        first = self.reserve("op-a", one_at_a_time)
        self.assertEqual(self.reserve("op-b", one_at_a_time), BudgetDenied("op-b", "inflight:brain", "concurrency"))
        self.ledger.settle(first, "succeeded", now=T0)
        self.assertIsInstance(self.reserve("op-b", one_at_a_time), BudgetReservation, "上一个结束就能开始下一个")

    def test_all_levels_must_pass_or_nothing_is_taken(self) -> None:
        household, pet = BudgetLimit("household:h1", 1), BudgetLimit("pet:p2:brain", 5)
        self.assertIsInstance(self.reserve("op-1", household, pet), BudgetReservation)
        self.assertEqual(self.reserve("op-2", household, pet).scope, "household:h1")
        self.assertEqual(self.ledger.usage("pet:p2:brain", now=T0), {"used": 0, "inflight": 1}, "被拒的那次在任何一层都不占")

    def test_operation_id_replay_never_double_reserves(self) -> None:
        quota = BudgetLimit("purpose:brain", 5)
        hold = self.reserve("op-replay", quota)
        in_flight = self.reserve("op-replay", quota)
        self.assertEqual(in_flight, BudgetDenied("op-replay", "operation", "in_flight", retry_after=hold.expires_at), "还在途：不许再发")
        self.assertEqual(self.ledger.usage("purpose:brain", now=T0), {"used": 0, "inflight": 1})
        self.assertEqual(self.ledger.settle(hold, "unknown", provider_request_id="req-42", now=T0).status, "unknown")
        replay = self.reserve("op-replay", quota)
        self.assertEqual((replay.reservation_id, replay.status), (hold.reservation_id, "unknown"), "结果不明：同一操作原样返回，不能重新占用后盲目重发")
        self.assertEqual(self.ledger.usage("purpose:brain", now=T0), {"used": 1, "inflight": 0}, "unknown 保守计入已用")
        self.assertEqual(self.ledger.settle(hold, "succeeded", now=T0).status, "settled", "查清后补记结果")
        self.assertEqual(self.ledger.settle(hold, "not_sent", now=T0).status, "settled", "已结算的不再改")
        self.assertEqual(self.ledger.usage("purpose:brain", now=T0), {"used": 1, "inflight": 0})
        with self.storage.connect() as conn:
            row = conn.execute("SELECT outcome, provider_request_id FROM web_budget_reservations WHERE operation_id = 'op-replay'").fetchone()
        self.assertEqual((row["outcome"], row["provider_request_id"]), ("succeeded", "req-42"))

    def test_unknown_confirmed_not_sent_gives_the_units_back(self) -> None:
        quota = BudgetLimit("purpose:brain", 1)
        hold = self.reserve("op-lost", quota)
        self.ledger.settle(hold, "unknown", now=T0)
        self.assertIsInstance(self.reserve("op-other", quota), BudgetDenied)
        self.assertEqual(self.ledger.settle(hold, "not_sent", now=T0).status, "released", "向供应商查实没受理：退回")
        self.assertIsInstance(self.reserve("op-other", quota), BudgetReservation)

    def test_unsettled_reservation_expires_as_used_and_frees_concurrency(self) -> None:
        daily, inflight = BudgetLimit("purpose:image", 3), BudgetLimit("inflight:image", 1, kind=CONCURRENT)
        crashed = self.ledger.reserve("op-crash", provider="image", purpose="image", limits=[daily, inflight], ttl_seconds=30, now=T0)
        later = T0 + timedelta(seconds=31)
        fresh = self.ledger.reserve("op-next", provider="image", purpose="image", limits=[daily, inflight], now=later)
        self.assertIsInstance(fresh, BudgetReservation, "进程死在调用中途：过期后释放并发名额")
        self.assertEqual(self.ledger.get("op-crash").status, "expired")
        self.assertEqual(self.ledger.usage("purpose:image", now=later), {"used": 1, "inflight": 1}, "过期的那次保守算作已用")
        self.assertEqual(self.ledger.settle(crashed, "succeeded", provider_request_id="req-7", now=later).status, "settled", "迟到的结果只补记")
        self.assertEqual(self.ledger.usage("purpose:image", now=later), {"used": 1, "inflight": 1})
        self.assertEqual(self.ledger.expire_stale(now=later), 0)

    def test_accounting_window_is_the_utc_day_and_survives_restart(self) -> None:
        quota = BudgetLimit("purpose:brain", 1)
        late_evening = datetime(2026, 9, 22, 23, 59, 30, tzinfo=timezone.utc)
        hold = self.reserve("op-night", quota, now=late_evening)
        self.assertEqual(hold.accounting_window, "2026-09-22")
        self.assertIsInstance(self.reserve("op-night-2", quota, now=late_evening), BudgetDenied)
        after_midnight = late_evening + timedelta(minutes=1)
        self.ledger.settle(hold, "succeeded", now=after_midnight)
        self.assertEqual(self.ledger.usage("purpose:brain", now=late_evening), {"used": 1, "inflight": 0}, "跨日结算记在原来那一天")
        restarted = BudgetLedger(JourneyStorage(Path(self.db)))
        self.assertIsInstance(restarted.reserve("op-next-day", provider="llm", purpose="brain", limits=[quota], now=after_midnight), BudgetReservation)
        self.assertIsInstance(restarted.reserve("op-same-day", provider="llm", purpose="brain", limits=[quota], now=late_evening), BudgetDenied,
                              "重启不清零")

    def test_reservation_follows_the_callers_transaction(self) -> None:
        quota = BudgetLimit("purpose:brain", 1)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertIsInstance(self.ledger.reserve("op-tx", provider="llm", purpose="brain", limits=[quota], now=T0, conn=conn), BudgetReservation)
            conn.rollback()
        self.assertIsNone(self.ledger.get("op-tx"), "调用方回滚：预占一并撤销")
        hold = self.reserve("op-tx", quota)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO probe_effects (task_id, writer) VALUES ('op-tx', 'result')")
            self.ledger.settle(hold, "succeeded", now=T0, conn=conn)
        self.assertEqual((self.effects(), self.ledger.get("op-tx").status), (["result"], "settled"), "业务结果与结算同一事务提交")

    def test_real_processes_racing_for_a_quota(self) -> None:
        ctx = mp.get_context("spawn")
        barrier, out = ctx.Barrier(6), ctx.Queue()
        procs = [ctx.Process(target=child_reserve, args=(self.db, n, barrier, out)) for n in range(6)]
        for proc in procs:
            proc.start()
        results = [out.get(timeout=120) for _ in procs]
        for proc in procs:
            proc.join(timeout=60)
        self.assertEqual(([p.exitcode for p in procs], results.count(True)), ([0] * 6, 3), "6 个进程抢 3 个名额：恰好 3 个")
        self.assertEqual(self.ledger.usage("purpose:brain"), {"used": 0, "inflight": 3})

    def test_call_outcomes_map_to_distinct_cost_states_and_retries_pay_again(self) -> None:
        quota = BudgetLimit("purpose:brain", 2)
        common = {"provider": "llm", "purpose": "brain", "limits": [quota], "now": T0}
        provider = CountingProvider(fail=provider_error("not_sent"))  # 还没发出去就被供应商客户端挡下
        held, _, settled = reserve_then_call(self.ledger, provider, "op-a1", **common)
        self.assertEqual((settled.status, self.ledger.usage("purpose:brain", now=T0)), ("released", {"used": 0, "inflight": 0}), "没发出去：退回额度")
        provider.fail = provider_error("unknown")  # 超时：外部是否受理不明
        held, _, settled = reserve_then_call(self.ledger, provider, "op-a2", **common)
        self.assertEqual((settled.status, self.ledger.usage("purpose:brain", now=T0)), ("unknown", {"used": 1, "inflight": 0}), "结果不明：保守计入已用")
        replay = reserve_then_call(self.ledger, provider, "op-a2", **common)
        self.assertEqual((replay[0].status, replay[1], len(provider.calls)), ("unknown", None, 2), "同一 operation_id 重试不再发起调用")
        provider.fail = None
        held, result, settled = reserve_then_call(self.ledger, provider, "op-a2-retry-1", **common)
        self.assertEqual((settled.status, result, len(provider.calls)), ("settled", "ok:op-a2-retry-1", 3), "重试用新的 operation_id，另算一次调用")
        self.assertEqual(self.ledger.usage("purpose:brain", now=T0), {"used": 2, "inflight": 0}, "重试要另占额度，不绕过原来的上限")
        denied, result, _ = reserve_then_call(self.ledger, provider, "op-a2-retry-2", **common)
        self.assertEqual((denied.reason, result, len(provider.calls)), ("limit_reached", None, 3), "额度用完就不再调用")

    def test_partial_send_is_settled_by_actually_sent_units(self) -> None:
        """预占 2 个单位（要先画证件照）但只真的发出去 1 次：按实际发出的单位结算，剩下的退回。"""
        quota = BudgetLimit("pet:p9:image", 3)
        sent_one = self.ledger.reserve("op-partial", provider="image", purpose="illustration", subject_scope="pet:p9", units=2, limits=[quota], now=T0)
        self.assertEqual(sent_one.reserved_units, 2)
        settled = self.ledger.settle(sent_one, "failed", actual_units=1, now=T0)  # 证件照发出去了，第二次被上限挡下
        self.assertEqual((settled.status, self.ledger.usage("pet:p9:image", now=T0)), ("settled", {"used": 1, "inflight": 0}))
        sent_none = self.ledger.reserve("op-none", provider="image", purpose="illustration", subject_scope="pet:p9", units=2, limits=[quota], now=T0)
        self.ledger.settle(sent_none, "not_sent", now=T0)
        self.assertEqual(self.ledger.usage("pet:p9:image", now=T0), {"used": 1, "inflight": 0}, "一次都没发出去才整笔退回")

    def test_invalid_requests_are_refused(self) -> None:
        for op, kwargs in (("", {}), ("op", {"units": 0})):
            self.assertEqual(self.reserve(op, BudgetLimit("x", 1), **kwargs).reason, "invalid_request")
        self.assertEqual(self.reserve("op", BudgetLimit("x", 1, kind="hourly")).reason, "invalid_request")
        with self.assertRaises(ValueError):
            self.ledger.settle(self.reserve("op-ok", BudgetLimit("x", 1)), "refunded")


class BudgetWithoutMigrationTests(BudgetTestBase):
    """迁移 0050 之后，“跑完迁移的库”一定有额度表；缺表场景由本用例在一次性临时库里显式构造（迁移后删表）。"""

    budget_tables = False

    def test_missing_tables_are_reported_not_faked(self) -> None:
        migrated = open_storage(str(Path(self.tmp_dir) / "migrated.sqlite3"))
        self.assertEqual(tables_in(migrated), set(BUDGET_TABLES), "迁移 0050_budget 会建好这两张表")
        self.assertEqual(tables_in(self.storage), set(), "本用例的库：迁移之后把两张表删掉，缺表条件确实成立")
        ledger, provider = BudgetLedger(self.storage), CountingProvider()
        denied, result, settled = reserve_then_call(ledger, provider, "op-missing", provider="llm", purpose="brain",
                                                    limits=[BudgetLimit("purpose:brain", 1)], now=T0)
        self.assertEqual((type(denied), denied.scope, denied.reason), (BudgetDenied, "ledger", "ledger_unavailable"))
        self.assertEqual((provider.calls, result, settled), ([], None, None), "缺表时不发起付费调用，也没有结算")
        self.assertEqual(ledger.expire_stale(now=T0), 0)
        self.assertEqual(self.usage_row("llm"), (0, 0), "被拒的调用不计入供应商用量")
        self.assertFalse(ledger.available(), "缺表如实报告，不假装可用")
        meter = ProviderMeter(self.storage, {"llm": 1})
        self.assertEqual([meter.allow("llm"), meter.allow("llm")], [True, False], "没有额度表时，供应商自己的每日上限照样原子")


if __name__ == "__main__":
    unittest.main()
