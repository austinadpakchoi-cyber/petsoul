"""主人主动发起的拍照命令 `POST /pets/{pet_id}/photo-request`（COORD-I-PHOTO-COMMAND，归 I）。

它只管 **home / train / flight_adventure** 三个场景——到咖啡馆拍照仍走行程里的到访活动，那条路不变。
之所以要单开一条：在家时既没有行程也没有到访，途中要到店之后才有到访，
**事件模型里根本没有那个时刻**，不是"有调用点没接上"。

这里钉四类事：
  ① **状态不成立就 409**，而且是"连记录都不写"的那种拒绝，不是先写了再 hold；
  ② 虚构飞行必须**主人显式选**，且不写世界事件、不进旅程历史、不发勋章；
  ③ 同一分钟内连点**不会多排一次、不会多花钱**（分钟桶 source_key 命中既有 dedupe）；
  ④ 权限与 CSRF 照旧。

替身生图，不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class PhotoRequestCommandTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("photo-cmd-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        # 参考照的**来源**走正式装配（`web_composition.reference_origin_of`），**不在测试里注入 lambda**。
        # 这里用真实的 `set_portrait` 把基准照持久化下来——它会在同一条 UPDATE 里置 photo_generated=1，
        # 装配据此读出 `original_companion`。来源说不清的宠物会被导演 hold，那是正确行为。
        self.web.pets.set_portrait(self.owner.pet_id, b"reference-photo", "image/png")

    def ask(self, scene: str, narrative: str = "daily_life", who=None, pet_id: str | None = None):
        user = who or self.owner
        return user.post(f"/pets/{pet_id or self.owner.pet_id}/photo-request", {"scene": scene, "narrative": narrative})

    def world_events(self) -> list[str]:
        with self.app.state.storage.connect() as conn:
            return [r["kind"] for r in conn.execute("SELECT kind FROM web_world_events WHERE pet_id = ?", (self.owner.pet_id,))] \
                if self._has_pet_column(conn) else \
                [r["kind"] for r in conn.execute("SELECT kind FROM web_world_events")]

    @staticmethod
    def _has_pet_column(conn) -> bool:
        return any(row["name"] == "pet_id" for row in conn.execute("PRAGMA table_info(web_world_events)"))

    def fund(self, amount: int = 300) -> None:
        """东京那趟要 120 旅费，默认钱包只有 20，先充够。"""
        from app.schemas.base import EconomyTransactionType

        self.web.economy.apply(self.owner.pet_id, amount, EconomyTransactionType.owner_fund_granted,
                               f"test-fund-{self.owner.pet_id}", "测试用旅费", "test")

    def board_tokyo_train(self) -> None:
        """出发去东京，把时钟推到**正在坐爪爪铁路那一段**（打车 35 ＋ 候机 60 ＋ 飞行 240 之后的 40 分钟）。"""
        self.fund()
        response = self.owner.post("/journey/depart", {"destination_key": "tokyo_flight"})
        self.assertEqual(response.status_code, 200, response.text)
        self.clock.advance(minutes=35 + 60 + 240 + 5)

    # ---- ① 状态不成立 → 409，且什么都不写 ----
    def test_asking_for_a_home_photo_while_away_is_refused_without_writing_anything(self) -> None:
        calls_before = len(self.illustrator.prompts)
        self.board_tokyo_train()

        response = self.ask("home")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["code"], "CONFLICT")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts), calls_before, "拒绝掉的命令不许发起任何生图调用")
        with self.app.state.storage.connect() as conn:
            rows = conn.execute("SELECT COUNT(*) AS n FROM web_illustrations WHERE source_event_id LIKE 'photo-request:%'").fetchone()
        self.assertEqual(rows["n"], 0, "409 是「命令不成立」，连插画记录都不该写")

    def test_asking_for_a_train_photo_at_home_is_refused(self) -> None:
        response = self.ask("train")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["details"]["activity"], "at_home", "要说清此刻在做什么")

    def test_a_train_photo_is_refused_while_on_a_non_train_leg(self) -> None:
        """刚出发还在打车去机场：有行程、也在途中，但**这一段不是列车**，照样拒。"""
        self.fund()
        self.assertEqual(self.owner.post("/journey/depart", {"destination_key": "tokyo_flight"}).status_code, 200)
        self.clock.advance(minutes=10)  # 还在打车那一段

        response = self.ask("train")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["details"]["leg_mode"], "taxi", "要说清现在这一段是什么，不能含糊")

    # ---- 成功路径 ----
    def test_a_home_photo_is_accepted_when_really_at_home(self) -> None:
        response = self.ask("home")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["scene"], "home")
        self.assertEqual(body["narrative"], "daily_life")
        self.assertFalse(body["fictional"])
        self.assertTrue(body["task_id"], "要真的排上队")
        self.web.illustrations.run_pending()
        self.assertEqual(self.web.illustrations.tasks.get(body["task_id"]).status, "succeeded")

    def test_a_train_photo_is_accepted_while_actually_on_the_train(self) -> None:
        self.board_tokyo_train()

        response = self.ask("train")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["scene"], body["place"]), ("train", "列车上"))
        self.assertEqual(body["city"], "东京", "途中按这趟行程的城市算，不是家所在地")
        self.assertTrue(body["captured_at"].endswith("+09:00") or "+09:00" in body["captured_at"],
                        f"拍摄时刻要按**当前这一段的落点**换算（东京 +09:00），不是家所在地：{body['captured_at']}")

    # ---- ② 虚构飞行：必须显式选，且不进真实世界 ----
    def test_a_fictional_flight_must_be_chosen_explicitly(self) -> None:
        refused = self.ask("flight_adventure")  # narrative 默认 daily_life

        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"]["details"]["expected_narrative"], "fictional_adventure")

    def test_a_daily_scene_cannot_be_dressed_up_as_fiction(self) -> None:
        refused = self.ask("home", narrative="fictional_adventure")

        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"]["details"]["expected_narrative"], "daily_life")

    def test_a_fictional_flight_writes_no_world_event_and_no_medal(self) -> None:
        """主人选了虚构飞行：受理、也留得下记录，但**不能变成真的出过门**。"""
        events_before = self.world_events()

        response = self.ask("flight_adventure", narrative="fictional_adventure")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["fictional"], "响应要明说这是虚构的")
        self.assertEqual(body["narrative"], "fictional_adventure")
        self.assertEqual(self.world_events(), events_before, "不许写世界事件——它没有真的飞过")
        with self.app.state.storage.connect() as conn:
            journeys = conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()["n"]
            medals = conn.execute("SELECT COUNT(*) AS n FROM web_collection_items WHERE pet_id = ? AND kind = 'badge'",
                                  (self.owner.pet_id,)).fetchone()["n"]
        self.assertEqual(journeys, 0, "不许凭空多出一趟旅程")
        self.assertEqual(medals, 0, "不许发勋章——勋章要真的赢得过")
        self.assertTrue(body["task_id"], "但它确实留下了可恢复的记录，不是什么都没发生")

    # ---- ③ 同一次点击重发不多花钱 ----
    def test_resending_the_same_click_does_not_cost_twice(self) -> None:
        """同一个 Idempotency-Key 重发（网络抖动、客户端重试）：同一个任务、一次调用。

        **不同 key 是不同的操作**——主人真的又点了一次，就该真的再拍一张。
        防止连点多花钱靠的是额度层（全局与每宠上限），不是在入口把两次不同的点击合并掉。
        """
        calls_before = len(self.illustrator.prompts)

        first = self.ask_with_key("home", "same-click-1")
        self.clock.advance(seconds=5)
        again = self.ask_with_key("home", "same-click-1")

        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertEqual(first.json()["task_id"], again.json()["task_id"], "同一个 key 重发要落到同一个任务上")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts) - calls_before, 1, "只发生一次替身调用")

    # ---- ⑤ 幂等与恢复（COORD-I-IDEMPOTENCY 的三个反例，先红后绿）----
    def ask_with_key(self, scene: str, key: str, narrative: str = "daily_life", pet_id: str | None = None):
        return self.owner.post(f"/pets/{pet_id or self.owner.pet_id}/photo-request",
                               {"scene": scene, "narrative": narrative}, key=key)

    def photo_request_tasks(self) -> int:
        """这条命令一共排了几个生图任务（按领域编号认，不看时间）。"""
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_tasks WHERE dedupe_key LIKE '%photo-request:%'").fetchone()["n"]

    def forget_receipt(self, key: str) -> None:
        """模拟"任务已经排上队、幂等回执还没写完就退出了"：只抹掉回执，任务与插画记录都留着。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM web_idempotency_keys WHERE idem_key = ?", (key,))

    def test_a_retry_after_a_crash_finds_the_same_task_even_minutes_later(self) -> None:
        """回执没保存就退出，六分钟后同一个 Idempotency-Key 接手：**必须找回同一个任务**，不能因为跨了分钟就另排一次。"""
        first = self.ask_with_key("home", "recover-key-1")
        self.assertEqual(first.status_code, 200, first.text)
        task_id, captured_at = first.json()["task_id"], first.json()["captured_at"]
        self.forget_receipt("recover-key-1")

        self.clock.advance(minutes=6)  # 早就跨过分钟桶
        again = self.ask_with_key("home", "recover-key-1")

        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["task_id"], task_id, "接手要找回原来那个任务，不能另排一次")
        self.assertEqual(again.json()["captured_at"], captured_at, "拍摄时刻是首次登记时的那一刻，不能改写成接手时刻")
        self.assertEqual(self.photo_request_tasks(), 1, "接手不许多排一个任务——多一个就是多花一次钱")

    def test_the_same_key_on_another_pet_does_not_return_the_first_pets_photo(self) -> None:
        """同一位主人、同一个 Idempotency-Key，换一只宠物：**绝不能把上一只的照片任务回给它**。"""
        second = self.owner.upload_pet("小豆", "cat", household_id=self.household_id())
        self.assertEqual(second.status_code, 201, second.text)
        other = second.json()["pet_id"]
        self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": other}).status_code, 200)

        mine = self.ask_with_key("home", "shared-key-1")
        theirs = self.ask_with_key("home", "shared-key-1", pet_id=other)

        self.assertEqual(mine.status_code, 200, mine.text)
        if theirs.status_code == 200:
            self.assertNotEqual(theirs.json()["task_id"], mine.json()["task_id"], "两只宠物各拍各的，任务不能串")
        else:
            self.assertEqual(theirs.status_code, 409, f"要么各自独立，要么明确拒绝重用，不能串：{theirs.text}")

    def test_replaying_a_key_returns_the_original_even_after_the_pet_left_home(self) -> None:
        """首单成立之后 TA 出门了，同一个 key 重放：**仍然取回原来那次的结果**，不能因为"现在不在家"就把原结果丢掉。"""
        first = self.ask_with_key("home", "replay-key-1")
        self.assertEqual(first.status_code, 200, first.text)
        task_id = first.json()["task_id"]
        self.board_tokyo_train()  # 现在 TA 在列车上，home 这个条件已经不成立

        again = self.ask_with_key("home", "replay-key-1")

        self.assertEqual(again.status_code, 200, f"重放要取回原操作，不是按当下状态重新判一次：{again.text}")
        self.assertEqual(again.json()["task_id"], task_id)

    def household_id(self) -> str:
        return self.owner.get("/onboarding").json()["households"][0]["household_id"]

    def test_recovering_a_lost_receipt_after_the_pet_left_home(self) -> None:
        """**两个条件交错**：回执丢了 **而且** TA 已经离家。

        单独任何一个都已经能过——回执还在时走幂等、回执丢了但还在家时按同一个编号找回原任务。
        合起来才暴露真正的洞：handler 会重新按**当下**状态核验，于是判"现在不在家"直接 409，
        **原来那次登记明明还躺在库里，却再也取不回来**。这不是重复收费，是把主人已经成立的那次请求弄丢了。

        正确行为：进了 handler 先按稳定编号找有没有**已提交的原登记**，有就照首次持久下来的内容重建响应；
        只有确实没有登记，才按当前场景当成一条新命令。访问授权仍然每次都查，不因为要恢复就放松。
        """
        first = self.ask_with_key("home", "interleaved-key-1")
        self.assertEqual(first.status_code, 200, first.text)
        original = first.json()
        self.forget_receipt("interleaved-key-1")
        self.board_tokyo_train()  # 回执没了，人也走了

        again = self.ask_with_key("home", "interleaved-key-1")

        self.assertEqual(again.status_code, 200, f"原登记还在，就该取回来，不是按当下状态重判：{again.text}")
        recovered = again.json()
        self.assertEqual(recovered["task_id"], original["task_id"], "要拿回原来那个任务")
        self.assertEqual(recovered["captured_at"], original["captured_at"], "拍摄时刻来自首次登记")
        self.assertEqual((recovered["place"], recovered["city"]), (original["place"], original["city"]),
                         "地点与城市也来自首次登记，不能按重放时的现状重新拼")
        self.assertEqual(recovered["narrative"], original["narrative"])
        self.assertEqual(recovered["scene"], original["scene"])
        self.assertEqual(self.photo_request_tasks(), 1, "不许多排一个任务")

    def test_recovery_still_checks_access_every_time(self) -> None:
        """恢复不是绕过权限：回执丢了、登记还在，但来问的人已经不是这家的人——照样 404。"""
        self.ask_with_key("home", "interleaved-key-2")
        self.forget_receipt("interleaved-key-2")
        stranger = self.user("photo-cmd-stranger2")
        stranger.adopt_and_move_in("adopt-mochi")

        response = stranger.post(f"/pets/{self.owner.pet_id}/photo-request",
                                 {"scene": "home", "narrative": "daily_life"}, key="interleaved-key-2")

        self.assertEqual(response.status_code, 404, "访问授权每次都要查，不能为了恢复放松")

    # ---- ④ 权限与 CSRF ----
    def test_an_outsider_cannot_ask_for_a_photo(self) -> None:
        stranger = self.user("photo-cmd-stranger")
        stranger.adopt_and_move_in("adopt-mochi")

        response = self.ask("home", who=stranger, pet_id=self.owner.pet_id)

        self.assertEqual(response.status_code, 404, "不是这家的人，连存不存在都不告诉")

    def test_the_command_requires_csrf(self) -> None:
        response = self.owner.client.post(f"/api/v1/web/pets/{self.owner.pet_id}/photo-request",
                                          json={"scene": "home", "narrative": "daily_life"})

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
