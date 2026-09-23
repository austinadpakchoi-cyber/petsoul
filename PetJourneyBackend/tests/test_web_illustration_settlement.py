"""生图的费用口径与展示状态（对应包 A 的 CR-A1、CR-A3、CR-A5）。

一次"画一张图"可能发出两次付费调用：没有主人上传的照片时，先画一张证件照当参考，再画正图。
所以要按**实际发出了几次**结算，不能一次失败就把整笔退回；超时属于"可能已经受理并计费"，
既不能当作没发生，也不能盲目自动重试。任务终态、预算结算、页面上看到的状态必须是同一个说法。
替身生图，不联网、不产生付费调用。
"""

from __future__ import annotations

import contextlib
import sqlite3
import unittest
from unittest import mock

from app.web_journey import illustrations as illustrations_mod
from app.web_providers import ImageUnavailable, WebProviders
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class SimulatedExit(BaseException):
    """模拟进程被杀：不是 Exception，任务循环的兜底捕不到，任务就停在“领取中”。"""


class DisplayWriteProxy:
    """注入故障用：改展示状态那一步必定失败，其余照常。"""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith("UPDATE WEB_ILLUSTRATIONS"):
            raise sqlite3.OperationalError("disk I/O error (injected)")
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextlib.contextmanager
def failing_display_write(storage):
    """与 unit_of_work 同签名：任务重排照常写，改展示状态时抛错，用来验证两次写入真的同生共死。"""
    with storage.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        yield DisplayWriteProxy(conn)


class StagedIllustrator(FakeIllustrator):
    """按顺序演每一次调用：None 表示成功，字符串表示这次抛 ImageUnavailable(该原因)。"""

    def __init__(self, *outcomes: str | None) -> None:
        super().__init__()
        self.outcomes = list(outcomes)
        self.sent = 0

    def render(self, prompt, reference=None, size="2048x2048"):
        outcome = self.outcomes.pop(0) if self.outcomes else None
        self.prompts.append(prompt)
        if outcome is not None:
            if outcome not in ("daily_cap", "not_configured"):
                self.sent += 1  # 已经发出去了（可能已计费）
            raise ImageUnavailable(outcome)
        self.sent += 1
        return _ok()


def _ok():
    from app.image_provider.models import GeneratedImage

    return GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\nfake", mime_type="image/png", model="fake-seedream", provider="fake", source="url")


class IllustrationSettlementTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("art-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.illustrations = self.web.illustrations

    def use(self, *outcomes: str | None) -> StagedIllustrator:
        illustrator = StagedIllustrator(*outcomes)
        self.web.providers = WebProviders(enabled=True, chat=self.web.providers.chat, geo=None, illustrator=illustrator, meter=None)
        self.illustrations.illustrator = illustrator
        return illustrator

    def request(self) -> str:
        task_id = self.illustrations.request_image(self.owner.user_id, self.owner.pet_id, "settle:selfie", style="selfie",
                                                   place="码头", city="香港", scene="坐着")
        self.assertIsNotNone(task_id)
        return task_id

    def reservations(self) -> list[dict]:
        with self.app.state.storage.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT operation_id, status, reserved_units, actual_units, outcome FROM web_budget_reservations ORDER BY rowid")]

    def used(self) -> int:
        """这一天"生图"这个用途实际记账的次数（没设上限的用量层 A 也会记）。"""
        from app.web_platform.budget import BudgetLedger

        return BudgetLedger(self.app.state.storage).usage("usage:image:illustration", now=self.clock.now)["used"]

    def task_status(self, task_id: str) -> str:
        return self.illustrations.tasks.get(task_id).status

    def illustration_status(self, task_id: str) -> str:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,)).fetchone()["status"]

    # ---- CR-A1：按实际发出结算 ----
    def test_a_portrait_that_was_sent_is_not_refunded_when_the_second_call_is_capped(self) -> None:
        art = self.use(None, "daily_cap")  # 证件照发出去了，正图被每日上限挡下
        task_id = self.request()

        self.illustrations.run_pending()

        self.assertEqual(art.sent, 1, "确实只发出了一次")
        rows = self.reservations()
        self.assertEqual(len(rows), 1, rows)
        self.assertNotEqual(rows[0]["status"], "released", f"发出去的那次不能整笔退回：{rows[0]}")
        self.assertEqual(self.used(), 1, f"已用应当等于实际发出的次数：{rows[0]}")

    def test_nothing_sent_is_fully_released(self) -> None:
        art = self.use("daily_cap")  # 第一次就被挡下：一次都没发出
        task_id = self.request()

        self.illustrations.run_pending()

        self.assertEqual(art.sent, 0)
        rows = self.reservations()
        self.assertEqual(rows[0]["status"], "released", f"一次都没发出才整笔退回：{rows[0]}")
        self.assertEqual(self.used(), 0)
        self.assertEqual(self.illustration_status(task_id), "failed", "如实显示没画成")

    # ---- CR-A3：超时＝结果不明，不盲目重试 ----
    def test_a_timeout_counts_as_unknown_and_is_not_retried_automatically(self) -> None:
        art = self.use(None, "timeout")  # 证件照成功，正图超时（可能已经受理并计费）
        task_id = self.request()

        self.illustrations.run_pending()

        self.assertEqual(art.sent, 2, "超时那次也已经发出去了")
        rows = self.reservations()
        self.assertEqual(rows[0]["outcome"], "unknown", f"结果不明要记 unknown，不能当作没发生：{rows[0]}")
        self.assertEqual(rows[0]["status"], "unknown", f"预占停在「结果不明」，等查清后再结算：{rows[0]}")
        self.assertGreaterEqual(self.used(), 2, f"结果不明保守计入（按预占的单位数算）：{rows[0]}")
        self.assertEqual(self.illustration_status(task_id), "failed", "页面如实显示没画成")
        self.assertEqual(self.task_status(task_id), "failed", "不排自动重试，等主人点重画")

    def test_the_owner_can_redraw_after_a_timeout(self) -> None:
        self.use(None, "timeout")
        task_id = self.request()
        self.illustrations.run_pending()
        self.use(None)  # 重画这次直接成功（已有参考照，只要一次调用）

        self.illustrations.retry(task_id)

        self.assertEqual(self.task_status(task_id), "queued", "重画要能把任务排回去")
        self.assertEqual(self.illustration_status(task_id), "processing")
        self.illustrations.run_pending()
        self.assertEqual(self.illustration_status(task_id), "ready")

    def test_provider_failures_are_classified_by_whether_the_call_may_have_landed(self) -> None:
        """images.failure_reason 的归类，分两个互不相同的问题：可能计费吗？该自动重试吗？"""
        import http.client
        import urllib.error
        from app.web_providers.images import failure_reason

        unknown = [TimeoutError("read timed out"), urllib.error.URLError("timed out"), http.client.RemoteDisconnected("closed"),
                   ConnectionResetError("reset by peer"), http.client.IncompleteRead(b"")]
        # 确定没受理，而且换个时间重试是合理的：连不上、域名解析不了
        retryable = [ConnectionRefusedError("refused"), urllib.error.URLError("Name or service not known")]
        # 确定没受理，但重试同一个请求还是同样的结果：参数、认证、配置错误
        rejected = [urllib.error.HTTPError("u", 400, "Bad Request", {}, None),
                    urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)]
        self.assertEqual([failure_reason(exc) for exc in unknown], ["timeout"] * len(unknown))
        self.assertEqual([failure_reason(exc) for exc in retryable], ["provider_error"] * len(retryable))
        self.assertEqual([failure_reason(exc) for exc in rejected], ["rejected"] * len(rejected))
        # 认不出来的异常不再假定"生成失败"：可能是受理之后才出的问题，按结果不明处理，由主人决定是否重画
        self.assertEqual(failure_reason(ValueError("bad payload")), "unconfirmed")

    # ---- 恢复：展示状态写完、任务终态没写就退出 ----
    def test_a_crash_after_the_display_write_does_not_resend_on_recovery(self) -> None:
        art = self.use(None, "timeout")  # 证件照成功、正图超时：结果不明
        task_id = self.request()
        original = self.illustrations.tasks.fail_claim

        def killed(*args, **kwargs):  # noqa: ANN002, ANN003 - 展示状态已提交、任务终态还没写，进程就没了
            raise SimulatedExit("killed before the task state was written")

        self.illustrations.tasks.fail_claim = killed
        with self.assertRaises(SimulatedExit):
            self.illustrations.run_pending()
        self.illustrations.tasks.fail_claim = original
        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("running", "failed"),
                         "展示状态已经落库，任务还停在领取中")
        before = self.reservations()
        self.assertEqual([r["status"] for r in before], ["unknown"], before)

        self.clock.advance(minutes=5)  # 租期过了：任务被回收重排，worker 再领一次
        self.illustrations.run_pending()

        self.assertEqual(art.sent, 2, "恢复之后不能再调用一次供应商")
        self.assertEqual(self.reservations(), before, "上一笔“结果不明”原样保留，不回写成未发送，也不另起一笔")
        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("failed", "failed"))
        self.assertEqual(self.illustrations.outcome_of(task_id), "unknown", "消费者能分辨“结果未确认”与“明确失败”")

    def test_a_definite_provider_error_is_still_retried_automatically(self) -> None:
        art = self.use("provider_error", None)  # 确定没成功：这类仍然自动重试
        task_id = self.request()

        self.illustrations.run_pending()
        self.assertEqual(self.task_status(task_id), "queued", "确定失败的按原策略重排")
        self.clock.advance(minutes=2)
        self.illustrations.run_pending()

        # 第一次尝试的证件照发出后报错（确定没成功），重试时证件照与正图各再发一次 → 共 3 次
        self.assertEqual(art.sent, 3, "确定失败的会自动重试，并且真的又发了出去")
        self.assertEqual(self.illustration_status(task_id), "ready")
        self.assertIsNone(self.illustrations.outcome_of(task_id), "画成了就既不是失败也不是未确认")

    def test_an_explicit_redraw_starts_a_new_attempt_and_keeps_the_unknown_record(self) -> None:
        self.use(None, "timeout")
        task_id = self.request()
        self.illustrations.run_pending()
        self.assertEqual(self.illustrations.outcome_of(task_id), "unknown")
        self.use(None)  # 重画这次成功（已经有参考照，只要一次调用）

        self.illustrations.retry(task_id)
        self.illustrations.run_pending()

        rows = self.reservations()
        self.assertEqual([r["status"] for r in rows], ["unknown", "settled"], f"旧的一笔仍是结果不明，新尝试另起一笔：{rows}")
        self.assertEqual(self.illustration_status(task_id), "ready")
        self.assertIsNone(self.illustrations.outcome_of(task_id))

    # ---- CR-A5：重画的两次写入合并成一个事务 ----
    def test_redraw_reschedules_the_task_and_the_display_in_one_transaction(self) -> None:
        self.use("timeout")
        task_id = self.request()
        self.illustrations.run_pending()
        self.assertEqual(self.task_status(task_id), "failed")
        seen: list[bool] = []
        original = self.illustrations.tasks.retry_failed

        def watched(tid, **kwargs):
            seen.append(kwargs.get("conn") is not None)
            return original(tid, **kwargs)

        self.illustrations.tasks.retry_failed = watched

        self.illustrations.retry(task_id)

        self.assertEqual(seen, [True], "任务重排要和展示状态在同一个事务里（retry_failed 要收到 conn）")
        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("queued", "processing"))

    def test_a_redraw_that_fails_midway_rolls_back_both_writes(self) -> None:
        """故障注入：改展示状态那一步失败时，任务重排也要回滚——不能只断言传了 conn。"""
        self.use("timeout")
        task_id = self.request()
        self.illustrations.run_pending()
        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("failed", "failed"))

        with mock.patch.object(illustrations_mod, "unit_of_work", failing_display_write):
            with self.assertRaises(sqlite3.OperationalError):
                self.illustrations.retry(task_id)

        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("failed", "failed"),
                         "一步失败，两边一起回滚：不会出现“任务已重排、页面还写着没画成”")
        self.illustrations.retry(task_id)
        self.assertEqual((self.task_status(task_id), self.illustration_status(task_id)), ("queued", "processing"), "修好后重画照常可用")


if __name__ == "__main__":
    unittest.main()
