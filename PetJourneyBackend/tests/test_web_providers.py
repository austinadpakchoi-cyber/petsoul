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

    def test_model_replies_are_on_by_default_grounded_and_labelled(self) -> None:
        """2026-09-24 起模型回信默认开启（用户：聊天都是固定的、ds 没参与）。原先这条钉的是「默认关闭、需主人开启」。

        先读一次会话：真实页面一打开就会读，它会替没改过设置的人建出偏好行——第一版修复正是栽在这里
        （建行落到列默认值 0，这条的「默认关闭」照样绿）。叮嘱的取舍、关掉即停这两条保护不变。
        """
        chat = FakeChat(["妈妈，我在阳台晒太阳，毯子暖暖的。"])
        self.install(chat=chat)
        owner = self.user("chat-model")
        owner.pet_id = owner.upload_pet("年糕", "cat").json()["pet_id"]
        self.confirm(owner, "叫我妈妈就好。它最喜欢那条蓝色的毯子。", "它小时候走丢过一次，别告诉它。")
        owner.move_in()
        self.assertTrue(owner.get("/session").json()["authenticated"])
        settings = owner.get("/settings").json()
        self.assertTrue(settings["model_replies"], "默认开启，读过会话之后也还是开启")
        self.assertTrue(settings["model_replies_available"])
        self.assertEqual(settings["model_provider"], "测试模型")
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-model-0001", "text": "想你啦"})
        self.assertEqual(len(chat.calls), 1, "没选过的主人，第一条就由模型写")
        prompt = json.dumps(chat.calls[-1], ensure_ascii=False)
        self.assertIn("妈妈", prompt, "使用确认过的称呼")
        self.assertIn("蓝色的毯子", prompt, "使用允许私密通讯的叮嘱")
        self.assertNotIn("走丢", prompt, "只留在这里的私密内容不进入模型")
        self.assertFalse(owner.patch("/settings", {"model_replies": False}).json()["model_replies"])
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-template-1", "text": "在干嘛"})
        self.assertEqual(len(chat.calls), 1, "关掉之后不再调用模型")
        self.clock.advance(seconds=25)
        items = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        pet_replies = [m for m in items if m["sender"] == "pet"]
        self.assertEqual([m["composed_by"] for m in pet_replies], ["model", "template"])
        self.assertEqual(pet_replies[0]["text"], "妈妈，我在阳台晒太阳，毯子暖暖的。")

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
        # 这一句**已经不是"开启授权"了**（逐次询问 2026-09-23 取消，开不开都会生成），
        # 但留着它有用：它现在验的是**旧设置 API 兼容**——旧客户端仍会发
        # `PATCH /settings {"generated_photos": …}`，服务端必须照常接受并回显，不能 422。
        # 方法名里的 `opt_in` 是历史遗留；这条没红，本轮不改名，以免打断别处对它的引用。
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
        self.assertIn("Any signs or screens are blank", illustrator.prompts[-1])
        self.assertNotIn("小岚", illustrator.prompts[-1])
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

    # ---- 生不出图时一次都不调：触发条件换过一次，原名 `test_no_illustration_without_opt_in` ----
    #
    # 这条原先靠「主人没开启 `generated_photos`」制造"不生图"。用户 2026-09-23 决定
    # **取消 AI 生图的逐次授权询问**（角色与生活/旅行两类都取消，见
    # `CR-GENERATED-PHOTOS-AUTOMATIC-2026-09-23.md`），那道开关连同组合根的接线已摘除——
    # 「没开启」这个状态**不再存在**。所以 `photo_status` 现在是 `processing`，
    # **那是正确的新行为，红的是这条断言本身**（A 在冻结版本上把它归为"产品规则变化后的旧断言"，
    # 实现回归 0；这份文件归 I，由我更新）。
    #
    # **但它真正钉的规则没变，而且那条规则不是"没有图"**：三句断言合起来钉的是
    # **不该生图的时候，一次供应商调用都不发生**——`run_pending()` 返回 0、`prompts` 为空。
    # 那是**费用保护**：生图按张计费，多调一次就是多一笔真实费用。
    # 所以触发条件换成**供应商不可用**——取消询问之后仍然存在、而且更常见的一种"不该生图"。
    #
    # 明信片那条链路的同一条规则在
    # `test_web_agent_media.py::test_without_a_provider_the_postcard_is_words_only`；
    # 这里走的是**冒险插画**，两条是不同链路，不重复。
    def adventure_with_provider(self, tag: str, candidate: str, *, available: bool) -> dict:
        """跑一趟冒险，回报三个落点。**只拨 `available` 这一个开关**。

        `IllustrationService.available()` 读的就是这个属性（`illustrations.py:98`）。

        **两趟得用不同的居民**：领养是一次性的（同一个候选第二次会 `ADOPTION_TAKEN`，
        「每一位只能进一个家庭」）。所以严格说两趟不是**完全**相同的条件——
        但两位都是 cat（`adopt-lan` 小岚 / `adopt-mochi` 麻薯）、走同一条冒险、
        同一套假供应商，差别不落在被观测的三个点上。
        """
        illustrator = FakeIllustrator()
        illustrator.available = available
        self.install(illustrator=illustrator)
        owner = self.user(f"hero-provider-{tag}")
        owner.adopt_and_move_in(candidate)
        self.cafe_adventure(owner)
        status = self.adventure_message(owner)["photo_status"]
        handled = self.web.illustrations.run_pending()  # 先跑，再数提示词
        return {"photo_status": status, "handled": handled, "calls": len(illustrator.prompts)}

    def test_a_down_provider_yields_no_illustration_and_no_call(self) -> None:
        """**正负对照**：同一条路径只拨供应商可用性，三个落点各自翻面。

        为什么不是"设成不可用、断言三个都是空"：那样**三句断言同因**
        （可用→排队→调用），一个反例只能证明"整体在承重"，分不开哪一句在管什么。
        正负对照能让每个落点各自显示差异。

        **正例必须非零**，否则那一格的"翻面"是假的——一个本来就是 0 的落点，
        断言它在负例里是 0，跟没测一样。所以下面先把三个正例前提断言掉。
        """
        up = self.adventure_with_provider("up", "adopt-lan", available=True)
        down = self.adventure_with_provider("down", "adopt-mochi", available=False)

        self.assertEqual(up["photo_status"], "processing", "正例前提：供应商在，这次确实要生成")
        self.assertGreater(up["handled"], 0, "正例前提：确实排进了任务，否则下面那句 0 没有意义")
        self.assertGreater(up["calls"], 0, "正例前提：确实调过供应商，否则下面那句 0 没有意义")

        self.assertIsNone(down["photo_status"], "生不出图就如实没有，不拿别的冒充")
        self.assertEqual(down["handled"], 0, "不该生成时连任务都不排")
        self.assertEqual(down["calls"], 0, "供应商不可用就一次都不该调它——生图按张计费")


if __name__ == "__main__":
    unittest.main()
