"""爪爪驾校拿证：四科全部通过时，在同一次提交里签发驾驶证、发借车券、登记拿证消息；领证仪式只做一次；借车券抵一次租车费。

也覆盖一致性：签发失败时整次结算回滚、可以重试且不重复发证；消息投递失败不影响驾照；旧版驾照显示“旧版驾考已通过”。
"""

from __future__ import annotations

import unittest

from app.schemas import EconomyTransactionType
from school_helpers import School
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class LicenseTestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("license-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.web.life.consider = lambda user_id, pet_id, now: None
        self.school = School(self, self.owner)
        self.owner.post("/driving/enroll")

    def licenses(self) -> list[dict]:
        return [c for c in self.owner.get("/credentials").json() if c["kind"] == "driver_license" and c["credential_id"]]

    def notes(self) -> list[str]:
        return [m["text"] for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]]

    def collection(self) -> dict[str, dict]:
        return {c["kind"]: c for c in self.owner.get("/collection").json()}


class LicenseFlowTests(LicenseTestBase):
    def test_passing_all_four_issues_the_license_voucher_and_note_together(self) -> None:
        for subject in ("s1", "s2", "s3"):
            self.assertTrue(self.school.exam(subject)["result"]["passed"])
            self.assertEqual(self.licenses(), [], "四科齐全之前没有驾照")
        final = self.school.exam("s4")
        self.assertEqual(final["result"]["next"]["kind"], "licensed")
        status = self.owner.get("/driving").json()
        self.assertEqual((status["stage"], status["voucher_available"], status["ceremony_done"]), ("licensed", True, False))
        licenses = self.licenses()
        self.assertEqual(len(licenses), 1)
        self.assertEqual(licenses[0]["title"], "PetSoul · 爪爪驾驶证 · 小型车（C）")
        detail = self.owner.get(f"/credentials/{licenses[0]['credential_id']}").json()
        fields = {f["label"]: f["value"] for f in detail["fields"]}
        self.assertIn("科一 100 分", fields["成绩"])
        self.assertIn("不代表现实驾驶资格", fields["说明"])
        self.assertEqual(sum("我拿到驾照啦" in t for t in self.notes()), 1)
        self.assertEqual(self.collection()["car_voucher"]["title"], "驾校借车券")

        first = self.owner.post("/driving/ceremony").json()
        again = self.owner.post("/driving/ceremony").json()
        self.assertEqual((first["first_time"], again["first_time"]), (True, False), "仪式只做一次，再打开是回看")
        self.assertEqual(first["license"]["number"], licenses[0]["number"])
        self.assertEqual([c["kind"] for c in self.owner.get("/collection").json()].count("license_photo"), 1, "合影只生成一张")
        self.assertTrue(self.owner.get("/driving").json()["ceremony_done"])
        titles = [i["title"] for i in self.owner.get("/timeline").json()]
        self.assertIn("报名了爪爪驾校", titles)
        self.assertIn("科目四考试通过", titles)
        # 标题写死中文、不读 `CATALOG`：读同一份就成了 `CATALOG == CATALOG`，改名改错也照样绿。
        # 2026-09-24 由「拿到驾驶证」改成这个：`timeline.py` 改成「动词 ＋ CATALOG.label」拼接后，
        # 实际标题是「拿到爪爪驾驶证」。`CATALOG` 的 label 一直写着「爪爪驾驶证」，timeline 里硬编码的
        # 却是「驾驶证」——**早就漂了、没人报过**，而这条用例是全仓唯一会因此变红的地方。
        # **它红是它在干活**，不是缺陷；改名时连它一起改。
        self.assertIn("拿到爪爪驾驶证", titles)
        self.assertIn("和你一起领了驾照", titles)

    def test_voucher_waives_the_first_drive_rental_once(self) -> None:
        self.school.pass_all()
        destinations = {d["destination_key"]: d for d in self.owner.get("/journey/destinations").json()}
        self.assertIn("local:drive_trip", destinations)
        balance = self.owner.home()["wallet"]["balance"]
        self.assertEqual(self.owner.post("/journey/depart", {"destination_key": "local:drive_trip"}).status_code, 200)
        self.assertEqual(self.owner.home()["wallet"]["balance"], balance, "第一次自驾用借车券，不扣租车费")
        self.assertNotIn("car_voucher", self.collection(), "借车券用掉了")
        self.clock.advance(hours=6)
        self.owner.get("/journey/map")
        self.web.economy.apply(self.owner.pet_id, 50, EconomyTransactionType.web_reward, "test:second-drive", reason="测试", source="test")
        before = self.owner.home()["wallet"]["balance"]
        self.assertEqual(self.owner.post("/journey/depart", {"destination_key": "local:drive_trip"}).status_code, 200)
        self.assertEqual(self.owner.home()["wallet"]["balance"], before - 20, "之后自驾照常付租车费")


class LicenseConsistencyTests(LicenseTestBase):
    def pass_first_three(self) -> None:
        for subject in ("s1", "s2", "s3"):
            self.assertTrue(self.school.exam(subject)["result"]["passed"])

    def test_issue_failure_rolls_back_the_final_settlement_and_retry_issues_once(self) -> None:
        self.pass_first_three()
        session = self.school.start("s4")
        self.school.answer_all(session)
        original = self.web.driving.issue_license

        def fail(*args, **kwargs):
            raise RuntimeError("transient credential store failure")

        self.web.driving.issue_license = fail
        with self.assertRaises(RuntimeError):
            self.web.driving.submit(self.owner.pet_id, session["session_id"], self.clock.now)
        self.web.driving.issue_license = original
        still = self.owner.get(f"/driving/sessions/{session['session_id']}").json()
        self.assertEqual(still["state"], "running", "签发失败：整次结算回滚，考局还在")
        self.assertEqual({s["subject"]: s["state"] for s in self.owner.get("/driving").json()["subjects"]}["s4"], "in_exam")
        self.assertEqual(self.licenses(), [])
        done = self.owner.post(f"/driving/sessions/{session['session_id']}/submit").json()
        self.assertTrue(done["result"]["passed"])
        self.assertEqual(len(self.licenses()), 1, "重试后只签发一本")
        self.assertTrue(self.web.journeys.can_drive(self.owner.pet_id))

    def test_message_failure_does_not_block_the_license_and_notes_arrive_later_once(self) -> None:
        self.pass_first_three()
        original = self.web.driving.say

        def broken(*args, **kwargs):
            raise RuntimeError("communicator down")

        self.web.driving.say = broken
        self.assertTrue(self.school.exam("s4")["result"]["passed"])
        self.assertEqual(len(self.licenses()), 1, "消息发不出去也照样拿证")
        self.assertTrue(self.web.journeys.can_drive(self.owner.pet_id))
        self.assertFalse(any("我拿到驾照啦" in t for t in self.notes()))
        self.web.driving.say = original
        self.web.ticker.tick(self.clock.now)
        self.web.ticker.tick(self.clock.now)
        self.assertEqual(sum("我拿到驾照啦" in t for t in self.notes()), 1, "定时器补投，只出现一次")

    def test_legacy_license_shows_subjects_as_passed_and_needs_no_new_exam(self) -> None:
        with self.web.driving.storage.connect() as conn:  # 旧版（自动答题）拿到的驾照
            self.web.credentials.insert(conn, user_id=self.owner.user_id, pet_id=self.owner.pet_id, kind="driver_license", source_key="exam:ex-legacy",
                                        issued_at=LUNCH_UTC, title="爪爪驾驶证 · 小型车（C）", data={"class": "C", "practical_score": 100, "theory_score": "10/10"})
        status = self.owner.get("/driving").json()
        self.assertEqual(status["stage"], "licensed")
        self.assertTrue(all(s["state"] == "passed" and s["legacy"] for s in status["subjects"]))
        self.assertEqual(self.school.create("s1").json()["error"]["details"]["reason"], "already_passed")
        self.assertEqual(self.owner.post("/driving/ceremony").json()["first_time"], True)


if __name__ == "__main__":
    unittest.main()
