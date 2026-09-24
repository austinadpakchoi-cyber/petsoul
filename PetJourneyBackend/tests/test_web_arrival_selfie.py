"""到站自拍（用户 2026-09-24：「每一个用户注册完成之后都会收到宠物在聊天框和明信片给他发的一个到站的自拍图」）。

注册时还没有宠物，所以落在 TA 第一次住进家（入住＝到站）。钉的是主人能感受到的事，不是「某个函数被调用了」：

  · 入住之后，下一轮认知线就有：家庭频道一条「我到站啦」带自拍（先冲洗中）＋收藏里一张到站明信片
    （TA 写的话、**家的真实片区**、同一张自拍）；
  · **图只画一次**：一个生图任务，画好后两处一起换上同一张图；
  · 入住请求本身不调模型、不排生图（只登记），不拖慢入住；
  · 每只宠物只一次：重复入住、重复跑轮次都不多发；多宠家庭每只各一次；
  · 生图不可用时寄手写明信片，消息**不提自拍**；
  · 写话：家里允许用模型时由模型写（只给真实片区），关掉就用模板；
  · 出错整体回滚、按退避重试，用尽次数放弃并留下原因；登记后 TA 已不在这个家就不发。
"""

from __future__ import annotations

import json
import unittest

from app.web_arrival.service import source_key
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat, FakeIllustrator


class ArrivalBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        self.chat = FakeChat(["到站啦！新家楼下有好多鸽子，我拍了一张自拍给你们。"])
        self.web.communicator.chat = self.chat
        self.web.providers.chat = self.chat  # 到站明信片写话读的是 providers.chat（与回程明信片同一个入口）

    def arrive(self, name: str, candidate: str = "adopt-lan"):
        owner = self.user(name)
        owner.adopt_and_move_in(candidate)
        return owner

    def run_round(self) -> int:
        return self.web.arrival.run(self.clock.now)

    def arrival_message(self, owner, pet_id: str | None = None, channel: str = "private") -> dict | None:
        """这位家人能看到的、TA 发的「我到站啦」。默认在「我和 TA」私聊里找（前端聊天框默认打开的就是它）。
        按内容找：消息摘要只外露旅程世界事件的来源号（`jn-…:事件键`），其他去重键一律不外露（通讯器的隐私口径）。"""
        pet_id = pet_id or owner.pet_id
        items = owner.get(f"/communicator/{pet_id}/messages").json()["items"]
        found = [m for m in items if m["sender"] == "pet" and m["channel"] == channel and m["text"].startswith("我到站啦")]
        self.assertLessEqual(len(found), 1, "同一只宠物的到站消息只能有一条")
        if found:
            self.assertIsNone(found[0]["source_event_id"], "去重键不外露（与其他非旅程来信同一口径）")
        return found[0] if found else None

    def arrival_postcard(self, owner, pet_id: str | None = None) -> dict | None:
        pet_id = pet_id or owner.pet_id
        items = owner.get("/collection", params={"pet_id": pet_id}).json()
        found = [i for i in items if i["kind"] == "postcard" and i["source_event_id"] == source_key(pet_id)]
        self.assertLessEqual(len(found), 1, "同一只宠物的到站明信片只能有一张")
        return found[0] if found else None

    def selfie_tasks(self, pet_id: str) -> list[dict]:
        with self.app.state.storage.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT task_id, status FROM web_tasks WHERE dedupe_key = ?", (f"illustration:{source_key(pet_id)}",))]


class ArrivalDeliveryTests(ArrivalBase):
    def test_move_in_leads_to_one_selfie_shown_in_the_chat_and_on_the_postcard(self) -> None:
        # 麦穗有打包的原创形象照，自拍直接拿它当参考：供应商只被调一次。
        # （没有照片的宠物会先生成一张形象照再画自拍，是插画服务的既有规则，不在这里重测。）
        owner = self.arrive("arrival-main", "adopt-maisui")
        self.assertIsNone(self.arrival_message(owner), "入住请求本身只登记，不直接发")
        self.assertEqual(self.run_round(), 1)

        message, postcard = self.arrival_message(owner), self.arrival_postcard(owner)
        self.assertIsNotNone(message, "聊天框（「我和 TA」私聊）里要有 TA 的到站消息")
        self.assertIsNotNone(postcard, "收藏里要有到站明信片")
        self.assertEqual((message["sender"], message["channel"]), ("pet", "private"))
        self.assertIsNone(self.arrival_message(owner, channel="family"), "只发一条：不再同时往家庭频道发")
        self.assertIn("自拍", message["text"])
        self.assertEqual((message["photo_status"], postcard["image_status"]), ("processing", "processing"), "先显示冲洗中")
        self.assertEqual(len(self.selfie_tasks(owner.pet_id)), 1, "两处共用一个生图任务：只画一次")

        place = self.web.home_places.get(self.web.homes.by_pet(owner.pet_id).home_id)
        self.assertEqual((postcard["place"], postcard["city"]), (place.area_label, place.city), "地点是家的真实片区，不编")
        self.assertIn(place.area_label, postcard["title"])
        self.assertTrue(postcard["note"], "明信片上有 TA 写的话")

        self.web.illustrations.run_pending()
        message, postcard = self.arrival_message(owner), self.arrival_postcard(owner)
        self.assertEqual((message["photo_status"], postcard["image_status"]), ("ready", "ready"))
        self.assertTrue(message["photo_url"])
        self.assertEqual(message["photo_url"], postcard["image_url"], "聊天里和明信片上是同一张自拍")
        self.assertEqual(len(self.illustrator.prompts), 1, "有参考照的宠物：供应商只被调用了一次（两处共用这一张）")

    def test_the_selfie_prompt_paints_the_area_without_naming_it(self) -> None:
        """提示词里只放片区的画面特征：地名写进去，街边招牌最容易被画出那几个字（P 在真图上吃过亏）；
        片区名交给界面排版——明信片的 place / city 仍是真实片区。也不写"星球""车站"，免得被照字面画成科幻星球或火车站。"""
        owner = self.arrive("arrival-prompt")
        self.run_round()
        self.web.illustrations.run_pending()
        place = self.web.home_places.get(self.web.homes.by_pet(owner.pet_id).home_id)
        prompt = self.illustrator.prompts[-1]
        self.assertEqual(place.area_key, "hk_central", "前提：没选过环境的家落在默认片区中环")
        self.assertIn("高楼林立", prompt, "画的是中环的样子")
        for literal in (place.area_label, place.city, "星球", "车站", "火车站"):
            self.assertNotIn(literal, prompt)
        self.assertEqual((self.arrival_postcard(owner)["place"], self.arrival_postcard(owner)["city"]), (place.area_label, place.city))

    def test_the_move_in_request_itself_never_calls_the_model_or_the_image_service(self) -> None:
        owner = self.arrive("arrival-fast")
        self.assertEqual((self.chat.calls, self.selfie_tasks(owner.pet_id)), ([], []), "入住请求里既不调模型、也不排生图")
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["state"], "pending", "只登记了一行")

    def invite_member(self, owner, name: str):
        household_id = owner.get("/onboarding").json()["households"][0]["household_id"]
        invite = owner.post(f"/households/{household_id}/invites", {"role": "caregiver", "relation_hint": None, "ttl_hours": 24})
        self.assertEqual(invite.status_code, 201, invite.text)
        other = self.user(name)
        joined = other.post("/invites/accept", {"token": invite.json()["token"]})
        self.assertEqual(joined.status_code, 200, joined.text)
        return other, household_id

    def test_the_chat_message_is_for_the_mover_and_the_postcard_for_the_family(self) -> None:
        """聊天消息是写给接 TA 入住那位家人的私聊；明信片属于这只宠物，后来加入的家人也看得到。"""
        owner = self.arrive("arrival-family")
        other, _ = self.invite_member(owner, "arrival-family-2")
        self.run_round()
        self.assertIsNotNone(self.arrival_message(owner), "接 TA 入住的那位在「我和 TA」里收到")
        self.assertIsNone(self.arrival_message(other, owner.pet_id), "别的家人看不到这条私聊")
        self.assertIsNotNone(self.arrival_postcard(other, owner.pet_id), "明信片全家同一份")

    def test_if_the_mover_left_the_family_the_message_goes_to_the_family_channel(self) -> None:
        """登记之后、发出之前，接 TA 入住的那位已不是有效成员：私聊写不进去，退回家庭频道，家里仍然收得到。"""
        owner = self.arrive("arrival-mover-left")
        other, household_id = self.invite_member(owner, "arrival-stays")
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_household_members SET status = 'removed' WHERE household_id = ? AND user_id = ?",
                         (household_id, owner.user_id))
        self.assertEqual(self.run_round(), 1)
        self.assertIsNotNone(self.arrival_message(other, owner.pet_id, channel="family"), "留在家里的家人在家庭频道收到")


class ArrivalOnceTests(ArrivalBase):
    def test_repeated_move_in_and_rounds_send_exactly_once(self) -> None:
        owner = self.arrive("arrival-once")
        again = owner.post("/onboarding/move-in", {"public_posts": True})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(self.run_round(), 1)
        self.assertEqual(self.run_round(), 0, "第二轮没有可发的")
        self.web.arrival.register(owner.pet_id, "hh-whatever", owner.user_id, self.clock.now)  # 重复登记也不重来
        self.assertEqual(self.run_round(), 0)
        self.assertIsNotNone(self.arrival_message(owner))  # 内部断言了只有一条
        self.assertIsNotNone(self.arrival_postcard(owner))
        self.assertEqual(len(self.selfie_tasks(owner.pet_id)), 1)

    def test_a_second_worker_holding_a_stale_row_does_not_deliver_again(self) -> None:
        """两个轮次读到同一行旧快照（认知线有租约，正常不会并发；这里钉住事务内复核这道保险）：后到的什么都不再写。"""
        owner = self.arrive("arrival-race")
        stale = self.web.arrival.state_of(owner.pet_id)
        self.assertEqual(self.web.arrival._deliver(dict(stale), self.clock.now), "delivered")
        self.assertEqual(self.web.arrival._deliver(dict(stale), self.clock.now), "already")
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["attempts"], 1, "没有被第二次标记")

    def test_a_malformed_registration_fails_loudly_instead_of_vanishing(self) -> None:
        """登记缺家庭编号必须当场报错：`INSERT OR IGNORE` 会把 NOT NULL 违例一起吞掉，登记无声消失、自拍永远不发。"""
        owner = self.user("arrival-malformed")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.web.arrival.register("PJ-NOT-A-PET", None, owner.user_id, self.clock.now)

    def test_each_new_pet_in_a_family_gets_its_own_arrival(self) -> None:
        owner = self.arrive("arrival-two-pets")
        self.run_round()
        household_id = owner.get("/onboarding").json()["households"][0]["household_id"]
        created = owner.upload_pet("第二只", "dog", household_id=household_id)
        self.assertEqual(created.status_code, 201, created.text)
        second = created.json()["pet_id"]
        moved = owner.post("/onboarding/move-in", {"pet_id": second, "public_posts": True})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(self.run_round(), 1, "第二只到站也有自己的一份")
        self.assertIsNotNone(self.arrival_message(owner, second))
        self.assertIsNotNone(self.arrival_postcard(owner, second))
        self.assertIsNotNone(self.arrival_message(owner), "第一只的那份还在，只有一条")

    def test_pets_that_moved_in_before_the_feature_are_not_back_filled(self) -> None:
        """没有登记行＝不发：上线前已入住的宠物不会隔几天突然收到「我到站啦」。"""
        owner = self.arrive("arrival-legacy")
        with self.app.state.storage.connect() as conn:
            conn.execute("DELETE FROM web_pet_arrivals WHERE pet_id = ?", (owner.pet_id,))  # 模拟功能上线前入住的宠物
        self.assertEqual(self.run_round(), 0)
        self.assertIsNone(self.arrival_message(owner))
        self.assertIsNone(self.arrival_postcard(owner))


class ArrivalFallbackTests(ArrivalBase):
    def test_without_an_image_service_it_is_a_handwritten_card_and_never_claims_a_selfie(self) -> None:
        self.web.illustrations.illustrator = None
        owner = self.arrive("arrival-no-image")
        self.assertEqual(self.run_round(), 1)
        message, postcard = self.arrival_message(owner), self.arrival_postcard(owner)
        self.assertNotIn("自拍", message["text"], "没有排自拍就不能说有自拍")
        self.assertIsNone(message["photo_status"])
        self.assertIsNone(postcard["image_status"], "手写明信片：页面显示纸质卡片")
        self.assertEqual(self.selfie_tasks(owner.pet_id), [])
        self.assertTrue(postcard["note"])

    def test_the_note_is_model_written_with_real_facts_when_the_family_allows_it(self) -> None:
        owner = self.arrive("arrival-model")
        self.run_round()
        self.assertEqual(len(self.chat.calls), 1)
        prompt = json.dumps(self.chat.calls[0], ensure_ascii=False)
        place = self.web.home_places.get(self.web.homes.by_pet(owner.pet_id).home_id)
        self.assertIn(place.area_label, prompt, "只给真实片区")
        self.assertEqual(self.arrival_postcard(owner)["note"], "到站啦！新家楼下有好多鸽子，我拍了一张自拍给你们。")
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["note_composed_by"], "model")

    def test_when_the_family_turned_model_replies_off_the_note_is_a_template(self) -> None:
        owner = self.user("arrival-template")
        self.assertFalse(owner.patch("/settings", {"model_replies": False}).json()["model_replies"])
        owner.adopt_and_move_in("adopt-lan")
        self.run_round()
        self.assertEqual(self.chat.calls, [], "关掉模型回信的家，不为到站明信片调用模型")
        self.assertIn("到站", self.arrival_postcard(owner)["note"])
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["note_composed_by"], "template")

    def test_a_model_failure_falls_back_to_the_template(self) -> None:
        self.chat.error = RuntimeError("timeout")
        owner = self.arrive("arrival-model-down")
        self.assertEqual(self.run_round(), 1, "模型挂了照样发")
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["note_composed_by"], "template")


if __name__ == "__main__":
    unittest.main()
