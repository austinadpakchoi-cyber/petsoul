"""决策包接真实服务（工作包 C 的隔离集成）：真实网页服务 + 临时库 + 假模型，证明“模型的选择改变了真实计划”。

每个场景新建一套临时库、同一位领养伙伴、同一时刻，只改变假模型的选择：
- 选打工 → journeys.depart 生成真实的打工旅程，到点工资恰好入账一次；选散步 → 真实散步，不花钱、没有工资；选继续待在家 → 没有旅程；
- 思考期间家人改了 DNA → 提案被拒（stale_context），不出门；
- 真实接待流程确认的叮嘱：只允许私聊用的、只留在接待处的不进；本人没同意交给模型前，出行 / 家中互动的叮嘱也不进。
这里的 depart 只是最简单的演示版提交；正式的同事务复核、预算结算与决定记录由集成窗口实现。不联网、不调用供应商。
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.config import Settings
from app.main import create_app
from app.schemas.base import EconomyTransactionType
from app.schemas.runtime_internal import AudienceScope, HeartbeatAction, Versions
from app.schemas.web.pets import PetDNA
from app.web_agent.decision import (Brain, DecisionRequest, ServiceContextReader, build_context, destination_key_of, offers_from_options,
                                    reason_of)
from app.web_agent.decision.prompt import render
from app.web_agent.decision.testing import ScriptedModel, reservation_for
from app.web_journey.local import job_of
from app.web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate
from web_base import LUNCH_UTC, FakeClock, WebUser

NOTES_TEXT = "叫我妈妈就好。它最喜欢那条蓝色的毯子。它不喜欢被抱。以后想带它去看海。它小时候走丢过一次，别告诉它。"


def answer(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


def demo_versions(web):
    """只供测试：用现有表近似投影语义版本（正式的 runtime / activity / privacy / membership epoch 由集成窗口维护）。"""
    def versions_of(pet_id: str) -> Versions:
        saved = web.dna.saved(pet_id)
        household_id = web.households.household_of_pet(pet_id)
        with web.dna.storage.connect() as conn:
            journeys = conn.execute("SELECT COUNT(*) AS n, COUNT(completed_at) AS done FROM web_journeys WHERE pet_id = ?", (pet_id,)).fetchone()
            grants = conn.execute("SELECT COUNT(*) AS n, COUNT(revoked_at) AS revoked FROM web_memory_grants WHERE pet_id = ?", (pet_id,)).fetchone()
            members = conn.execute("SELECT COUNT(*) AS n FROM web_household_members WHERE household_id = ? AND status = 'active'", (household_id,)).fetchone()
        return Versions(runtime_epoch=1, activity_epoch=1 + journeys["n"] + journeys["done"], dna_version=saved.version if saved else 0,
                        privacy_epoch=1 + grants["n"] + grants["revoked"], membership_epoch=members["n"])
    return versions_of


class ChainBase(unittest.TestCase):
    """共用脚手架：固定时钟、每个场景一套全新临时库。本身不含用例。"""

    def setUp(self) -> None:
        self.clock = FakeClock(LUNCH_UTC).install(self)

    def world(self, name: str, *, adopt: bool = True, habitat: str = "seaside"):
        """一套全新的临时库：一位家人领养同一位伙伴、住在指定环境（adopt=False 时只注册账号）。"""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        settings = Settings(database_path=root / "web.sqlite3", upload_dir=root / "uploads", web_private_media_dir=root / "private",
                            public_base_url="http://testserver", auth_secret="web-test-secret-0123456789abcdef-0123", apple_auth_mode="mock",
                            scheduler_enabled=False, legacy_api_policy="open", economy_admin_token="admin-test-token", web_cookie_secure=False,
                            web_demo_catalog=True)
        app = create_app(settings)
        owner = WebUser(app, name)
        self.addCleanup(owner.client.close)
        if adopt:
            owner.post("/adoption/adopt", {"candidate_id": "adopt-lan"})
            state = owner.get("/onboarding").json()
            owner.pet_id, owner.home_id = state["pet_id"], state["home_id"]
            self.assertEqual(owner.post("/onboarding/move-in", {"public_posts": False, "habitat": habitat}).status_code, 200)
        return app.state.web, owner

    def reader(self, web) -> ServiceContextReader:
        return ServiceContextReader(web, versions_of=demo_versions(web), now=lambda: self.clock.now)

    def request(self, web, pet_id: str, offers=()) -> DecisionRequest:
        now = self.clock.now
        household = AudienceScope("household", household_id=web.households.household_of_pet(pet_id))
        return DecisionRequest(operation_id=f"op-{pet_id}", pet_id=pet_id, purpose="life_plan", audience=household, as_of=now,
                               deadline_at=now + timedelta(seconds=60), offers=offers, reason_codes=("activity_due",), model_consent=True)

    def decide(self, web, owner, choose: str, *, on_call=None):
        now = self.clock.now
        reader = self.reader(web)
        offers = offers_from_options(web.journeys.destinations(owner.user_id, owner.pet_id, owner.home_id, now), pet_id=owner.pet_id, as_of=now,
                                     expected_versions=reader.versions(owner.pet_id), income_of=lambda key: job_of(key).pay if job_of(key) else 0)
        keys = [destination_key_of(o) for o in offers]
        alias = "continue" if choose == "continue" else f"o{keys.index(choose) + 1}"
        model = ScriptedModel(json.dumps({"choice": alias, "intent": "就这么定了"}, ensure_ascii=False), on_call=on_call)
        clock = SimpleNamespace(now_utc=lambda: self.clock.now, monotonic=time.monotonic)
        request = self.request(web, owner.pet_id, offers)
        result = Brain(reader=reader, model=model, clock=clock).propose(request, reservation_for(request.operation_id, now=now))
        journey = None
        if result.proposal is not None and not result.proposal.continue_current:  # 演示版提交：选中行动 → 现有的出发
            offer = {o.offer_id: o for o in offers}[result.proposal.selected_offer_id]
            journey = web.journeys.depart(owner.user_id, owner.pet_id, owner.home_id, destination_key_of(offer), now)
        return result, journey, model


class DecisionChainTests(ChainBase):
    def test_the_model_choice_decides_the_real_plan(self) -> None:
        for choice, wage in (("work:fishing_port", 28), ("local:stroll", 0), ("continue", None)):
            with self.subTest(choice=choice):
                web, owner = self.world(f"chain-{choice.replace(':', '-')}")
                before = web.economy.wallet(owner.pet_id).balance
                result, journey, model = self.decide(web, owner, choice)
                self.assertEqual((result.proposal.composed_by, len(model.calls)), ("model", 1))
                self.assertIn("去渔港帮忙收网", model.calls[0][1]["content"], "规则给出的真实可行行动进了提示")
                active = web.journeys.repo.active_for_pet(owner.pet_id)
                if wage is None:
                    self.assertEqual((journey, active), (None, None))
                    continue
                self.assertEqual((journey.destination_key, active.journey_id), (choice, journey.journey_id))
                self.clock.advance(hours=4)
                web.journeys.advance_all(self.clock.now)
                self.clock.advance(hours=-4)  # 下一套临时库仍从同一时刻开始
                with web.dna.storage.connect() as conn:
                    paid = conn.execute("SELECT COUNT(*) AS n FROM economy_transactions WHERE idempotency_key = ?",
                                        (f"web:job:{journey.journey_id}",)).fetchone()["n"]
                self.assertEqual((web.economy.wallet(owner.pet_id).balance - before, paid), (wage, 1 if wage else 0))

    def test_dna_corrected_while_thinking_blocks_the_plan(self) -> None:
        web, owner = self.world("chain-dna")
        fix = lambda n: web.dna.save(owner.user_id, owner.pet_id, PetDNA(personality="其实很恋家"), self.clock.now)  # noqa: E731
        result, journey, _ = self.decide(web, owner, "work:fishing_port", on_call=fix)
        self.assertEqual((result.failure.code.value, reason_of(result.failure), journey), ("stale_context", "versions_changed", None))
        self.assertIn("dna_version", result.failure.detail)
        self.assertIsNone(web.journeys.repo.active_for_pet(owner.pet_id))

    def test_real_reception_notes_respect_purpose_and_consent(self) -> None:
        web, owner = self.world("chain-notes", adopt=False)
        created = owner.upload_pet("团子", "cat")
        self.assertEqual(created.status_code, 201, created.text)
        pet_id = created.json()["pet_id"]
        session = owner.post("/reception/sessions", {"pet_id": pet_id, "branch": "own_pet"}).json()
        session = owner.post(f"/reception/sessions/{session['session_id']}/turns", {"text": NOTES_TEXT, "expected_revision": session["draft_revision"]}).json()
        purposes = {"wish_place": ["travel_preference"], "owner_title": ["private_chat"]}
        decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "keep_here", "purposes": []} if c["kind"] == "owner_private" else
                     {"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": purposes.get(c["suggested_slot"], ["home_interaction"]),
                      "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]} for c in session["candidates"]]
        body = {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions}
        self.assertEqual(owner.post("/reception/confirmations", body).status_code, 200)
        self.assertEqual(owner.post("/onboarding/move-in", {"public_posts": False, "habitat": "seaside"}).status_code, 200)
        reader, request = self.reader(web), self.request(web, pet_id)
        # 2026-09-24 起“模型回信”默认开启：没选过的本人，叮嘱**按用途**交给模型；原先这里是“默认拒绝”那一侧
        allowed = build_context(reader, request).context
        memory = " ".join(f.text for f in allowed.memory_refs)
        self.assertIn("看海", memory)
        self.assertIn("毯子", memory)
        self.assertTrue(all(f.scope.kind == "private" and f.scope.user_id == owner.user_id for f in allowed.memory_refs))
        prompt = " ".join(m["content"] for m in render(allowed).messages)
        for secret in ("走丢", "妈妈"):  # 只留在接待处的倾诉、只允许私聊用的称呼：默认开启也不给
            self.assertNotIn(secret, memory)
            self.assertNotIn(secret, prompt)
        web.identity.set_prefs(owner.user_id, model_replies=False)  # 本人撤回
        refused = build_context(reader, request)
        self.assertEqual(refused.context.memory_refs, (), "本人关掉“模型回信”：叮嘱只影响规则生活，不交给模型")
        self.assertTrue(any(d.endswith(":member_model_consent") for d in refused.dropped))


def pick(keyword: str, intent: str = "就这么定了"):
    """按提示词里的行动说明挑一项：模拟“模型读了可行机会再选”，不依赖行动的排列顺序。"""
    def choose(messages) -> str:
        line = next(l for l in messages[-1]["content"].splitlines() if l.startswith("- o") and keyword in l)
        return answer(choice=line.split()[1], intent=intent)
    return choose


class BrainWiringTests(ChainBase):
    """走集成窗口的真实装配（web.brain_life）：只把模型换成假模型，其余读取、预占、复核、出发都用真实路径。"""

    def brain_world(self, name: str, reply, *, mode: str = "shadow"):
        web, owner = self.world(name)
        web.identity.set_prefs(owner.user_id, model_replies=True)  # 家庭同意把共用资料交给模型
        web.brain_life.mode = mode
        model = ScriptedModel(reply)
        web.brain_life.brain.model = model
        web.projector.model_available = lambda: True  # 假模型顶替供应商；心跳据此认为大脑可用
        return web, owner, model

    def prompt_of(self, model: ScriptedModel) -> tuple[str, str]:
        self.assertTrue(model.calls, "模型没有被调用")
        return model.calls[0][0]["content"], model.calls[0][1]["content"]

    def work_once(self, web, owner) -> None:
        """先真的去打一次工并收工：给时间线留下一段过去的事实（出发、收工、工资）。"""
        web.journeys.depart(owner.user_id, owner.pet_id, owner.home_id, "work:fishing_port", self.clock.now)
        self.clock.advance(hours=4)
        web.journeys.advance_all(self.clock.now)

    def test_the_prompt_is_built_from_real_records(self) -> None:
        web, owner, model = self.brain_world("wiring-ctx", answer(choice="continue", intent="今天就在家陪你"))
        saved = owner.put(f"/pets/{owner.pet_id}/dna", {"personality": "好奇，爱凑热闹", "habits": ["午后在窗台晒太阳"], "favorite_places": ["海边"],
                                                        "owner_title": "妈妈", "shared_memories": ["我们的暗号是咪咪"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.work_once(web, owner)
        self.assertEqual(owner.post("/journey/suggest", {"destination_key": "local:cafe"}).status_code, 200)
        outcome = web.brain_life.consider(owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by), ("proposed", "model"))
        system, prompt = self.prompt_of(model)
        # DNA：家人确认并保存的那一份，个人层不进生活决策
        self.assertIn("家人已确认", prompt)
        for text in ("好奇，爱凑热闹", "午后在窗台晒太阳", "海边"):
            self.assertIn(text, prompt)
        for personal in ("妈妈", "咪咪"):
            self.assertNotIn(personal, prompt + system)
        # 过去的事实来自真实时间线；余额、机会来自真实服务
        self.assertIn("收工回到家", prompt)
        self.assertRegex(prompt, r"- e\d+ \[\d+ 小时前\] ")
        self.assertIn(f"银行卡余额 {web.economy.wallet(owner.pet_id).balance} 星币", prompt)
        keys = {d.destination_key for d in web.journeys.destinations(owner.user_id, owner.pet_id, owner.home_id, self.clock.now) if d.available and d.affordable}
        titles = {d.title for d in web.journeys.destinations(owner.user_id, owner.pet_id, owner.home_id, self.clock.now) if d.destination_key in keys}
        for title in titles:
            self.assertIn(title, prompt)
        self.assertIn("收入 28 星币", prompt)  # 工钱由规则给出，不是模型编的
        # 家人的建议是建议，不是命令
        self.assertIn("有家人建议：去附近喝一杯", prompt)
        self.assertIn("家人的建议可以采纳，也可以不采纳", system)
        for internal in (owner.pet_id, owner.user_id, "op-", "life:"):
            self.assertNotIn(internal, prompt)

    def test_future_wishes_are_not_told_as_things_that_happened(self) -> None:
        web, owner = self.world("wiring-wish", adopt=False)
        pet = owner.upload_pet("团子", "cat").json()["pet_id"]
        session = owner.post("/reception/sessions", {"pet_id": pet, "branch": "own_pet"}).json()
        session = owner.post(f"/reception/sessions/{session['session_id']}/turns",
                             {"text": NOTES_TEXT, "expected_revision": session["draft_revision"]}).json()
        decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "keep_here", "purposes": []} if c["kind"] == "owner_private" else
                     {"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet",
                      "purposes": ["travel_preference"] if c["suggested_slot"] == "wish_place" else ["home_interaction"],
                      "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]} for c in session["candidates"]]
        self.assertEqual(owner.post("/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"],
                                                                 "decisions": decisions}).status_code, 200)
        self.assertEqual(owner.post("/onboarding/move-in", {"public_posts": False, "habitat": "seaside"}).status_code, 200)
        owner.pet_id, owner.home_id = pet, owner.get("/onboarding").json()["home_id"]
        web.identity.set_prefs(owner.user_id, model_replies=True)
        web.brain_life.mode = "shadow"
        model = ScriptedModel(answer(choice="continue", intent="在家待着"))
        web.brain_life.brain.model = model
        self.work_once(web, owner)
        web.brain_life.consider(pet, self.clock.now)
        _, prompt = self.prompt_of(model)
        wish = next(line for line in prompt.splitlines() if "看海" in line)
        fact = next(line for line in prompt.splitlines() if "收工回到家" in line)
        self.assertTrue(wish.startswith("- n") and "愿望" in wish, wish)  # 还没发生的心愿，标成愿望
        self.assertTrue(fact.startswith("- e") and "前]" in fact, fact)  # 已经发生的事，带发生时间
        self.assertIn("小习惯：", prompt)
        self.assertNotIn("走丢", prompt)  # 只留在接待处的私人倾诉

    def _two_dnas(self):
        """两套一模一样的世界，只有 DNA 不同（早睡早起 / 爱熬夜）。"""
        early = self.brain_world("dna-early", answer(choice="continue", intent="在家待着"))
        night = self.brain_world("dna-night", answer(choice="continue", intent="在家待着"))
        for (web, owner, _), dna in ((early, {"personality": "早睡早起，天一亮就精神", "habits": ["每天早上六点叫醒主人"]}),
                                     (night, {"personality": "爱熬夜，夜里最精神", "habits": ["半夜在客厅跑酷"]})):
            self.assertEqual(owner.put(f"/pets/{owner.pet_id}/dna", dna).status_code, 200)
        return early, night

    def test_same_offers_only_the_dna_section_changes(self) -> None:
        """同样的可行机会下，只有 DNA 段不同。这只说明 DNA 进了上下文，不说明模型会因此偏好不同的选择。"""
        early, night = self._two_dnas()
        prompts = []
        for web, owner, model in (early, night):
            web.brain_life.consider(owner.pet_id, self.clock.now)
            prompts.append(self.prompt_of(model)[1])
        self.assertIn("早睡早起", prompts[0])
        self.assertIn("爱熬夜", prompts[1])
        sections = [{prefix: [l for l in text.splitlines() if l.startswith(f"- {prefix}")] for prefix in "doenc"} for text in prompts]
        self.assertEqual(sections[0]["o"], sections[1]["o"], "可行机会逐行一致")
        self.assertNotEqual(sections[0]["d"], sections[1]["d"])
        for prefix in "enc":  # 其余各栏条数一致（证件编号等每套库随机，不逐字比）
            self.assertEqual(len(sections[0][prefix]), len(sections[1][prefix]))

    def test_rhythm_from_dna_changes_what_is_feasible(self) -> None:
        """作息由 DNA 推出，直接改变“此刻能不能出门”——这条是确定性规则，和模型无关。"""
        early, night = self._two_dnas()
        early_profile, night_profile = (web.profile_of(owner.pet_id) for web, owner, _ in (early, night))
        self.assertLess(early_profile.wake, night_profile.wake)
        morning = self.clock.now.replace(hour=23, minute=0)  # 香港次日 07:00
        for (web, owner, _), awake in ((early, True), (night, False)):
            self.assertEqual(web.journeys.awake_at(owner.pet_id, morning), awake)
            if awake:
                self.assertEqual(web.journeys.depart(owner.user_id, owner.pet_id, owner.home_id, "local:stroll", morning).destination_key, "local:stroll")
            else:
                with self.assertRaises(Exception) as refused:
                    web.journeys.depart(owner.user_id, owner.pet_id, owner.home_id, "local:stroll", morning)
                self.assertEqual(getattr(refused.exception, "reason", None), "pet_asleep")

    def test_a_suggestion_stays_advice_and_the_choice_is_the_pets(self) -> None:
        web, owner, model = self.brain_world("wiring-advice", pick("去渔港帮忙收网", "先去打工攒点钱"), mode="live")
        self.assertEqual(owner.post("/journey/suggest", {"destination_key": "local:cafe"}).status_code, 200)
        outcome = web.brain_life.consider(owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by, outcome.destination_key), ("departed", "model", "work:fishing_port"))
        journey = web.journeys.repo.active_for_pet(owner.pet_id)
        self.assertEqual(journey.destination_key, "work:fishing_port", "TA 自己选了打工，没有被建议牵着走")
        self.assertEqual([s["status"] for s in owner.get("/journey/suggestions").json()], ["pending"], "建议还在考虑中，不会被当成命令执行")

    def test_no_money_still_leaves_a_life(self) -> None:
        web, owner, model = self.brain_world("wiring-broke", pick("去渔港帮忙收网", "先去挣点钱"), mode="live")
        wallet = web.economy.wallet(owner.pet_id).balance
        web.economy.apply(owner.pet_id, -wallet, EconomyTransactionType.web_travel_fee, "test:drain", reason="测试清空余额",
                          source="test.decision", now=self.clock.now)
        outcome = web.brain_life.consider(owner.pet_id, self.clock.now)
        _, prompt = self.prompt_of(model)
        self.assertIn("银行卡余额 0 星币", prompt)
        self.assertIn("在家附近走走", prompt)  # 不花钱的还在
        self.assertIn("去渔港帮忙收网", prompt)  # 可以自己去挣
        for paid in ("去附近喝一杯", "进城逛逛", "坐船去澳门"):
            self.assertNotIn(paid, prompt)  # 钱不够的不进可行机会
        self.assertEqual((outcome.status, outcome.destination_key), ("departed", "work:fishing_port"))
        self.assertEqual(web.economy.wallet(owner.pet_id).balance, 0, "打工不花钱")

    def test_the_local_clock_comes_from_the_real_place(self) -> None:
        web, owner = self.world("wiring-clock")
        reader = ServiceContextReader(web, versions_of=web.projector.versions, now=lambda: self.clock.now)
        place = web.home_places.get(owner.home_id)
        local = reader.local_time(owner.pet_id, self.clock.now)
        self.assertEqual(str(local.tzinfo), place.timezone, "当地时间取这只宠物住的地方，不是写死的时区")
        self.assertEqual(local.utcoffset(), self.clock.now.astimezone(ZoneInfo(place.timezone)).utcoffset())

    def test_in_another_timezone_the_clock_follows_the_pet(self) -> None:
        """TA 在外地时，当地时间要跟着 TA 走。默认只认家的时区，所以正式装配要注入运行投影的时区。"""
        web, owner = self.world("wiring-tokyo", habitat="city")
        web.economy.apply(owner.pet_id, 300, EconomyTransactionType.web_reward, "test:topup", reason="测试用旅费", source="test.decision",
                          now=self.clock.now)
        web.journeys.depart(owner.user_id, owner.pet_id, owner.home_id, "tokyo_flight", self.clock.now)
        for _ in range(24):  # 推到 TA 真的在东京那家店里
            self.clock.advance(minutes=30)
            web.journeys.advance_all(self.clock.now)
            if web.projector.state(owner.pet_id, self.clock.now).timezone == "Asia/Tokyo":
                break
        state = web.projector.state(owner.pet_id, self.clock.now)
        self.assertEqual(state.timezone, "Asia/Tokyo", "先确认投影认得 TA 此刻在东京")
        home_only = ServiceContextReader(web, versions_of=web.projector.versions, now=lambda: self.clock.now)
        self.assertEqual(str(home_only.local_time(owner.pet_id, self.clock.now).tzinfo), web.home_places.get(owner.home_id).timezone)
        with_projection = ServiceContextReader(web, versions_of=web.projector.versions, now=lambda: self.clock.now,
                                               timezone_of=lambda pet_id, now: web.projector.state(pet_id, now).timezone)
        local = with_projection.local_time(owner.pet_id, self.clock.now)
        self.assertEqual(str(local.tzinfo), "Asia/Tokyo")
        self.assertEqual(local.hour, self.clock.now.astimezone(ZoneInfo("Asia/Tokyo")).hour)
        unknown = ServiceContextReader(web, versions_of=web.projector.versions, now=lambda: self.clock.now,
                                       timezone_of=lambda pet_id, now: None)
        self.assertIsNone(unknown.local_time(owner.pet_id, self.clock.now), "投影说时区不可用时，不编一个当地时间")

    def test_staying_home_is_recorded_and_the_next_round_does_not_think_again(self) -> None:
        web, owner, model = self.brain_world("wiring-stay", answer(choice="continue", intent="今天在家陪你"), mode="live")
        before = evaluate(web.projector.state(owner.pet_id, self.clock.now), (), HeartbeatPolicy(), self.clock.now,
                          facts=web.projector.facts(owner.pet_id, self.clock.now))
        self.assertIs(before.action, HeartbeatAction.REQUEST_BRAIN, "还没决定过：该想一想")
        outcome = web.brain_life.consider(owner.pet_id, self.clock.now)
        self.assertEqual((outcome.status, outcome.composed_by), ("stayed", "model"))
        row = web.projector.runtime.row(owner.pet_id)
        self.assertEqual(row["last_decision_by"], "model")
        self.assertIsNone(web.journeys.repo.active_for_pet(owner.pet_id))
        later = self.clock.now + timedelta(minutes=5)
        after = evaluate(web.projector.state(owner.pet_id, later), (), HeartbeatPolicy(), later, facts=web.projector.facts(owner.pet_id, later))
        self.assertIsNot(after.action, HeartbeatAction.REQUEST_BRAIN, "刚决定过就不该再想一次")
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()
