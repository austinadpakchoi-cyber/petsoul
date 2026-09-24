"""科一练习卷的抽题（6c2b 驾校巡检 2026-09-24 报）。

旧规则：前 4 次练习 20 题里拖放 0 道、排序 1 道，第一次正式卷却有拖放 1、排序 3——玩家第一次见到拖放界面就是在正式考试里。
这里钉的是练习卷该有的性质，而不是某个具体公式：

  · 每张练习卷三种题型（选择、拖放、排序）都至少一道；
  · 5 道题来自 5 个不同知识点；
  · **没有题永远练不到**：任意连续 12 次练习必把 30 道题全练到（只换题型、不管覆盖的改法会让几道题再也练不到）；
  · 正式卷的抽法不变（这次只动练习）。
"""

from __future__ import annotations

import unittest

from app.web_driving.questions import ALL, QUIZ_KINDS, S1_BANK, S1_TOPICS, paper
from school_helpers import School
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

S1_IDS = {q.question_id for topic in S1_TOPICS for q in S1_BANK[topic]}
RUNS = range(0, 120)


class PracticePaperRuleTests(unittest.TestCase):
    def test_every_practice_paper_has_all_three_kinds(self) -> None:
        for number in RUNS:
            with self.subTest(practice=number):
                self.assertEqual({q.kind for q in paper("s1", number, practice=True)}, set(QUIZ_KINDS))

    def test_five_questions_from_five_different_topics(self) -> None:
        for number in RUNS:
            with self.subTest(practice=number):
                questions = paper("s1", number, practice=True)
                self.assertEqual(len(questions), 5)
                self.assertEqual(len({q.topic for q in questions}), 5)

    def test_no_question_is_left_unpracticed(self) -> None:
        for first in range(0, 100):
            seen: set[str] = set()
            for number in range(first, first + 12):
                seen |= {q.question_id for q in paper("s1", number, practice=True)}
            with self.subTest(from_practice=first):
                self.assertEqual(S1_IDS - seen, set(), "连续 12 次练习里有题一次都没出现")

    def test_formal_papers_are_unchanged(self) -> None:
        """正式卷每个知识点 1 题、补考换题——抽法原样保留（这两张是改动前的实际出题）。"""
        self.assertEqual([q.question_id for q in paper("s1", 0)],
                         ["s1.stop.1", "s1.dir.2", "s1.warn.3", "s1.walk.1", "s1.sig.2", "s1.emg.3", "s1.pre.1", "s1.park.2", "s1.slow.3", "s1.rev.1"])
        self.assertEqual([q.question_id for q in paper("s1", 1)],
                         ["s1.stop.2", "s1.dir.3", "s1.warn.1", "s1.walk.2", "s1.sig.3", "s1.emg.1", "s1.pre.2", "s1.park.3", "s1.slow.1", "s1.rev.2"])


class PracticePaperLiveTests(WebPlatformTestBase):
    def test_the_first_real_practice_already_shows_drag_and_order(self) -> None:
        """走真实接口：报名后第一次科一练习，卷面上就有拖放题和排序题（玩家在正式考试前就见过这两种界面）。"""
        FakeClock(LUNCH_UTC).install(self)
        owner = self.user("practice-kinds")
        owner.adopt_and_move_in("adopt-lan")
        self.web.life.consider = lambda user_id, pet_id, now: None  # 只测驾校：不被自主出门打断
        self.assertEqual(owner.post("/driving/enroll").status_code, 200)
        session = School(self, owner).start("s1", "practice")
        kinds = [ALL[q["question_id"]].kind for q in session["quiz"]["questions"]]
        self.assertEqual([q["kind"] for q in session["quiz"]["questions"]], kinds, "卷面给出的题型与题库一致")
        self.assertIn("match", kinds)
        self.assertIn("order", kinds)


if __name__ == "__main__":
    unittest.main()
