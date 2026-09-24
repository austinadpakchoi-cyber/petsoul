"""第九批：宠物运行总览（心跳 / 大脑 / 钱袋子）、暂停与恢复、每天生了多少张图、内容条目说中文名。

数据都用真实的领域对象造：规则生活真跑一轮、决策编号走 RuntimeStore.open_decision、额度走 BudgetLedger 的预占与结算。
总览只读——用例核「看一次不改运行表」。暂停只在各条运行线都认它的范围内开放：规则生活的闸落地后对驿站居民开放，
用例真跑规则生活、带对照（同一轮里没暂停的那位确实出门）；玩家自己的宠物还挡着（到点回复与主动来信还不认暂停）。
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

from admin_base import AdminTestBase
from test_admin_belongings import WorldFixture

from app.web_admin import labels as L
from app.web_admin import pet_runtime
from app.web_platform.budget import BudgetLedger, BudgetLimit


def _runtime(case, pet_id: str) -> dict:
    with case.app.state.storage.connect() as conn:
        row = conn.execute("SELECT * FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()
    return dict(row) if row else {}


def _a_resident(case) -> str:
    with case.app.state.storage.connect() as conn:
        return conn.execute("SELECT pet_id FROM web_residents WHERE status = 'resident' ORDER BY pet_id LIMIT 1").fetchone()["pet_id"]


class OverviewTests(WorldFixture):
    def test_every_pet_is_listed_from_recorded_facts(self):
        self.app.state.web.life.run(self.clock.now)  # 真跑一轮规则生活：记下这一时段的决定（可能出门）
        runtime = self.app.state.web.projector.runtime
        runtime.open_decision(self.alice.pet_id, self.clock.now, new_id=lambda: "op-thinking-1")  # 一轮还没结束的思考
        before = _runtime(self, self.alice.pet_id)

        support = self.staff("runtime-support", ["support"])  # pet.read + economy.read，没有 provider.read
        support.login_ok()
        body = support.get("/pets-runtime").json()
        rows = {row["pet_id"]: row for row in body["pets"]}
        alice = rows[self.alice.pet_id]
        self.assertEqual((alice["kind"], alice["owner_name"]["username"]), ("household", "belong-alice"))
        self.assertEqual(alice["brain"]["state"], "thinking")
        self.assertIsInstance(alice["wallet"], int, "有 economy.read 就给钱袋子")
        self.assertIsNone(alice["usage_today"], "没有 provider.read 不给 AI 用量")
        resident = rows[_a_resident(self)]
        self.assertEqual(resident["kind"], "resident")
        self.assertTrue(resident["residence"])
        self.assertEqual(body["modes"]["pause_open"], True, "规则生活的闸已落地：对驿站居民开放")
        for row in body["pets"]:
            self.assertIn(row["heartbeat"]["state"], L.HEARTBEAT_STATE)
            self.assertIn(row["brain"]["state"], L.BRAIN_STATE)
        decided = [row for row in body["pets"] if row["rule_life"]]
        self.assertTrue(decided, "规则生活刚跑过一轮，至少有一只记下了决定")
        for row in decided:
            self.assertTrue(row["rule_life"]["decision"]["label"], f"规则生活的决定要有说法：{row['rule_life']}")
        self.assertEqual(_runtime(self, self.alice.pet_id), before, "看一次总览不改运行表")

        self.clock.advance(minutes=11)
        again = {row["pet_id"]: row for row in support.get("/pets-runtime").json()["pets"]}
        self.assertEqual(again[self.alice.pet_id]["brain"]["state"], "stuck", "一轮思考超过 10 分钟还没结束，要提醒")
        audit = support.get("/audit?action=pet.runtime_list").json()["entries"]
        self.assertEqual(len(audit), 2, "看一次留一条")
        self.assertEqual(audit[0]["changes"]["sections"], ["runtime", "wallets"])

    def test_sections_follow_permissions(self):
        sre = self.staff("runtime-sre", ["sre"])  # pet.read + provider.read，没有 economy.read
        sre.login_ok()
        rows = {row["pet_id"]: row for row in sre.get("/pets-runtime").json()["pets"]}
        self.assertIsNone(rows[self.alice.pet_id]["wallet"], "钱袋子是游戏资产：没有 economy.read 不给")
        self.assertIsInstance(rows[self.alice.pet_id]["usage_today"], dict)
        for username, roles in (("runtime-editor", ["content_editor"]), ("runtime-moderator", ["moderator"])):
            staff = self.staff(username, roles)
            staff.login_ok()
            self.assert_admin_error(staff.get("/pets-runtime"), 403, "FORBIDDEN")

    def test_ai_usage_today_comes_from_the_budget_counters(self):
        ledger = BudgetLedger(self.app.state.storage)
        pet = self.alice.pet_id
        reserved = ledger.reserve("op-brain-1", provider="llm", purpose="life_plan", subject_scope=f"pet:{pet}",
                                  limits=[BudgetLimit(f"pet:{pet}:life_plan", 12)], now=self.clock.now)
        ledger.settle(reserved, "succeeded", now=self.clock.now)
        ledger.reserve("op-brain-2", provider="llm", purpose="life_plan", subject_scope=f"pet:{pet}",
                       limits=[BudgetLimit(f"pet:{pet}:life_plan", 12)], now=self.clock.now)  # 还在途
        sre = self.staff("usage-sre", ["sre"])
        sre.login_ok()
        row = next(r for r in sre.get("/pets-runtime").json()["pets"] if r["pet_id"] == pet)
        self.assertEqual(row["usage_today"]["life_plan"], {"used": 1, "inflight": 1})


class PauseTests(WorldFixture):
    def residents(self, n: int) -> list[str]:
        with self.app.state.storage.connect() as conn:
            rows = conn.execute("SELECT pet_id FROM web_residents WHERE status = 'resident' ORDER BY pet_id LIMIT ?", (n,)).fetchall()
        self.assertEqual(len(rows), n, "前提：测试库里有足够的驿站居民")
        return [r["pet_id"] for r in rows]

    def test_residents_are_open_and_owned_pets_are_not_yet(self):
        """规则生活的闸已落地：驿站居民可以暂停；玩家自己的宠物还要等到点回复与主动来信也认暂停。"""
        self.assertTrue(pet_runtime.PAUSE_OPEN)
        sre = self.staff("pause-sre", ["sre"])
        sre.login_ok()
        resident = _a_resident(self)
        self.assertIsNone(sre.get(f"/pets/{resident}/pause/preview").json()["blocked_reason"])
        owned = sre.get(f"/pets/{self.alice.pet_id}/pause/preview").json()
        self.assertIn("到点回复", owned["blocked_reason"])
        refused = sre.post(f"/pets/{self.alice.pet_id}/pause", {"paused": True, "reason": "想暂停玩家的宠物"})
        self.assert_admin_error(refused, 409, "CONFLICT")
        self.assertEqual(_runtime(self, self.alice.pet_id).get("maintenance", 0), 0, "玩家的宠物：一个字节都不写")

    def test_pause_needs_pet_maintain(self):
        support = self.staff("pause-support", ["support"])
        support.login_ok()
        self.assert_admin_error(support.post(f"/pets/{_a_resident(self)}/pause", {"paused": True, "reason": "客服想暂停"}), 403, "FORBIDDEN")

    def test_the_command_itself(self):
        """只写 maintenance 一列并换代、原因必填、版本检查、同号重放不重复生效、审计。"""
        sre = self.staff("pause-sre-cmd", ["sre"])
        sre.login_ok()
        resident = _a_resident(self)
        before = _runtime(self, resident)
        self.assert_admin_error(sre.post(f"/pets/{resident}/pause", {"paused": True, "reason": "短"}), 422, "VALIDATION_FAILED")
        paused = sre.post(f"/pets/{resident}/pause", {"paused": True, "reason": "居民行为异常，先暂停观察", "expected_version": 0},
                          key="op-pause-resident-1")
        self.assertEqual(paused.status_code, 200, paused.text)
        after = _runtime(self, resident)
        self.assertEqual(after["maintenance"], 1)
        self.assertEqual(after["runtime_epoch"], before.get("runtime_epoch", 0) + 1, "同一事务里换代：在途的思考提交时作废")
        self.assertEqual((after.get("last_evaluated_at"), after.get("next_check_at")),
                         (before.get("last_evaluated_at"), before.get("next_check_at")), "心跳自己的标记不碰")
        replay = sre.post(f"/pets/{resident}/pause", {"paused": True, "reason": "居民行为异常，先暂停观察", "expected_version": 0},
                          key="op-pause-resident-1")
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(_runtime(self, resident)["runtime_epoch"], after["runtime_epoch"], "同号重放不重复换代")
        self.assertTrue(self.app.state.web.projector.runtime.paused(resident), "与运行线同一个口径：共享谓词认得它")
        due = self.app.state.web.projector.runtime.due_pets(self.clock.now, watchdog=timedelta(minutes=5), roster=[resident])
        self.assertNotIn(resident, [pet for pet, _ in due], "暂停的宠物不进心跳候选")
        self.assert_admin_error(sre.post(f"/pets/{resident}/pause", {"paused": True, "reason": "再暂停一次看看", "expected_version": 1}),
                                409, "CONFLICT")
        self.assert_admin_error(sre.post(f"/pets/{resident}/pause", {"paused": False, "reason": "用旧版本号恢复", "expected_version": 0}),
                                409, "VERSION_CONFLICT")
        owner = self.owner()
        overview = owner.get("/overview").json()
        attention = {m["key"]: m["value"] for m in overview["attention"]}
        self.assertEqual(attention.get("pets.paused"), 1, "首页「需要处理」里看得到被暂停的宠物")
        late = next(m for m in overview["metrics"] if m["key"] == "pets.heartbeat_late")
        # 测试环境按配置是开着的（runner=embedded，只是没起执行者）：该跑就算「心跳过点」；按配置关着时不算，见 test_admin_review10
        self.assertIsInstance(late["value"], int)
        resumed = sre.post(f"/pets/{resident}/pause", {"paused": False, "reason": "观察结束，恢复运行", "expected_version": 1})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(_runtime(self, resident)["maintenance"], 0)
        audit = sre.get("/audit?action=pet.pause").json()["entries"]
        self.assertEqual([(e["target_id"], e["reason"]) for e in audit], [(resident, "居民行为异常，先暂停观察")])
        self.assertEqual(sre.get("/audit?action=pet.resume").json()["entries"][0]["changes"]["to"], "running")
        row = next(r for r in sre.get("/pets-runtime").json()["pets"] if r["pet_id"] == resident)
        self.assertEqual((row["paused"], row["pause_record"]["version"], row["pause_record"]["reason"]), (False, 2, "观察结束，恢复运行"))

    def test_a_paused_resident_really_stops_going_out(self):
        """真跑规则生活，带对照：同一轮里没暂停的那位确实出门，暂停的那位不出门、也不占这个时段；恢复后照常出门。"""
        import app.web_agent.life as life_mod
        from app.schemas.base import EconomyTransactionType

        patch = mock.patch.object(life_mod, "_roll", lambda *parts: 0.0)  # 掷骰恒为 0：这一轮一定想出门
        patch.start()
        self.addCleanup(patch.stop)
        control, paused = self.residents(2)
        web = self.app.state.web
        for pet in (control, paused):  # 居民零余额起步：先给旅费，免得「没出门」只是因为没钱
            web.economy.apply(pet, 60, EconomyTransactionType.web_reward, f"test:topup:{pet}", reason="测试旅费", source="test")
        sre = self.staff("pause-sre-life", ["sre"])
        sre.login_ok()
        self.assertEqual(sre.post(f"/pets/{paused}/pause", {"paused": True, "reason": "先暂停这一位，看它还出不出门"}).status_code, 200)

        web.life.run(self.clock.now)

        went = lambda pet: web.journeys.repo.active_for_pet(pet) is not None  # noqa: E731
        self.assertTrue(went(control), "对照不成立：这一轮本来就不会出门，那「被拦住」证明不了什么")
        self.assertFalse(went(paused), "暂停的居民不该被规则生活送出门")
        with self.app.state.storage.connect() as conn:
            slots = conn.execute("SELECT COUNT(*) FROM web_pet_decisions WHERE pet_id = ?", (paused,)).fetchone()[0]
        self.assertEqual(slots, 0, "被暂停的这一轮不占决定名额")

        self.assertEqual(sre.post(f"/pets/{paused}/pause", {"paused": False, "reason": "观察结束，恢复运行"}).status_code, 200)
        web.life.run(self.clock.now)
        self.assertTrue(went(paused), "恢复之后照常出门：暂停不把 TA 永久关着")

    def test_a_go_decision_that_could_not_depart_reads_as_a_decision(self):
        """规则生活在出发之前就记下「go:<地点>」，出发被拒也不撤回（领域有意这样设计，见 web_agent/life.py）。
        后台那一栏是「这个时段的决定」：说法要写成决定、不能读成已经出门；旁边没有进行中的旅程（Q 独立验收报的）。"""
        import app.web_agent.life as life_mod
        from app.schemas.base import EconomyTransactionType

        want = mock.patch.object(life_mod, "_roll", lambda *parts: 0.0)  # 掷骰恒为 0：这一轮一定想出门
        want.start()
        self.addCleanup(want.stop)
        [pet] = self.residents(1)
        web = self.app.state.web
        web.economy.apply(pet, 60, EconomyTransactionType.web_reward, f"test:topup:{pet}", reason="测试旅费", source="test")
        refused = mock.patch.object(web.journeys, "depart", side_effect=RuntimeError("测试：出发被拦下"))  # 规则生活用的就是这个对象
        refused.start()
        self.addCleanup(refused.stop)

        web.life.run(self.clock.now)

        self.assertIsNone(web.journeys.repo.active_for_pet(pet), "前提：出发被拦下，没有进行中的旅程")
        row = next(r for r in self.owner().get("/pets-runtime").json()["pets"] if r["pet_id"] == pet)
        self.assertIsNone(row["trip"])
        self.assertTrue(row["rule_life"]["decision"]["code"].startswith("go:"), "领域照样记下了这个时段的决定")
        self.assertTrue(row["rule_life"]["decision"]["label"].startswith("决定出门去「"), "说法是决定，不是已经出门")


class ImagesDailyTests(AdminTestBase):
    def test_each_day_splits_calls_and_counted_units_by_purpose_and_result(self):
        from web_base import LUNCH_UTC, FakeClock

        clock = FakeClock(LUNCH_UTC).install(self)
        ledger = BudgetLedger(self.app.state.storage)
        limits = [BudgetLimit("provider:image:daily", 100)]

        def call(op: str, purpose: str, outcome: str | None) -> None:
            reserved = ledger.reserve(op, provider="image", purpose=purpose, limits=limits, subject_scope="pet:PJ-TEST", now=clock.now)
            if outcome:
                ledger.settle(reserved, outcome, now=clock.now)

        call("img-1", "illustration", "succeeded")
        call("img-2", "illustration", "failed")
        call("img-3", "illustration", "not_sent")
        call("img-4", "character", "unknown")
        call("img-5", "character", None)  # 还在路上
        sre = self.staff("images-sre", ["sre"])
        sre.login_ok()
        body = sre.get("/usage/images-daily").json()
        today = next(day for day in body["days"] if day["day"] == LUNCH_UTC.date().isoformat())
        illustration, character = today["purposes"]["illustration"], today["purposes"]["character"]
        self.assertEqual(illustration["buckets"], {"ok": 1, "failed": 1, "not_sent": 1})
        self.assertEqual((illustration["calls"], illustration["units"]), (3, 2), "没发出的计 0：调用 3 次、计入 2 张")
        self.assertEqual(character["buckets"], {"unknown": 1, "inflight": 1})
        self.assertEqual((character["calls"], character["units"]), (2, 1), "在途的还没计：调用 2 次、计入 1 张")
        self.assertEqual(today["total"], {"calls": 5, "units": 3})
        self.assertEqual(today["global_counter"]["used"] + today["global_counter"]["inflight"], 4,
                         "全站计数器：已用 3＋在途 1（没发出的已退回）")
        self.assertEqual(set(body["caps"]), {"global_daily", "per_pet_daily"})
        for bucket in {**illustration["buckets"], **character["buckets"]}:
            self.assertIn(bucket, L.IMAGE_BUCKET)
        support = self.staff("images-support", ["support"])
        support.login_ok()
        self.assert_admin_error(support.get("/usage/images-daily"), 403, "FORBIDDEN")


class ContentNamesTests(AdminTestBase):
    def test_sources_and_errors_use_names_not_keys(self):
        editor = self.staff("names-editor", ["content_editor"])
        editor.login_ok()
        for content_type in ("adventure", "crop", "job", "destination", "resident"):
            sources = editor.get(f"/content-sources/{content_type}").json()["sources"]
            self.assertTrue(sources)
            for source in sources:
                self.assertTrue(source["name"] and source["name"] != source["slug"], f"{content_type}：下拉框要显示中文名")
        wrong = editor.post("/content", {"content_type": "adventure", "slug": "no-such-thing", "title": "x",
                                         "body": {"title": "x", "badge": "y", "story": "{pet}"}})
        self.assert_admin_error(wrong, 422, "VALIDATION_FAILED")
        self.assertIn("咖啡馆小侦探", wrong.json()["error"]["message"])
        self.assertNotIn("cafe_detective", wrong.json()["error"]["message"])

    def test_publish_diff_and_option_errors_are_in_words(self):
        publisher = self.staff("names-publisher", ["content_publisher"])
        publisher.login_ok()
        created = publisher.post("/content", {"content_type": "announcement", "slug": "notice-names", "title": "维护通知",
                                              "body": {"title": "维护通知", "body": "今晚维护", "severity": "loud", "audience": "all"}})
        self.assertEqual(created.status_code, 201, created.text)
        issue = next(i for i in created.json()["issues"] if i["field"] == "severity")
        self.assertIn("一般 / 通知 / 维护", issue["message"])
        fixed = publisher.put(f"/content/{created.json()['item']['item_id']}",
                              {"body": {"title": "维护通知", "body": "今晚维护", "severity": "notice", "audience": "all"},
                               "expected_version": created.json()["item"]["version"]})
        self.assertEqual(fixed.status_code, 200, fixed.text)
        published = publisher.post(f"/content/{created.json()['item']['item_id']}/publish",
                                   {"revision": 2, "expected_version": fixed.json()["item"]["version"], "reason": "发布维护通知"})
        self.assertEqual(published.status_code, 200, published.text)
        self.assertIn("标题", published.json()["diff_summary"])
        self.assertNotIn("title", published.json()["diff_summary"])


if __name__ == "__main__":
    unittest.main()
