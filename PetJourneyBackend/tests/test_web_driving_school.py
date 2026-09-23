"""爪爪驾校的考试规则与考局（服务端裁定）：

- 报名后才能上课考试；正式考试按科目一 → 四依次解锁，练习随时可以；
- 每科首次考试＋一次补考；两次不过从第二次结算起冷却 7×24 小时；冷却结束开始新一轮；已通过的科目保留；
- begin 之后才计次；一小时没开始的考局作废；同一时间只有一场未结束的正式考试；放弃要二次确认并计为不通过；
- 科一科四：正式考试交卷前不给提示，交卷后才给正确答案；作答与题目、选项对得上；补考换题；
- 科二科三：只接受连续的操作片段，相同的重发原样返回，服务端复算出失败当场结算；复算出错作废不计次。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from school_helpers import School, wrong_answer
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class SchoolTestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("school-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.web.life.consider = lambda user_id, pet_id, now: None  # 只测驾校：不被自主出门打断
        self.school = School(self, self.owner)

    def subjects(self) -> dict[str, dict]:
        return {s["subject"]: s for s in self.owner.get("/driving").json()["subjects"]}

    def reason(self, response) -> str:
        return response.json()["error"]["details"]["reason"]


class EnrollmentAndUnlockTests(SchoolTestBase):
    def test_enroll_first_then_formal_exams_unlock_in_order_and_practice_is_always_open(self) -> None:
        self.assertEqual(self.reason(self.school.create("s1")), "not_enrolled")
        self.assertEqual(self.owner.post("/driving/enroll").json()["stage"], "enrolled")
        states = {k: v["state"] for k, v in self.subjects().items()}
        self.assertEqual(states, {"s1": "available", "s2": "locked", "s3": "locked", "s4": "locked"})
        self.assertEqual(self.subjects()["s2"]["unlock_hint"], "先通过科目一")
        self.assertEqual(self.reason(self.school.create("s2")), "locked")
        for subject in ("s2", "s3", "s4"):
            self.assertEqual(self.school.create(subject, "practice").status_code, 200, "练习随时可以")
        self.assertTrue(self.school.quiz("s1")["result"]["passed"])
        self.assertEqual(self.subjects()["s2"]["state"], "available")
        curriculum = self.owner.get("/driving/curriculum").json()
        self.assertEqual(len(curriculum["subjects"]), 4)
        self.assertTrue(all(s["red_lines"] for s in curriculum["subjects"] if s["subject"] in ("s2", "s3")), "红线提前列出")


class RetakeAndCooldownTests(SchoolTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner.post("/driving/enroll")

    def test_first_attempt_retake_then_seven_day_cooldown_then_a_new_round(self) -> None:
        first = self.school.quiz("s1", wrong=2)
        self.assertEqual((first["attempt_kind"], first["result"]["passed"], first["result"]["score"]), ("first", False, 80))
        self.assertEqual((first["result"]["next"]["kind"], first["result"]["next"]["attempts_left"]), ("retake", 1))
        self.assertEqual((self.subjects()["s1"]["attempts_left"], self.subjects()["s1"]["next_attempt"]), (1, "retake"))
        self.clock.advance(hours=2)
        second = self.school.quiz("s1", wrong=3)
        self.assertEqual((second["attempt_kind"], second["result"]["passed"]), ("retake", False))
        settled = datetime.fromisoformat(second["settled_at"])
        until = datetime.fromisoformat(second["result"]["next"]["cooldown_until"])
        self.assertEqual(until - settled, timedelta(hours=7 * 24), "从第二次结算起 7×24 小时")
        status = self.subjects()["s1"]
        self.assertEqual((status["state"], status["attempts_left"]), ("cooldown", 0))
        refused = self.school.create("s1")
        self.assertEqual(self.reason(refused), "cooldown")
        self.assertEqual(refused.json()["error"]["details"]["cooldown_until"], status["cooldown_until"], "错误里的时间与状态同一格式（Z 结尾）")
        self.assertEqual(self.school.create("s1", "practice").status_code, 200, "等待期间照常练习")
        self.clock.advance(days=6, hours=23)
        self.assertEqual(self.reason(self.school.create("s1")), "cooldown", "差 1 小时还没到")
        self.clock.advance(hours=1, seconds=1)
        self.web.ticker.tick(self.clock.now)
        status = self.subjects()["s1"]
        self.assertEqual((status["state"], status["round_no"], status["attempts_left"], status["next_attempt"]), ("available", 2, 2, "first"))
        notes = [m["text"] for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]]
        self.assertEqual(sum("又可以约考试啦" in t for t in notes), 1, "冷却结束时 TA 提一次")
        self.web.ticker.tick(self.clock.now + timedelta(minutes=1))
        third = self.school.quiz("s1")
        self.assertEqual((third["attempt_kind"], third["round_no"], third["result"]["passed"]), ("first", 2, True))

    def test_retake_gets_a_different_paper_of_the_same_scope(self) -> None:
        first = self.school.quiz("s1", wrong=2)
        second = self.school.start("s1")
        first_ids = [q["question_id"] for q in first["quiz"]["questions"]]
        second_ids = [q["question_id"] for q in second["quiz"]["questions"]]
        self.assertTrue(set(first_ids).isdisjoint(second_ids), "补考换题")
        self.assertEqual([i.split(".")[1] for i in first_ids], [i.split(".")[1] for i in second_ids], "每个知识点各一题，范围相同")

    def test_passed_subjects_are_kept_when_a_later_subject_cools_down(self) -> None:
        self.school.quiz("s1")
        for _ in range(2):
            session = self.school.start("s2")
            self.owner.post(f"/driving/sessions/{session['session_id']}/abandon", {"confirm": True})
        status = self.subjects()
        self.assertEqual((status["s1"]["state"], status["s2"]["state"], status["s3"]["state"]), ("passed", "cooldown", "locked"))


class SessionLifecycleTests(SchoolTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner.post("/driving/enroll")

    def test_only_begun_exams_count_and_unstarted_ones_expire(self) -> None:
        created = self.school.create("s1").json()
        self.assertEqual((created["state"], self.subjects()["s1"]["attempts_used"]), ("preparing", 0))
        self.assertEqual(self.school.create("s1").json()["session_id"], created["session_id"], "同一科未结束的正式考局原样返回")
        self.assertEqual(self.reason(self.school.create("s4", "formal")), "exam_in_progress", "先把这一场考完或放弃")
        self.clock.advance(minutes=61)
        self.assertIsNone(self.owner.get("/driving").json()["open_session"], "一小时没开始：作废")
        void = self.owner.get(f"/driving/sessions/{created['session_id']}").json()
        self.assertEqual((void["state"], void["void_reason"]), ("void", "not_started"))
        self.assertEqual(self.subjects()["s1"]["attempts_used"], 0, "作废不计次")

    def test_one_open_formal_exam_at_a_time(self) -> None:
        self.school.quiz("s1")
        open_s2 = self.school.start("s2")
        with self.web.driving.storage.connect() as conn:  # 让科四的前置条件成立，只看“同时只有一场”
            conn.execute("INSERT INTO web_school_subjects (pet_id, subject, user_id, passed_at, passed_score, updated_at) VALUES (?, 's3', ?, ?, 100, ?)",
                         (self.owner.pet_id, self.owner.user_id, LUNCH_UTC.isoformat(), LUNCH_UTC.isoformat()))
        blocked = self.school.create("s4")
        self.assertEqual((blocked.status_code, self.reason(blocked), blocked.json()["error"]["details"]["session_id"]), (409, "exam_in_progress", open_s2["session_id"]))
        self.assertEqual(self.owner.get("/driving").json()["open_session"]["session_id"], open_s2["session_id"])

    def test_abandon_needs_confirmation_and_counts_as_a_failure(self) -> None:
        session = self.school.start("s1")
        unconfirmed = self.owner.post(f"/driving/sessions/{session['session_id']}/abandon", {"confirm": False})
        self.assert_envelope(unconfirmed, 422, "VALIDATION_FAILED")
        abandoned = self.owner.post(f"/driving/sessions/{session['session_id']}/abandon", {"confirm": True}).json()
        self.assertEqual((abandoned["result"]["passed"], abandoned["result"]["fatal"]["kind"]), (False, "abandoned"))
        self.assertEqual(self.subjects()["s1"]["attempts_used"], 1)
        preparing = self.school.create("s1").json()
        self.owner.post(f"/driving/sessions/{preparing['session_id']}/abandon", {"confirm": True})
        self.assertEqual(self.subjects()["s1"]["attempts_used"], 1, "还没开始的考局放弃：作废，不计次")

    def test_formal_quiz_gives_no_hints_until_submitted_and_validates_answers(self) -> None:
        session = self.school.start("s1")
        qid = session["quiz"]["questions"][0]["question_id"]
        saved = self.owner.put(f"/driving/sessions/{session['session_id']}/answers", {"question_id": qid, "answer": wrong_answer(qid)}).json()
        self.assertEqual((saved["saved"], saved["feedback"], saved["answered"]), (True, None, 1), "正式考试交卷前不给提示")
        self.assertNotIn("answer", session["quiz"]["questions"][0], "题目里没有答案")
        bogus = self.owner.put(f"/driving/sessions/{session['session_id']}/answers", {"question_id": qid, "answer": {"choice": "s1.nope.a"}})
        self.assertEqual((bogus.status_code, self.reason(bogus)), (422, "invalid_answer"))
        foreign = self.owner.put(f"/driving/sessions/{session['session_id']}/answers", {"question_id": "s4.drop.1.1", "answer": {"choice": "s4.drop.1.1.a"}})
        self.assertEqual((foreign.status_code, self.reason(foreign)), (422, "question_not_in_paper"))
        resumed = self.owner.get(f"/driving/sessions/{session['session_id']}").json()
        self.assertEqual(list(resumed["quiz"]["answers"]), [qid], "续考时恢复已保存的作答")
        self.school.answer_all(session)
        result = self.owner.post(f"/driving/sessions/{session['session_id']}/submit").json()
        again = self.owner.post(f"/driving/sessions/{session['session_id']}/submit").json()
        self.assertEqual(again["result"], result["result"], "只结算一次")
        self.assertEqual(self.subjects()["s1"]["attempts_used"], 0, "通过后不再计失败次数")
        self.assertTrue(all("correct_answer" in r for r in result["result"]["review"]), "交卷后才给正确答案与讲解")

    def test_practice_quiz_explains_right_away(self) -> None:
        session = self.school.start("s4", "practice")
        qid = session["quiz"]["questions"][0]["question_id"]
        feedback = self.owner.put(f"/driving/sessions/{session['session_id']}/answers", {"question_id": qid, "answer": wrong_answer(qid)}).json()["feedback"]
        self.assertFalse(feedback["correct"])
        self.assertTrue(feedback["explanation"] and feedback["pet_line"].startswith("原来是这样"))

    def test_drive_inputs_must_be_continuous_and_duplicates_are_idempotent(self) -> None:
        session = self.school.start("s2", "practice", item="reverse_straight")
        path = f"/driving/sessions/{session['session_id']}/inputs"
        chunk = {"item_index": 0, "from_tick": 0, "upto_tick": 30, "events": [{"t": 0, "c": "g", "v": -1}, {"t": 1, "c": "t", "v": 1}]}
        first = self.owner.post(path, chunk).json()
        self.assertEqual(self.owner.post(path, chunk).json(), first, "完全相同的重发：原样返回")
        changed = dict(chunk, events=[{"t": 0, "c": "t", "v": 1}])
        self.assertEqual(self.reason(self.owner.post(path, changed)), "resync")
        self.assertEqual(self.reason(self.owner.post(path, dict(chunk, from_tick=60, upto_tick=90))), "gap")
        self.assert_envelope(self.owner.post(path, dict(chunk, from_tick=30, upto_tick=60, events=[{"t": 31, "c": "s", "v": 13}])), 422, "VALIDATION_FAILED")
        self.assert_envelope(self.owner.post(path, dict(chunk, from_tick=30, upto_tick=60, score=100)), 422, "VALIDATION_FAILED")
        other = self.user("school-stranger")
        other.adopt_and_move_in("adopt-pudding")
        self.assert_envelope(other.get(f"/driving/sessions/{session['session_id']}"), 404, "NOT_FOUND")
        self.assert_envelope(other.post(path, dict(chunk, from_tick=30, upto_tick=60)), 404, "NOT_FOUND")

    def test_a_replay_fault_voids_the_exam_without_counting(self) -> None:
        self.school.quiz("s1")
        session = self.school.start("s2")
        import app.web_driving.service as service

        original = service.Replay

        class Broken(original):
            def apply(self, events, upto_tick):
                raise RuntimeError("simulated platform fault")

        service.Replay = Broken
        try:
            response = self.owner.post(f"/driving/sessions/{session['session_id']}/inputs", {"item_index": 0, "from_tick": 0, "upto_tick": 30, "events": []})
        finally:
            service.Replay = original
        self.assertEqual(self.reason(response), "platform_fault")
        void = self.owner.get(f"/driving/sessions/{session['session_id']}").json()
        self.assertEqual((void["state"], void["void_reason"]), ("void", "platform_fault"))
        self.assertEqual(self.subjects()["s2"]["attempts_used"], 0, "平台故障不计次")


if __name__ == "__main__":
    unittest.main()
