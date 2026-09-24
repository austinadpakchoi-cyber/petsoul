"""每宠运行投影 + 心跳 shadow（包 B 接入第一步）：真实库 → RuntimeState / HeartbeatFacts → 纯策略结论，只记录不执行。"""

from __future__ import annotations

import hashlib
import unittest
from datetime import timedelta

from app.schemas.runtime_internal import HeartbeatAction
from app.web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat


class RuntimeShadowTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.chat = FakeChat(["不会被调用"])
        self.web.providers.chat = self.chat
        self.web.communicator.chat = self.chat
        self.owner = self.user("shadow-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.projector = self.web.projector

    def fingerprint(self) -> dict:
        with self.app.state.storage.connect() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            return {t: hashlib.sha1(repr([tuple(row) for row in conn.execute(f"SELECT * FROM {t}")]).encode("utf-8")).hexdigest() for t in tables}

    def runtime_row(self, pet_id: str) -> dict:
        return self.projector.runtime.row(pet_id)

    def test_projection_reads_where_the_pet_actually_is(self) -> None:
        state = self.projector.state(self.owner.pet_id, self.clock.now)
        self.assertEqual((state.primary_activity.kind, state.realm_id), ("at_home", "dev"))
        self.assertEqual(state.timezone, "Asia/Hong_Kong", "时区取家所在地，不是宿主机")
        self.assertTrue(state.household_id, "家庭宠物带 household_id")
        self.assertIsNotNone(state.sleep_window, "作息来自 DNA 画像")
        self.owner.post("/journey/depart", {"destination_key": "work:florist"})
        self.clock.advance(minutes=60)
        working = self.projector.state(self.owner.pet_id, self.clock.now)
        self.assertEqual(working.primary_activity.kind, "work")
        self.assertFalse(working.primary_activity.interruptible, "干活中不可打断")
        self.assertTrue(working.scene_ref.startswith("visit:"))
        self.assertEqual(working.versions.itinerary_version, 1)

    def test_due_work_becomes_a_commitment_and_the_policy_says_apply_rule(self) -> None:
        self.owner.post("/journey/depart", {"destination_key": "work:florist"})
        self.clock.advance(hours=3)  # 收工时间过了，后台还没结算
        facts = self.projector.facts(self.owner.pet_id, self.clock.now)
        self.assertEqual([(item.kind.value, item.commitment) for item in facts.due_items], [("journey", True)], "工钱是对家人的承诺")
        decision = evaluate(self.projector.state(self.owner.pet_id, self.clock.now), (), HeartbeatPolicy(), self.clock.now, facts=facts)
        self.assertEqual(decision.action, HeartbeatAction.APPLY_RULE, "到期的确定性事项优先执行规则，不请求大脑")
        self.assertTrue(any(intent.kind == "settle_due" for intent in decision.task_intents), decision.task_intents)
        self.run_background()
        self.assertEqual(self.projector.facts(self.owner.pet_id, self.clock.now).due_items, (), "结算之后没有到期事项了")

    def test_a_scheduled_trip_shows_as_getting_ready_at_home(self) -> None:
        journey = self.owner.post("/journey/depart", {"destination_key": "work:florist"}).json()
        later = self.clock.now + timedelta(hours=6)  # 改成“已经定好、六小时后才出门”（真实远行就是这样从开船时间反推的）
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_journeys SET departed_at = ?, completes_at = ? WHERE journey_id = ?",
                         (later.isoformat(), (later + timedelta(hours=3)).isoformat(), journey["journey_id"]))
        state = self.projector.state(self.owner.pet_id, self.clock.now)
        activity = state.primary_activity
        self.assertEqual((activity.kind, activity.ref), ("at_home", f"journey:{journey['journey_id']}"), "在家收拾东西，等着出门")
        self.assertEqual(activity.ends_at, later)
        self.assertFalse(activity.interruptible, "打断就赶不上已核验的班次")
        decision = evaluate(state, (), HeartbeatPolicy(), self.clock.now, facts=self.projector.facts(self.owner.pet_id, self.clock.now))
        self.assertLessEqual(decision.next_check_at, later, "下次检查不能晚于出门时刻")

    def test_queued_reply_is_a_due_item_without_reading_the_text(self) -> None:
        self.clock.now = self.clock.now.replace(hour=18)  # 香港凌晨，TA 睡着
        self.owner.post(f"/communicator/{self.owner.pet_id}/messages", {"client_message_id": "shadow-0001", "text": "睡了吗"})
        facts = self.projector.facts(self.owner.pet_id, self.clock.now.replace(hour=23, minute=59))
        replies = [item for item in facts.due_items if item.kind.value == "reply"]
        self.assertEqual(len(replies), 1)
        self.assertTrue(replies[0].commitment and replies[0].inputs if hasattr(replies[0], "inputs") else replies[0].commitment)
        self.assertNotIn("睡了吗", str(facts), "到期事项只带引用与时间，不带正文")

    def test_semantic_versions_change_when_the_facts_behind_them_change(self) -> None:
        pet = self.owner.pet_id
        start = self.projector.versions(pet)
        self.owner.post("/journey/depart", {"destination_key": "work:florist"})
        after_depart = self.projector.versions(pet)
        self.assertEqual(start.stale_fields(after_depart), ("activity_epoch",), "定了新行程就换代")
        self.clock.advance(minutes=30)
        self.run_background()  # 到店开工：主活动又变了
        after_visit = self.projector.versions(pet)
        self.assertEqual(after_depart.stale_fields(after_visit), ("activity_epoch",))
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        token = self.owner.post(f"/households/{household_id}/invites", {"role": "caregiver"}).json()["token"]
        member = self.user("shadow-member")
        member.post("/invites/accept", {"token": token})
        after_join = self.projector.versions(pet)
        self.assertEqual(after_visit.stale_fields(after_join), ("membership_epoch",), "家里多了一位家人就换代")
        self.owner.delete(f"/households/{household_id}/members/{member.user_id}")
        self.assertEqual(after_join.stale_fields(self.projector.versions(pet)), ("membership_epoch",), "移除成员也换代")

    def test_shadow_records_decisions_without_touching_the_world(self) -> None:
        self.owner.post("/journey/depart", {"destination_key": "work:florist"})
        self.clock.advance(hours=3)
        before = self.fingerprint()
        result = self.web.shadow.run(self.clock.now)
        after = self.fingerprint()
        self.assertGreaterEqual(result.evaluated, 1, "家里的宠物与驿站居民都评估到")
        self.assertGreaterEqual(result.actions.get("apply_rule", 0), 1, result.actions)
        self.assertEqual(result.unavailable, 0, "没有评估不了的宠物")
        self.assertEqual({t for t in after if after[t] != before.get(t)}, {"web_entity_runtime"}, "shadow 只写运行记录")
        self.assertEqual(self.chat.calls, [], "shadow 不调模型")
        row = self.runtime_row(self.owner.pet_id)
        self.assertTrue(row["last_evaluated_at"], "记下这次评估")
        self.assertTrue(row["next_check_at"], "记下下次检查时刻")
        self.assertEqual(self.projector.versions(self.owner.pet_id).itinerary_version, 1)

    def test_ops_runtime_answers_why_the_pet_is_quiet(self) -> None:
        self.owner.post("/journey/depart", {"destination_key": "work:florist"})
        self.clock.advance(minutes=60)
        self.run_background()  # 世界已经推到“正在干活”
        detail = self.client.get(f"/api/v1/web/ops/runtime/{self.owner.pet_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual((body["activity_kind"], body["interruptible"], body["brain_mode"]), ("work", False, "off"))
        self.assertEqual(body["timezone"], "Asia/Hong_Kong")
        self.assertEqual(body["heartbeat_action"], "continue", "活动进行中：继续，不请求大脑")
        self.assertTrue(body["next_check_at"], "什么时候再看")
        self.assertTrue(body["silence_reason"], "为什么安静")
        self.assertEqual(body["versions"]["itinerary"], 1)
        self.assertNotIn("text", detail.text, "不下发正文")
        forbidden = self.client.get(f"/api/v1/web/ops/runtime/{self.owner.pet_id}", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(forbidden.status_code, 403, "只给本机或管理令牌")
        self.assertEqual(self.client.get("/api/v1/web/ops/runtime/PJ-NOBODY").status_code, 404, "没有这只宠物就明确 404")
        self.clock.advance(hours=3)
        due = self.client.get(f"/api/v1/web/ops/runtime/{self.owner.pet_id}").json()
        self.assertEqual([(item["kind"], item["commitment"]) for item in due["due_items"]], [("journey", True)])
        self.assertEqual(due["heartbeat_action"], "apply_rule", "到期的确定性事项优先")

    def test_unknown_timezone_is_reported_not_guessed(self) -> None:
        from app.web_home.place import HomePlace

        class BrokenPlaces:  # 库里的时区认不出（数据坏了 / 新片区还没接时区）
            def get(self, home_id: str) -> HomePlace:
                return HomePlace("seaside", "海边", "hk-saikung", "西贡", "香港", 22.38, 114.27, "Mars/Base", True)

        self.projector.home_places = BrokenPlaces()
        state = self.projector.state(self.owner.pet_id, self.clock.now)
        self.assertEqual(state.timezone, "Mars/Base", "原样带上，不悄悄换成香港")
        decision = evaluate(state, (), HeartbeatPolicy(), self.clock.now, facts=self.projector.facts(self.owner.pet_id, self.clock.now))
        self.assertEqual(decision.action, HeartbeatAction.RECOVER)
        self.assertTrue(decision.next_check_at, "恢复类结论也要给下次检查时刻")


if __name__ == "__main__":
    unittest.main()
