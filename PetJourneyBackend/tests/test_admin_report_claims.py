"""举报认领与处理回执（方案 §3「社区审核与客服：举报分派……回复处理结果」）。

认领：同一条被举报的内容同一时刻只归一位审核员；别人不能处理它；处理完认领自动结束；30 分钟过期后别人可以接手。
回执：举报人只看自己的举报，结局只有固定措辞，不含员工身份、内部原因与被举报内容。
"""

from __future__ import annotations

import json
import unittest

from admin_base import AdminTestBase
from test_admin_concurrency import race
from web_base import LUNCH_UTC, FakeClock


class ReportFixture(AdminTestBase):
    """共用准备：一条公开动态、一条举报、两位审核员。本身没有用例。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.author = self.user("claim-poster")
        self.author.adopt_and_move_in("adopt-lan", public_posts=True)
        self.reporter = self.user("claim-reporter")
        self.first = self.staff("claim-moderator-1", ["moderator"])
        self.first.login_ok()
        self.second = self.staff("claim-moderator-2", ["moderator"])
        self.second.login_ok()
        self.post_id = self.public_post()
        report = self.reporter.post("/reports", {"target_kind": "post", "target_id": self.post_id, "reason": "内容不适"})
        self.assertEqual(report.status_code, 204, report.text)

    def public_post(self) -> str:
        self.author.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        self.run_background()
        self.clock.advance(minutes=30)
        self.run_background()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT post_id FROM web_posts WHERE visibility = 'public' ORDER BY created_at DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row, "这段旅程应当产生一条公开动态")
        return row["post_id"]

    def target(self) -> dict:
        return {"target_kind": "post", "target_id": self.post_id}

    def act(self, staff, decision: str = "takedown"):
        return staff.post("/moderation", {**self.target(), "decision": decision, "reason": "违反公开内容规范"})

    def queue_row(self, staff) -> dict:
        return next(r for r in staff.get("/reports?only_open=false").json()["reports"] if r["target_id"] == self.post_id)


class ReportClaimTests(ReportFixture):
    def test_a_claim_keeps_others_from_handling_it(self):
        claimed = self.first.post("/reports/claim", self.target())
        self.assertEqual(claimed.status_code, 200, claimed.text)
        self.assertEqual(claimed.json()["outcome"], "claimed")
        self.assertTrue(self.queue_row(self.first)["claim"]["mine"])
        seen_by_other = self.queue_row(self.second)["claim"]
        self.assertEqual((seen_by_other["username"], seen_by_other["mine"]), (self.first.username, False))
        self.assertNotIn("staff_id", seen_by_other, "队列里不回员工号，只回名字和是不是我")

        error = self.assert_admin_error(self.second.post("/reports/claim", self.target()), 409, "CONFLICT")
        self.assertEqual(error["details"]["claimed_by"], self.first.username)
        blocked = self.assert_admin_error(self.act(self.second), 409, "CONFLICT")
        self.assertEqual(blocked["details"]["reason"], "claimed_by_other")
        denied = [e for e in self.first.get("/audit?action=report.takedown").json()["entries"] if e["status"] == "denied"]
        self.assertEqual(denied[0]["actor_username"], self.second.username, "被挡下的那一次也留痕")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT visibility FROM web_posts WHERE post_id = ?", (self.post_id,)).fetchone()[0], "public")

        done = self.act(self.first)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertIsNone(self.queue_row(self.first)["claim"], "处理完，认领自动结束")

    def test_an_expired_claim_can_be_taken_over(self):
        self.assertEqual(self.first.post("/reports/claim", self.target()).status_code, 200)
        self.clock.advance(minutes=31)
        self.second.login_ok()  # 假时钟跨过了会话的空闲期
        taken = self.second.post("/reports/claim", self.target())
        self.assertEqual(taken.status_code, 200, taken.text)
        self.assertEqual(taken.json()["outcome"], "took_over_expired")
        audit = [e for e in self.second.get("/audit?action=report.claim").json()["entries"] if e["outcome"] == "took_over_expired"]
        self.assertEqual(audit[0]["changes"]["took_over_from"], self.first.staff_id)

    def test_only_the_claimer_can_release(self):
        self.first.post("/reports/claim", self.target())
        self.assert_admin_error(self.second.post("/reports/release", self.target()), 409, "CONFLICT")
        released = self.first.post("/reports/release", self.target())
        self.assertTrue(released.json()["released"])
        self.assertEqual(self.second.post("/reports/claim", self.target()).status_code, 200, "放掉之后别人就能认领")

    def test_claiming_needs_the_permission_and_a_reported_target(self):
        support = self.staff("claim-support", ["support"])
        support.login_ok()
        self.assert_admin_error(support.post("/reports/claim", self.target()), 403, "FORBIDDEN")
        self.assert_admin_error(self.first.post("/reports/claim", {"target_kind": "post", "target_id": "no-such-post"}), 404, "NOT_FOUND")

    def test_two_moderators_racing_to_claim_get_one_claim(self):
        responses = race([lambda staff=staff: staff.post("/reports/claim", self.target()) for staff in (self.first, self.second)])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM admin_report_claims").fetchone()[0], 1)


class ReporterOutcomeTests(ReportFixture):
    """举报人看回执（玩家侧 /api/v1/web/reports/mine）。"""

    def mine(self, player=None) -> list[dict]:
        response = (player or self.reporter).get("/reports/mine")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["reports"]

    def test_the_reporter_sees_received_then_the_outcome(self):
        before = self.mine()
        self.assertEqual([(r["target_id"], r["status"], r["outcome"]) for r in before], [(self.post_id, "received", "received")])
        self.assertEqual(before[0]["reason"], "内容不适", "自己写的举报理由看得到")

        self.assertEqual(self.act(self.first).status_code, 200)
        after = self.mine()[0]
        self.assertEqual((after["status"], after["outcome"]), ("resolved", "content_removed"))
        self.assertEqual(after["message"], "已处理：这条内容已不再公开展示。")
        payload = json.dumps(after, ensure_ascii=False)
        for secret in (self.first.staff_id, self.first.username, "违反公开内容规范"):
            self.assertNotIn(secret, payload, "回执里不能有员工身份或内部处理原因")

    def test_dismiss_reads_as_no_violation_found(self):
        self.assertEqual(self.act(self.first, "dismiss").status_code, 200)
        self.assertEqual(self.mine()[0]["outcome"], "no_violation_found")

    def test_each_player_only_sees_their_own_reports(self):
        stranger = self.user("claim-stranger")
        self.assertEqual(self.mine(stranger), [])
        self.assertEqual(self.client.get("/api/v1/web/reports/mine").status_code, 401, "没登录就看不到")

    def test_missing_admin_tables_read_as_not_configured_not_received(self):
        self.app.state.admin.tables_ready = False
        response = self.reporter.get("/reports/mine")
        self.assertEqual(response.status_code, 503, "查不到处理记录不等于还没处理，不能拿「已收到」顶上")
        self.assertEqual(response.json()["error"]["code"], "NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
