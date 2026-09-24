"""自主决策接进真实生活循环（包 C 接入）：规则给可行机会 → 模型选一项 → 复核后变成真实行程。

用脚本化的假模型，不联网、不产生付费调用。默认配置下（PETJOURNEY_WEB_BRAIN_MODE=off）一次模型都不会调用。
"""

from __future__ import annotations

import json
import unittest

from app.schemas.web.pets import PetDNA
from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class BrainLifeTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("brain-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})  # 家庭同意把共用资料交给模型
        self.life = self.web.brain_life

    def offers(self) -> list:
        now = self.clock.now
        options = self.web.journeys.destinations(self.owner.user_id, self.owner.pet_id, self.owner.home_id, now)
        return list(offers_from_options(options, pet_id=self.owner.pet_id, as_of=now, expected_versions=self.web.projector.versions(self.owner.pet_id),
                                        income_of=lambda key: job_of(key).pay if job_of(key) else 0))

    def use_choice(self, key: str, *, on_call=None) -> ScriptedModel:
        keys = [destination_key_of(offer) for offer in self.offers()]
        alias = "continue" if key == "continue" else f"o{keys.index(key) + 1}"
        model = ScriptedModel(json.dumps({"choice": alias, "intent": "去挣点旅费"}, ensure_ascii=False), on_call=on_call)
        self.life.brain.model = model
        self.web.projector.model_available = lambda: True  # 心跳据此判断“大脑现在能用”（真实环境看供应商是否配置可用）
        return model

    def work_key(self) -> str:
        return next(destination_key_of(offer) for offer in self.offers() if destination_key_of(offer).startswith("work:"))

    def test_brain_is_off_by_default_and_never_calls_the_model(self) -> None:
        model = self.use_choice(self.work_key())
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((self.life.mode, outcome.status, outcome.reason), ("off", "skipped", "brain_off"))
        self.assertEqual(model.calls, [], "默认配置一次模型都不调用")
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id))

    def test_the_model_choice_becomes_the_real_plan(self) -> None:
        self.life.mode = "live"
        work = self.work_key()
        model = self.use_choice(work)
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by, outcome.destination_key), ("departed", "model", work))
        self.assertEqual(len(model.calls), 1, "一次决策只调用一次模型")
        journey = self.web.journeys.repo.active_for_pet(self.owner.pet_id)
        self.assertEqual(journey.destination_key, work, "模型选的那一项变成真实行程")
        row = self.web.projector.runtime.row(self.owner.pet_id)
        self.assertEqual(row["last_decision_by"], "model", "运行记录写下是谁决定的")
        self.clock.advance(hours=5)
        self.run_background()
        with self.app.state.storage.connect() as conn:
            paid = conn.execute("SELECT COUNT(*) AS n FROM economy_transactions WHERE idempotency_key = ?", (f"web:job:{journey.journey_id}",)).fetchone()["n"]
        self.assertEqual(paid, 1, "真的干完了这份工作，工资一次")

    def test_a_different_choice_is_a_different_plan(self) -> None:
        self.life.mode = "live"
        self.use_choice("local:stroll")
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.destination_key), ("departed", "local:stroll"))
        self.assertEqual(self.web.journeys.repo.active_for_pet(self.owner.pet_id).destination_key, "local:stroll")
        self.assertEqual(self.web.economy.wallet(self.owner.pet_id).balance, self.owner.home()["wallet"]["balance"], "散步不发工资")

    def test_continue_means_staying_home(self) -> None:
        self.life.mode = "live"
        self.use_choice("continue")
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by), ("stayed", "model"))
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "留在家里也是一个明确结果")

    def test_dna_changed_while_thinking_blocks_the_plan(self) -> None:
        self.life.mode = "live"
        work = self.work_key()
        self.use_choice(work, on_call=lambda n: self.web.dna.save(self.owner.user_id, self.owner.pet_id, PetDNA(personality="其实很恋家"), self.clock.now))
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "stale_context", "思考期间家人改了 DNA：这次结论不作数")
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "不按旧资料出门")

    def test_a_member_removed_while_thinking_blocks_the_plan(self) -> None:
        self.life.mode = "live"
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        token = self.owner.post(f"/households/{household_id}/invites", {"role": "caregiver"}).json()["token"]
        member = self.user("brain-member")
        member.post("/invites/accept", {"token": token})
        work = self.work_key()
        self.use_choice(work, on_call=lambda n: self.owner.delete(f"/households/{household_id}/members/{member.user_id}"))
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual(outcome.status, "failed")
        self.assertIn(outcome.reason, ("stale_context", "revoked"), "思考期间家里少了一位家人：这次结论不作数")
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "不按旧的成员关系出门")

    def test_without_the_family_switch_the_model_is_not_called(self) -> None:
        self.life.mode = "live"
        self.owner.patch("/settings", {"model_replies": False})
        model = self.use_choice(self.work_key())
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.reason), ("failed", "disabled"))
        self.assertEqual(model.calls, [], "家庭没同意就一次都不调用")
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id))

    def test_the_cognition_lane_runs_a_decision_when_the_heartbeat_asks_for_one(self) -> None:
        self.life.mode = "live"
        work = self.work_key()
        model = self.use_choice(work)
        self.web.cognition.tick(self.clock.now)  # 认知线的一轮：心跳说“需要想一想”的宠物才会走决策
        journey = self.web.journeys.repo.active_for_pet(self.owner.pet_id)
        self.assertIsNotNone(journey, "模型选了工作：后台真的让 TA 出门了")
        self.assertEqual(journey.destination_key, work)
        self.assertEqual(len(model.calls), 1, "一轮里一只宠物只想一次")
        self.web.cognition.tick(self.clock.now)
        self.assertEqual(len(model.calls), 1, "已经在路上了就不再想")

    def test_the_cognition_lane_does_nothing_when_the_brain_is_off(self) -> None:
        model = self.use_choice(self.work_key())
        self.web.cognition.tick(self.clock.now)
        self.assertEqual((self.life.mode, model.calls), ("off", []), "默认关闭：后台一轮也不会调用模型")
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id))

    def test_shadow_mode_only_records(self) -> None:
        self.life.mode = "shadow"
        work = self.work_key()
        model = self.use_choice(work)
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by, outcome.destination_key), ("proposed", "model", work))
        self.assertEqual(len(model.calls), 1)
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "shadow 不出门")


if __name__ == "__main__":
    unittest.main()
