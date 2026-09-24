"""P1 剩下的内容类型：作物与物资、打工岗位、原创待领养居民。

每一种都验三件事：
1. **玩家侧真的读到了发布的那一版**（走玩家 API，不是后台自己算）；
2. **不可发布的字段被明确拒绝**，并说得出为什么（不是静默忽略）；
3. **既有事实不被静默改写**（已经种下的批次、已经结算的工资、已经被领养的居民）。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, PREFIX, FakeClock


class ContentTypeBase(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.publisher = self.staff("ct-publisher", ["content_publisher"])
        self.publisher.login_ok()

    def publish(self, content_type: str, slug: str, body: dict, *, reason: str = "内容类型验收") -> dict:
        created = self.publisher.post("/content", {"content_type": content_type, "slug": slug,
                                                   "title": f"{content_type}:{slug}", "body": body})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        published = self.publisher.post(f"/content/{item['item_id']}/publish",
                                        {"revision": 1, "expected_version": item["version"], "reason": reason})
        self.assertEqual(published.status_code, 200, published.text)
        return {"item": item, "published": published.json()}

    def try_publish(self, content_type: str, slug: str, body: dict):
        return self.publisher.post("/content", {"content_type": content_type, "slug": slug,
                                                "title": f"{content_type}:{slug}", "body": body})


class CropContentTests(ContentTypeBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("crop-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.home_id = self.player.get("/home").json()["home_id"]

    def crops(self) -> dict[str, dict]:
        response = self.player.get("/farm/crops")
        self.assertEqual(response.status_code, 200, response.text)
        return {row["crop_key"]: row for row in response.json()}

    def farm(self, action: str, plot_id: str, crop_key: str | None = None):
        body = {"action": action, "home_id": self.home_id, "plot_id": plot_id}
        if crop_key:
            body["crop_key"] = crop_key
        return self.player.post("/farm/actions", body)

    def test_published_label_and_price_reach_the_player(self):
        before = self.crops()["sun_pea"]
        self.assertEqual(before["label"], "太阳豌豆")
        self.publish("crop", "sun_pea", {"label": "春日豌豆", "unit_value": 5, "grow_seconds": before["grow_seconds"]})
        after = self.crops()["sun_pea"]
        self.assertEqual(after["label"], "春日豌豆", "玩家的作物清单必须读到已发布的那一版")
        self.assertEqual(after["unit_value"], 5)
        # 不可发布的两项保持内置值
        self.assertEqual(after["yield_units"], before["yield_units"])
        self.assertEqual(after["steal_total"], before["steal_total"])

    def test_growing_batch_keeps_the_ripening_time_it_was_planted_with(self):
        """`grow_seconds` 只在种下那一刻读：改了不影响已经种下的批次。"""
        planted = self.farm("plant", f"{self.home_id}-p1", "sun_pea")
        self.assertEqual(planted.status_code, 200, planted.text)
        ripe_before = planted.json()["plot"]["ripe_at"]

        self.publish("crop", "sun_pea", {"label": "太阳豌豆", "unit_value": 2, "grow_seconds": 7200})
        plots = self.player.get("/home").json()["plots"]
        mine = next(p for p in plots if p["plot_id"] == f"{self.home_id}-p1")
        self.assertEqual(mine["ripe_at"], ripe_before, "已经种下的那一批成熟时间不能被新版本改写")

        # 新种下的那一块才用新的生长时间
        second = self.farm("plant", f"{self.home_id}-p2", "sun_pea")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertGreater(second.json()["plot"]["ripe_at"], ripe_before)

    def test_yield_and_steal_cannot_be_published(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "crop", "slug": "sun_pea", "title": "x",
            "body": {"label": "太阳豌豆", "unit_value": 2, "grow_seconds": 180, "yield_units": 99, "steal_total": 0},
        }).json()
        self.assertFalse(check["ok"])
        fields = {issue["field"] for issue in check["issues"]}
        self.assertEqual(fields, {"yield_units", "steal_total"})
        self.assertTrue(any("进行中的那一批" in issue["message"] for issue in check["issues"]), check)

    def test_price_out_of_range_and_unknown_slug_are_rejected(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "crop", "slug": "sun_pea", "title": "x",
            "body": {"label": "太阳豌豆", "unit_value": 5000, "grow_seconds": 180}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual([i["field"] for i in check["issues"]], ["unit_value"])
        invented = self.try_publish("crop", "diamond-bean", {"label": "钻石豆", "unit_value": 5, "grow_seconds": 180})
        self.assertEqual(invented.status_code, 422, invented.text)

    def test_already_issued_resident_orders_keep_their_reward(self):
        """居民订单的奖励在**下单时**按当时的收购价算好并落库，改价不会改写已经发出的订单。"""
        before = self.player.get("/market")
        self.assertEqual(before.status_code, 200, before.text)
        orders_before = {o["order_id"]: (o["reward"], o["item_label"]) for o in before.json()["orders"]}
        self.assertTrue(orders_before, before.text)

        self.publish("crop", "star_tomato", {"label": "红宝石番茄", "unit_value": 9, "grow_seconds": 600})

        after = self.player.get("/market").json()
        for order in after["orders"]:
            reward_before, _ = orders_before[order["order_id"]]
            self.assertEqual(order["reward"], reward_before, "已经发出的订单奖励不能被改价改写")
        tomato_orders = [o for o in after["orders"] if o["item_key"] == "star_tomato"]
        if tomato_orders:
            # 展示名与"此刻的杂货铺价"是活的（那本来就是现在的价），奖励不是
            self.assertEqual(tomato_orders[0]["item_label"], "红宝石番茄")

    def test_withdraw_puts_the_builtin_value_back(self):
        result = self.publish("crop", "moon_radish", {"label": "银月萝卜", "unit_value": 6, "grow_seconds": 1800})
        self.assertEqual(self.crops()["moon_radish"]["label"], "银月萝卜")
        item = self.publisher.get(f"/content/{result['item']['item_id']}").json()["item"]
        withdrawn = self.publisher.post(f"/content/{item['item_id']}/withdraw",
                                        {"expected_version": item["version"], "reason": "改版回滚"})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        self.assertEqual(self.crops()["moon_radish"]["label"], "月光萝卜", "撤下之后回到内置值")


class JobContentTests(ContentTypeBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("job-owner")
        self.player.adopt_and_move_in("adopt-lan")

    def work_once(self) -> list[dict]:
        """去打一次工，推到收工与到家，返回这段时间新增的工资流水。"""
        with self.app.state.storage.connect() as conn:
            before = {r["tx_id"] for r in conn.execute("SELECT tx_id FROM economy_transactions WHERE type = 'web_job_income'")}
        departed = self.player.post("/journey/depart", {"destination_key": "work:florist"})
        self.assertEqual(departed.status_code, 200, departed.text)
        self.clock.advance(hours=4)
        self.run_background()
        with self.app.state.storage.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT tx_id, amounts_json, reason FROM economy_transactions WHERE type = 'web_job_income'")]
        return [r for r in rows if r["tx_id"] not in before]

    def test_published_pay_is_used_by_new_work_and_old_wages_are_untouched(self):
        import json

        first = self.work_once()
        self.assertEqual(len(first), 1, first)
        first_pay = json.loads(first[0]["amounts_json"])["travel_coin"]
        self.assertEqual(first_pay, 16, "花店内置工钱是 16")

        self.publish("job", "florist", {"label": "在花店帮忙", "pay": 30, "hours": 2})

        second = self.work_once()
        self.assertEqual(len(second), 1, second)
        self.assertEqual(json.loads(second[0]["amounts_json"])["travel_coin"], 30, "新一次打工要用已发布的工钱")

        with self.app.state.storage.connect() as conn:
            kept = conn.execute("SELECT amounts_json FROM economy_transactions WHERE tx_id = ?", (first[0]["tx_id"],)).fetchone()
        self.assertEqual(json.loads(kept["amounts_json"])["travel_coin"], first_pay, "已经结算过的工资一分都不能改")

    def test_world_rule_fields_cannot_be_published(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "job", "slug": "florist", "title": "x",
            "body": {"label": "在花店帮忙", "pay": 30, "hours": 2, "keyword": "任意", "habitats": ["seaside"]}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual({i["field"] for i in check["issues"]}, {"keyword", "habitats"})

    def test_pay_bounds_are_enforced(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "job", "slug": "florist", "title": "x",
            "body": {"label": "在花店帮忙", "pay": 100000, "hours": 2}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual([i["field"] for i in check["issues"]], ["pay"])


class ResidentContentTests(ContentTypeBase):
    def candidates(self, player) -> dict[str, dict]:
        response = player.get("/adoption/candidates")
        self.assertEqual(response.status_code, 200, response.text)
        return {row["candidate_id"]: row for row in response.json()}

    def test_published_copy_reaches_the_adoption_list(self):
        player = self.user("resident-reader")
        before = self.candidates(player)["adopt-lan"]
        self.publish("resident", "adopt-lan",
                     {"personality": "慢热，喜欢在窗台上晒太阳", "dream": "想看一次真正的海", "source_note": "PetSoul 原创伙伴"})
        after = self.candidates(player)["adopt-lan"]
        self.assertEqual(after["personality"], "慢热，喜欢在窗台上晒太阳")
        self.assertEqual(after["dream"], "想看一次真正的海")
        self.assertEqual(after["name"], before["name"], "名字属于身份，不能被运营改")
        self.assertEqual(after["species"], before["species"])

    def test_identity_fields_cannot_be_published(self):
        check = self.publisher.post("/content/validate", {
            "content_type": "resident", "slug": "adopt-lan", "title": "x",
            "body": {"personality": "安静", "dream": "看海", "name": "换个名字", "species": "dog"}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual({i["field"] for i in check["issues"]}, {"name", "species"})
        self.assertTrue(any("身份" in i["message"] for i in check["issues"]), check)

    def test_an_adopted_resident_can_no_longer_be_edited(self):
        adopter = self.user("resident-adopter")
        adopter.adopt_and_move_in("adopt-lan")
        blocked = self.try_publish("resident", "adopt-lan", {"personality": "改一下", "dream": "改一下"})
        self.assertEqual(blocked.status_code, 422, blocked.text)
        self.assertIn("已经被领养", blocked.json()["error"]["message"], "状态说人话，不给原始代码")

    def test_resident_adopted_after_the_draft_is_skipped_at_publish_time(self):
        """草稿建好之后居民被领养了：发布时如实跳过，不改写已领养居民的资料。"""
        created = self.publisher.post("/content", {"content_type": "resident", "slug": "adopt-doudou",
                                                   "title": "豆豆文案", "body": {"personality": "爱跑", "dream": "追蝴蝶"}})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]

        adopter = self.user("doudou-adopter")
        adopter.adopt_and_move_in("adopt-doudou")

        published = self.publisher.post(f"/content/{item['item_id']}/publish",
                                        {"revision": 1, "expected_version": item["version"], "reason": "晚到的发布"})
        self.assertEqual(published.status_code, 200, published.text)
        self.assertTrue(published.json()["resident_apply"].startswith("skipped:"), published.text)
        self.assertIn("名单上的文案没有改", published.json()["resident_apply_note"], "跳过了要当场说出来，不能只显示发布成功")
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT personality FROM web_adoption_candidates WHERE candidate_id = 'adopt-doudou'").fetchone()
        self.assertNotEqual(row["personality"], "爱跑", "已领养居民的资料不能被发布改写")


class OverlayFallbackTests(AdminTestBase):
    def test_catalogs_fall_back_to_builtin_when_the_resolver_blows_up(self):
        """后台读不出来不能让世界推进失败：解析器抛异常时目录回落到内置值。"""
        from app.content_overlay import set_resolver
        from app.web_farm.service import CROPS
        from app.web_journey.local import JOBS

        original_label = CROPS.base_of("sun_pea").label

        def boom(content_type: str, slug: str):
            raise RuntimeError("发布表读不到")

        set_resolver(boom)
        try:
            self.assertEqual(CROPS["sun_pea"].label, original_label)
            self.assertEqual(JOBS["florist"].pay, JOBS.base_of("florist").pay)
            self.assertEqual(len(JOBS.values()), len(JOBS))
        finally:
            set_resolver(self.app.state.admin.content.live)


if __name__ == "__main__":
    unittest.main()
