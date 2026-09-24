"""写实照片与邮局明信片（用户 2026-09-22：照片要写实，不把宠物卡通化；明信片是 TA 路过邮局寄给主人的）。假生图，不触网。"""

from __future__ import annotations

import json
import unittest

from app.web_providers import PlaceCandidate, WebProviders
from app.web_providers.geo import name_score
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat, FakeGeo, FakeIllustrator


class MediaTestBase(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        web = self.web
        web.providers = WebProviders(enabled=True, chat=web.providers.chat, geo=None, illustrator=self.illustrator, meter=None)
        web.illustrations.illustrator = self.illustrator
        self.owner = self.user("postcard-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def collection(self) -> list[dict]:
        return self.owner.get("/collection").json()

    def visit_id(self) -> str:
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()  # 任务进程写攻略（slow 通道）
        self.clock.advance(minutes=7)
        return self.owner.get("/journey/map").json()["current_visit_id"]



class RealisticMediaTests(MediaTestBase):
    def test_pet_mails_a_postcard_from_the_post_office_with_a_realistic_selfie(self) -> None:
        self.owner.patch("/settings", {"generated_photos": True})
        self.visit_id()
        self.clock.advance(minutes=30)  # 店里待完，回程路过邮局
        card = next(i for i in self.collection() if i["kind"] == "postcard")
        self.assertEqual((card["city"], card["image_status"]), ("香港", "processing"))
        self.assertTrue(card["note"] and card["place"])
        notes = [m["text"] for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]]
        self.assertTrue(any("邮局" in t for t in notes), notes)
        self.web.illustrations.run_pending()
        card = next(i for i in self.collection() if i["kind"] == "postcard")
        self.assertEqual(card["image_status"], "ready")
        self.assertTrue(card["image_url"].startswith("/api/v1/web/media/illustrations/"))
        prompt = self.illustrator.prompts[-1]
        for rule in ("写实摄影照片", "邮筒", "不是卡通", "不要出现人、人手或手机", "牌子和显示屏保持空白"):
            self.assertIn(rule, prompt)

    # ---- 生不出图时不冒充：触发条件换过一次，见下 ----
    #
    # 这两条原先靠「主人没开启 `generated_photos`」来制造"生不出图"。用户 2026-09-23 决定
    # **取消 AI 生图的逐次授权询问**（角色与生活/旅行两类都取消），那道开关连同接线已摘除，
    # 「没开启」这个状态**不再存在**——原样留着就是断言一个到不了的前提。
    #
    # **但这两条真正钉的产品规则没变**：生不出图的时候**如实说没有，不拿别的东西冒充**
    # （方案「不将照片框当作已完成的场景角色，也不拿通用猫代替」）。所以触发条件换成
    # **供应商不可用**——那是取消询问之后仍然存在、而且更常见的一种"生不出图"。
    def no_provider(self) -> None:
        """供应商不可用：`IllustrationService.available()` 读的就是这个属性（`illustrations.py:97`）。

        **先确认替身真的装在服务上。** 下面两条用例的核心断言是 `prompts == []`（一次都没调过），
        **而替身要是根本没装上去，`prompts` 也永远是空——断言恒真、什么都不测、还照样绿**。
        `setUp` 里那行 `web.illustrations.illustrator = self.illustrator` 是**只写没读**的：
        属性哪天改了名，赋值会悄悄挂到一个新属性上，不报错。

        这个前提以前只写在注释里（「文件级有别的用例会 `prompts[-1]` 炸」）——
        **那是可读、不是可执行**：救它的是**别的测试方法**，单跑这一条时没有任何东西会响。
        改成断言之后，破了就炸在这一行，而不是变成「某条用例悄悄不再测东西」。
        """
        assert self.web.illustrations.illustrator is self.illustrator, \
            "替身没装在 IllustrationService 上：prompts 会恒为空，下面的断言将失去意义"
        self.illustrator.available = False

    def test_without_a_provider_the_postcard_is_words_only(self) -> None:
        self.no_provider()
        self.visit_id()
        self.clock.advance(minutes=30)
        card = next(i for i in self.collection() if i["kind"] == "postcard")
        self.assertIsNone(card["image_status"])
        self.assertIsNone(card["image_url"])
        self.assertTrue(card["note"], "图生不出来，话还是要写——明信片本身不该消失")
        self.assertEqual(self.illustrator.prompts, [], "供应商不可用就一次都不该调它")

    def test_cafe_photo_is_a_realistic_photo_task_or_an_honest_paper_card(self) -> None:
        self.no_provider()
        visit_id = self.visit_id()
        photo = next(a for a in self.owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "take_photo")
        done = self.owner.post(f"/visits/{visit_id}/actions", {"activity_id": photo["activity_id"]}).json()
        text = next(a for a in done["activities"] if a["kind"] == "take_photo")["result_text"]
        self.assertIn("没有照片", text, "生不出照片时：纸质卡片，不冒充照片")
        card = next(m for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"] if "纸质卡片" in m["text"])
        svg = self.owner.get(card["photo_url"].removeprefix("/api/v1/web")).text
        self.assertNotIn("<circle cx=\"400\" cy=\"200\" r=\"70\"", svg, "卡片上不画卡通动物")

    def test_companion_without_photo_gets_one_realistic_portrait_reused_as_reference(self) -> None:
        self.owner.patch("/settings", {"generated_photos": True})
        self.visit_id()
        self.clock.advance(minutes=30)
        self.web.illustrations.run_pending()
        portrait = [p for p in self.illustrator.prompts if "正面半身像" in p]
        self.assertEqual(len(portrait), 1, "先生成一张证件照")
        self.assertIn("必须是参考图里的同一只", self.illustrator.prompts[-1], "之后的照片以证件照为参考")
        pet = self.owner.home()["pet"]
        self.assertTrue(pet["photo_generated"])
        self.assertTrue(pet["photo_url"])

    def test_adventure_pictures_are_photorealistic_not_cartoon(self) -> None:
        self.owner.patch("/settings", {"generated_photos": True})
        visit_id = self.visit_id()
        greet = next(a for a in self.owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        self.owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.web.illustrations.run_pending()
        prompt = self.illustrator.prompts[-1]
        self.assertIn("Photorealistic", prompt)
        self.assertIn("Not a cartoon", prompt)
        self.assertNotIn("picture-book", prompt)

    def test_daily_strolls_do_not_send_postcards(self) -> None:
        self.owner.post("/journey/depart", {"destination_key": "local:stroll"})
        self.clock.advance(hours=2)
        self.assertEqual([i for i in self.collection() if i["kind"] == "postcard"], [])


class TravelGuideTests(MediaTestBase):
    GUIDE = json.dumps({"title": "港岛慢慢走", "summary": "喝杯咖啡再看海。", "owner_tips": ["带把伞"],
                        "stops": [{"name": "示例·海边咖啡馆（演示店）", "time": "上午", "why": "我爱晒太阳", "tip": "以现场为准"},
                                  {"name": "卜公码头", "time": "中午", "why": "能看船", "tip": "注意防晒"},
                                  {"name": "不存在的秘密花园", "time": "傍晚", "why": "听说很美", "tip": "以现场为准"}]}, ensure_ascii=False)

    def use_chat(self, reply: str) -> FakeChat:
        chat = FakeChat([reply])
        self.web.guides.chat = chat
        self.owner.patch("/settings", {"model_replies": True})
        return chat

    def test_pet_writes_a_guide_and_every_stop_is_checked_on_the_map(self) -> None:
        geo = FakeGeo()
        geo.known = {"卜公码头": PlaceCandidate(provider="amap", place_id="amap:B0PIER", name="卜公码头", address="中环海滨", lat=22.285, lng=114.16,
                                                 category="景点", attribution="地点资料：高德地图")}
        self.web.guides.geo = geo
        chat = self.use_chat(self.GUIDE)
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(self.owner.get("/guides").json(), [], "出发请求不等模型写攻略")
        self.run_background()
        self.assertIn("第一站必须是", chat.calls[-1][0]["content"])
        guides = self.owner.get("/guides").json()
        self.assertEqual(len(guides), 1)
        guide = guides[0]
        self.assertEqual((guide["title"], guide["composed_by"]), ("港岛慢慢走", "model"))
        stops = {s["name"]: s for s in guide["stops"]}
        self.assertTrue(stops["卜公码头"]["verified"])
        self.assertEqual(stops["卜公码头"]["address"], "中环海滨")
        self.assertFalse(stops["不存在的秘密花园"]["verified"])
        self.assertIsNone(stops["不存在的秘密花园"]["address"], "查不到的不编地址")
        self.assertEqual(stops["不存在的秘密花园"]["attribution"], "TA 听说的，未核实")
        self.assertEqual(self.owner.get(f"/guides/{guide['guide_id']}").json()["guide_id"], guide["guide_id"])
        notes = [m["text"] for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]]
        self.assertTrue(any("攻略" in t for t in notes), notes)

    def test_writing_a_guide_does_not_re_emit_departure(self) -> None:
        delivered: list[str] = []
        sink, lane = self.web.journeys.consumers["communicator"]

        class Counting:
            def on_world_event(self, event) -> None:
                delivered.append(event.key)
                sink.on_world_event(event)

        self.web.journeys.consumers["communicator"] = (Counting(), lane)
        self.use_chat(self.GUIDE)
        journey = self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"}).json()
        self.run_background()  # 写攻略会回头读状态，读状态又会补齐事件：出发事件也不能被再次投递
        self.run_background()
        self.assertEqual(delivered.count("departed"), 1, "出发事件只投递一次")
        with self.app.state.storage.connect() as conn:
            rows = conn.execute("SELECT consumer, status FROM web_outbox WHERE event_id = ?", (f"{journey['journey_id']}:departed",)).fetchall()
        self.assertEqual(sorted(r["consumer"] for r in rows), sorted(self.web.journeys.consumers), "每个下游只登记一行")
        self.assertEqual({r["status"] for r in rows}, {"delivered"})

    def test_map_check_only_accepts_places_whose_names_really_match(self) -> None:
        self.assertEqual(name_score("中山路", "中韦小海豚度假酒店一店(中山路地铁站店)"), 0, "不把街道核对成酒店")
        self.assertEqual(name_score("八大关风景区", "八大关风景区"), 3)
        self.assertEqual(name_score("青岛第二海水浴场", "青岛第二海水浴场(东门)"), 3)
        self.assertEqual(name_score("太平角公园", "青岛太平角公园"), 1)
        self.assertEqual(name_score("海边小屋民宿", "海边小屋民宿"), 3, "问的就是住处时可以")

    def test_template_guide_without_model_and_no_guide_for_a_stroll(self) -> None:
        self.owner.post("/journey/depart", {"destination_key": "local:stroll"})
        self.run_background()
        self.assertEqual(self.owner.get("/guides").json(), [], "散步不写攻略")
        self.clock.advance(hours=2)
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()
        guide = self.owner.get("/guides").json()[0]
        self.assertEqual((guide["composed_by"], len(guide["stops"])), ("template", 1))

    def test_journal_page_image_when_generated_photos_are_on(self) -> None:
        self.use_chat(self.GUIDE)
        self.owner.patch("/settings", {"generated_photos": True})
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()
        self.assertEqual(self.owner.get("/guides").json()[0]["image_status"], "processing")
        self.web.illustrations.run_pending()
        guide = self.owner.get("/guides").json()[0]
        self.assertEqual(guide["image_status"], "ready")
        journal = next(p for p in self.illustrator.prompts if "手账" in p)
        self.assertIn("港岛慢慢走", journal)
        self.assertIn("不要出现人或人手", journal)


if __name__ == "__main__":
    unittest.main()
