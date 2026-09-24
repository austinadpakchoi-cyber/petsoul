"""成功结果恢复：**角色链路**（中性站姿与其余姿态）。真实装配 ＋ 假供应商 ＋ 不联网，**0 次付费调用**。

用户 2026-09-24 派单「修角色、插画的成功结果恢复，Q 用禁网故障注入复验」。缺口：付费调用已成功、预占已结算成
`settled/succeeded`，结果却没写进去（发布事务里抛异常、丢了租约），自动重试会**再调一次供应商**。

这里用**真实链路造出那个状态**：要么在发布写入那一步注入一次失败，要么在画的时候把时钟推过租期。
判据只看**有区分力**的三件事（Q 提醒「最终 ready」修前修后都绿，分不开）：

  1. 供应商调用次数**不变**；
  2. 这一次尝试**没有新预占**，账本用量**也不涨**（这两件可以分别失败，分开断言）；
  3. 发布出来的就是上一次那张：路径带 `-1`，文件字节的 sha256 与记录一致。

每一条"之后没多"都配一条"之前真的有"——替身没装上时，"调用次数不变"会空转变绿。
插画链路那半在 `test_web_illustration_reclaim.py`；判定表本身在 `test_web_paid_result.py`。
"""

from __future__ import annotations

import hashlib
import unittest
from contextlib import contextmanager
from unittest import mock

import app.web_character.poses as poses_module
import app.web_character.service as service_module
from character_fakes import FakeCharacterIllustrator, opaque_png
from pose_chain_base import PoseChainBase

from app.web_platform import paid_result


class _SlowIllustrator(FakeCharacterIllustrator):
    """第一张画得太久：画完时租期（120 秒）早就过了，发布时领取围栏拒绝，这次结果整批作废。"""

    def __init__(self, clock) -> None:
        super().__init__()
        self._clock = clock

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        image = super().render(prompt, reference, size=size, background=background)
        if self.calls == 1:
            self._clock.advance(minutes=5)
        return image


class _BusyOnce(FakeCharacterIllustrator):
    """第一次连不上（`provider_error`，确定没受理），之后正常——对照组：**确实没付过钱的，照常重试并真的再发一次**。"""

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        self.fail_reason = "provider_error" if self.calls == 0 else None
        return super().render(prompt, reference, size=size, background=background)


class CharacterReclaimTests(PoseChainBase):
    # ---- 辅助 ----
    @contextmanager
    def writes_fail(self, module, times: int = 1):
        """在**发布写入**那一步（领取围栏事务里）注入失败：前 `times` 次抛异常，之后照常。
        注入的是"写入失败"不是"调用失败"——调用失败重试不会多付钱，那不是这里要验的。"""
        real, count = module.mark_ready_in, []

        def flaky(*args, **kwargs):
            count.append(1)
            if len(count) <= times:
                raise RuntimeError("写入失败（测试注入）")
            return real(*args, **kwargs)

        with mock.patch.object(module, "mark_ready_in", flaky):
            yield count

    def task_of(self, row) -> dict:
        return dict(self.query("SELECT * FROM web_tasks WHERE task_id = ?", (row["task_id"],))[0])

    def reservations_of(self, task_id: str) -> list[tuple]:
        rows = self.query("SELECT operation_id, status, outcome, actual_units FROM web_budget_reservations "
                          "WHERE operation_id LIKE ? ORDER BY rowid", (f"character:{task_id}:%",))
        return [(row["operation_id"].rsplit(":", 1)[1], row["status"], row["outcome"], row["actual_units"]) for row in rows]

    def used(self) -> int:
        return self.web.character.ledger.usage("usage:image:character", now=self.clock.now)["used"]

    def later(self) -> None:
        self.clock.advance(minutes=10)  # 过了重试等待（第 n 次失败后 60s×2^(n-1)）

    def assert_first_attempt_paid_and_lost(self, row) -> None:
        """前提（非空）：第一次**真的发了、真的结算成 succeeded**，而结果**确实没写进去**——反例是真的。"""
        self.assertEqual(self.illustrator.calls, 1, "前提：第一次真的调了一次供应商")
        self.assertEqual(self.reservations_of(row["task_id"]), [("1", "settled", "succeeded", 1)])
        self.assertNotEqual(self.neutral()["state"], "ready", "前提：结果确实没写进去")
        self.assertTrue(self.task_of(row)["last_error"], "前提：任务带着错误排回去了，下一次是**自动重试**")

    # ---- ① 发布写入失败一次 → 认领，不重画 ----
    def test_a_paid_neutral_that_failed_to_publish_is_reclaimed_not_redrawn(self) -> None:
        with self.writes_fail(service_module):
            self.web.character.run_pending(limit=1)
            row = self.neutral()
            self.assert_first_attempt_paid_and_lost(row)
            used = self.used()
            self.later()
            self.web.character.run_pending(limit=1)

        row = self.neutral()
        self.assertEqual(self.illustrator.calls, 1, "重试没有再付一次")
        self.assertEqual(self.reservations_of(row["task_id"]), [("1", "settled", "succeeded", 1)], "第二次尝试没有新预占")
        self.assertEqual(self.used(), used, "账本用量也没涨")
        self.assertEqual(row["state"], "ready")
        self.assertTrue(row["rel_path"].endswith("-1.png"), "发布的是第一次那张，不是第二次画的")
        self.assertEqual(hashlib.sha256((self.web.character.root / row["rel_path"]).read_bytes()).hexdigest(), row["sha256"])
        self.assertEqual(self.active()["set_id"], row["set_id"], "这一套照常生效")

    # ---- ② 丢了租约 → 同样认领 ----
    def test_losing_the_lease_mid_draw_is_reclaimed_too(self) -> None:
        """触发条件换成"丢租约"（Q 的 C29 就是这么撞上的）：发布时围栏拒绝，下一次领取回收成 `lease_expired` 再跑。"""
        self.illustrator = _SlowIllustrator(self.clock)
        self.web.character.illustrator = self.illustrator

        self.web.character.run_pending(limit=1)
        row = self.neutral()
        self.assertEqual(self.illustrator.calls, 1, "前提：第一次真的调了")
        self.assertEqual(self.reservations_of(row["task_id"]), [("1", "settled", "succeeded", 1)])
        self.assertNotEqual(row["state"], "ready", "前提：围栏拒绝了这次写入")
        self.assertEqual(self.task_of(row)["status"], "running", "前提：任务还停在 running，等下一次领取按 lease_expired 回收")
        self.web.character.run_pending(limit=1)

        row = self.neutral()
        self.assertEqual(self.task_of(row)["attempts"], 2, "第二次领取就是回收后的那次重试")
        self.assertEqual(self.illustrator.calls, 1, "重试没有再付一次")
        self.assertEqual(self.reservations_of(row["task_id"]), [("1", "settled", "succeeded", 1)])
        self.assertEqual(row["state"], "ready")
        self.assertTrue(row["rel_path"].endswith("-1.png"))

    # ---- ③ 找不回来：不重付，取舍如实钉住 ----
    def test_a_missing_receipt_is_not_paid_for_again_and_the_picture_stays_on_disk(self) -> None:
        """钱付了、小票没了（例如写图前后崩了）：**不重复付费 ✔**；代价如实写下——**那张图还在磁盘上，但不会被发布**，
        主人看到"没画成"、可以显式调整形象。"不重复付费"与"不浪费已付费的结果"是两件事，这一支只做到了前一件。"""
        with self.writes_fail(service_module):
            self.web.character.run_pending(limit=1)
            row = self.neutral()
            self.assert_first_attempt_paid_and_lost(row)
            stem = f"characters/{row['user_id']}/{row['asset_id']}-1"
            (self.web.character.root / (stem + paid_result.RECEIPT_SUFFIX)).unlink()
            self.later()
            self.web.character.run_pending(limit=1)

        row = self.neutral()
        self.assertEqual(self.illustrator.calls, 1, "不重复付费")
        self.assertEqual((row["state"], row["reason"]), ("failed", "unknown_result"))
        self.assertTrue((self.web.character.root / f"{stem}.png").is_file(), "那张付过钱的图仍在磁盘上……")
        self.assertIsNone(self.active(), "……但没有被当成功发布")

    def test_a_picture_changed_on_disk_is_not_reclaimed(self) -> None:
        with self.writes_fail(service_module):
            self.web.character.run_pending(limit=1)
            row = self.neutral()
            self.assert_first_attempt_paid_and_lost(row)
            (self.web.character.root / f"characters/{row['user_id']}/{row['asset_id']}-1.png").write_bytes(opaque_png())
            self.later()
            self.web.character.run_pending(limit=1)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual((self.neutral()["state"], self.neutral()["reason"]), ("failed", "unknown_result"),
                         "字节对不上小票：不认，也不重付")

    def test_a_second_publish_failure_ends_without_paying_again(self) -> None:
        """角色任务最多跑 2 次：第二次**认领**之后发布又失败，任务进终态——**仍然不重付**。
        那张图留在磁盘上（与"找不回来"同一取舍）；「调整形象」是新建任务，会是一次新的付费尝试。"""
        with self.writes_fail(service_module, times=2):
            self.web.character.run_pending(limit=1)
            self.assert_first_attempt_paid_and_lost(self.neutral())
            self.later()
            self.web.character.run_pending(limit=1)

        row = self.neutral()
        self.assertEqual(self.illustrator.calls, 1, "第二次是认领，不是重画")
        self.assertEqual(self.reservations_of(row["task_id"]), [("1", "settled", "succeeded", 1)])
        self.assertEqual((row["state"], row["reason"]), ("failed", "attempts_exhausted"))
        self.assertTrue((self.web.character.root / f"characters/{row['user_id']}/{row['asset_id']}-1.png").is_file())

    # ---- ④ 对照：没付过钱的，行为不变 ----
    def test_a_provider_error_is_still_retried_and_sent_again(self) -> None:
        """**别把修复做成"一律不重试"**：连不上＝确定没受理，第一笔预占整笔释放，重试照常再发一次。"""
        self.illustrator = _BusyOnce()
        self.web.character.illustrator = self.illustrator

        self.web.character.run_pending(limit=1)
        row = self.neutral()
        self.assertEqual([item[1:3] for item in self.reservations_of(row["task_id"])], [("released", "not_sent")],
                         "前提：第一次确定没发出，那笔预占整笔释放")
        self.later()
        self.web.character.run_pending(limit=1)

        self.assertEqual(self.illustrator.calls, 2, "确定没付过钱的，重试真的再发一次")
        self.assertEqual(self.neutral()["state"], "ready")

    def test_a_timeout_is_still_never_resent(self) -> None:
        """超时＝可能已经计费、结果不明：与修复前一样，不重发。"""
        self.illustrator = FakeCharacterIllustrator(fail_reason="timeout")
        self.web.character.illustrator = self.illustrator

        self.web.character.run_pending(limit=1)
        self.later()
        self.web.character.run_pending(limit=1)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual(self.web.character.view(self.pet_id).state, "unknown")

    # ---- ⑤ 其余姿态走同一条认领 ----
    def test_a_pose_that_failed_to_publish_is_reclaimed(self) -> None:
        self.switch_on()
        self.go_live()
        with self.writes_fail(poses_module):
            self.web.character.run_pending(limit=1)  # 第一个姿态：画了、发布写入失败
            self.assertEqual(self.illustrator.calls, 2, "前提：中性 1 ＋ 这个姿态 1")
            self.later()
            self.web.character.run_pending(limit=10)

        self.assertEqual(self.illustrator.calls, 6, "中性 1 ＋ 五个姿态各 1：没有哪一个画了两次")
        rows = self.pose_rows()
        self.assertEqual({row["state"] for row in rows}, {"ready"})
        self.assertTrue(all(row["rel_path"].endswith("-1.png") for row in rows), "认领的那一张也是它第一次画的")


if __name__ == "__main__":
    unittest.main()
