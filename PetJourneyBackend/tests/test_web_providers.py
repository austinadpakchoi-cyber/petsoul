"""真实供应商接入（全部用假实现，不触网）：真实地点与路线估时、模型回信、接待模型回应、冒险插画任务。"""

from __future__ import annotations

import json
import unittest

from app.web_providers import ChatUnavailable, WebProviders
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import REAL_CAFE, FakeChat, FakeGeo, FakeIllustrator


class ProviderIntegrationTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)

    def install(self, *, chat=None, geo=None, illustrator=None) -> None:
        web = self.web
        web.providers = WebProviders(enabled=True, chat=chat or web.providers.chat, geo=geo, illustrator=illustrator or web.providers.illustrator, meter=None)
        web.journeys.geo = geo
        web.communicator.chat = web.providers.chat
        web.reception.chat = web.providers.chat
        web.illustrations.illustrator = web.providers.illustrator

    # ---- 地图 ----
    def test_departure_uses_real_cafe_and_routed_estimates(self) -> None:
        geo = FakeGeo(place=REAL_CAFE, minutes=8)
        self.install(geo=geo)
        owner = self.user("geo-owner")
        owner.adopt_and_move_in("adopt-lan")
        snapshot = owner.post("/journey/depart", {"destination_key": "harbour_cafe"}).json()
        outbound, back = snapshot["legs"][0], snapshot["legs"][-1]
        self.assertEqual(outbound["destination"]["name"], REAL_CAFE.name)
        self.assertEqual(back["origin"]["name"], REAL_CAFE.name)
        self.assertEqual(outbound["time_basis"], "routed_estimate")
        self.assertEqual(outbound["freshness"], "verified")
        self.assertEqual(len(outbound["route"]), 3, "真实道路几何替换示意线")
        self.clock.advance(minutes=8)
        visit = owner.get(f"/visits/{owner.get('/journey/map').json()['current_visit_id']}").json()
        self.assertEqual(visit["place"]["provider"], "amap")
        self.assertEqual(visit["place"]["attribution"], "地点资料：高德地图")
        self.assertEqual(visit["place"]["address"], REAL_CAFE.address)
        self.assertTrue(visit["interior_is_original"], "店内仍是原创场景")

    def test_geo_failure_falls_back_to_demo_honestly(self) -> None:
        self.install(geo=FakeGeo(fail=True))
        owner = self.user("geo-fail")
        owner.adopt_and_move_in("adopt-lan")
        response = owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(response.status_code, 200, response.text)
        leg = response.json()["legs"][0]
        self.assertEqual(leg["time_basis"], "demo_fixture")
        self.assertIn("示例", leg["destination"]["name"])

    def test_ferry_and_flight_stay_demo_while_road_legs_are_estimated(self) -> None:
        self.install(geo=FakeGeo(place=None))
        owner = self.user("geo-ferry")
        owner.adopt_and_move_in("adopt-lan")
        self.web.economy.apply(owner.pet_id, 40, __import__("app.schemas", fromlist=["EconomyTransactionType"]).EconomyTransactionType.web_reward,
                               "test:ferry-fund", reason="测试", source="test")
        legs = owner.post("/journey/depart", {"destination_key": "macau_ferry"}).json()["legs"]
        by_mode = {(l["mode"], l["kind"]): l["time_basis"] for l in legs}
        self.assertEqual(by_mode[("taxi", "connection")], "routed_estimate")
        self.assertEqual(by_mode[("ferry", "main")], "demo_fixture", "没有核验时刻表的轮渡不标估时")

    # ---- 模型回信 ----
    def confirm(self, owner, text: str, private_text: str | None = None) -> None:
        session = owner.post("/reception/sessions", {"pet_id": owner.pet_id, "branch": "own_pet"}).json()
        full = text + (private_text or "")
        session = owner.post(f"/reception/sessions/{session['session_id']}/turns", {"text": full, "expected_revision": session["draft_revision"]}).json()
        decisions = []
        for c in session["candidates"]:
            if c["kind"] == "owner_private":
                decisions.append({"candidate_id": c["candidate_id"], "text": c["text"], "target": "keep_here", "purposes": []})
            else:
                decisions.append({"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": ["private_chat", "home_interaction"],
                                  "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]})
        owner.post("/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions})

    def test_model_replies_are_opt_in_grounded_and_labelled(self) -> None:
        chat = FakeChat(["妈妈，我在阳台晒太阳，毯子暖暖的。"])
        self.install(chat=chat)
        owner = self.user("chat-model")
        owner.pet_id = owner.upload_pet("年糕", "cat").json()["pet_id"]
        self.confirm(owner, "叫我妈妈就好。它最喜欢那条蓝色的毯子。", "它小时候走丢过一次，别告诉它。")
        owner.move_in()
        settings = owner.get("/settings").json()
        self.assertFalse(settings["model_replies"], "默认关闭")
        self.assertTrue(settings["model_replies_available"])
        self.assertEqual(settings["model_provider"], "测试模型")
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-template-1", "text": "在干嘛"})
        self.assertEqual(chat.calls, [], "未开启时不调用模型")
        self.assertTrue(owner.patch("/settings", {"model_replies": True}).json()["model_replies"])
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-model-0001", "text": "想你啦"})
        prompt = json.dumps(chat.calls[-1], ensure_ascii=False)
        self.assertIn("妈妈", prompt, "使用确认过的称呼")
        self.assertIn("蓝色的毯子", prompt, "使用允许私密通讯的叮嘱")
        self.assertNotIn("走丢", prompt, "只留在这里的私密内容不进入模型")
        self.clock.advance(seconds=25)
        items = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        pet_replies = [m for m in items if m["sender"] == "pet"]
        self.assertEqual([m["composed_by"] for m in pet_replies], ["template", "model"])
        self.assertEqual(pet_replies[-1]["text"], "妈妈，我在阳台晒太阳，毯子暖暖的。")

    def test_model_failure_or_bad_output_falls_back_to_template(self) -> None:
        owner = self.user("chat-fallback")
        owner.adopt_and_move_in("adopt-lan")
        owner.patch("/settings", {"model_replies": True})
        self.install(chat=FakeChat(error=ChatUnavailable("network")))
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-fail-00001", "text": "在吗"})
        self.install(chat=FakeChat(["作为一个AI，我不能……"]))
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-fail-00002", "text": "在吗"})
        self.install(chat=FakeChat(["看这个 https://example.com"]))
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-fail-00003", "text": "在吗"})
        self.clock.advance(seconds=25)
        replies = [m for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if m["sender"] == "pet"]
        self.assertEqual({m["composed_by"] for m in replies}, {"template"})

    # ---- 接待 ----
    def test_reception_model_follow_up_is_opt_in_and_notes_stay_verbatim(self) -> None:
        chat = FakeChat(["听起来它很会撒娇呢。它平时最喜欢窝在哪里？"])
        self.install(chat=chat)
        owner = self.user("reception-model")
        owner.pet_id = owner.upload_pet("汤圆", "cat").json()["pet_id"]
        guided = owner.post("/reception/sessions", {"pet_id": owner.pet_id, "branch": "own_pet"}).json()
        self.assertEqual(guided["mode"], "guided_notes", "没有选择就不用模型")
        owner.post(f"/reception/sessions/{guided['session_id']}/skip")
        other = self.user("reception-model-2")
        other.pet_id = other.upload_pet("麻团", "cat").json()["pet_id"]
        session = other.post("/reception/sessions", {"pet_id": other.pet_id, "branch": "own_pet", "use_model": True}).json()
        self.assertEqual(session["mode"], "model_conversation")
        self.assertIn("测试模型", session["host"]["disclosure"])
        text = "叫我姐姐就好。它最喜欢那条蓝色的毯子。"
        session = other.post(f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]}).json()
        host = session["turns"][-1]
        self.assertEqual(host["composed_by"], "model")
        self.assertEqual(host["text"], "听起来它很会撒娇呢。它平时最喜欢窝在哪里？")
        self.assertTrue(all(c["source_excerpt"] in text for c in session["candidates"]), "便笺仍只摘录原话")
        self.install(chat=FakeChat(error=ChatUnavailable("timeout")))
        session = other.post(f"/reception/sessions/{session['session_id']}/turns", {"text": "它不喜欢被抱。", "expected_revision": session["draft_revision"]}).json()
        self.assertEqual(session["turns"][-1]["composed_by"], "guided", "模型不可用时回到固定引导")

    # ---- 冒险插画 ----
    def cafe_adventure(self, owner) -> str:
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)
        return visit_id

    def adventure_message(self, owner) -> dict:
        return next(m for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if "咖啡馆小侦探" in m["text"])

    def test_illustration_is_opt_in_async_private_and_retryable(self) -> None:
        illustrator = FakeIllustrator(fail_reason="provider_error")
        self.install(illustrator=illustrator)
        owner = self.user("hero-owner")
        owner.adopt_and_move_in("adopt-lan")
        self.assertTrue(owner.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.cafe_adventure(owner)
        message = self.adventure_message(owner)
        self.assertEqual((message["photo_status"], message["state"]), ("processing", "processing"))
        self.assertTrue(any(b["kind"] == "badge" for b in owner.get("/collection").json()), "勋章由规则结算，不等生图")
        self.web.illustrations.run_pending()  # 第一次失败 → 60 秒后重试
        self.clock.advance(seconds=61)
        self.web.illustrations.run_pending()  # 第二次失败 → 用尽重试
        message = self.adventure_message(owner)
        self.assertEqual((message["photo_status"], message["state"]), ("failed", "failed"))
        illustrator.fail_reason = None
        retried = owner.post(f"/communicator/{owner.pet_id}/messages/{message['message_id']}/retry-photo")
        self.assertEqual(retried.status_code, 200, retried.text)
        self.web.illustrations.run_pending()
        message = self.adventure_message(owner)
        self.assertEqual(message["photo_status"], "ready")
        self.assertTrue(message["photo_url"].startswith("/api/v1/web/media/illustrations/"))
        self.assertIn("No text", illustrator.prompts[-1])
        self.assertIn("小岚", illustrator.prompts[-1])
        self.assertEqual(owner.get(message["photo_url"].removeprefix("/api/v1/web")).status_code, 200)
        stranger = self.user("hero-stranger")
        self.assertEqual(stranger.client.get(message["photo_url"]).status_code in (401, 404, 409), True, "插画只给主人")
        # 已经画好的：对象还在，所以回当前状态（200），**不是 404**——404 留给"根本找不到这件东西"。
        # 关键是不能有副作用：不新建尝试、不再调一次替身、状态仍然是 ready。
        calls_before = len(illustrator.prompts)
        done = owner.post(f"/communicator/{owner.pet_id}/messages/{message['message_id']}/retry-photo")
        self.assertEqual(done.status_code, 200, done.text)
        self.web.illustrations.run_pending()
        self.assertEqual(len(illustrator.prompts), calls_before, "已经画好的不会再发起一次替身调用")
        self.assertEqual(self.adventure_message(owner)["photo_status"], "ready", "状态也没被改动")

    def test_no_illustration_without_opt_in(self) -> None:
        illustrator = FakeIllustrator()
        self.install(illustrator=illustrator)
        owner = self.user("hero-optout")
        owner.adopt_and_move_in("adopt-lan")
        self.cafe_adventure(owner)
        message = self.adventure_message(owner)
        self.assertIsNone(message["photo_status"])
        self.assertEqual(self.web.illustrations.run_pending(), 0)
        self.assertEqual(illustrator.prompts, [])


if __name__ == "__main__":
    unittest.main()
