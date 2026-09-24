"""主人说了「今天别出门」之后，**TA 自己不会再出门；主人自己点出发照样能走**（TRV-02 合同 15 节）。

谓词本身由 C 单独验过（`test_web_commitment_gate.py`）。**这份验的是另一件事：接线。**
那五条用例把谓词直接造出来调，所以**即使组合根一行都没接，它们照样全绿**——
「测回调的会静悄悄地绿，测正式入口的在接线消失时才会红」，这里要的是后者。

这份只走**默认装配**：不自己安装谓词、不自己传参数，全部经由真实的
`web_agent_wiring` 与 `web.life` / `web.brain_life` / `/journey/depart`。

**每一条「没出门」都先有一个「同样的事实真的会出门」的对照**，而且掷骰被钉死在 0.0——
这样「被拦住」只可能是硬闸的作用：规则生活里主人的叮嘱本来只把出门概率乘 0.15
（`life.py:269`，"多半就在家"），仍有约一成会出门。**软偏好管 TA 想不想去，硬闸管允不允许。**
不把掷骰钉死，这份用例验到的可能只是那 15%。
"""

from __future__ import annotations

import json
import unittest

import app.web_agent.life as life_module
from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.commitments import OWNER_ASKED_STAY_HOME
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class CommitmentWiringTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("commitment-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        # 掷骰钉死为 0：这一轮**一定**想出门。只有这样"没出门"才说明是闸起了作用，
        # 而不是主人的叮嘱把概率压低之后正好没掷中。
        original = life_module._roll
        life_module._roll = lambda *parts: 0.0
        self.addCleanup(lambda: setattr(life_module, "_roll", original))

    def say(self, text: str) -> None:
        """照主人真实的做法：在通讯器里说一句，不直接改库。

        **`client_message_id` 至少 8 个字符**——短了会 422、消息压根不创建，
        而调用方看不出来：后面那句「TA 出门了」会照样成立，用例白绿。所以这里断言响应码。
        """
        reply = self.owner.post(f"/communicator/{self.pet}/messages",
                                {"client_message_id": f"say-{abs(hash(text)) % 99999:05d}", "text": text})
        self.assertEqual(reply.status_code, 200, f"这句话没发出去，后面的观察都不算数：{str(reply.json())[:200]}")

    def stay_home(self) -> None:
        self.say("今天别出门了，外面下雨")

    def went_out(self) -> bool:
        return self.web.journeys.repo.active_for_pet(self.pet) is not None

    def let_the_brain_choose(self, key: str) -> None:
        # 家里得先开「模型回信」，否则认知线整条是 disabled——那样"没出门"只是因为它压根没跑。
        # （第一版就栽在这儿：`went_out()` 是假的、用例却绿着，是断言 outcome 的原因码才抓出来。）
        self.owner.patch("/settings", {"model_replies": True})
        now = self.clock.now
        options = self.web.journeys.destinations(self.owner.user_id, self.pet, self.owner.home_id, now)
        offers = list(offers_from_options(options, pet_id=self.pet, as_of=now,
                                          expected_versions=self.web.projector.versions(self.pet),
                                          income_of=lambda k: job_of(k).pay if job_of(k) else 0))
        keys = [destination_key_of(offer) for offer in offers]
        self.web.brain_life.mode = "live"
        self.web.brain_life.brain.model = ScriptedModel(
            json.dumps({"choice": f"o{keys.index(key) + 1}", "intent": "出去走走"}, ensure_ascii=False))
        self.web.projector.model_available = lambda: True

    def test_the_default_assembly_binds_the_predicate(self) -> None:
        """接线本身。**没有这一条，下面每一条的"没出门"都可能只是因为闸根本没装**——

        服务里那个槽默认是 None，而"明确要闸却没有闸"会被拒绝出发（`commitment_gate_unavailable`），
        看起来同样是"没出门"。所以要先证明装上的是真谓词，而不是一个缺席。
        """
        gate = self.web.journeys.active_commitment_in

        self.assertIsNotNone(gate, "组合根没接上承诺谓词：那样自主出发会一律被 commitment_gate_unavailable 拒绝")
        with self.web.journeys.storage.connect() as conn:
            self.assertIsNone(gate(conn, self.pet, self.clock.now), "还没人说过什么，此刻不该有拦路的承诺")
            self.stay_home()
            self.assertEqual(gate(conn, self.pet, self.clock.now), OWNER_ASKED_STAY_HOME,
                             "说过之后要认得出来，而且给的是种类名、不是主人的原话")

    def test_without_the_message_the_rule_engine_really_does_go_out(self) -> None:
        """对照组。这一条要是红了，下面两条的"没出门"就毫无意义。"""
        self.web.life.run(self.clock.now)

        self.assertTrue(self.went_out(), "前提不成立：这一轮本来就不会出门，那“被拦住”就证明不了什么")

    def test_the_owner_asking_to_stay_home_stops_the_rule_engine(self) -> None:
        self.stay_home()

        self.web.life.run(self.clock.now)

        self.assertFalse(self.went_out(), "主人说了今天别出门，规则生活不该还把 TA 送出门")

    def test_the_brain_cannot_override_the_owner_asking_to_stay_home(self) -> None:
        """模型这条路也要认这道闸：**它挑了一个地方，仍然出不去**。

        这里有意让模型**明确选中**一个目的地——若只是它自己决定留在家，那就不是闸的功劳。
        """
        self.let_the_brain_choose("local:cafe")
        self.stay_home()

        outcome = self.web.brain_life.consider(self.pet, self.clock.now)

        self.assertFalse(self.went_out(), "模型选了地方，但主人说了别出门：不该出得去")
        self.assertEqual((outcome.status, outcome.reason), ("rejected", "commitment_active"),
                         "要记成一次明确的“这回没出成”，并写明原因；不是崩溃、也不是“TA 决定留在家”")

    def test_asking_a_question_does_not_lock_the_pet_in_for_half_a_day(self) -> None:
        """**问一句话不是下指令。** 这四句都不该让 TA 半天不能自己出门（I 2026-09-24 裁定：词表只留祈使式）。

        为什么这条放在接线这一层、而不是只验词表：**误判的代价是在这一层才出现的**。
        接线之前它只走 `life.py:269` 的 `chance *= 0.15`（软偏好，仍有约一成会出门，没人会注意）；
        接线之后是**硬闸，12 小时内一切自主出门被拒**。同一个误判，
        后果从「今天少出去几次」变成「半天不能动」——而且撞产品前提：宠物自主、主人只建议。

        最后一句是 I 给的，比前三句更强：**它的意思恰恰是要出门**，
        判定却把它读成相反的意思。前三句是「判宽了」，它是「判反了」。

        `今天在家做了蛋糕` 是 Q 补的，它证明**「排除疑问句」这条修法不够**：它是陈述句、照样命中。
        真正的毛病是**主语错位**——那几个词条描述的是「谁在家」，不是「禁止 TA 出门」，
        而一半以上的误命中是**主人在说自己**。所以裁定是把这类词条整条去掉，不是再加一层判断。

        `今天别出门了` 那条正例对照在下一个用例里，别删——
        没有它，这些全绿也可能只是因为闸整个不工作了。
        """
        for text in ("今天在家吗", "今天在家吗？我带了点心回来", "我今天休息，陪你玩",
                     "我们今天休息一下再出发", "今天在家做了蛋糕", "我待在家里想你"):
            with self.subTest(text=text):
                self.setUp()  # 每句话各用一只干净的宠物，免得上一句的 12 小时窗口盖住这一句
                self.say(text)
                self.web.life.run(self.clock.now)
                self.assertTrue(self.went_out(), f"「{text}」不是「别出门」，不该关掉 TA 半天的自主权")

    def test_a_real_instruction_still_blocks(self) -> None:
        """上一条的正例对照：**祈使式仍然要拦住**。

        没有这一条，上面四句「还能出门」可能只是因为闸整个失效了。
        """
        self.stay_home()

        self.web.life.run(self.clock.now)

        self.assertFalse(self.went_out(), "「今天别出门了」是明确的叮嘱，仍然要认")

    def test_the_owner_clicking_depart_is_not_blocked(self) -> None:
        """合同 15 节裁定：**主人自己点「出发」一律不拦**——主人改主意了，拦他没道理。

        这一条同时是上面那些的反向对照：证明闸是**按来路**分的，
        不是把这只宠物整个锁住了。
        """
        self.stay_home()

        self.owner.post("/journey/depart", {"destination_key": "local:cafe"})

        self.assertTrue(self.went_out(), "主人自己点的出发不该被自己先前那句话拦住")


if __name__ == "__main__":
    unittest.main()
