"""宠物自主世界第一阶段：宠物 DNA、按 TA 的状态决定何时回复（睡着/飞行/危机/先后顺序）、主动消息与世界定时器。

全部用假时钟与假模型，不触网。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, time, timedelta, timezone

from app.schemas import EconomyTransactionType
from app.schemas.web.social import MessageTopic
from app.web_agent.proactive import night_owl, ping_times, pings_per_day
from app.web_agent.ticker import WorldTicker
from app.web_providers import WebProviders
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat

HK_2AM = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)  # 香港 9/23 02:00


class AgentTestBase(WebPlatformTestBase):
    start = LUNCH_UTC

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(self.start).install(self)

    def owner(self, name: str, candidate: str = "adopt-lan"):
        owner = self.user(name)
        owner.adopt_and_move_in(candidate)
        owner.get("/session")  # 主人来过
        return owner

    def items(self, owner) -> list[dict]:
        return owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]

    def send(self, owner, cid: str, text: str) -> dict:
        response = owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": cid, "text": text})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, owner, text: str) -> None:
        """走一遍接待：主人交代的内容全部交给 TA（私信与家园可用）。"""
        session = owner.post("/reception/sessions", {"pet_id": owner.pet_id, "branch": "own_pet"}).json()
        session = owner.post(f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]}).json()
        decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": ["private_chat", "home_interaction"],
                      "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]} for c in session["candidates"] if c["kind"] != "owner_private"]
        owner.post("/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions})

    def use_model(self, owner, replies: list[str]) -> FakeChat:
        chat = FakeChat(replies)
        web = self.web
        web.providers = WebProviders(enabled=True, chat=chat, geo=None, illustrator=web.providers.illustrator, meter=None)
        web.communicator.chat = chat
        owner.patch("/settings", {"model_replies": True})
        return chat


class PetDNATests(AgentTestBase):
    def test_draft_then_owner_confirms_and_persona_reads_it(self) -> None:
        owner = self.owner("dna-owner")
        draft = owner.get(f"/pets/{owner.pet_id}/dna").json()
        self.assertFalse(draft["confirmed"], "没保存过是草稿")
        self.assertIn("adoption_profile", draft["draft_sources"])
        self.assertTrue(draft["dna"]["personality"], "领养伙伴的性格进入草稿")
        saved = owner.put(f"/pets/{owner.pet_id}/dna", {
            "owner_title": "姐姐", "nicknames": ["团子", "团子", "  "], "catchphrase": "咕噜咕噜", "favorite_foods": ["冻干鸡肉"],
            "habits": ["睡觉要压着姐姐的拖鞋"], "shared_memories": ["每次姐姐回家都要先蹭三下"],
        }).json()
        self.assertTrue(saved["confirmed"])
        self.assertEqual(saved["dna"]["nicknames"], ["团子"], "去重、去空白")
        stranger = self.owner("dna-stranger", "adopt-pudding")
        self.assert_envelope(stranger.get(f"/pets/{owner.pet_id}/dna"), 404, "NOT_FOUND")
        self.assert_envelope(stranger.put(f"/pets/{owner.pet_id}/dna", {"owner_title": "坏人"}), 404, "NOT_FOUND")

        chat = self.use_model(owner, ["姐姐～我在呢，咕噜咕噜。"])
        self.send(owner, "dna-msg-0001", "在干嘛呀")
        prompt = json.dumps(chat.calls[-1], ensure_ascii=False)
        for fact in ("姐姐", "团子", "咕噜咕噜", "冻干鸡肉", "拖鞋", "蹭三下"):
            self.assertIn(fact, prompt)
        self.assertIn("原创伙伴", prompt, "领养伙伴不套用“已离开”的说法")
        self.clock.advance(seconds=25)
        reply = [m for m in self.items(owner) if m["sender"] == "pet"][-1]
        self.assertEqual((reply["text"], reply["composed_by"]), ("姐姐～我在呢，咕噜咕噜。", "model"))

    def test_dna_draft_is_what_the_owner_told_at_registration(self) -> None:
        owner = self.user("dna-register")
        owner.pet_id = owner.upload_pet("年糕", "dog").json()["pet_id"]
        self.confirm(owner, "叫我妈妈就好。它最喜欢那条蓝色的毯子。它每天早上都要叼着拖鞋来叫我起床。")
        owner.move_in()
        draft = owner.get(f"/pets/{owner.pet_id}/dna").json()
        self.assertFalse(draft["confirmed"])
        self.assertIn("reception_notes", draft["draft_sources"])
        self.assertEqual(draft["dna"]["owner_title"], "妈妈")
        self.assertTrue(any("毯子" in h for h in draft["dna"]["hobbies"] + draft["dna"]["habits"]), draft["dna"])

    def test_own_pet_frame_and_missing_is_comfort_not_coming_home(self) -> None:
        owner = self.user("dna-own")
        owner.pet_id = owner.upload_pet("年糕", "dog").json()["pet_id"]
        owner.move_in()
        owner.get("/session")
        self.web.intent.mode = __import__("app.schemas.web.intent", fromlist=["IntentLayerMode"]).IntentLayerMode.assist
        chat = self.use_model(owner, ["我也想你呀，我在这边很好。"])
        self.send(owner, "own-msg-0001", "好想你")
        system = chat.calls[-1][0]["content"]
        self.assertIn("不在同一个世界", system)
        self.assertIn("情绪上的慰藉", system)
        self.assertIn("不要说要回去", system)


class ReplyTimingTests(AgentTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    start = HK_2AM

    def test_asleep_messages_queue_and_get_one_reply_after_waking(self) -> None:
        owner = self.owner("sleepy")
        first = self.send(owner, "night-0001", "睡了吗")
        self.assertEqual(first["state"], "awaiting_reply")
        self.assertEqual(first["status_note"], "TA 睡着啦，醒来会看到。")
        expected = datetime.fromisoformat(first["expected_reply_at"])
        self.assertEqual(expected.astimezone(timezone(timedelta(hours=8))).hour, 7, "香港早上醒来后回复")
        self.clock.advance(minutes=30)
        self.send(owner, "night-0002", "晚安")
        self.assertEqual([m["sender"] for m in self.items(owner)], ["owner", "owner"], "睡着时不回")
        self.clock.now = expected + timedelta(minutes=1)
        items = self.items(owner)
        self.assertEqual([m["sender"] for m in items], ["owner", "owner", "pet"], "两条合并成一次回复")
        self.assertTrue(items[-1]["text"].startswith("刚睡醒"))
        self.assertEqual({m["state"] for m in items if m["sender"] == "owner"}, {"delivered"})
        self.assertIsNone(items[0]["status_note"], "回复后不再显示等待说明")

    def test_distress_is_answered_immediately_with_help_lines(self) -> None:
        owner = self.owner("distress")
        self.send(owner, "hurt-0001", "我真的撑不下去了，想去找你")
        self.clock.advance(seconds=5)
        reply = [m for m in self.items(owner) if m["sender"] == "pet"]
        self.assertEqual(len(reply), 1, "情绪危机不等 TA 醒来")
        self.assertIn("2389 2222", reply[0]["text"])
        self.assertIn("12356", reply[0]["text"])

    def test_ticker_delivers_queued_reply_without_anyone_reading(self) -> None:
        owner = self.owner("ticker")
        sent = self.send(owner, "tick-0001", "晚安呀")
        self.clock.now = datetime.fromisoformat(sent["expected_reply_at"]) + timedelta(seconds=1)
        self.tick_all(self.clock.now)  # 到点的排队回复在认知线（与世界线分开的线程和租约）
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM web_messages WHERE pet_id = ? AND sender = 'pet' AND reply_to IS NOT NULL", (owner.pet_id,)).fetchone()
        self.assertEqual(row["n"], 1)


class ReplyOrderAndFlightTests(AgentTestBase):
    def test_replies_follow_send_order(self) -> None:
        owner = self.owner("order")
        for i in range(4):
            self.send(owner, f"order-000{i}", f"第{i}句")
        self.clock.advance(minutes=2)
        items = self.items(owner)
        pets = [m for m in items if m["sender"] == "pet"]
        self.assertEqual(len(pets), 4)
        times = [m["created_at"] for m in items]
        self.assertEqual(items[-1]["sender"], "pet")
        self.assertEqual(times, sorted(times))

    def test_in_flight_waits_until_landing(self) -> None:
        owner = self.owner("flyer")
        self.web.economy.apply(owner.pet_id, 200, EconomyTransactionType.web_reward, "test:flight-fund", reason="测试", source="test")
        legs = owner.post("/journey/depart", {"destination_key": "tokyo_flight"}).json()["legs"]
        flight = next(l for l in legs if l["mode"] == "flight" and l["kind"] == "main")
        self.clock.now = datetime.fromisoformat(flight["times"]["planned_departure_utc"]) + timedelta(minutes=30)
        sent = self.send(owner, "fly-0001", "飞到哪了")
        self.assertEqual(sent["status_note"], "TA 在飞机上，落地后会看到。")
        landing = datetime.fromisoformat(flight["times"]["planned_arrival_utc"])
        self.assertGreaterEqual(datetime.fromisoformat(sent["expected_reply_at"]), landing)
        self.clock.now = landing - timedelta(minutes=1)
        mine = next(m for m in self.items(owner) if m["message_id"] == sent["message_id"])
        self.assertEqual(mine["state"], "awaiting_reply", "落地前不回")


class ProactiveTests(AgentTestBase):
    HK = timezone(timedelta(hours=8))

    def first_ping(self, owner, day) -> datetime:
        persona = self.web.proactive.persona_of(owner.user_id, owner.pet_id)
        t = ping_times(owner.pet_id, day, pings_per_day(persona), owl=night_owl(persona))[0]
        return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=self.HK).astimezone(timezone.utc) + timedelta(minutes=1)

    def test_pings_at_random_moments_once_each_and_respect_opt_out(self) -> None:
        owner = self.owner("pinger")
        day = (self.clock.now + timedelta(days=1)).astimezone(self.HK).date()
        self.clock.now = self.first_ping(owner, day)
        owner.get("/session")
        self.clock.now += timedelta(minutes=31)  # 主人刚来过不算“正在聊天”
        self.assertEqual(self.web.proactive.run(self.clock.now), 1)
        self.assertEqual(self.web.proactive.run(self.clock.now + timedelta(minutes=5)), 0, "同一时刻只发一次")
        ping = self.items(owner)[-1]
        self.assertEqual((ping["sender"], ping["composed_by"]), ("pet", "template"))
        self.assertIn(ping["topic"], {"morning", "share", "goodnight"})
        owner.patch("/settings", {"pet_messages": False})
        self.assertFalse(self.web.proactive.share_news(owner.user_id, owner.pet_id, self.clock.now, "e1", "刚把偷菜的赶跑了"), "主人关闭后不再主动发")

    def test_news_can_arrive_while_owner_sleeps_but_daily_cap_holds(self) -> None:
        owner = self.owner("night-news")
        self.clock.now = HK_2AM
        self.assertTrue(self.web.proactive.share_news(owner.user_id, owner.pet_id, self.clock.now, "steal-1", "刚才有只小狐狸来偷菜，被我吓跑啦"))
        self.assertFalse(self.web.proactive.share_news(owner.user_id, owner.pet_id, self.clock.now, "steal-1", "重复"), "同一件事只说一次")
        news = self.items(owner)[-1]
        self.assertEqual((news["topic"], news["text"]), ("news", "刚才有只小狐狸来偷菜，被我吓跑啦"))
        sent = sum(self.web.proactive.share_news(owner.user_id, owner.pet_id, self.clock.now, f"e{i}", f"第{i}件事") for i in range(10))
        self.assertEqual(sent, 5, "每天最多 6 条")

    def test_missed_owner_gets_gentle_thinking_of_you_and_inactive_owner_none(self) -> None:
        owner = self.owner("missed")
        day = (self.clock.now + timedelta(days=3)).astimezone(self.HK).date()
        self.clock.now = self.first_ping(owner, day)
        self.assertEqual(self.web.proactive.run_one(owner.user_id, owner.pet_id, self.clock.now), MessageTopic.thinking_of_you)
        later = self.clock.now + timedelta(days=10)
        self.assertIsNone(self.web.proactive.due_ping(owner.user_id, owner.pet_id, later), "7 天以上没来就不再发")

    def test_chattiness_and_night_owl_come_from_dna(self) -> None:
        owner = self.owner("owl")
        owner.put(f"/pets/{owner.pet_id}/dna", {"personality": "活泼话多", "habits": ["爱熬夜看窗外"]})
        persona = self.web.proactive.persona_of(owner.user_id, owner.pet_id)
        self.assertEqual((pings_per_day(persona), night_owl(persona)), (3, True))
        day = self.clock.now.date()
        for t in ping_times(owner.pet_id, day, 30, owl=True):
            self.assertTrue(t >= time(7, 30) or t <= time(1, 30))

    def test_model_writes_proactive_in_pet_voice(self) -> None:
        owner = self.owner("proactive-model")
        chat = self.use_model(owner, ["早呀！我刚伸完懒腰。"])
        day = (self.clock.now + timedelta(days=1)).astimezone(self.HK).date()
        self.clock.now = self.first_ping(owner, day)
        owner.get("/session")
        self.clock.now += timedelta(minutes=31)
        self.web.proactive.run(self.clock.now)
        self.assertIn("主动发给主人", chat.calls[-1][0]["content"])
        self.assertEqual(self.items(owner)[-1]["composed_by"], "model")

    def test_settings_timezone_validation(self) -> None:
        owner = self.owner("tz-owner")
        self.assert_envelope(owner.patch("/settings", {"timezone": "Mars/Olympus"}), 422, "VALIDATION_FAILED")
        settings = owner.patch("/settings", {"timezone": "Asia/Tokyo"}).json()
        self.assertEqual((settings["timezone"], settings["pet_messages"]), ("Asia/Tokyo", True))


class TickerUnitTests(unittest.TestCase):
    def test_one_failing_job_does_not_stop_others(self) -> None:
        ran: list[str] = []

        def boom(now):
            raise RuntimeError("boom")

        ticker = WorldTicker([("a", boom), ("b", lambda now: ran.append("b"))], interval_seconds=0)
        ticker.tick(LUNCH_UTC)
        self.assertEqual(ran, ["b"])
        ticker.start()  # interval=0 表示关闭：不启动线程
        self.assertIsNone(ticker._thread)


if __name__ == "__main__":
    unittest.main()
