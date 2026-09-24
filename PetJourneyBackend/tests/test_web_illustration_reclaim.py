"""成功结果恢复：**插画链路**。一次性临时库 ＋ 真实任务队列与额度账本 ＋ 假供应商，不联网、**0 次付费调用**。

用户 2026-09-24 派单「修角色、插画的成功结果恢复，Q 用禁网故障注入复验」。在**提交那一步**（`_commit` 里的 `on_ready`，
与写插画记录同一个领取围栏事务）注入失败，或在画的时候把时钟推过租期，造出"付费成功、结果没写进去"。

判据只看有区分力的：供应商调用次数不变、这一次尝试没有新预占、账本用量不涨、发布的是第一次那张（`-1`，字节一致）。
每条"之后没多"都配"之前真的有"。

插画与角色不同的两处，这里专门钉住：

  - **没原照时一次两张**（证件照＋场景，一笔预占两个单位）：认领之后，证件照也不重画；
  - **重画也先认领**：重画只对 failed 的任务开放，那张付过钱的图主人从没见过，认领它就是主人要的那张。
    **这是被记录的设计，不是"点了重画却没重画"的 bug**（Q 要求钉一格，免得将来有人把认领去掉、重复付费原样回来）。
    对照：没有可认领的图时，重画照旧是一次新的付费尝试，不拦。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from web_base import LUNCH_UTC, FakeClock

from app.image_provider.models import GeneratedImage
from app.web_journey.adventures import ADVENTURES
from app.web_journey.illustrations import IllustrationService
from app.web_platform import paid_result
from app.web_platform.budget import BudgetLedger, BudgetLimit
from app.web_platform.tasks import WebTaskQueue
from app.web_providers import ImageUnavailable
from task_budget_helpers import open_storage

KEY = "cafe_detective"
PHOTO = (b"\x89PNG\r\n\x1a\nowner-photo", "image/png")


class _Illustrator:
    """**替身**生图：每次返回不同的字节（能看出发布的是第几次那张），可以按次数注入超时、连不上、画得太久。"""

    available = True
    provider_label = "测试生图（假）"

    def __init__(self, *, fail=None, clock=None) -> None:
        self.calls: list[str] = []
        self.fail = fail or {}  # {第几次: 原因}
        self.clock = clock

    def render(self, prompt, reference=None, size="2048x2048", background=None) -> GeneratedImage:
        self.calls.append(size)
        reason = self.fail.get(len(self.calls))
        if reason:
            raise ImageUnavailable(reason)
        if self.clock is not None and len(self.calls) == 1:
            self.clock.advance(minutes=5)  # 画得太久：租期（120 秒）早过了，提交时围栏拒绝
        return GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\ncall-%d" % len(self.calls), mime_type="image/png",
                              model="fake", provider="fake", source="b64")


class IllustrationReclaimTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.storage = open_storage(str(root / "reclaim.sqlite3"))
        self.queue = WebTaskQueue(self.storage)
        self.ledger = BudgetLedger(self.storage)
        self.illustrations = IllustrationService(self.storage, root / "media", self.queue)
        self.use(_Illustrator())
        self.illustrations.character_of = lambda pet_id: ("cat", "小银", None)
        self.illustrations.reference_photo_of = lambda pet_id: PHOTO
        self.illustrations.reserve = lambda operation_id, pet_id, units: self.ledger.reserve(
            operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}",
            units=units, limits=[BudgetLimit("provider:image:daily", 50)])
        self.illustrations.settle = lambda permit, outcome, actual_units=None: self.ledger.settle(
            permit, outcome, actual_units=actual_units)
        self.portraits: list[bytes] = []

    # ---- 辅助 ----
    def use(self, illustrator: _Illustrator) -> None:
        self.illustrator = illustrator
        self.illustrations.illustrator = illustrator

    def adventure(self) -> str:
        event = SimpleNamespace(journey=SimpleNamespace(user_id="u-1", pet_id="pet-1"), source_event_id="ev-1",
                                data={"adventure_key": KEY, "title": ADVENTURES[KEY].title, "badge": ""})
        return self.illustrations.request(event)

    def commit_fails(self, times: int = 1) -> None:
        """在**提交**那一步（`on_ready`，与写插画记录同一个领取围栏事务）注入失败：前 `times` 次抛异常。"""
        count = []

        def flaky(task_id, url, conn=None):
            count.append(1)
            if len(count) <= times:
                raise RuntimeError("写入失败（测试注入）")

        self.illustrations.on_ready = flaky

    def without_owner_photo(self) -> None:
        """没有主人原照：要先画一张证件照当参考，一次预占两个单位。"""
        self.illustrations.reference_photo_of = lambda pet_id: None
        self.illustrations.portrait_saver = lambda pet_id, data, mime: self.portraits.append(data) or True

    def query(self, sql: str, params: tuple = ()):
        with self.storage.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def illustration(self, task_id: str) -> dict:
        return dict(self.query("SELECT * FROM web_illustrations WHERE task_id = ?", (task_id,))[0])

    def task(self, task_id: str) -> dict:
        return dict(self.query("SELECT * FROM web_tasks WHERE task_id = ?", (task_id,))[0])

    def reservations(self, task_id: str) -> list[tuple]:
        rows = self.query("SELECT operation_id, status, outcome, actual_units FROM web_budget_reservations "
                          "WHERE operation_id LIKE ? ORDER BY rowid", (f"illustration:{task_id}:%",))
        return [(row["operation_id"].rsplit(":", 1)[1], row["status"], row["outcome"], row["actual_units"]) for row in rows]

    def used(self) -> int:
        return self.ledger.usage("usage:image:illustration", now=self.clock.now)["used"]

    def later(self) -> None:
        self.clock.advance(minutes=10)  # 过了重试等待

    def run_once_more(self) -> None:
        self.later()
        self.illustrations.run_pending()

    def assert_published_first_picture(self, task_id: str) -> None:
        row = self.illustration(task_id)
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["rel_path"].endswith("-1.png"), "发布的是第一次那张")
        data = (self.illustrations.root / row["rel_path"]).read_bytes()
        receipt = json.loads((self.illustrations.root / (row["rel_path"][:-4] + paid_result.RECEIPT_SUFFIX)).read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(data).hexdigest(), receipt["sha256"], "字节与小票一致")

    # ---- ① 提交失败一次 → 自动重试认领 ----
    def test_a_paid_illustration_that_failed_to_commit_is_reclaimed_not_redrawn(self) -> None:
        self.commit_fails()
        task_id = self.adventure()

        self.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.calls), 1, "前提：第一次真的调了一次供应商")
        self.assertEqual(self.reservations(task_id), [("1", "settled", "succeeded", 1)])
        self.assertNotEqual(self.illustration(task_id)["status"], "ready", "前提：结果确实没写进去")
        self.assertTrue(self.task(task_id)["last_error"], "前提：下一次是自动重试")
        used = self.used()
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 1, "重试没有再付一次")
        self.assertEqual(self.reservations(task_id), [("1", "settled", "succeeded", 1)], "第二次尝试没有新预占")
        self.assertEqual(self.used(), used, "账本用量也没涨")
        self.assert_published_first_picture(task_id)
        self.assertEqual(self.illustration(task_id)["used_reference_photo"], 1)

    def test_without_an_owner_photo_the_portrait_is_not_redrawn_either(self) -> None:
        """一次两张（证件照＋场景）：认领之后**两张都不重画**，证件照也只存过一次。"""
        self.without_owner_photo()
        self.commit_fails()
        task_id = self.adventure()

        self.illustrations.run_pending()
        self.assertEqual(self.illustrator.calls, ["2048x2048", "2048x2048"], "前提：证件照＋场景，两次调用")
        self.assertEqual(self.reservations(task_id), [("1", "settled", "succeeded", 2)])
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 2, "认领之后一张都没重画")
        self.assertEqual(len(self.portraits), 1, "证件照只存过一次")
        self.assert_published_first_picture(task_id)
        self.assertEqual(self.illustration(task_id)["used_reference_photo"], 1, "用的是那次画的证件照")

    # ---- ② 丢了租约 → 同样认领 ----
    def test_losing_the_lease_mid_draw_is_reclaimed(self) -> None:
        self.use(_Illustrator(clock=self.clock))
        task_id = self.adventure()

        # 每轮只跑一个：默认一轮最多五个，第一次被围栏拒绝后，同一轮的下一次循环就会回收它、认领、发布——
        # 中间状态留不下来，"前提"就无从核对
        self.illustrations.run_pending(limit=1)
        self.assertEqual(len(self.illustrator.calls), 1)
        self.assertEqual(self.reservations(task_id), [("1", "settled", "succeeded", 1)])
        self.assertEqual(self.task(task_id)["status"], "running", "前提：围栏拒绝了提交，任务等下一次领取按 lease_expired 回收")
        self.illustrations.run_pending(limit=1)

        self.assertEqual(len(self.illustrator.calls), 1, "重试没有再付一次")
        self.assertEqual(self.task(task_id)["attempts"], 2)
        self.assert_published_first_picture(task_id)

    # ---- ③ 重画也先认领（被记录的设计）＋ 对照 ----
    def test_after_a_second_commit_failure_a_redraw_still_reclaims(self) -> None:
        """自动重试最多 2 次：第二次认领后提交**又**失败，任务进 failed；主人点「重画」，第三次**仍然认领**。

        **这就是那格被记录的设计**：存在可认领的图时，重画 → 0 次供应商调用、0 笔新预占，发布第一次那张。
        看起来像"点了重画却没重画"——但那张图主人从没见过；把认领去掉，重复付费就原样回来。
        """
        self.commit_fails(times=2)
        task_id = self.adventure()
        self.illustrations.run_pending()
        self.run_once_more()
        self.assertEqual(self.task(task_id)["status"], "failed", "前提：两次都没写进去，任务进终态")
        self.assertEqual(self.illustration(task_id)["status"], "failed", "主人看到的是没画成，可以点重画")
        self.assertEqual(len(self.illustrator.calls), 1, "前提：第二次是认领，不是重画")

        self.assertEqual(self.illustrations.retry(f"{task_id}#2"), "requeued")
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 1, "重画也没有再付一次")
        self.assertEqual(self.reservations(task_id), [("1", "settled", "succeeded", 1)], "三次执行，只有第一次那一笔预占")
        self.assert_published_first_picture(task_id)

    def test_a_redraw_with_nothing_to_reclaim_pays_for_a_new_picture(self) -> None:
        """**正向对照**：上一次超时（可能已计费、结果不明），自动重试不重发；主人显式重画——没有可认领的图，
        照旧是一次新的付费尝试，**不能拦**。防的是把修复做成"一律不重画"。"""
        self.use(_Illustrator(fail={1: "timeout"}))
        task_id = self.adventure()
        self.illustrations.run_pending()
        self.run_once_more()
        self.assertEqual(len(self.illustrator.calls), 1, "前提：超时之后自动重试不重发")

        self.assertEqual(self.illustrations.retry(f"{task_id}#1"), "requeued")
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 2, "主人要的新一张，真的画了")
        row = self.illustration(task_id)
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["rel_path"].endswith("-2.png"), "发布的是重画那一次的")

    # ---- ④ 找不回来：不重付；对照：确实没付过钱的照常重试 ----
    def test_a_missing_receipt_is_not_paid_for_again(self) -> None:
        """钱付了、小票没了：**不重复付费 ✔**；那张图还在磁盘上，但**不被发布**（取舍如实钉住）。"""
        self.commit_fails()
        task_id = self.adventure()
        self.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.calls), 1)
        stem = f"illustrations/u-1/{self.illustration(task_id)['illustration_id']}-1"
        (self.illustrations.root / (stem + paid_result.RECEIPT_SUFFIX)).unlink()
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 1, "不重复付费")
        self.assertEqual(self.illustration(task_id)["status"], "failed", "如实落「没画成」")
        self.assertTrue((self.illustrations.root / f"{stem}.png").is_file(), "那张付过钱的图仍在磁盘上，但没有被发布")

    def test_a_provider_error_is_still_retried_and_sent_again(self) -> None:
        """连不上＝确定没受理：第一笔预占整笔释放，自动重试照常再发一次——**别把修复做成"一律不重试"**。"""
        self.use(_Illustrator(fail={1: "provider_error"}))
        task_id = self.adventure()
        self.illustrations.run_pending()
        self.assertEqual([item[1:3] for item in self.reservations(task_id)], [("released", "not_sent")])
        self.run_once_more()

        self.assertEqual(len(self.illustrator.calls), 2, "确定没付过钱的，重试真的再发一次")
        self.assertEqual(self.illustration(task_id)["status"], "ready")


if __name__ == "__main__":
    unittest.main()
