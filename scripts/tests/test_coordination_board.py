"""Isolated coordination tests. No backend, provider or real business DB imports."""
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coordination_board.projection import ZONE, build_board, parse_events, read_document
from coordination_board.server import BoardServer

NOW = datetime(2026, 9, 23, 4, 0, tzinfo=ZONE)
NAME = "WINDOW-claude-20260922-234337-4bef.log.md"


class BlackboardTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / "output/playwright/live-blackboard-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.repo = Path(self.temp.name)
        self.root = self.repo / "docs/coordination"
        self.root.mkdir(parents=True)
        self.review = {"snapshotAt": "2026-09-23T00:38:00+08:00", "packages": []}
        (self.root / "petsoul-agent-oversight.snapshot.json").write_text(json.dumps(self.review), encoding="utf-8")
        self.path = self.root / NAME
        self.path.write_text("## START — pkg-A-infra\n时间：2026-09-23 01:00 +08:00\n是否释放：否。\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_refresh_observes_append_without_changing_review(self):
        first = build_board(self.repo, NOW)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("\n## HANDOFF — pkg-A-infra\n时间：2026-09-23 02:00 +08:00\n结果：新切片\n是否释放：否。\n")
        second = build_board(self.repo, NOW)
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(second["events"][0]["title"], "HANDOFF — pkg-A-infra")
        self.assertEqual(first["review"], second["review"])
        self.assertEqual(second["windows"][0]["processState"], "未探测；日志沉默不代表停止")

    def test_record_time_beats_physical_order_without_scope_inference(self):
        self.path.write_text("## RELEASE — pkg-A-infra\n时间：2026-09-23 02:00 +08:00\n是否释放：是，仅测试文件。\n\n## START — pkg-A-infra\n时间：2026-09-23 01:00 +08:00\n是否释放：否。", encoding="utf-8")
        board = build_board(self.repo, NOW)
        window = board["windows"][0]
        self.assertNotEqual(window["latestEventId"], window["lastAppendedId"])
        self.assertEqual(board["events"][0]["taskId"], "pkg-A-infra")
        self.assertNotIn("released", window)
        self.assertIn("仅测试文件", board["events"][0]["releaseStatement"])

    def test_placeholder_and_future_times_not_promoted(self):
        text = "## PROGRESS\n时间：2026-09-23 03:1X +0800\n\n## VERIFY\n时间：2026-09-24 03:00 +0800"
        events = parse_events(text, NAME, NOW)
        self.assertTrue(all(event["recordedAt"] is None for event in events))
        self.assertTrue(all(event["timeNotes"] for event in events))

    def test_correction_preserved_as_own_record(self):
        text = "## HANDOFF\n时间：2026-09-23 00:26 +08:00\n通过。\nCORRECTION（2026-09-23 00:28 +08:00）：前述 SCOPE_CHANGE 时间有误。\n- 时间：写的是00:36，实际约00:33。\n不是新的交接。"
        events = parse_events(text, NAME, NOW)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["kinds"], ["CORRECTION"])
        self.assertEqual(events[1]["recordedAt"], "2026-09-23T00:28:00+08:00")
        self.assertIn("SCOPE_CHANGE 时间有误", events[1]["body"])

    def test_incidental_dates_are_not_event_time(self):
        events = parse_events("## PROGRESS\n对方于2026-09-23 03:00已经交接。", NAME, NOW)
        self.assertIsNone(events[0]["recordedAt"])

    def test_source_links_and_timezone_conversion(self):
        events = parse_events("# 日志\n\n## VERIFY\n时间：2026-09-22T17:25:41Z\n结果：PASS", NAME, NOW)
        self.assertEqual(events[0]["line"], 3)
        self.assertEqual(events[0]["recordedAt"], "2026-09-23T01:25:41+08:00")
        self.assertEqual(events[0]["tier"], "窗口原文 · 未自动验收")

    def test_broken_review_does_not_hide_logs(self):
        (self.root / "petsoul-agent-oversight.snapshot.json").write_text("{partial", encoding="utf-8")
        board = build_board(self.repo, NOW)
        self.assertIsNone(board["review"])
        self.assertEqual(len(board["windows"]), 1)
        self.assertEqual(len(board["errors"]), 1)

    def test_secret_redaction_and_allowlist(self):
        self.path.write_text("api_key=abcdefghijklmnopqrst\n-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", encoding="utf-8")
        text, _ = read_document(self.root, NAME)
        self.assertNotIn("abcdefghijklmnop", text)
        self.assertNotIn("\nabc\n", text)
        for name in ("../AGENTS.md", "accounts.json", ".env", "WINDOW-../../foo.log.md"):
            with self.assertRaises(ValueError):
                read_document(self.root, name)

    def test_empty_source_returns_explicit_error(self):
        self.path.unlink()
        board = build_board(self.repo, NOW)
        self.assertEqual(board["windows"], [])
        self.assertEqual(board["errors"][0]["reason"], "Missing")

    def test_http_refresh_no_store_and_no_mutations(self):
        with BoardServer(self.repo, 0) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/board") as response:
                    first = json.load(response)
                    self.assertIn("no-store", response.headers["Cache-Control"])
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write("\n## PROGRESS\n时间：2026-09-23 02:00 +0800\n结果：追加立即可见")
                with urlopen(base + "/api/board") as response:
                    second = json.load(response)
                self.assertNotEqual(first["revision"], second["revision"])
                self.assertIn("追加立即可见", second["events"][0]["body"])
                for request, code in [
                    (Request(base + "/api/board", method="POST", data=b"{}"), 405),
                    (Request(base + "/api/log?name=..%2FAGENTS.md"), 400),
                    (Request(base + "/.env"), 404),
                    (Request(base + "/api/board", headers={"Origin": "https://attacker.invalid"}), 403),
                    (Request(base + "/api/board", headers={"Host": "attacker.invalid"}), 403),
                ]:
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request)
                    self.assertEqual(raised.exception.code, code)
            finally:
                server.shutdown()
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
