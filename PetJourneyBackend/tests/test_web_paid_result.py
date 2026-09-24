"""已付费结果的认领（`web_platform/paid_result.py`）：小票与"重试前问上一次"的判定表。纯单元：一次性临时库，不联网、0 次付费调用。

两条链路（角色、插画）的整链故障注入在 `test_web_character_reclaim.py` / `test_web_illustration_reclaim.py`；
这里只钉判定本身——**哪一种上一次，换来哪一种这一次**：

    没有预占                           → 照常执行
    reserved / unknown / expired        → 不重发（可能已经发出）
    settled ＋ succeeded，小票与图都对    → 认领，不预占、不发送
    settled ＋ succeeded，找不到或对不上  → 不重发（宁可不画，也不重复付费）
    released、settled ＋ failed         → 照常重试（与修复前相同）
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from app.image_provider.models import GeneratedImage
from app.web_platform import paid_result
from app.web_platform.budget import BudgetLedger
from task_budget_helpers import open_storage

PREFIX = "character:wt_demo:"
TEMPLATE = "characters/u-1/pc-demo-{attempt}"
PNG = b"\x89PNG\r\n\x1a\n" + b"paid-bytes"


def image(data: bytes = PNG) -> GeneratedImage:
    return GeneratedImage(image_bytes=data, mime_type="image/png", model="fake-model", provider="fake", source="b64")


class _Root(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "media"
        (self.root / "characters" / "u-1").mkdir(parents=True)
        self.storage = open_storage(str(Path(tmp.name) / "ledger.sqlite3"))
        self.ledger = BudgetLedger(self.storage)

    def paid_image(self, attempt: int, data: bytes = PNG) -> str:
        """这一次的图落盘并写小票，与链路里的顺序相同：先图、后小票。"""
        stem = TEMPLATE.format(attempt=attempt)
        rel = f"{stem}.png"
        (self.root / rel).write_bytes(data)
        paid_result.write_receipt(self.root, stem, rel, image(data))
        return rel

    def reservation(self, attempt: int, outcome: str | None, units: int = 1):
        permit = self.ledger.reserve(f"{PREFIX}{attempt}", provider="image", purpose="character", subject_scope="pet:p-1",
                                     units=units, limits=[])
        if outcome is not None:
            self.ledger.settle(permit, outcome, actual_units=None if outcome == "not_sent" else units)
        return permit

    def resume(self):
        return paid_result.resume(self.storage, PREFIX, self.root, TEMPLATE)


class ReceiptTests(_Root):
    def test_a_receipt_brings_back_the_very_same_bytes(self) -> None:
        rel = self.paid_image(1)

        found = paid_result._reclaim(self.root, TEMPLATE.format(attempt=1))

        self.assertIsNotNone(found)
        reclaimed, found_rel, _ = found
        self.assertEqual((found_rel, reclaimed.image_bytes, reclaimed.provider, reclaimed.model), (rel, PNG, "fake", "fake-model"))
        self.assertEqual(reclaimed.source, "reclaimed", "认领来的要看得出是认领来的，不冒充刚画的")

    def test_an_image_changed_after_the_receipt_is_not_reclaimed(self) -> None:
        rel = self.paid_image(1)
        (self.root / rel).write_bytes(PNG + b"tampered")

        self.assertIsNone(paid_result._reclaim(self.root, TEMPLATE.format(attempt=1)), "字节现算 sha256 对不上就不认")

    def test_a_receipt_pointing_at_another_picture_is_not_reclaimed(self) -> None:
        """小票只能指向**这一次**那张图：换成同目录里另一张（比如别的尝试的），不认。"""
        self.paid_image(1)
        other = self.paid_image(2, PNG + b"-2")
        receipt = self.root / (TEMPLATE.format(attempt=1) + paid_result.RECEIPT_SUFFIX)
        body = json.loads(receipt.read_text(encoding="utf-8"))
        body.update(rel=other, sha256=hashlib.sha256(PNG + b"-2").hexdigest())
        receipt.write_text(json.dumps(body), encoding="utf-8")

        self.assertIsNone(paid_result._reclaim(self.root, TEMPLATE.format(attempt=1)))

    def test_a_half_written_receipt_is_ignored(self) -> None:
        self.paid_image(1)
        (self.root / (TEMPLATE.format(attempt=1) + paid_result.RECEIPT_SUFFIX)).write_text('{"rel": "characters/u-1/pc', encoding="utf-8")

        self.assertIsNone(paid_result._reclaim(self.root, TEMPLATE.format(attempt=1)))

    def test_failing_to_write_a_receipt_does_not_fail_the_attempt(self) -> None:
        """写不下小票只记日志：这一次的图就在内存里，照样能发布——不能为一张小票制造一次重试。"""
        with self.assertLogs("petsoul.web.paid_result", level="WARNING"):
            paid_result.write_receipt(self.root / "no-such-folder", "characters/u-9/x-1", "characters/u-9/x-1.png", image())


class ResumeDecisionTests(_Root):
    def test_no_reservation_means_carry_on(self) -> None:
        self.assertIsNone(self.resume(), "第一次尝试：没有上一次")

    def test_maybe_sent_is_never_resent(self) -> None:
        """与修复前完全相同：reserved（崩在调用中途）、unknown（超时）一律不重发。"""
        self.reservation(1, None)
        self.assertEqual(self.resume().blocked, "previous_reserved")
        self.reservation(2, "unknown")
        self.assertEqual(self.resume().blocked, "previous_unknown")

    def test_a_paid_success_with_its_receipt_is_reclaimed(self) -> None:
        rel = self.paid_image(1)
        self.reservation(1, "succeeded")

        resumed = self.resume()

        self.assertIsNone(resumed.blocked)
        self.assertEqual((resumed.attempt, resumed.rel, resumed.image.image_bytes), (1, rel, PNG))

    def test_a_paid_success_without_its_receipt_is_not_paid_for_again(self) -> None:
        """钱付了、图找不回来（写图前崩了、小票没写下）：**不自动再付一次**。这是取舍：那张图若在磁盘上，也不会被发布。"""
        self.reservation(1, "succeeded")

        self.assertEqual(self.resume().blocked, "paid_result_missing")

    def test_a_release_or_a_paid_failure_is_retried_as_before(self) -> None:
        """确定没发出（released），或发出去了但供应商说失败（settled＋failed）：照常重试——**不把修复做成"一律不重试"**。"""
        self.reservation(1, "not_sent")
        self.assertIsNone(self.resume())
        self.reservation(2, "failed")
        self.assertIsNone(self.resume(), "settled＋failed 不能被当成可认领")

    def test_the_latest_attempt_is_picked_by_number_not_by_text(self) -> None:
        """按字符串比，"9" 会排在 "10" 后面——那会拿第 9 次的结局去判第 10 次之后该怎么办。"""
        self.paid_image(9)
        self.reservation(9, "succeeded")
        self.reservation(10, "not_sent")
        self.assertIsNone(self.resume(), "最近一次是第 10 次（没发出），照常重试")

    def test_the_receipt_of_that_attempt_is_used_not_the_current_one(self) -> None:
        """按**上一次那次的代数**找：第 3 次付费成功，就认领 `-3` 那张。"""
        self.paid_image(1, PNG + b"-1")
        rel = self.paid_image(3, PNG + b"-3")
        self.reservation(1, "not_sent")
        self.reservation(3, "succeeded")

        resumed = self.resume()

        self.assertEqual((resumed.attempt, resumed.rel, resumed.image.image_bytes), (3, rel, PNG + b"-3"))

    def test_an_unreadable_ledger_blocks_instead_of_resending(self) -> None:
        """读不到账本就不敢再发一次；**没有额度表**（迁移之前的库）则维持原来的重试行为。"""
        class _Broken:
            def __init__(self, message: str) -> None:
                self.message = message

            @contextmanager
            def connect(self):
                raise sqlite3.OperationalError(self.message)
                yield  # pragma: no cover

        self.assertEqual(paid_result.resume(_Broken("database is locked"), PREFIX, self.root, TEMPLATE).blocked,
                         "ledger_unreadable")
        self.assertIsNone(paid_result.resume(_Broken("no such table: web_budget_reservations"), PREFIX, self.root, TEMPLATE))


if __name__ == "__main__":
    unittest.main()
