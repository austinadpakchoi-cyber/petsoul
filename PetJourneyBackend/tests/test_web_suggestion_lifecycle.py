"""家人的建议在 TA 出门之后怎么记（对应 C 的 CR-C4），以及模型建议的复查间隔（CR-C3）。

原来 TA 一出门就把所有还在考虑中的建议一股脑标成"采纳"或"去了别处"。
可是"这次没选它"不等于"不去了"——24 小时的考虑窗口还没过，TA 完全可能晚点去。
所以：选中的那条算采纳，其余留在考虑中、只记一次"这次想过了"，窗口过了再统一收口。
用脚本化的假模型，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_agent.life import expire_suggestions
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class SuggestionLifecycleTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("suggest-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True

    def suggest(self, key: str) -> None:
        response = self.owner.post("/journey/suggest", {"destination_key": key})
        self.assertEqual(response.status_code, 200, response.text)

    def rows(self) -> dict[str, dict]:
        with self.app.state.storage.connect() as conn:
            return {r["destination_key"]: dict(r) for r in conn.execute("SELECT * FROM web_owner_suggestions WHERE pet_id = ?", (self.owner.pet_id,))}

    def model_picks(self, key: str) -> None:
        now = self.clock.now
        options = self.web.journeys.destinations(self.owner.user_id, self.owner.pet_id, self.owner.home_id, now)
        keys = [destination_key_of(o) for o in offers_from_options(options, pet_id=self.owner.pet_id, as_of=now,
                                                                   expected_versions=self.web.projector.versions(self.owner.pet_id),
                                                                   income_of=lambda k: job_of(k).pay if job_of(k) else 0)]
        self.life.brain.model = ScriptedModel(json.dumps({"choice": f"o{keys.index(key) + 1}", "intent": "去走走"}, ensure_ascii=False))

    def test_the_chosen_suggestion_is_accepted_and_the_others_stay_in_consideration(self) -> None:
        self.suggest("local:stroll")
        self.suggest("local:cafe")  # 同一位家人同时只保留一条在考虑中：第二条会替换第一条
        rows = self.rows()
        self.assertEqual(rows["local:cafe"]["status"], "pending")

        self.model_picks("local:cafe")
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "departed", outcome.reason)
        rows = self.rows()
        self.assertEqual(rows["local:cafe"]["status"], "accepted", "选中的那条算采纳")
        self.assertTrue(rows["local:cafe"]["decided_at"])

    def test_a_suggestion_not_chosen_this_time_is_only_marked_as_considered(self) -> None:
        self.suggest("local:cafe")
        self.model_picks("local:stroll")  # TA 这次去了别的地方

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "departed", outcome.reason)
        row = self.rows()["local:cafe"]
        self.assertEqual(row["status"], "pending", f"这次没选它不等于不去了，24 小时内还算数：{row}")
        self.assertTrue(row["considered_at"], f"但要记下这次想过了：{row}")
        self.assertIsNone(row["decided_at"], "还没有结论就不写结论时刻")

    def test_the_consideration_window_closes_the_suggestion(self) -> None:
        self.suggest("local:cafe")
        self.model_picks("local:stroll")
        self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual(self.rows()["local:cafe"]["status"], "pending")

        self.clock.advance(hours=25)
        closed = expire_suggestions(self.app.state.storage, self.clock.now)

        self.assertEqual(closed, 1)
        row = self.rows()["local:cafe"]
        self.assertEqual(row["status"], "passed", "窗口过了就收口，别一直挂着「还在考虑中」")
        self.assertTrue(row["decided_at"])

    def test_the_window_job_leaves_fresh_suggestions_alone(self) -> None:
        self.suggest("local:cafe")
        self.clock.advance(hours=2)

        self.assertEqual(expire_suggestions(self.app.state.storage, self.clock.now), 0)
        self.assertEqual(self.rows()["local:cafe"]["status"], "pending")

    def test_the_api_reports_when_it_was_considered(self) -> None:
        self.suggest("local:cafe")
        self.model_picks("local:stroll")
        self.life.consider(self.owner.pet_id, self.clock.now)

        items = self.owner.get("/journey/suggestions").json()

        cafe = next(item for item in items if item["destination_key"] == "local:cafe")
        self.assertEqual(cafe["status"], "pending")
        self.assertTrue(cafe["considered_at"], f"页面要能显示「TA 这次想过了」：{cafe}")

    # ---- CR-C3：模型建议的复查间隔要被用上 ----
    def test_the_models_suggested_review_interval_is_honoured(self) -> None:
        from datetime import datetime

        self.life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "在家歇会儿",
                                                          "review_after_minutes": 60}, ensure_ascii=False))

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "stayed", outcome.reason)
        row = self.web.projector.runtime.row(self.owner.pet_id)
        self.assertTrue(row.get("next_review_at"), f"决定之后要写下次复查时刻，不能留空：{dict(row)}")
        review_at = datetime.fromisoformat(row["next_review_at"])
        self.assertEqual(review_at, self.clock.now + timedelta(minutes=60), "模型说 60 分钟后再想想，就按 60 分钟")

    def test_without_a_suggested_interval_the_default_is_used(self) -> None:
        from datetime import datetime

        self.life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "在家"}, ensure_ascii=False))

        self.life.consider(self.owner.pet_id, self.clock.now)

        row = self.web.projector.runtime.row(self.owner.pet_id)
        self.assertEqual(datetime.fromisoformat(row["next_review_at"]), self.clock.now + timedelta(minutes=15), "没建议就用默认的空闲复查间隔")


if __name__ == "__main__":
    unittest.main()
