"""照片链路在**正式装配**上确实接上了：同连接授权读口、同事务登记、该不该生成的判断。

（CR-A14 / image-revocation-20260923 / COORD-C-ATOMIC 方案 B）

为什么要单独有这一条：`on_unknown` / `on_retrying` 那次就是"实现写好了、用例里手工装上回调也过了，
正式组合根却始终是 None"——网页上主人点了重画，页面还写着"没画成"。
所以这里**不手工安装任何回调**，直接建真实应用，断言组合根把 `consent_in` 接上了、而且它真的在调用方的
连接上读。手工注入的局部单测不能替代这一条。

不联网、不调用真实供应商、不产生付费调用。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class PhotoConsentWiringTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("consent-wiring-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        self.illustrations = self.web.illustrations
        self.assertEqual(self.owner.patch("/settings", {"generated_photos": True}).status_code, 200)
        self.household_id = self.web.households.household_of_pet(self.pet)
        self.assertTrue(self.household_id, "前提：这只宠物有家庭")

    def test_the_composition_root_actually_wires_the_same_connection_read(self) -> None:
        """presence：正式装配里它必须不是 None。缺注入时 A 侧会 hold 并记 consent_check_unwired，
        那是安全的降级——但对已经接好的正式链路来说，None 就是漏接。"""
        self.assertIsNotNone(self.illustrations.consent_in, "组合根没有接上同连接授权读口")

    def test_it_answers_the_same_as_the_existing_household_authorisation(self) -> None:
        """语义必须与现有 `opted_in` 一致：全仓只有一份实现，两者不可能漂移。"""
        with self.web.journeys.storage.connect() as conn:
            self.assertTrue(self.illustrations.consent_in(conn, self.owner.user_id, self.pet))
        self.assertTrue(self.illustrations.opted_in(self.owner.user_id, self.pet))

    def test_a_revocation_inside_the_open_transaction_is_visible_to_it(self) -> None:
        """这就是 FINDING 里"写入前撤权仍发布 ready"的根因：另开连接读到的是事务外的旧值。

        在一个**开着的写事务**里撤销，同连接读口必须当场看见；而自己开连接的 `opted_in` 此刻还看不见。
        """
        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE web_households SET generated_photos = 0 WHERE household_id = ?", (self.household_id,))

            inside = self.illustrations.consent_in(conn, self.owner.user_id, self.pet)
            outside = self.illustrations.opted_in(self.owner.user_id, self.pet)
            still_open = conn.in_transaction

            conn.rollback()

        self.assertFalse(inside, "同连接读口必须看见这个事务里刚撤销的授权")
        self.assertTrue(outside, "前提：另开连接此刻确实还读不到——这正是要修的那个缺口")
        self.assertTrue(still_open, "读口不能替调用方收尾：调用之后事务还得开着")

    def test_it_does_not_commit_the_callers_transaction(self) -> None:
        """回滚之后授权要回到原样——说明那次撤销没有被这个读口顺手提交掉。"""
        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE web_households SET generated_photos = 0 WHERE household_id = ?", (self.household_id,))
            self.illustrations.consent_in(conn, self.owner.user_id, self.pet)
            conn.rollback()

        self.assertTrue(self.illustrations.opted_in(self.owner.user_id, self.pet), "回滚之后授权应当还在")

    def test_a_pet_without_a_household_is_refused(self) -> None:
        """没有家庭的居民一律不生图：授权不明时宁可少发一张，也不发出付费调用。"""
        with self.web.journeys.storage.connect() as conn:
            self.assertFalse(self.illustrations.consent_in(conn, self.owner.user_id, "PJ-NOBODY"))
            self.assertFalse(self.illustrations.consent_in(conn, self.owner.user_id, None))


class PhotoChainWiringTests(WebPlatformTestBase):
    """同事务登记与“该不该生成”这两处接线。C 的服务里它们的默认值分别是 None 与 False，
    **不接就等于一张照片都不生成**（而且 C 会抛 photo_not_wired），所以必须在正式装配上钉住。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("photo-chain-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.assertEqual(self.owner.patch("/settings", {"generated_photos": True}).status_code, 200)
        self.journeys = self.web.journeys

    def visit_and_journey(self, destination_key: str):
        from types import SimpleNamespace

        place = {"name": "示例·海边咖啡馆", "category": "咖啡馆", "timezone": "Asia/Hong_Kong"}
        return (SimpleNamespace(visit_id="vs-0001", place=dict(place, place_id="world:local:cafe"), version=1),
                SimpleNamespace(user_id=self.owner.user_id, pet_id=self.owner.pet_id, city="香港", destination_key=destination_key))

    def enqueue(self, destination_key: str) -> dict:
        """走真实的同事务登记口，把排进去的那条任务 payload 取出来。"""
        import json

        self.web.illustrations.available = lambda: True  # 这个环境没配生图供应商；它代表“供应商已配置”，不是本条要验的东西
        visit, journey = self.visit_and_journey(destination_key)
        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task_id = self.journeys.photo_request_in(conn, visit, journey, captured_at=self.clock.now,
                                                     source_key=f"photo:{destination_key}")
            row = conn.execute("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
            payload = json.loads(row["payload_json"])
        return payload

    def test_the_reference_origin_is_wired_and_never_guesses(self) -> None:
        """参考照**是从哪来的**：导演要求标注来源（CR-A15）。这一条钉两件事——

        接上了（不接的话领养来的新伙伴永远拍不出主动照片，而且没有任何症状）；
        以及**拿不准时返回 None**，绝不把我们自己画的基准照冒名成主人原照。
        """
        origin_of = self.web.illustrations.reference_origin_of
        self.assertIsNotNone(origin_of, "组合根没有接上参考照来源")

        self.assertIsNone(origin_of("PJ-NOBODY"), "没有这只宠物就没有来源，不能编一个")
        adopted = origin_of(self.owner.pet_id)
        self.assertIn(adopted, (None, "owner_original", "original_companion"),
                      f"只能是导演认的那两种，或者如实说不知道：{adopted}")

    def test_the_outcome_reader_is_wired_on_the_same_connection(self) -> None:
        """"确认没画成"与"结果未确认"要分得开，而且要在**调用方那个 conn** 上读。

        另开连接读到的是事务外的旧值：晚到的 unknown 会被当成 failed 写进页面，
        主人看到"没画成"，而那次调用其实可能已经被受理、也已经计费。
        """
        reader = self.web.communicator.illustration_outcome_in
        self.assertIsNotNone(reader, "组合根没有接上同连接的结果读口")

        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO web_illustrations (illustration_id, user_id, pet_id, source_event_id, task_id, status, created_at, updated_at) "
                         "VALUES ('il-probe', ?, ?, 'src-probe', 'task-probe', 'failed', '2026-09-22T04:00:00+00:00', '2026-09-22T04:00:00+00:00')",
                         (self.owner.user_id, self.owner.pet_id))

            inside = reader(conn, "task-probe")
            still_open = conn.in_transaction
            conn.rollback()

        self.assertIsNotNone(inside, "同连接必须看得见这个事务里刚写下的那条记录")
        self.assertTrue(still_open, "读口不能替调用方收尾")

    def test_the_atomic_registration_hook_is_wired(self) -> None:
        """没接的话 C 会直接抛 photo_not_wired——宁可不拍，也不留下“镜头没响、队列里却多一张图”的孤儿任务。"""
        self.assertIsNotNone(self.journeys.photo_request_in, "组合根没有接上同事务登记口")

    def test_generation_is_on_only_when_the_provider_and_the_household_both_say_yes(self) -> None:
        visit, journey = self.visit_and_journey("local:cafe")

        self.web.illustrations.available = lambda: False
        self.assertFalse(self.journeys.photo_generation_on(visit, journey), "没配生图供应商就不该走拍照这条路")

        self.web.illustrations.available = lambda: True
        self.assertTrue(self.journeys.photo_generation_on(visit, journey), "供应商可用 ＋ 这家开了生成照片")

        self.assertEqual(self.owner.patch("/settings", {"generated_photos": False}).status_code, 200)
        self.assertFalse(self.journeys.photo_generation_on(visit, journey), "这家关掉之后就不该再生成")

    def test_a_cafe_visit_carries_the_scene_key_and_the_verified_fact(self) -> None:
        payload = self.enqueue("local:cafe")

        self.assertEqual(payload.get("scene_key"), "cafe")
        facts = payload.get("scene_facts")
        self.assertIsInstance(facts, list, f"形状以消费端为准：SceneFact 的字典列表，不是 token 元组：{payload}")
        self.assertEqual({f["token"] for f in facts}, {"at_cafe"})
        for fact in facts:
            self.assertEqual(set(fact), {"fact_id", "token", "pet_id", "household_id", "event_id", "verified"},
                             f"六个键一个都不能少，少了消费端当成没有事实 → 一直 hold：{fact}")
            self.assertTrue(fact["verified"], "只认 verified is True 的条目")
            self.assertEqual(fact["event_id"], "photo:local:cafe", "event_id 必须等于 source_key（跨重试不变）")
            self.assertEqual(fact["fact_id"], "photo:local:cafe:at_cafe",
                             "fact_id 要带上 event_id，否则每一次到访都是同一个字符串、事后追不到哪一次")
            self.assertEqual(fact["pet_id"], self.owner.pet_id)
            self.assertTrue(fact["household_id"], "要说清这条事实属于哪个家庭")
        self.assertIn("at_cafe", payload.get("fact_basis", {}), "每条事实都要有依据，给诊断用")
        self.assertTrue(payload.get("household_id"), "家庭编号要带上")
        # 代数只由**进照片的那几个字段**算（地点身份/名字/类目/时区），不是 visit.version：
        # 登记发生在 _commit_activity 之前，提交后 version 就 +1，主人再选座点饮品还会继续加，
        # 用它的话每张照片登记完当场就过期。
        from app.web_agent.photo_scene import fact_revision

        visit, _journey = self.visit_and_journey("local:cafe")
        self.assertEqual(payload.get("revision"), fact_revision(visit.place), "代数要由照片所据的事实算")
        self.assertIsInstance(payload.get("revision"), int)
        self.assertEqual(payload.get("place_timezone"), "Asia/Hong_Kong", "拍照时刻要按真实地点换算")
        self.assertNotIn("hold_reason", payload, "事实齐了就不该有 hold 原因")

    def test_normal_life_does_not_expire_an_already_registered_photo(self) -> None:
        """正常生活（选座、点饮品、活动结果）不该让已登记的照片过期；只有地点或类目被更正才该 hold。"""
        from app.web_agent.photo_scene import fact_revision

        place = {"name": "示例·海边咖啡馆", "category": "咖啡馆", "timezone": "Asia/Hong_Kong", "place_id": "world:local:cafe"}
        before = fact_revision(place)

        self.assertEqual(fact_revision(dict(place, activities=["点了杯饮品"])), before, "正常生活不动这几个字段")
        self.assertNotEqual(fact_revision(dict(place, category="餐厅")), before, "类目被更正就该变")
        self.assertNotEqual(fact_revision(dict(place, place_id="amap:B0OTHER")), before, "换了地点就该变")
        self.assertIsNone(fact_revision(None), "没有地点就没有代数，交给消费端 hold")

    def test_a_stroll_is_not_handed_to_the_director(self) -> None:
        """散步没有对应场景键：不传，照旧走模板。这是**正常**的旧路，不是 hold。"""
        payload = self.enqueue("local:stroll")

        self.assertNotIn("scene_key", payload, f"非目标场景不该带场景键：{payload}")
        self.assertNotIn("scene_facts", payload, "非目标场景不该带事实")
        self.assertNotIn("hold_reason", payload, "非目标场景没有“缺事实”一说")



if __name__ == "__main__":
    unittest.main()
