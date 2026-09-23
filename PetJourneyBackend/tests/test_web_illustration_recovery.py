"""生图失败要按**调用阶段**定性，恢复要认得出"哪一次"尝试（包 A 第 3 片的补充）。

两件事：
1. 供应商已经受理并出图，之后解析、解码、取图才失败——不能当成"生成失败"自动重发（钱已经花了）；
2. 判断"上一次可能已经发出"只看**最近一次**尝试：更早的 unknown 记录要保留，但不能挡住后来那次明确失败的正常重试；
   账本读不出来时按"不确定"处理，不能等同于"没有未知记录"。
替身生图，不联网、不产生付费调用。
"""

from __future__ import annotations

import sqlite3
import unittest
from unittest import mock

from app.image_provider.seedream import DoubaoSeedreamImageProvider
from app.web_providers import ImageUnavailable, WebProviders
from app.web_providers.images import failure_reason
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator

# 这些原因表示"一次都没发出去"：不计入已发出，也不该计费
NOT_SENT = ("daily_cap", "not_configured", "rejected", "provider_error")


class StagedIllustrator(FakeIllustrator):
    """按顺序演每一次调用：None 表示成功，字符串表示这次抛 ImageUnavailable(该原因)。"""

    def __init__(self, *outcomes: str | None) -> None:
        super().__init__()
        self.outcomes = list(outcomes)
        self.attempts = 0  # 调用了几次（不管计不计费）
        self.sent = 0  # 其中可能已经计费的几次

    def render(self, prompt, reference=None, size="2048x2048"):
        outcome = self.outcomes.pop(0) if self.outcomes else None
        self.prompts.append(prompt)
        self.attempts += 1
        if outcome is not None:
            if outcome not in NOT_SENT:
                self.sent += 1  # 已经发出去了（可能已计费）
            raise ImageUnavailable(outcome)
        self.sent += 1
        from app.image_provider.models import GeneratedImage

        return GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\nfake", mime_type="image/png", model="fake", provider="fake", source="url")


class SimulatedExit(BaseException):
    """模拟进程被杀：不是 Exception，任务循环的兜底捕不到，任务停在"领取中"。"""


class LedgerErrorConnection:
    """注入故障：读额度表时报错（锁死、损坏），其余查询照常。"""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql, params=()):
        if "web_budget_reservations" in sql:
            raise sqlite3.OperationalError("database is locked (injected)")
        return self._conn.execute(sql, params)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class UnreadableLedger:
    def __init__(self, storage) -> None:
        self._storage = storage

    def connect(self):
        return LedgerErrorConnection(self._storage.connect())

    def __getattr__(self, name):
        return getattr(self._storage, name)


class IllustrationRecoveryTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("recover-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.illustrations = self.web.illustrations

    def use(self, *outcomes: str | None) -> StagedIllustrator:
        illustrator = StagedIllustrator(*outcomes)
        self.web.providers = WebProviders(enabled=True, chat=self.web.providers.chat, geo=None, illustrator=illustrator, meter=None)
        self.illustrations.illustrator = illustrator
        return illustrator

    def request(self) -> str:
        task_id = self.illustrations.request_image(self.owner.user_id, self.owner.pet_id, "recover:selfie", style="selfie",
                                                   place="码头", city="香港", scene="坐着")
        self.assertIsNotNone(task_id)
        return task_id

    def reservations(self) -> list[tuple[str, str | None]]:
        with self.app.state.storage.connect() as conn:
            return [(r["status"], r["outcome"]) for r in conn.execute(
                "SELECT status, outcome FROM web_budget_reservations ORDER BY rowid")]

    def status(self, task_id: str) -> tuple[str, str]:
        """(任务状态, 页面上的插画状态)"""
        with self.app.state.storage.connect() as conn:
            shown = conn.execute("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,)).fetchone()["status"]
        return self.illustrations.tasks.get(task_id).status, shown

    # ---- 一、按调用阶段定性 ----
    def test_a_failure_after_the_generation_was_accepted_is_not_a_failed_generation(self) -> None:
        """真实适配器：响应已经回来（生成已受理），取图那一步失败 → 结果不明，不是"生成失败"。"""
        provider = DoubaoSeedreamImageProvider(self.settings)
        accepted = {"data": [{"url": "https://example.invalid/pic.png"}], "model": "seedream-fake"}
        with mock.patch.object(DoubaoSeedreamImageProvider, "_api_key", return_value="k"), \
             mock.patch.object(DoubaoSeedreamImageProvider, "_post_json", return_value=accepted), \
             mock.patch.object(DoubaoSeedreamImageProvider, "_download_image", side_effect=ValueError("unexpected content type")):
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate_image_with_references("prompt", references=[], size="2048x2048")
        self.assertEqual(failure_reason(ctx.exception), "unconfirmed", "取图失败发生在受理之后：结果不明")

        malformed = {"data": [], "model": "seedream-fake"}  # 响应回来了但结构不对：同样是受理之后
        with mock.patch.object(DoubaoSeedreamImageProvider, "_api_key", return_value="k"), \
             mock.patch.object(DoubaoSeedreamImageProvider, "_post_json", return_value=malformed):
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate_image_with_references("prompt", references=[], size="2048x2048")
        self.assertEqual(failure_reason(ctx.exception), "unconfirmed", "解析失败发生在受理之后：结果不明")

        with mock.patch.object(DoubaoSeedreamImageProvider, "_api_key", return_value="k"), \
             mock.patch.object(DoubaoSeedreamImageProvider, "_post_json", side_effect=ConnectionRefusedError("connection refused")):
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate_image_with_references("prompt", references=[], size="2048x2048")
        self.assertEqual(failure_reason(ctx.exception), "provider_error", "连不上：确定没发出，可以自动重试")

    def test_ssl_and_http_status_are_classified_by_evidence_not_by_message_text(self) -> None:
        """两条定向反例：

        1. SSL 错误也可能发生在**请求发出之后**的读取阶段，不能只因为字符串里有 ssl 就当作"没发出、可以自动重发"；
        2. HTTP 状态要按 `HTTPError.code` 判断。408 必须明确处理，不能指望错误文案里恰好有 timeout；
           认证/参数这类错误反复重试同一请求也没有意义。
        """
        import ssl
        import urllib.error

        def wrapped(cause: BaseException) -> BaseException:
            """模拟适配器的包装：RuntimeError(...) from 原异常（发送阶段抛出）。"""
            try:
                try:
                    raise cause
                except BaseException as exc:  # noqa: BLE001
                    raise RuntimeError(f"seedream image request failed: {exc}") from exc
            except RuntimeError as outer:
                return outer

        # 真实 SSLError 的字符串里带 [SSL: ...]，旧的宽泛 "ssl" 标记正是被它命中
        read_phase_ssl = wrapped(ssl.SSLError(1, "[SSL: APPLICATION_DATA_AFTER_CLOSE_NOTIFY] application data after close notify (_ssl.c:2706)"))
        self.assertEqual(failure_reason(read_phase_ssl), "unconfirmed", "读取阶段的 SSL 错误：可能已经受理，不能自动重发")

        def http(code: int, reason: str) -> BaseException:
            return wrapped(urllib.error.HTTPError("https://example.invalid/x", code, reason, {}, None))

        self.assertEqual(failure_reason(http(408, "")), "timeout", "408 按状态码判定，不依赖文案里有没有 timeout")
        self.assertEqual(failure_reason(http(401, "Unauthorized")), "rejected", "认证错误：没受理，重试同一请求也没用")
        self.assertEqual(failure_reason(http(400, "Bad Request")), "rejected", "参数错误：没受理，不该反复重试")
        self.assertEqual(failure_reason(http(429, "Too Many Requests")), "provider_error", "限流：没受理，过一会儿重试是合理的")
        self.assertEqual(failure_reason(http(503, "Service Unavailable")), "unconfirmed", "5xx 阶段不明：保守记结果不明")

    def test_a_rejected_request_is_refunded_and_not_retried(self) -> None:
        """参数/认证被拒：一次都没受理 → 整笔退回；但也不自动重试，避免同一个坏请求反复发。"""
        art = self.use("rejected")
        task_id = self.request()

        self.illustrations.run_pending()

        self.assertEqual(art.sent, 0, "被当场拒绝：没有产出，也不计费")
        self.assertEqual(self.reservations(), [("released", "not_sent")], "整笔退回")
        self.assertEqual(self.status(task_id), ("failed", "failed"), "不自动重试，等主人处理")
        self.assertEqual(self.illustrations.outcome_of(task_id), "failed", "这是明确失败，不是结果未确认")

    def test_an_unconfirmed_result_is_settled_as_unknown_and_not_retried(self) -> None:
        art = self.use("unconfirmed")  # 已受理、取图失败
        task_id = self.request()

        self.illustrations.run_pending()

        self.assertEqual(art.sent, 1, "这一次确实发出去了")
        self.assertEqual(self.reservations(), [("unknown", "unknown")], "按结果不明结算，不能当作没发生")
        self.assertEqual(self.status(task_id), ("failed", "failed"), "不排自动重试，等主人点重画")
        self.assertEqual(self.illustrations.outcome_of(task_id), "unknown", "对外要能分辨出是结果未确认")

    # ---- 二、只看最近一次尝试 ----
    def test_an_old_unknown_does_not_block_a_later_attempt(self) -> None:
        self.use(None, "timeout")  # 第一次：证件照成功、正图超时 → 结果不明
        task_id = self.request()
        self.illustrations.run_pending()
        first = self.reservations()
        self.assertEqual([row[0] for row in first], ["unknown"])

        definite = self.use("rejected")  # 主人重画：这次被供应商当场拒绝（已有参考照，只要一次调用）
        self.illustrations.retry(task_id)
        self.illustrations.run_pending()

        self.assertEqual((definite.attempts, definite.sent), (1, 0), "旧的 unknown 不能挡住重画之后的这次调用；被拒的那次不计费")
        rows = self.reservations()
        self.assertEqual(rows[0], first[0], "更早那笔 unknown 原样保留，没有被回写")
        self.assertEqual(rows[1], ("released", "not_sent"), f"本次被当场拒绝：整笔退回，按自己的结果结算：{rows}")
        # 方法级断言：判断只看最近一次。旧实现会把更早那笔 unknown 当成"最近一次"，从而挡住本来合法的重试
        self.assertIsNone(self.illustrations._unconfirmed_attempt(task_id), "最近一次已经明确失败，不该再被更早的 unknown 影响")

        ok = self.use(None)  # 再重画一次：应当照常发出并成功
        self.illustrations.retry(task_id)
        self.illustrations.run_pending()

        self.assertEqual((ok.attempts, ok.sent), (1, 1))
        self.assertEqual(self.status(task_id)[1], "ready")
        self.assertEqual([row[0] for row in self.reservations()], ["unknown", "released", "settled"])
        self.assertIsNone(self.illustrations.outcome_of(task_id), "画成了就不再是失败或未确认")

    def test_an_unreadable_ledger_counts_as_unconfirmed(self) -> None:
        """恢复路径上账本读不出来：按"不确定"处理，不能当成"没有未知记录"而再发一次。"""
        art = self.use(None, "timeout")
        task_id = self.request()
        original = self.illustrations.tasks.fail_claim

        def killed(*args, **kwargs):  # noqa: ANN002, ANN003 - 展示状态已提交、任务终态还没写，进程就没了
            raise SimulatedExit("killed before the task state was written")

        self.illustrations.tasks.fail_claim = killed
        with self.assertRaises(SimulatedExit):
            self.illustrations.run_pending()
        self.illustrations.tasks.fail_claim = original
        self.assertEqual(art.sent, 2)

        with mock.patch.object(self.illustrations, "storage", UnreadableLedger(self.app.state.storage)):
            self.assertEqual(self.illustrations._unconfirmed_attempt(task_id), "ledger_unreadable", "读不到账本≠没有未知记录")
            self.assertEqual(self.illustrations.outcome_of(task_id), "unknown")
            self.clock.advance(minutes=5)  # 租期过了：任务被回收重排，worker 再领一次
            self.illustrations.run_pending()

        self.assertEqual(art.sent, 2, "账本读不出来时不冒险再调用一次供应商")
        self.assertEqual(self.status(task_id), ("failed", "failed"))

if __name__ == "__main__":
    unittest.main()
