"""每宠运行投影的两个口径问题（CR-B4、CR-B5）。

CR-B4 出门次数：心跳原来按"最近 24 小时"数，规则生活按"当地当天 0 点以来"数。
  跨午夜就会打架——心跳说"今天够了、不再规划"，规则生活却还允许出门。两处必须是同一个口径。

CR-B5 共享 RuntimeState 的两个字段：`pending_commitment_deadline` 恒为 None、`cognition_status` 恒为 "quiet"。
  任何按共享类型读状态的消费者（/ops/runtime、`facts_from_state` 最小模式）都看不到
  "有承诺待兑现 / 大脑不可用"，最小模式还会把承诺整个丢掉。

按到期取宠物（CR-B6）拆在 test_web_runtime_due_selection.py。
用真实装配与真实库，假时钟；不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.utils import iso
from app.web_runtime.heartbeat_policy import HeartbeatPolicy
from app.web_runtime.state import facts_from_state
from web_base import FakeClock, WebPlatformTestBase

HK = timezone(timedelta(hours=8))  # 这批夹具的宠物住在 Asia/Hong_Kong
LOCAL_NOON = datetime(2026, 9, 22, 12, 0, tzinfo=HK)


class RuntimeProjectionTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LOCAL_NOON.astimezone(timezone.utc)).install(self)
        self.owner = self.user("projection-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        self.projector = self.web.projector
        self.assertEqual(self.projector.state(self.pet, self.clock.now).timezone, "Asia/Hong_Kong", "前提：时区取到了")

    # ---- CR-B4 ----
    def went_out_at(self, local: datetime) -> None:
        """在当地时间 local 出过一趟门。直接写 web_journeys：这一条验的是**投影怎么数**，不是出门本身。"""
        with self.web.journeys.storage.connect() as conn:
            conn.execute("INSERT INTO web_journeys (journey_id, user_id, pet_id, home_id, destination_key, title, city, lifecycle, "
                         "itinerary_version, fee, departed_at, completes_at, created_at) "
                         "VALUES (?, ?, ?, ?, 'local:stroll', '附近散步', '香港', 'completed', 1, 0, ?, ?, ?)",
                         (f"j-{local:%m%d%H%M}", self.owner.user_id, self.pet, self.owner.home_id,
                          iso(local.astimezone(timezone.utc)), iso(local.astimezone(timezone.utc) + timedelta(hours=1)),
                          iso(local.astimezone(timezone.utc))))

    def projected_outings(self) -> int:
        return self.projector.facts(self.pet, self.clock.now).autonomy.outings_today

    def rule_engine_outings(self) -> int:
        """规则生活自己数的那一份：当地当天 0 点以来的出门记录（life.LifeEngine 的口径）。"""
        local = self.clock.now.astimezone(HK)
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return len(self.web.life._history(self.pet, day_start.astimezone(timezone.utc)))

    def test_outings_are_counted_by_the_local_day_not_a_rolling_window(self) -> None:
        self.went_out_at(datetime(2026, 9, 22, 20, 0, tzinfo=HK))  # 昨天晚上两趟
        self.went_out_at(datetime(2026, 9, 22, 22, 0, tzinfo=HK))
        self.clock.now = datetime(2026, 9, 23, 0, 30, tzinfo=HK).astimezone(timezone.utc)  # 刚过当地午夜

        self.assertEqual(self.projected_outings(), 0, "过了当地午夜就是新的一天：今天还没出过门")

    def test_across_midnight_the_heartbeat_and_the_rule_engine_agree(self) -> None:
        """CR-B4 的验收口径：跨午夜时两处必须给出同一个数。"""
        self.went_out_at(datetime(2026, 9, 22, 20, 0, tzinfo=HK))
        self.went_out_at(datetime(2026, 9, 22, 22, 0, tzinfo=HK))

        for label, local in (("午夜前", datetime(2026, 9, 22, 23, 0, tzinfo=HK)),
                             ("刚过午夜", datetime(2026, 9, 23, 0, 30, tzinfo=HK)),
                             ("第二天早上", datetime(2026, 9, 23, 9, 0, tzinfo=HK))):
            with self.subTest(when=label):
                self.clock.now = local.astimezone(timezone.utc)
                self.assertEqual(self.projected_outings(), self.rule_engine_outings(),
                                 f"{label}：心跳数的和规则生活数的必须一样")

    def test_before_midnight_todays_outings_still_count(self) -> None:
        """对照组：同一天之内照常算进去，别把"按当地日"修成"永远是 0"。"""
        self.went_out_at(datetime(2026, 9, 22, 9, 0, tzinfo=HK))
        self.went_out_at(datetime(2026, 9, 22, 11, 0, tzinfo=HK))

        self.assertEqual(self.projected_outings(), 2, "当地同一天里出的门要算数")

    def test_an_unknown_timezone_is_a_degraded_count_not_a_local_day(self) -> None:
        """时区取不到时退回最近 24 小时。这是**退化口径**，不是"当地自然日"——
        它只保证不比当地日少算（偏保守的一侧），**不能**拿来当作两处口径一致的证明。
        真正的处置仍然由心跳给出：时区不可用是一个明确的状态，不套用任何默认城市。"""
        from app.web_runtime.heartbeat_policy import evaluate
        from app.web_runtime.reasons import ReasonCode

        self.went_out_at(datetime(2026, 9, 22, 9, 0, tzinfo=HK))

        degraded = self.projector.facts(self.pet, self.clock.now, timezone=None)
        self.assertEqual(degraded.autonomy.outings_today, 1, "退化口径按最近 24 小时数")

        from dataclasses import replace

        blind = replace(self.projector.state(self.pet, self.clock.now), timezone=None)
        decision = evaluate(blind, (), HeartbeatPolicy(), self.clock.now, facts=degraded)
        self.assertIn(ReasonCode.TIMEZONE_UNKNOWN.value, decision.reason_codes, f"时区不可用要如实说出来：{decision.reason_codes}")

    # ---- CR-B5 ----
    def queue_a_reply(self, client_id: str) -> None:
        """TA 睡着的时候留言：回复排到醒来之后，这就成了一件"待兑现的承诺"。"""
        self.clock.now = datetime(2026, 9, 23, 2, 0, tzinfo=HK).astimezone(timezone.utc)  # 香港凌晨两点
        posted = self.owner.post(f"/communicator/{self.pet}/messages", {"client_message_id": client_id, "text": "在家吗"})
        self.assertEqual(posted.status_code, 200, posted.text)

    def test_the_shared_state_reports_a_pending_commitment(self) -> None:
        self.queue_a_reply("projection-0001")

        state = self.projector.state(self.pet, self.clock.now)
        facts = self.projector.facts(self.pet, self.clock.now)

        due = [item.due_at for item in facts.due_items if item.commitment]
        self.assertTrue(due, "前提：确实有一件待兑现的承诺")
        self.assertEqual(state.pending_commitment_deadline, min(due), "共享状态要说出最早那件承诺什么时候到期")

    def test_the_minimal_facts_keep_the_commitment(self) -> None:
        """最小模式（只拿得到共享 RuntimeState 的消费者）不能把承诺整个丢掉——这正是字段恒为空的代价。"""
        self.queue_a_reply("projection-0002")

        minimal = facts_from_state(self.projector.state(self.pet, self.clock.now))

        self.assertTrue([item for item in minimal.due_items if item.commitment], "最小事实里也要留着这件承诺")

    def test_the_shared_state_says_why_the_brain_is_quiet(self) -> None:
        disabled = self.projector.state(self.pet, self.clock.now)
        self.assertEqual(disabled.cognition_status, "disabled", "没开模型回信：如实说成 disabled，不是 quiet")

        self.owner.patch("/settings", {"model_replies": True})
        self.projector.model_available = lambda: True
        available = self.projector.state(self.pet, self.clock.now)
        self.assertEqual(available.cognition_status, "quiet", "开了又有额度：安静就是安静")

        resets_at = self.clock.now + timedelta(hours=6)
        self.projector.budget_facts = lambda pet_id: (0, resets_at)
        exhausted = self.projector.state(self.pet, self.clock.now)

        self.assertEqual(exhausted.cognition_status, "backoff", "额度用完要看得出来是在等，不是没事干")

    def test_the_state_and_the_facts_agree_when_facts_are_passed_in(self) -> None:
        """调用方已经算好 facts 时可以传进来，省掉一次重复计算，结论必须和自己算的一样。"""
        facts = self.projector.facts(self.pet, self.clock.now)

        passed = self.projector.state(self.pet, self.clock.now, facts=facts)
        derived = self.projector.state(self.pet, self.clock.now)

        self.assertEqual((passed.pending_commitment_deadline, passed.cognition_status),
                         (derived.pending_commitment_deadline, derived.cognition_status))


class ExamAndRefTests(WebPlatformTestBase):
    """CR-B7 时钟健康、CR-B8 三小项、CR-B11 "留在家"的显式有效期。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LOCAL_NOON.astimezone(timezone.utc)).install(self)
        self.owner = self.user("exam-ref-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        self.projector = self.web.projector

    def open_formal_exam(self, *, last_active: datetime | None = None, mode: str = "formal", state: str = "running") -> str:
        session_id = f"ds-{mode}-{state}"
        at = iso(last_active or self.clock.now)
        with self.web.journeys.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_school_sessions (session_id, pet_id, user_id, subject, mode, paper_no, rules_version, content_version, "
                "config_json, state, item_index, progress_json, created_at, begun_at, last_active_at) "
                "VALUES (?, ?, ?, 'theory', ?, 1, 'r1', 'c1', '{}', ?, 0, '{}', ?, ?, ?)",
                (session_id, self.pet, self.owner.user_id, mode, state, at, at, at))
        return session_id

    # ---- CR-B8①：正式考局投影成 exam ----
    def test_a_running_formal_exam_is_projected_as_an_exam(self) -> None:
        session_id = self.open_formal_exam()

        activity = self.projector.state(self.pet, self.clock.now).primary_activity

        self.assertEqual(activity.kind, "exam", f"考试期间不能把 TA 当成在家空闲：{activity}")
        self.assertEqual(activity.ref, f"exam:{session_id}")
        self.assertFalse(activity.interruptible, "正式考试不可打断")

    def test_a_practice_session_is_not_an_exam(self) -> None:
        """对照组：练习局随时可以停，不该占住 TA。"""
        self.open_formal_exam(mode="practice")

        self.assertEqual(self.projector.state(self.pet, self.clock.now).primary_activity.kind, "at_home")

    def test_an_abandoned_exam_does_not_trap_the_pet_forever(self) -> None:
        """开了很久没动的残局按放弃处理——否则这只宠物会永远停在"考试中"，再也排不上调度。"""
        self.open_formal_exam(state="preparing", last_active=self.clock.now - timedelta(hours=3))

        self.assertEqual(self.projector.state(self.pet, self.clock.now).primary_activity.kind, "at_home")

    # ---- CR-B8②：一次评估只读一次运行记录 ----
    def test_one_evaluation_reads_the_runtime_row_only_once(self) -> None:
        """三次分别读可能读到三个时刻的快照；而且每轮每只多花两次查询。"""
        original = self.projector.runtime.row
        reads: list[str] = []
        self.projector.runtime.row = lambda pet_id: (reads.append(pet_id), original(pet_id))[1]

        state, facts = self.projector.snapshot(self.pet, self.clock.now)

        self.assertEqual(reads, [self.pet], f"一次快照只该读一次运行记录：{reads}")
        self.assertIsNotNone(state.versions)
        self.assertIsNotNone(facts.autonomy)

    # ---- CR-B8③：引用里不带家人编号 ----
    def queue_reply(self, client_id: str) -> None:
        self.clock.now = datetime(2026, 9, 23, 2, 0, tzinfo=HK).astimezone(timezone.utc)  # 香港凌晨，TA 睡着
        self.assertEqual(self.owner.post(f"/communicator/{self.pet}/messages",
                                         {"client_message_id": client_id, "text": "在家吗"}).status_code, 200)

    def test_a_due_reply_reference_does_not_carry_the_family_member_id(self) -> None:
        self.queue_reply("exam-ref-0001")

        facts = self.projector.facts(self.pet, self.clock.now)
        refs = [item.ref for item in facts.due_items if item.kind.value == "reply"]

        self.assertTrue(refs, "前提：确实有一件回复承诺")
        for ref in refs:
            self.assertNotIn(self.owner.user_id, ref, f"引用里不能带家人编号：{ref}")
        self.assertEqual(refs, [item.ref for item in self.projector.facts(self.pet, self.clock.now).due_items
                                if item.kind.value == "reply"], "同一位家人每次算出同一个引用（要能去重）")

    def test_different_family_members_get_different_references(self) -> None:
        """化名要能区分：两位家人的承诺不能挤成同一条。"""
        from app.web_agent.runtime_view import reply_ref

        first, second = reply_ref(self.pet, "user-aaa"), reply_ref(self.pet, "user-bbb")

        self.assertNotEqual(first, second)
        self.assertEqual(first, reply_ref(self.pet, "user-aaa"), "同一位家人永远同一个引用")

    # ---- CR-B7：时钟健康 ----
    def test_a_jumped_clock_is_reported_instead_of_being_trusted(self) -> None:
        """只看 last_evaluated_at 只能发现回拨；把墙上时钟与单调时钟一比，大幅前跳也能发现（CR-B7）。"""
        from app.web_runtime.reasons import SilenceReason

        shadow = self.web.shadow
        self.assertIsNotNone(shadow, "前提：这个环境开着心跳 shadow")
        self.projector.clock_monitor.reanchor(self.projector.clock)
        self.clock.now = self.clock.now + timedelta(hours=12)  # 墙上时钟大幅前跳，单调时钟没动

        shadow.run(self.clock.now)

        self.assertEqual(self.projector.runtime.row(self.pet).get("silence_reason"), SilenceReason.CLOCK_UNHEALTHY.value,
                         "时钟不可信时要如实说出来，不能照常按它做决定")

    # ---- CR-B11："留在家"的显式有效期 ----
    def test_staying_home_writes_an_explicit_review_time(self) -> None:
        """"TA 决定在家待到什么时候"要写成显式时刻，不能只靠心跳的间隔隐含表达。"""
        import json

        from app.web_agent.decision.testing import ScriptedModel

        self.owner.patch("/settings", {"model_replies": True})
        self.projector.model_available = lambda: True
        life = self.web.brain_life
        life.mode = "live"
        life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "今天想在家", "review_after_minutes": 45},
                                                    ensure_ascii=False))

        outcome = life.consider(self.pet, self.clock.now)

        self.assertEqual(outcome.status, "stayed", f"{outcome}")
        row = self.projector.runtime.row(self.pet)
        self.assertTrue(row.get("next_review_at"), f"留在家里也要写下什么时候再看：{dict(row)}")
        review_at = datetime.fromisoformat(row["next_review_at"])
        policy = HeartbeatPolicy()
        self.assertGreaterEqual(review_at, self.clock.now + policy.min_decision_interval, "夹在策略下限之上")
        self.assertLessEqual(review_at, self.clock.now + policy.max_review_interval, "夹在策略上限之内")


if __name__ == "__main__":
    unittest.main()
