"""认知线这一步的调度：多只宠物要排得过来，想不成要会退避，别和规则生活抢同一只宠物。

一轮最多想几只是有上限的（默认 5）。上限本身没问题，问题是"上限之外的怎么办"：
  - **公平**：排在后面的宠物必须轮得到，不能每轮都被前几只占满；
  - **退避**：留在家里、模型失败、额度不足之后，不能下一轮（30 秒后）又调一次模型——那是真金白银；
  - **不打架**：世界线的规则生活和认知线的模型生活不能在同一个时段各决定一次，把同一只宠物送出门两回。
用脚本化的假模型，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.schemas.runtime_internal import BudgetDenied
from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class AlwaysStroll:
    """每次都选"附近散步"的假模型：按 offers 顺序找到 local:stroll 的别名。"""

    provider_label = "scripted"
    available = True
    max_call_seconds = 5.0

    def __init__(self, keys_of) -> None:
        self.keys_of = keys_of
        self.calls: list[str] = []

    def complete(self, messages, *, max_tokens):
        from app.web_agent.decision.model_port import ModelReply

        pet = next((line for line in str(messages) if False), None)  # 不从提示词里猜，交给 keys_of
        keys = self.keys_of()
        alias = f"o{keys.index('local:stroll') + 1}" if "local:stroll" in keys else "continue"
        self.calls.append(alias)
        return ModelReply(text=json.dumps({"choice": alias, "intent": "出去走走"}, ensure_ascii=False),
                          requested_model="scripted", effective_model="scripted-1", latency_ms=1)


class BrainRoundTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("round-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True
        self.round = dict(self.web.cognition.jobs)["brain_life"]

    def more_pets(self, count: int) -> list[str]:
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        pets = [self.owner.pet_id]
        for index in range(count):
            created = self.owner.upload_pet(f"小{index}", "cat", household_id=household_id)
            self.assertEqual(created.status_code, 201, created.text)
            pet_id = created.json()["pet_id"]
            self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": pet_id}).status_code, 200)
            self.web.economy.apply_grant(pet_id, 60) if hasattr(self.web.economy, "apply_grant") else None
            pets.append(pet_id)
        return pets

    def keys_for(self, pet_id: str) -> list[str]:
        options = self.web.journeys.destinations(self.owner.user_id, pet_id, self.owner.home_id, self.clock.now)
        return [destination_key_of(o) for o in offers_from_options(
            options, pet_id=pet_id, as_of=self.clock.now, expected_versions=self.web.projector.versions(pet_id),
            income_of=lambda key: job_of(key).pay if job_of(key) else 0)]

    def use_stroller(self, pet_id_holder) -> AlwaysStroll:
        model = AlwaysStroll(lambda: self.keys_for(pet_id_holder()))
        self.life.brain.model = model
        return model

    def runtime_row(self, pet_id: str):
        return self.web.projector.runtime.row(pet_id) or {}

    def considered(self) -> list[str]:
        """这一轮真的被"想"过的宠物：用 brain_life.consider 的调用记录。"""
        return list(self._seen)

    def spy_on_consider(self) -> None:
        self._seen: list[str] = []
        original = self.life.consider

        def watched(pet_id, now=None):
            self._seen.append(pet_id)
            return original(pet_id, now)

        self.life.consider = watched

    # ---- 公平 ----
    def test_pets_past_the_per_round_limit_still_get_their_turn(self) -> None:
        from app.web_agent.brain_life import BrainOutcome

        pets = self.more_pets(7)  # 共 8 只
        self._seen: list[str] = []

        def watched(pet_id, now=None, _s=self._seen):  # 只记录"排到了谁"，不真的决定，免得状态变化影响公平性本身
            _s.append(pet_id)
            return BrainOutcome(pet_id, self.life.mode, "skipped", reason="probe")

        self.life.consider = watched

        seen: set[str] = set()
        for _ in range(4):  # 上限 3：四轮足够让 8 只都排到
            self._seen.clear()
            self.round(self.clock.now, limit=3)
            seen.update(self._seen)
            self.clock.advance(seconds=30)

        missed = [p for p in pets if p not in seen]
        self.assertEqual(missed, [], f"这些宠物一直没排上：{missed}（一共 {len(pets)} 只，看到 {len(seen)} 只）")

    # ---- 退避 ----
    def test_a_failed_decision_does_not_call_the_model_again_on_the_next_tick(self) -> None:
        model = ScriptedModel(RuntimeError("模型这次挂了"), RuntimeError("不该有第二次"))
        self.life.brain.model = model

        self.round(self.clock.now, limit=5)
        first = len(model.calls)
        self.clock.advance(seconds=30)
        self.round(self.clock.now, limit=5)

        self.assertGreaterEqual(first, 1, "第一轮确实想了一次")
        self.assertEqual(len(model.calls), first, "想不成之后要退避，不能 30 秒后又调一次模型")

    def test_budget_denied_backs_off_instead_of_retrying_every_tick(self) -> None:
        denied = BudgetDenied("op", "pet:brain", "limit_reached")
        self.life.reserve = lambda operation_id, purpose, pet_id: denied
        model = ScriptedModel(json.dumps({"choice": "continue", "intent": "在家"}, ensure_ascii=False))
        self.life.brain.model = model

        self.round(self.clock.now, limit=5)
        self.clock.advance(seconds=30)
        self.round(self.clock.now, limit=5)

        self.assertEqual(model.calls, [], "额度不足时本来就不该调用模型")
        row = self.runtime_row(self.owner.pet_id)
        self.assertTrue(row.get("next_review_at"), f"额度不足要记下什么时候再看：{dict(row)}")

    def test_staying_home_is_recorded_so_the_next_tick_does_not_rethink(self) -> None:
        model = ScriptedModel(json.dumps({"choice": "continue", "intent": "今天想在家"}, ensure_ascii=False),
                              RuntimeError("不该有第二次"))
        self.life.brain.model = model

        self.round(self.clock.now, limit=5)
        self.clock.advance(seconds=30)
        self.round(self.clock.now, limit=5)

        self.assertEqual(len(model.calls), 1, "决定留在家里之后，下一轮不该再想一次")
        self.assertEqual(self.runtime_row(self.owner.pet_id).get("last_decision_by"), "model")

    # ---- 不打架 ----
    def eager_rule_engine(self) -> None:
        """让规则生活这一轮一定想出门（掷骰恒为 0），好让"两条线抢同一只宠物"真的暴露出来。"""
        from unittest import mock

        import app.web_agent.life as life_mod

        patch = mock.patch.object(life_mod, "_roll", lambda *parts: 0.0)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_rule_engine_does_not_override_a_decision_the_brain_just_made(self) -> None:
        model = ScriptedModel(*[json.dumps({"choice": "continue", "intent": "在家待着"}, ensure_ascii=False) for _ in range(5)])
        self.life.brain.model = model
        self.eager_rule_engine()

        self.round(self.clock.now, limit=5)  # 认知线：TA 决定留在家里
        row_before = dict(self.runtime_row(self.owner.pet_id))
        self.assertEqual(row_before.get("last_decision_by"), "model", f"前提：这一轮确实由模型决定了：{row_before}")
        self.web.life.run(self.clock.now)  # 世界线的规则生活紧接着跑一轮

        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id),
                          f"TA 刚决定留在家里，规则生活不能在同一个时段把 TA 送出门：{row_before}")

    def test_the_rule_engine_records_who_decided_so_the_brain_does_not_redo_it(self) -> None:
        self.life.mode = "off"  # 大脑关着：世界照旧由规则生活推进
        self.eager_rule_engine()

        self.web.life.run(self.clock.now)

        row = self.runtime_row(self.owner.pet_id)
        if self.web.journeys.repo.active_for_pet(self.owner.pet_id) is not None:
            self.assertEqual(row.get("last_decision_by"), "rule", f"规则生活送 TA 出门之后也要记下是谁决定的：{dict(row)}")


if __name__ == "__main__":
    unittest.main()
