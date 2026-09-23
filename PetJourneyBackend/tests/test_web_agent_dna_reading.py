"""DNA 原话的读法（独立核查 P2 回归）：否定、纠正、混合与含糊说法分别对待；每条结论可追溯到原话；说不准的不强行归类。

核查反例：“不爱熬夜，不爱热闹，喜欢安静。”曾被判成夜猫子、爱热闹、01:30 入睡、每天想出门 3 次。
这里不只测这一句：同类的否定、纠正、混合和含糊说法都各有用例；也测 DNA 接口展示的出处与作息联动。
"""

from __future__ import annotations

import unittest
from datetime import datetime, time, timedelta, timezone

from app.web_agent.profile import derive_profile
from web_base import FakeClock, WebPlatformTestBase

HK = timezone(timedelta(hours=8))

# (原话, 作息, 热闹还是安静, 必须出现的特征状态)
NEGATION = [
    ("不熬夜", "regular", "steady", {"night_owl": "negated"}),
    ("从不熬夜", "regular", "steady", {"night_owl": "negated"}),
    ("很少熬夜", "regular", "steady", {"night_owl": "negated"}),
    ("不再熬夜了", "regular", "steady", {"night_owl": "negated"}),
    ("没那么黏人", "regular", "steady", {"social": "negated"}),
    ("晚上一点也不闹腾", "regular", "steady", {"social": "negated"}),
    ("一点也不怕生", "regular", "steady", {"homebody": "negated"}),
    ("不怎么爱出门", "regular", "steady", {"curious": "negated"}),
    ("安静不下来", "regular", "steady", {"homebody": "negated"}),
    ("不懒", "regular", "steady", {"sleepy": "negated"}),
]
CORRECTION = [
    ("以前爱熬夜，现在早睡早起", "early_bird", "steady", {"night_owl": "outweighed", "early_bird": "applied"}),
    ("不是夜猫子，是早起的", "early_bird", "steady", {"night_owl": "negated", "early_bird": "applied"}),
    ("不是夜猫子而是早起的", "early_bird", "steady", {"night_owl": "negated", "early_bird": "applied"}),
    ("小时候很黏人，现在很独立", "regular", "homebody", {"social": "outweighed", "homebody": "applied"}),
    ("不是不爱热闹，只是慢热", "regular", "homebody", {"social": "outweighed", "homebody": "applied"}),
    ("其实很胆小", "regular", "homebody", {"homebody": "applied"}),
]
MIXED_OR_UNSURE = [
    ("爱热闹但有点怕生", "regular", "steady", {"social": "uncertain", "homebody": "uncertain"}),
    ("白天很黏人，晚上很独立", "regular", "steady", {"social": "uncertain", "homebody": "uncertain"}),
    ("偶尔熬夜", "regular", "steady", {"night_owl": "uncertain"}),
    ("可能是个夜猫子", "regular", "steady", {"night_owl": "uncertain"}),
    ("有时候很黏人", "regular", "steady", {"social": "uncertain"}),
    ("不熬夜爱热闹", "regular", "steady", {"night_owl": "negated", "social": "uncertain"}),  # 否定词离得远：不强行判断
]
NOT_NEGATION = [  # 含“不/非/没/别”但不是否定
    ("非常黏人", "regular", "social", {"social": "applied"}),
    ("不管去哪都黏人", "regular", "social", {"social": "applied"}),
    ("没事就爱凑热闹", "regular", "social", {"social": "applied"}),
    ("不熬夜也爱热闹", "regular", "social", {"night_owl": "negated", "social": "applied"}),
]


def statuses(profile) -> dict[str, str]:
    return {t.key: t.status for t in profile.traits}


class DNAReadingTests(unittest.TestCase):
    def check(self, cases) -> None:
        for text, rhythm, sociability, expected in cases:
            with self.subTest(text=text):
                profile = derive_profile(text)
                self.assertEqual((profile.rhythm, profile.sociability), (rhythm, sociability))
                found = statuses(profile)
                self.assertEqual({k: found.get(k) for k in expected}, expected, found)

    def test_review_counterexample_reads_as_regular_quiet_homebody(self) -> None:
        profile = derive_profile("不爱熬夜，不爱热闹，喜欢安静。")
        self.assertEqual((profile.night_owl, profile.rhythm, profile.sociability), (False, "regular", "homebody"))
        self.assertEqual((profile.sleep_start, profile.wake, profile.outings_per_day, profile.chattiness), (time(23, 30), time(7, 30), 1, 1))
        self.assertEqual(statuses(profile), {"night_owl": "negated", "social": "negated", "homebody": "applied"})
        self.assertLessEqual(profile.route_interest.get("local:city_trip", 1.0), 1.0, "不爱热闹不会更想进城")
        self.assertIn("不爱熬夜：按平常作息（23:30 睡，07:30 起）", profile.reasons)

    def test_negations(self) -> None:
        self.check(NEGATION)

    def test_corrections_prefer_what_is_true_now(self) -> None:
        self.check(CORRECTION)

    def test_mixed_or_unsure_words_are_not_forced_into_a_trait(self) -> None:
        self.check(MIXED_OR_UNSURE)
        self.assertEqual(derive_profile("爱热闹但有点怕生").unclassified, ("爱热闹", "但有点怕生"))
        self.assertEqual(derive_profile("偶尔熬夜").unclassified, ("偶尔熬夜",))
        self.assertEqual(derive_profile("以前爱熬夜，现在早睡早起").unclassified, (), "被纠正的旧说法不算“说不准”")

    def test_words_that_only_look_negative(self) -> None:
        self.check(NOT_NEGATION)

    def test_likes_dislikes_and_fears_shape_routes_and_jobs(self) -> None:
        self.assertNotIn("local:stroll", derive_profile([("personality", "不喜欢海边散步")]).route_interest, "被否定的喜好不加分")
        fear = derive_profile([("fears", "大海"), ("hobbies", "看书")])
        self.assertEqual((fear.job_affinity.get("fishing_port"), fear.job_affinity.get("bookstore")), (0.5, 2.0), "害怕的更不愿意去，喜欢的更愿意")
        sea = derive_profile([("favorite_places", "海边"), ("hobbies", "爱看海")])
        self.assertEqual((sea.route_interest["local:stroll"], sea.route_interest["long"], sea.job_affinity["fishing_port"]), (1.5, 1.5, 2.0))
        self.assertEqual(derive_profile("讨厌热闹").route_interest["local:city_trip"], 0.5)

    def test_every_conclusion_points_back_to_the_owner_words(self) -> None:
        profile = derive_profile([("personality", "不爱熬夜，不爱热闹，喜欢安静。"), ("habits", "偶尔半夜跑出去")])
        night = next(t for t in profile.traits if t.key == "night_owl")
        self.assertEqual([(e.field, e.phrase, e.polarity) for e in night.evidence],
                         [("personality", "不爱熬夜", "negative"), ("habits", "偶尔半夜跑出去", "uncertain")])
        self.assertIn("不", night.evidence[0].note)
        self.assertIn("偶尔", night.evidence[1].note)
        home = next(t for t in profile.traits if t.key == "homebody")
        self.assertEqual([(e.phrase, e.implied) for e in home.evidence], [("喜欢安静", False), ("不爱热闹", True)])
        self.assertEqual(profile.sources, ("personality", "habits"))
        self.assertEqual(profile.rules_version, "dna-behavior-2026.2")


class DNABehaviorIntegrationTests(WebPlatformTestBase):
    """DNA 页面展示的行为倾向，就是作息、自主生活与主动消息实际用的那一份；改 DNA 立刻生效。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(datetime(2026, 9, 23, 0, 40, tzinfo=HK).astimezone(timezone.utc)).install(self)
        self.owner = self.user("dna-reader")
        self.owner.adopt_and_move_in("adopt-lan")

    def dna(self, personality: str) -> dict:
        response = self.owner.put(f"/pets/{self.owner.pet_id}/dna", {"personality": personality})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["behavior"]

    def asleep_at(self, hour: int, minute: int = 0) -> bool:
        local = datetime(2026, 9, 23, hour, minute, tzinfo=HK)
        return self.web.moments.build(self.owner.pet_id, local.astimezone(timezone.utc)).asleep

    def test_dna_page_explains_the_reading_and_the_schedule_follows_it(self) -> None:
        behavior = self.dna("不爱熬夜，不爱热闹，喜欢安静。")
        self.assertEqual((behavior["rhythm"], behavior["sociability"], behavior["sleep_start"], behavior["outings_per_day"]), ("regular", "homebody", "23:30", 1))
        night = next(t for t in behavior["traits"] if t["key"] == "night_owl")
        self.assertEqual((night["status"], night["evidence"][0]["field_label"], night["evidence"][0]["phrase"]), ("negated", "性格", "不爱熬夜"))
        self.assertTrue(self.asleep_at(0, 40), "不是夜猫子：凌晨已经睡了")
        self.assertEqual(self.owner.get(f"/pets/{self.owner.pet_id}/dna").json()["behavior"], behavior, "读取与保存返回同一份")

        self.assertEqual(self.dna("爱熬夜的夜猫子")["rhythm"], "night_owl")
        self.assertFalse(self.asleep_at(0, 40), "改成夜猫子：立刻按新的作息")
        corrected = self.dna("以前爱熬夜，现在早睡早起")
        self.assertEqual((corrected["rhythm"], corrected["sleep_start"]), ("early_bird", "22:00"))
        self.assertTrue(self.asleep_at(22, 30), "纠正后早睡")
        self.assertIs(self.web.life.profile_of, self.web.profile_of, "自主生活用的是同一份画像")
        self.assertIs(self.web.proactive.profile_of, self.web.profile_of, "主动消息用的是同一份画像")

    def test_notes_only_allowed_for_private_chat_do_not_drive_behavior(self) -> None:
        def confirm(text: str, purposes: list[str]) -> None:
            session = self.owner.post("/reception/sessions", {"pet_id": self.owner.pet_id, "branch": "own_pet"}).json()
            session = self.owner.post(f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]}).json()
            decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": purposes, "slot": c["suggested_slot"],
                          "slot_value": c["suggested_slot_value"]} for c in session["candidates"] if c["kind"] != "owner_private"]
            self.assertTrue(decisions)
            self.owner.post("/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions})

        confirm("它是个夜猫子，半夜最精神", ["private_chat"])
        behavior = self.owner.get(f"/pets/{self.owner.pet_id}/dna").json()["behavior"]
        self.assertEqual(behavior["rhythm"], "regular", "只允许私信使用的叮嘱不影响作息")
        confirm("它是个夜猫子，半夜最精神", ["private_chat", "home_interaction"])
        behavior = self.owner.get(f"/pets/{self.owner.pet_id}/dna").json()["behavior"]
        self.assertEqual(behavior["rhythm"], "night_owl", "允许用于家中互动的叮嘱会影响作息（确认后立刻生效）")
        self.assertIn("note", behavior["sources"])


if __name__ == "__main__":
    unittest.main()
