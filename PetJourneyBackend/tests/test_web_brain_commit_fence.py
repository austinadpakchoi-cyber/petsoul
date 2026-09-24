"""自主决策的最终提交围栏：模型在想的这段时间里，世界可能已经变了。

一次决策分两步：先把可行机会交给模型，等它给出提案，再执行。这中间隔着一次真实的模型调用——
几十秒到几分钟都可能。所以**执行前必须按"此刻"重新判一遍**，而不是拿发起时的那个时间去判：
  - 机会有没有过期（ActionOffer.valid_until）；
  - 这次决策有没有超过自己的截止期限（DEADLINE）；
  - 家庭还同不同意把资料交给模型（想的时候同意、执行时已经撤回，就不能再用它的提案）；
  - 语义版本（成员、授权、DNA、活动、行程）有没有变。
这里用脚本化的假模型，在"调用模型"的那一刻把世界改掉，看旧提案会不会仍被执行。不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest

from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class BrainCommitFenceTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("fence-brain")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"

    def offers(self):
        now = self.clock.now
        options = self.web.journeys.destinations(self.owner.user_id, self.owner.pet_id, self.owner.home_id, now)
        return list(offers_from_options(options, pet_id=self.owner.pet_id, as_of=now, expected_versions=self.web.projector.versions(self.owner.pet_id),
                                        income_of=lambda key: job_of(key).pay if job_of(key) else 0))

    def choose(self, key: str, *, during=None) -> ScriptedModel:
        """让模型选 key；during(第几次调用) 在模型"思考"的那一刻执行，用来改变世界。"""
        keys = [destination_key_of(offer) for offer in self.offers()]
        reply = json.dumps({"choice": f"o{keys.index(key) + 1}", "intent": "出去走走"}, ensure_ascii=False)
        model = ScriptedModel(reply, on_call=during)
        self.life.brain.model = model
        self.web.projector.model_available = lambda: True
        return model

    def stroll(self) -> str:
        return next(destination_key_of(o) for o in self.offers() if destination_key_of(o) == "local:stroll")

    def active(self):
        return self.web.journeys.repo.active_for_pet(self.owner.pet_id)

    def assert_not_executed(self, outcome, *, allow=()) -> None:
        """不执行有两种正当形态：决策层就拒绝出提案（failed），或提交前复核挡下（rejected）。
        两种都必须带明确原因，都不能真的出发。"""
        self.assertIn(outcome.status, ("failed", "rejected"), f"不能执行：{outcome}")
        self.assertTrue(outcome.reason, f"要记下原因：{outcome}")
        if allow:
            self.assertIn(outcome.reason.split(":")[0], allow, outcome.reason)
        self.assertIsNone(self.active(), "没有出发")

    def test_the_baseline_choice_really_departs(self) -> None:
        self.choose(self.stroll())
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by), ("departed", "model"), outcome.reason)
        self.assertIsNotNone(self.active())

    def test_an_offer_that_expired_while_the_model_was_thinking_is_not_executed(self) -> None:
        self.choose(self.stroll(), during=lambda _n: self.clock.advance(minutes=11))  # 机会只有 10 分钟

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assert_not_executed(outcome, allow=("offer_expired", "deadline_passed", "deadline_exceeded", "stale_context"))

    def test_a_decision_that_blew_past_its_deadline_is_not_executed(self) -> None:
        self.choose(self.stroll(), during=lambda _n: self.clock.advance(minutes=3))  # 截止是 90 秒

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assert_not_executed(outcome, allow=("deadline_passed", "deadline_exceeded", "offer_expired"))

    def test_consent_withdrawn_while_the_model_was_thinking_is_not_executed(self) -> None:
        """真实入口撤回"模型回信"：PATCH /settings 会让 privacy_epoch 前进一代，
        所以拦下这份提案的是**授权围栏**（decision 层答完后重读版本，revoked），比提交前的同意检查更早一步。
        两个围栏都算数，但不能是别的原因，也不能真的执行。"""
        def withdraw(_n: int) -> None:
            self.owner.patch("/settings", {"model_replies": False})

        self.choose(self.stroll(), during=withdraw)
        before = self.web.projector.versions(self.owner.pet_id)

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertIn("privacy_epoch", before.stale_fields(self.web.projector.versions(self.owner.pet_id)),
                      "前提：撤回确实发生了，而且把 privacy_epoch 推进了一代")
        self.assertFalse(self.web.projector.model_enabled(self.owner.pet_id), "前提：这个家现在确实不同意用模型")
        self.assert_not_executed(outcome, allow=("consent_withdrawn", "revoked"))
        self.assertIsNone(self.web.projector.runtime.row(self.owner.pet_id).get("last_decision_at"), "不能写成一次生活决定")

    def test_consent_withdrawn_without_a_version_bump_is_still_caught_at_commit(self) -> None:
        """纵深防御：万一哪个入口撤回了同意却没有推进版本代数，提交前的同意检查仍要单独拦下来。
        这一条直接改注入点（不走 HTTP），专门覆盖 _commit 里的 consent_withdrawn 分支。"""
        self.choose(self.stroll(), during=lambda _n: setattr(self.life, "model_consent", lambda pet_id: False))

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assert_not_executed(outcome, allow=("consent_withdrawn",))

    def test_leaving_home_while_the_model_was_thinking_is_rejected(self) -> None:
        def leave(_n: int) -> None:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "local:cafe", self.clock.now)

        self.choose(self.stroll(), during=leave)

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertIn(outcome.status, ("failed", "rejected"), f"TA 已经出门了：{outcome}")
        self.assertTrue(outcome.reason, outcome)
        self.assertEqual(self.active().destination_key, "local:cafe", "还是自己出门的那一趟，没有被模型的提案改掉")

    def test_a_revocation_landing_between_the_last_two_checks_still_blocks_staying_home(self) -> None:
        """"留在家里"的最后一道闸：提交前的版本复核过了之后、真正写下之前，家里用**正式接口**撤回了同意。
        这一刻的撤权必须由 record_decision_checked 在同一个事务里挡下来（Q-C12 的消费侧；正式入口本身由 I/identity 负责）。"""
        runtime = self.web.projector.runtime
        original = runtime.record_decision_checked
        landed: list[str] = []

        def revoke_then_write(pet_id, now, **kwargs):
            if not landed:  # 只在真正要写"留在家里"的那一刻撤权，模拟两次检查之间的竞态
                landed.append(self.owner.patch("/settings", {"model_replies": False}).status_code and "revoked")
            return original(pet_id, now, **kwargs)

        runtime.record_decision_checked = revoke_then_write
        self.life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "今天在家"}, ensure_ascii=False))
        self.web.projector.model_available = lambda: True

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(landed, ["revoked"], "前提：撤权确实在那一刻发生了")
        self.assert_not_executed(outcome, allow=("versions_changed",))
        self.assertIn("privacy_epoch", outcome.reason, outcome.reason)
        row = self.web.projector.runtime.row(self.owner.pet_id)
        self.assertIsNone(row.get("last_decision_at"), f"被挡下就不能写成一次生活决定：{dict(row)}")
        self.assertIsNone(row.get("last_decision_by"), f"也不能写决定人：{dict(row)}")

    def test_a_dna_change_while_the_model_was_thinking_is_rejected(self) -> None:
        def rewrite(_n: int) -> None:
            self.owner.put(f"/pets/{self.owner.pet_id}/dna", {"owner_title": "姐姐", "personality": "换了个说法", "catchphrase": "喵"})

        self.choose(self.stroll(), during=rewrite)

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assert_not_executed(outcome, allow=("versions_changed", "stale_context"))


if __name__ == "__main__":
    unittest.main()
