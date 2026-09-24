"""世界角色整链：**真实上传自动触发** → 排队 → 执行 → 校验 → 原子发布 → 纯读（CR-PLAYER-CHARACTER-01）。

这一套刻意**不手工排队、不手工装配**：

  - 排队走 `POST /api/v1/web/pets`（网页侧唯一的上传口）→ `create_own` → 它自己那个写事务里的
    `on_pet_photo_stored` 钩子。测试里**没有一行 `request_in`**；
  - 接线走正式组合根 `web_composition.install_character_service`，不在用例里塞 lambda；
  - 读状态走 `GET /pets/{pet_id}/character`，不是直接问服务对象。

只替换**图片供应商**：注入 `FakeCharacterIllustrator`（假的，见 `character_fakes` 抬头）。
不联网、**0 次付费调用**。

假供应商返回的透明 PNG 证明的是"校验与发布这条闸接对了"，
**不证明真实 GPT 链路能产出透明角色**——现有适配器压根没请求 `background=transparent`。
"""

from __future__ import annotations

import unittest

from character_fakes import FakeCharacterIllustrator, opaque_png
from web_base import tiny_png, WebPlatformTestBase


class CharacterAutoStartTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("character-owner")
        self.illustrator = FakeCharacterIllustrator()
        self.web.character.illustrator = self.illustrator
        # **这里不再有"先建家再开授权"那一段**。用户 2026-09-23 决定取消逐次询问后，
        # 上传就是上传——`test_the_very_first_pet_of_a_brand_new_account_is_queued_straight_away`
        # 专门钉住那个曾经的产品顺序缺口**已经消失**。
        # 仍然先建一只是为了拿到 `household_id`：同一账号加第二只宠物必须带它（否则 409 household_exists）。
        # **它不带照片**——摘掉授权闸之后，带照片的上传会当场排队，那会让下面每一条的计数都多算一只。
        first = self.owner.upload_pet("先建家", "cat", photo=None)
        self.assertEqual(first.status_code, 201, first.text)
        self.household_pet_id = first.json()["pet_id"]
        self.household_id = self.web.households.memberships(self.owner.user_id)[0].household_id

    # ---- 辅助 ----
    def upload(self, name: str = "小银", species: str = "cat", photo: bytes | None = None, **kwargs):
        kwargs.setdefault("household_id", self.household_id)
        response = self.owner.upload_pet(name, species, photo=tiny_png() if photo is None else photo, **kwargs)
        self.assertEqual(response.status_code, 201, response.text)
        self.owner.pet_id = response.json()["pet_id"]
        return response.json()

    def state(self, pet_id: str | None = None) -> dict:
        response = self.owner.get(f"/pets/{pet_id or self.owner.pet_id}/character")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def queued_tasks(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_tasks WHERE kind = 'pet_character'").fetchone()["n"]

    # ---- ① 上传就自动排上，主人一次都没点"开始生成"、也没被问过授权 ----
    def test_an_upload_queues_the_character_by_itself(self) -> None:
        self.upload()

        self.assertEqual(self.queued_tasks(), 1, "上传成功就该自动排一张，不该等主人再点")
        state = self.state()
        self.assertEqual(state["status"], "queued")
        self.assertIsNone(state["active"], "还没画出来，不能假装已经有形象")
        self.assertEqual(state["candidate"]["reference_version"], 1, "第一张参考照是第 1 版")
        self.assertEqual(self.illustrator.calls, 0, "排队不等于发送——这一步不许有任何供应商调用")

    def test_the_task_is_registered_in_the_uploads_own_transaction(self) -> None:
        """任务与宠物记录必须同生共死：上传那一刻库里就同时有这两样，不是事后补的。"""
        self.upload()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT t.task_id, c.asset_id FROM web_tasks t JOIN web_pet_characters c "
                               "ON c.task_id = t.task_id WHERE t.kind = 'pet_character'").fetchone()
        self.assertIsNotNone(row, "任务与角色记录要一起落库")

    def test_the_very_first_pet_of_a_brand_new_account_is_queued_straight_away(self) -> None:
        """**这条钉的是一个曾经存在、现在被消掉的产品顺序缺口。**

        原先：`generated_photos` 是**家庭级**设置，而家是在第一次上传那个事务里才建出来的——
        全新账号在第一次上传之前无处可设授权（`PATCH /settings` 那时 409 pet_required），
        授权默认关闭，于是**第一只宠物一定排不上角色任务**。
        当时我如实钉住了那个现状，并把它报为产品顺序缺口。

        现在：用户 2026-09-23 直接决定**取消逐次询问**，这道闸已摘除。
        全新账号第一只宠物**当场就排上**，不需要先去设置里打开任何东西。

        留这条用例而不是删掉：它是那个缺口的反向证据，**谁把授权闸加回来，它会当场红**。
        """
        fresh = self.user("character-brand-new")

        created = fresh.upload_pet("第一只", "cat", photo=tiny_png())

        self.assertEqual(created.status_code, 201, created.text)
        pet_id = created.json()["pet_id"]
        body = fresh.get(f"/pets/{pet_id}/character").json()
        self.assertEqual(body["status"], "queued", "全新账号的第一只宠物就该直接排上")
        self.assertIsNone(body["blocked_reason"], "没有任何东西挡着")
        self.assertIsNotNone(body["candidate"])

    def test_a_pet_without_a_household_is_not_generated(self) -> None:
        """**取消的是「询问」，不是「归属」。**

        原先那道家庭生图许可顺带做了一件事：没有家的宠物一律 False。
        摘授权时**不能把它一起摘掉**——没有家的宠物，生成出来的角色不属于任何人，
        也没有任何人有权读它（三条路由都走 `require_pet`）。所以单列成 `pet_has_no_household`。

        驿站里待领养的居民就是这种状态：有档案、没有家。
        """
        self.upload()  # 有照片、物种也支持，唯一缺的就是家
        pet_id = self.owner.pet_id
        with self.app.state.storage.connect() as conn:
            conn.execute("DELETE FROM web_household_pets WHERE pet_id = ?", (pet_id,))

        self.assertEqual(self.owner.get(f"/pets/{pet_id}/character").status_code, 404,
                         "连它属于谁都判不出来了，读接口本身就该挡下")
        with self.app.state.storage.connect() as conn:
            reason = self.web.character.blocked_reason_in(conn, pet_id)
            queued = self.web.character.request_in(conn, pet_id, self.owner.user_id, "cat", "pets/x/y.png")
        self.assertEqual(reason, "pet_has_no_household", "服务层要如实说为什么不生成")
        self.assertIsNone(queued, "也不该再排新的——没有家的宠物不生成")

    def test_an_upload_without_a_photo_queues_nothing(self) -> None:
        before = self.queued_tasks()

        response = self.owner.upload_pet("没照片", "cat", photo=None, household_id=self.household_id)

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.queued_tasks(), before, "没有原照就不是这只宠物，不画")
        self.assertEqual(self.owner.get(f"/pets/{response.json()['pet_id']}/character").json()["blocked_reason"],
                         "no_reference_photo")

    # ---- ② 跑完一轮：校验通过、原子发布、家园读得到 ----
    def test_the_worker_publishes_a_character_the_owner_can_then_read(self) -> None:
        self.upload()

        self.assertEqual(self.web.character.run_pending(), 1)

        state = self.state()
        self.assertEqual(state["status"], "ready")
        self.assertIsNone(state["candidate"], "已经发布，就没有在建的那一份了")
        active = state["active"]
        self.assertEqual(active["revision"], 1)
        self.assertEqual(active["reference_version"], 1)
        asset = active["assets"][0]
        self.assertEqual(asset["pose"], "neutral_full")
        self.assertTrue(asset["has_alpha"], "发布出来的必须是验过 alpha 的")
        self.assertTrue(asset["anchor"]["measured"], "锚点是从图像实测的，不是导演估的")
        self.assertEqual(asset["url"], f"/api/v1/web/media/characters/{asset['asset_id']}")
        # 主体框要落在画布里、四边有留白（校验就是按这个判的）
        box = asset["content_box"]
        self.assertTrue(0 < box["left"] < box["right"] < asset["width"], box)
        self.assertTrue(0 < box["top"] < box["bottom"] < asset["height"], box)

    def test_the_published_image_is_served_only_to_the_family(self) -> None:
        self.upload()
        self.web.character.run_pending()
        asset_id = self.state()["active"]["assets"][0]["asset_id"]

        mine = self.owner.get(f"/media/characters/{asset_id}")
        stranger = self.user("character-outsider")
        stranger.adopt_and_move_in("adopt-mochi")
        theirs = stranger.get(f"/media/characters/{asset_id}")

        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertEqual(mine.headers["content-type"], "image/png")
        self.assertEqual(theirs.status_code, 404, "不是这家的人，连存不存在都不告诉")

    def test_the_owners_original_photo_is_never_replaced(self) -> None:
        """原照是身份档案，角色是另一份资产。跑完一轮之后原照还在原地。"""
        summary = self.upload()
        before = self.owner.get(f"/media/pets/{self.owner.pet_id}/photo").content

        self.web.character.run_pending()

        after = self.owner.get(f"/media/pets/{self.owner.pet_id}/photo")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.content, before, "角色不许覆盖主人上传的原照")
        self.assertIsNotNone(summary["photo_url"], "原照的地址也不该被动过")

    # ---- ③ GET 不出图；刷新不重复生成 ----
    def test_reading_the_state_never_triggers_generation(self) -> None:
        """家园每次渲染都会打这条路由。它要是能触发生成，刷新页面就是在烧钱。"""
        self.upload()
        self.web.character.run_pending()
        calls_after_first_run = self.illustrator.calls

        for _ in range(5):
            self.state()

        self.assertEqual(self.illustrator.calls, calls_after_first_run, "读接口一次都不许发出去")
        self.assertEqual(self.queued_tasks(), 1, "读接口也不许多排一张任务")

    def test_a_second_worker_round_does_not_redraw(self) -> None:
        self.upload()
        self.web.character.run_pending()

        self.assertEqual(self.web.character.run_pending(), 0, "已经做完的任务不会被再领一次")
        self.assertEqual(self.illustrator.calls, 1, "一张图就是一次调用，不能变成两次付费")

    # ---- ④ 校验不过就不发布 ----
    def test_an_opaque_result_is_not_published_and_says_which_thing_to_fix(self) -> None:
        """有 alpha 通道、却一个透明像素都没有：不发布。

        原因记 `transparency_not_requested` 而不是 `opaque_background`——因为适配器**压根没请求**
        透明底（`transparency_requested` 默认 False）。两者处置完全不同：
        前者要改请求参数或核实中转，后者才是"请求了、中转没给"。
        """
        self.web.character.illustrator = FakeCharacterIllustrator(images=[opaque_png()])
        self.upload()

        self.web.character.run_pending()

        state = self.state()
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["candidate"]["reason"], "transparency_not_requested")
        self.assertIsNone(state["active"], "校验不过就不发布，绝不因为「返回了 PNG」就当作透明角色")

    def test_a_rejected_result_leaves_the_previous_character_in_place(self) -> None:
        """一次调整失败不破坏旧生效版本——旧形象一直有效，直到新版本合格才原子切换。"""
        self.upload()
        self.web.character.run_pending()
        first = self.state()["active"]["assets"][0]["asset_id"]

        self.web.character.illustrator = FakeCharacterIllustrator(images=[opaque_png()])
        accepted = self.owner.post(f"/pets/{self.owner.pet_id}/character/regenerate", {}, key="regen-key-1")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.web.character.run_pending()

        state = self.state()
        self.assertEqual(state["status"], "failed", "在建那一版如实说没成")
        self.assertIsNotNone(state["active"], "旧形象不能因为新任务出错就消失")
        self.assertEqual(state["active"]["assets"][0]["asset_id"], first, "还是原来那一份")

    # ---- ⑤ 「调整形象」是可选的，而且不能并排两个 ----
    def test_regenerating_while_one_is_already_queued_is_refused(self) -> None:
        self.upload()

        response = self.owner.post(f"/pets/{self.owner.pet_id}/character/regenerate", {}, key="regen-key-2")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["accepted"])
        self.assertEqual(body["reason"], "already_queued", "已经有在建的就明确拒绝，不再排一个")
        self.assertEqual(self.queued_tasks(), 1)

    def test_regenerating_starts_a_higher_revision(self) -> None:
        self.upload()
        self.web.character.run_pending()

        self.owner.post(f"/pets/{self.owner.pet_id}/character/regenerate", {}, key="regen-key-3")
        self.web.character.run_pending()

        state = self.state()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["active"]["revision"], 2, "新的一轮要比旧的号大，旧任务才覆盖不了它")
        self.assertEqual(state["active"]["reference_version"], 1, "参考照没换，版本不该跟着涨")
        self.assertEqual(self.illustrator.calls, 2)

    def test_regenerate_requires_csrf(self) -> None:
        self.upload()

        response = self.owner.client.post(
            f"/api/v1/web/pets/{self.owner.pet_id}/character/regenerate",
            json={}, headers={"Idempotency-Key": "regen-key-4"})

        self.assertEqual(response.status_code, 403, response.text)

    # ---- ⑥ 请求参数：竖幅、带参考照 ----
    def test_the_request_uses_a_portrait_canvas_and_the_owners_photo(self) -> None:
        """全身站立是竖构图。照片链路的 2048x2048 会被 GPT 适配器映射成方画幅，逼着模型裁身体。"""
        self.upload()

        self.web.character.run_pending()

        self.assertEqual(self.illustrator.sizes, ["1024x1536"])
        self.assertIsNotNone(self.illustrator.references[0], "必须带上主人的原照当身份参考")

    def test_the_prompt_never_asks_for_transparency(self) -> None:
        """模型没有 alpha 概念，提示词里写"透明"会让它把棋盘格画进 RGB。

        透明是请求参数 `background` 的职责（下一条），提示词只说**画面内容**。
        """
        self.upload()
        self.web.character.run_pending()

        prompt = self.illustrator.prompts[0]
        for word in ("透明", "alpha", "背景透明", "棋盘"):
            self.assertNotIn(word, prompt, f"提示词不该出现 {word}")
        self.assertIn("主体之外整片留空", prompt, "该说的是画面内容：主体之外留空")
        self.assertIn("不画影子", prompt, "阴影归渲染层，画进角色图会跟着它进每一个场景")

    def test_the_character_asks_the_adapter_for_a_transparent_background(self) -> None:
        """透明是**请求参数**的职责，而且是**按调用**请求的——角色链路每次都要带上它。

        这里原先是一条"不可达守卫"：断言 `transparency_requested` 仍为假，谁翻开就当场红、提示补棋盘格检测器。
        2026-09-23 用户批准按调用请求透明底，检测器已落地（`validate.CHECKERBOARD`），守卫退场。

        **退场前如实记下它的一个盲点**：它断言的是**测试应用**里的值，而测试配置下供应商是
        `NoIllustrator`（能力标记为假）——**生产那边无论怎么翻，它都照样绿**。它钉的是测试环境的值，
        不是生产的值。生产装配的那一面现在钉在
        `test_web_character_worker.py::test_the_composed_app_pumps_character_tasks_too`（用真实 GPT 配置建应用）。
        """
        self.upload()
        self.web.character.run_pending()

        self.assertEqual(self.illustrator.backgrounds, ["transparent"], "角色每次调用都要请求透明底")


if __name__ == "__main__":
    unittest.main()
