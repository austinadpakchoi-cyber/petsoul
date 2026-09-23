"""包 B：世界时钟与宠物心跳纯策略（app/web_runtime）。

全部用 FakeClock 或固定时刻驱动：不连数据库、不联网、不调模型，也不依赖宿主机时区。
这里只验证策略结论；装配进 worker、读真实库、执行意图由集成窗口负责，本文件通过不等于心跳已接入运行路径。
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone

from app.schemas.runtime_internal import ActivityRef, Clock, HeartbeatAction, RuntimeState, Versions, WakeEvent, WakeKind
from app.web_runtime.clock_policy import (
    ClockHealthStatus, ClockMonitor, FakeClock, SystemClock, ensure_utc, in_local_window, local_wall, next_local_occurrence, resolve_zone,
)
from app.web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate, evaluate_all, next_review_at, retry_plan
from app.web_runtime.reasons import IntentKind, ReasonCode, SilenceKind, SilenceReason, silence_of
from app.web_runtime.state import (
    AutonomyFacts, BrainAvailability, CognitionFacts, DueItem, DueKind, HeartbeatFacts, InFlightBrain, cognition_status, commitment_deadline,
)
from app.web_runtime.wake_events import merge_events

UTC = timezone.utc
HK = "Asia/Hong_Kong"
PET = "pet-a"
T0 = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)  # 香港 12:00：醒着，在默认出门时段（08:30–17:30）内
POLICY = HeartbeatPolicy()
BRAIN_ON = CognitionFacts(enabled=True, availability=BrainAvailability.AVAILABLE)
HOME = ActivityRef("at_home", None)


def versions(**changes) -> Versions:
    base = dict(runtime_epoch=1, activity_epoch=1, dna_version=1, privacy_epoch=1, membership_epoch=1, itinerary_version=None)
    base.update(changes)
    return Versions(**base)


def runtime(activity: ActivityRef | None = HOME, **changes) -> RuntimeState:
    base = dict(pet_id=PET, realm_id="test", versions=versions(), as_of=T0, household_id="hh-1", timezone=HK, region_id="hk-central",
                scene_ref="home:hm-1", primary_activity=activity, sleep_window=(time(23, 30), time(7, 30)))
    base.update(changes)
    return RuntimeState(**base)


def facts(due=(), cognition: CognitionFacts = BRAIN_ON, *, last_evaluated_at=None, maintenance=False, **autonomy) -> HeartbeatFacts:
    return HeartbeatFacts(due_items=tuple(due), cognition=cognition, autonomy=AutonomyFacts(**autonomy),
                          last_evaluated_at=last_evaluated_at, maintenance=maintenance)


def wake(kind: WakeKind, ref: str, at: datetime, sequence: int, *, pet: str = PET, event_id: str | None = None) -> WakeEvent:
    return WakeEvent(event_id or f"ev-{kind.value}-{sequence}", pet, kind, at, ref, sequence)


def apply(state: RuntimeState, heart: HeartbeatFacts, decision, now: datetime) -> tuple[RuntimeState, HeartbeatFacts]:
    """测试用的最小“集成层”：把意图当作已经提交，推出下一份投影。真实实现由集成窗口负责。"""
    kinds = {intent.kind for intent in decision.task_intents}
    activity, cognition, autonomy, due = state.primary_activity, heart.cognition, heart.autonomy, heart.due_items
    settled = {intent.source_ref for intent in decision.task_intents if intent.kind in (IntentKind.SETTLE_DUE.value, IntentKind.DELIVER_REPLY.value)}
    if settled:
        due = tuple(item for item in due if item.ref not in settled)
        if activity.ends_at is not None and activity.ends_at <= now:
            activity, autonomy = HOME, replace(autonomy, next_review_at=None)
    if IntentKind.RULE_LIFE_PLAN.value in kinds:
        autonomy = replace(autonomy, last_decision_at=now, next_review_at=next_review_at(now, POLICY))
    for intent in decision.task_intents:
        if intent.kind == IntentKind.BRAIN_DECIDE.value:
            operation = InFlightBrain(intent.dedupe_key, "life_plan", state.versions, now, intent.deadline_at)
            cognition = replace(cognition, operation=operation, last_requested_at=now)
    return (replace(state, primary_activity=activity, as_of=now),
            replace(heart, due_items=due, cognition=cognition, autonomy=autonomy, last_evaluated_at=now))


class ClockPolicyTests(unittest.TestCase):
    def test_fake_clock_and_monitor_detect_regression_and_jump(self):
        clock = FakeClock(T0)
        monitor = ClockMonitor(tolerance=timedelta(seconds=30))
        self.assertIsInstance(clock, Clock)
        self.assertIsInstance(SystemClock(), Clock)
        self.assertIsNotNone(SystemClock().now_utc().tzinfo)
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.OK)
        clock.advance(timedelta(hours=2))
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.OK)
        clock.jump_wall(timedelta(seconds=20))  # 容忍度内的小幅校时：吸收
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.OK)
        clock.jump_wall(timedelta(minutes=-10))
        regressed = monitor.sample(clock).health
        self.assertEqual((regressed.status, regressed.skew_seconds), (ClockHealthStatus.REGRESSED, -600.0))
        clock.advance(timedelta(minutes=1))  # 异常会一直保持，直到核对
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.REGRESSED)
        monitor.reanchor(clock)
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.OK)
        clock.jump_wall(timedelta(hours=48))
        jumped = monitor.sample(clock).health
        self.assertEqual((jumped.status, jumped.skew_seconds), (ClockHealthStatus.JUMPED, 172800.0))
        clock.jump_wall(timedelta(hours=-48))  # 墙上时钟回到推算值附近：自动恢复
        self.assertIs(monitor.sample(clock).health.status, ClockHealthStatus.OK)
        with self.assertRaises(ValueError):
            clock.advance(timedelta(seconds=-1))
        with self.assertRaises(ValueError):
            FakeClock(datetime(2026, 9, 22, 12, 0))

    def test_local_time_is_strict_about_zones_and_dst(self):
        for name in (None, "", "Mars/Olympus_Mons", "../etc/passwd"):
            self.assertIsNone(resolve_zone(name), name)
        hk = resolve_zone(HK)
        self.assertEqual(local_wall(T0, hk).hour, 12)
        self.assertTrue(in_local_window(time(0, 30), time(23, 30), time(7, 30)))
        self.assertFalse(in_local_window(time(12, 0), time(23, 30), time(7, 30)))
        self.assertFalse(in_local_window(time(9, 0), time(9, 0), time(9, 0)))
        self.assertEqual(next_local_occurrence(T0, hk, time(7, 30)), datetime(2026, 9, 22, 23, 30, tzinfo=UTC))
        at_wake = datetime(2026, 9, 22, 23, 30, tzinfo=UTC)  # 正好在起床时刻：给下一天，严格晚于 now
        self.assertEqual(next_local_occurrence(at_wake, hk, time(7, 30)), datetime(2026, 9, 23, 23, 30, tzinfo=UTC))
        new_york = resolve_zone("America/New_York")
        # 2026-03-08 夏令时开始：当地 02:30 不存在，顺延到跳变那一刻（当地 03:00，UTC 07:00）
        self.assertEqual(next_local_occurrence(datetime(2026, 3, 8, 5, 0, tzinfo=UTC), new_york, time(2, 30)),
                         datetime(2026, 3, 8, 7, 0, tzinfo=UTC))
        # 2026-11-01 夏令时结束：当地 01:30 出现两次，取第一次（夏令时，UTC 05:30）
        self.assertEqual(next_local_occurrence(datetime(2026, 11, 1, 3, 0, tzinfo=UTC), new_york, time(1, 30)),
                         datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
        self.assertEqual(ensure_utc(datetime(2026, 9, 22, 20, 0, tzinfo=hk)), datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        with self.assertRaises(ValueError):
            ensure_utc(datetime(2026, 9, 22, 12, 0))


class HeartbeatTests(unittest.TestCase):
    def decide(self, state, heart=None, events=(), now=T0, policy=POLICY, **kwargs):
        decision = evaluate(state, events, policy, now, facts=heart, **kwargs)
        # 共同约定：下一次检查一定有值、至少晚 min_delay、不超过看门狗；同一去重键只出现一次
        self.assertIsNotNone(decision.next_check_at)
        self.assertGreaterEqual(decision.next_check_at, now + policy.min_delay)
        self.assertLessEqual(decision.next_check_at, now + policy.max_check_interval)
        self.assertEqual(len({intent.dedupe_key for intent in decision.task_intents}), len(decision.task_intents))
        return decision

    def test_sleep_follows_local_rhythm_including_night_owls(self):
        clock = FakeClock(datetime(2026, 9, 22, 18, 0, tzinfo=UTC))  # 香港 9 月 23 日 02:00
        owl_window, owl_active = (time(1, 30), time(9, 30)), (time(10, 30), time(19, 30))
        now = clock.now_utc()
        regular = self.decide(runtime(as_of=now), facts(), now=now)
        self.assertEqual((regular.action, silence_of(regular)), (HeartbeatAction.CONTINUE, SilenceReason.ASLEEP))
        # 0.1.1：安静原因同时写进字段与原因码，集成层与运维两种读法都拿得到
        self.assertEqual(regular.silence_reason, SilenceReason.ASLEEP.value)
        self.assertIn(f"silence:{SilenceReason.ASLEEP.value}", regular.reason_codes)
        self.assertEqual(regular.next_check_at, datetime(2026, 9, 22, 23, 30, tzinfo=UTC))  # 香港 07:30 起床
        self.assertEqual((regular.task_intents, regular.brain_purpose), ((), None))
        owl = self.decide(runtime(sleep_window=owl_window, as_of=now), facts(active_window=owl_active), now=now)
        self.assertEqual((silence_of(owl), owl.next_check_at), (SilenceReason.ASLEEP, now + POLICY.max_check_interval))
        self.assertIn(ReasonCode.WATCHDOG.value, owl.reason_codes)  # 夜猫子 7.5 小时后才起床：6 小时的看门狗先到
        now = clock.advance(timedelta(hours=6))  # 香港 08:00：夜猫子还在睡，普通作息的醒了但还没到出门时段
        owl = self.decide(runtime(sleep_window=owl_window, as_of=now), facts(active_window=owl_active), now=now)
        self.assertEqual((silence_of(owl), owl.next_check_at), (SilenceReason.ASLEEP, datetime(2026, 9, 23, 1, 30, tzinfo=UTC)))
        morning = self.decide(runtime(as_of=now), facts(), now=now)
        self.assertEqual((silence_of(morning), morning.next_check_at), (SilenceReason.OUTSIDE_ACTIVE_HOURS, datetime(2026, 9, 23, 0, 30, tzinfo=UTC)))
        now = clock.advance(timedelta(minutes=30))  # 香港 08:30：该自己想想今天做什么了
        self.assertIs(self.decide(runtime(as_of=now), facts(), now=now).action, HeartbeatAction.REQUEST_BRAIN)
        unknown_rhythm = self.decide(runtime(sleep_window=None, as_of=now), facts(), now=now)
        self.assertIn(ReasonCode.DEFAULT_RHYTHM.value, unknown_rhythm.reason_codes)
        now = clock.advance(timedelta(hours=1))  # 香港 09:30：夜猫子醒了，它的出门时段 10:30 才开始
        owl = self.decide(runtime(sleep_window=owl_window, as_of=now), facts(active_window=owl_active), now=now)
        self.assertEqual((silence_of(owl), owl.next_check_at), (SilenceReason.OUTSIDE_ACTIVE_HOURS, datetime(2026, 9, 23, 2, 30, tzinfo=UTC)))

    def test_journey_stages_continue_without_thinking(self):
        stages = [
            ActivityRef("at_home", "journey:jn-1", T0, T0 + timedelta(minutes=20), interruptible=False),  # 在家收拾，按开船时间出门
            ActivityRef("travel", "leg:jn-1:1", T0, T0 + timedelta(minutes=40), interruptible=False),  # 在船上
            ActivityRef("visit", "visit:vs-1", T0, T0 + timedelta(minutes=50)),
            ActivityRef("work", "visit:vs-2", T0, T0 + timedelta(hours=3)),
            ActivityRef("exam", "exam:ex-1", T0, T0 + timedelta(minutes=30), interruptible=False),
            ActivityRef("local_activity", "journey:jn-2", T0, T0 + timedelta(minutes=40)),
        ]
        events = [wake(WakeKind.suggestion_received, "suggestion:sg-1", T0, 1), wake(WakeKind.message_received, "message:m-1", T0, 2)]
        for activity in stages:
            with self.subTest(activity.kind):
                decision = self.decide(runtime(activity), facts(), events=events)
                self.assertEqual((decision.action, silence_of(decision)), (HeartbeatAction.CONTINUE, SilenceReason.LIVING))
                self.assertEqual((decision.next_check_at, decision.brain_purpose, decision.task_intents), (activity.ends_at, None, ()))
                self.assertIn(ReasonCode.SUGGESTION_NOTED.value, decision.reason_codes)
                self.assertEqual(set(decision.consumed_event_ids), {"ev-suggestion_received-1", "ev-message_received-2"})
        clock = FakeClock(T0)
        work = ActivityRef("work", "visit:vs-2", T0, T0 + timedelta(hours=3))
        for sequence in range(179):  # 打工 3 小时里每分钟被家人唤醒一次，也不会反复请求大脑
            now = clock.advance(timedelta(minutes=1))
            decision = self.decide(runtime(work, as_of=now), facts(), [wake(WakeKind.suggestion_received, "suggestion:sg-2", now, sequence)], now=now)
            self.assertIs(decision.action, HeartbeatAction.CONTINUE)

    def test_due_work_settles_first_even_when_brain_is_off_or_pet_asleep(self):
        done_at = T0 + timedelta(hours=2)
        now = done_at + timedelta(minutes=5)
        job = DueItem("journey:jn-work", DueKind.JOURNEY, done_at, commitment=True, itinerary_version=1)
        state = runtime(ActivityRef("work", "visit:vs-work", T0 - timedelta(hours=1), done_at), versions=versions(itinerary_version=1), as_of=now)
        cognitions = {"大脑可用": BRAIN_ON, "大脑关闭": CognitionFacts(),
                      "额度用完": CognitionFacts(enabled=True, availability=BrainAvailability.EXHAUSTED, window_resets_at=now + timedelta(hours=10))}
        keys = set()
        for label, cognition in cognitions.items():
            with self.subTest(label):
                decision = self.decide(state, facts([job], cognition), now=now)
                self.assertIs(decision.action, HeartbeatAction.APPLY_RULE)
                [intent] = decision.task_intents
                self.assertEqual((intent.kind, intent.source_ref, intent.aggregate_id, intent.run_at),
                                 (IntentKind.SETTLE_DUE.value, "journey:jn-work", PET, now))
                self.assertIn(ReasonCode.DUE_COMMITMENT.value, decision.reason_codes)
                keys.add(intent.dedupe_key)
        self.assertEqual(len(keys), 1)  # 反复评估、认知状态变化都是同一个去重键：工钱只结算一次
        night = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)  # 香港 02:00，睡着了；深夜的求助消息 3 秒内要回
        reply = DueItem("reply:conv-a", DueKind.REPLY, night - timedelta(seconds=1), commitment=True)
        asleep = self.decide(runtime(as_of=night), facts([reply], CognitionFacts()), now=night)
        self.assertEqual((asleep.action, asleep.task_intents[0].kind), (HeartbeatAction.APPLY_RULE, IntentKind.DELIVER_REPLY.value))
        backoff = replace(job, attempts=2, retry_after=now + timedelta(minutes=3))  # 退避中：不重复交出，到点再试
        waiting = self.decide(state, facts([backoff]), now=now)
        self.assertEqual((waiting.action, waiting.task_intents, waiting.next_check_at), (HeartbeatAction.CONTINUE, (), now + timedelta(minutes=3)))

    def test_commitments_come_first_and_batches_are_bounded(self):
        items = [DueItem(f"journey:jn-{index}", DueKind.JOURNEY, T0 - timedelta(minutes=30 - index)) for index in range(3)]
        items += [DueItem(f"reply:conv-{who}", DueKind.REPLY, T0 - timedelta(minutes=1), commitment=True, input_high_watermark=5) for who in "abc"]
        decision = self.decide(runtime(), facts(items))
        self.assertEqual([intent.kind for intent in decision.task_intents], [IntentKind.DELIVER_REPLY.value] * 3 + [IntentKind.SETTLE_DUE.value] * 3)
        self.assertEqual([intent.source_ref for intent in decision.task_intents[3:]], ["journey:jn-0", "journey:jn-1", "journey:jn-2"])
        self.assertTrue(decision.task_intents[0].dedupe_key.endswith(":5"))  # 回复承诺的去重键带上输入水位
        small = HeartbeatPolicy(max_intents=2)
        bounded = self.decide(runtime(), facts(items), policy=small)
        self.assertEqual(len(bounded.task_intents), 2)
        self.assertIn(ReasonCode.MORE_DUE_ITEMS.value, bounded.reason_codes)
        self.assertEqual(bounded.next_check_at, T0 + small.follow_up)  # 剩下的等提交后接着处理，不零延迟复查
        overdue = DueItem("reply:conv-z", DueKind.REPLY, T0 - timedelta(hours=9), commitment=True, deadline_at=T0 - timedelta(hours=1))
        self.assertIn(ReasonCode.COMMITMENT_OVERDUE.value, self.decide(runtime(), facts([overdue])).reason_codes)

    def test_forty_eight_hours_offline_catches_up_once(self):
        for label, cognition, expected in (("大脑可用", BRAIN_ON, IntentKind.BRAIN_DECIDE), ("大脑关闭", CognitionFacts(), IntentKind.RULE_LIFE_PLAN)):
            with self.subTest(label):
                clock = FakeClock(T0)
                job = DueItem("journey:jn-w", DueKind.JOURNEY, T0 + timedelta(hours=3), commitment=True, itinerary_version=1)
                state = runtime(ActivityRef("work", "visit:vs-w", T0, T0 + timedelta(hours=3)), versions=versions(itinerary_version=1))
                heart = facts([job], cognition, last_evaluated_at=T0, next_review_at=T0 + timedelta(hours=4))
                now = clock.advance(timedelta(hours=48))  # 全家 48 小时没打开网页，worker 也停了
                decisions = []
                for _ in range(3):
                    decision = self.decide(replace(state, as_of=now), heart, now=now)
                    decisions.append(decision)
                    state, heart = apply(state, heart, decision, now)
                first, second, third = decisions
                self.assertEqual(first.action, HeartbeatAction.APPLY_RULE)
                self.assertEqual([intent.source_ref for intent in first.task_intents], ["journey:jn-w"])  # 工钱与回家只补一次
                self.assertIn(ReasonCode.CATCHING_UP.value, first.reason_codes)
                self.assertIsNone(first.brain_purpose)
                self.assertEqual([intent.kind for intent in second.task_intents], [expected.value])  # 只做一次当下的决定，不补写错过的时段
                self.assertIs(third.action, HeartbeatAction.CONTINUE)
                all_intents = [intent for decision in decisions for intent in decision.task_intents]
                self.assertEqual(sum(intent.kind == expected.value for intent in all_intents), 1)

    def test_unknown_timezone_is_explicit_not_hong_kong(self):
        for zone in (None, "", "Mars/Olympus_Mons", "../etc/passwd"):
            with self.subTest(zone=zone):
                decision = self.decide(runtime(timezone=zone), facts())
                self.assertEqual((decision.action, silence_of(decision)), (HeartbeatAction.RECOVER, SilenceReason.TIMEZONE_UNKNOWN))
                self.assertEqual((decision.task_intents, decision.brain_purpose), ((), None))
                self.assertEqual(decision.next_check_at, T0 + POLICY.dependency_recheck)
        self.assertIs(SilenceReason.TIMEZONE_UNKNOWN.kind, SilenceKind.FAULT)
        travel = ActivityRef("travel", "leg:jn-1:1", T0 - timedelta(hours=1), T0 - timedelta(minutes=1))
        due = DueItem("journey:jn-1", DueKind.JOURNEY, T0 - timedelta(minutes=1))
        self.assertIs(self.decide(runtime(travel, timezone=None), facts([due])).action, HeartbeatAction.APPLY_RULE)  # 到期按 UTC，照样结算
        self.assertIs(self.decide(runtime(), facts()).action, HeartbeatAction.REQUEST_BRAIN)  # 同一时刻按香港是白天：说明上面没有偷偷套用香港

    def test_new_message_neither_triggers_nor_cancels_thinking(self):
        operation = InFlightBrain("op-1", "life_plan", versions(), T0 - timedelta(seconds=20), T0 + timedelta(seconds=70))
        reply = DueItem("reply:conv-a", DueKind.REPLY, T0 + timedelta(seconds=15), commitment=True, input_high_watermark=2)
        events = [wake(WakeKind.message_received, "message:m-1", T0, 1), wake(WakeKind.message_received, "message:m-2", T0, 2)]
        thinking = facts([reply], replace(BRAIN_ON, operation=operation, last_requested_at=T0 - timedelta(seconds=20)))
        decision = self.decide(runtime(), thinking, events=events)
        self.assertEqual((decision.action, silence_of(decision), decision.task_intents), (HeartbeatAction.CONTINUE, SilenceReason.THINKING, ()))
        self.assertEqual(decision.next_check_at, T0 + timedelta(seconds=15))  # 回复承诺到点最先处理
        self.assertEqual(set(decision.consumed_event_ids), {"ev-message_received-1", "ev-message_received-2"})
        self.assertIn(ReasonCode.MESSAGE_RECEIVED.value, decision.reason_codes)
        calm = facts([reply], next_review_at=T0 + timedelta(hours=1))
        quiet = self.decide(runtime(), calm, events=events)  # 没有在思考：新消息也只等回复承诺，不触发生活规划
        self.assertEqual((quiet.action, silence_of(quiet), quiet.next_check_at), (HeartbeatAction.CONTINUE, SilenceReason.NO_NEW_DECISION, T0 + timedelta(seconds=15)))
        due_now = T0 + timedelta(seconds=15)
        delivered = self.decide(runtime(as_of=due_now), calm, now=due_now)
        self.assertEqual([(intent.kind, intent.source_ref) for intent in delivered.task_intents], [(IntentKind.DELIVER_REPLY.value, "reply:conv-a")])

    def test_version_changes_cancel_stale_thinking_and_items(self):
        operation = InFlightBrain("op-2", "life_plan", versions(), T0 - timedelta(seconds=10), T0 + timedelta(seconds=80))
        changed = {"dna_version": versions(dna_version=2), "privacy_epoch": versions(privacy_epoch=2), "membership_epoch": versions(membership_epoch=2),
                   "activity_epoch": versions(activity_epoch=2), "runtime_epoch": versions(runtime_epoch=2)}
        for name, current in changed.items():
            with self.subTest(name):
                event = wake(WakeKind.versions_changed, f"versions:{name}", T0, 1)
                decision = self.decide(runtime(versions=current), facts(cognition=replace(BRAIN_ON, operation=operation)), events=[event])
                self.assertIs(decision.action, HeartbeatAction.APPLY_RULE)
                self.assertEqual([(intent.kind, intent.source_ref) for intent in decision.task_intents], [(IntentKind.CANCEL_BRAIN.value, "brain:op-2")])
                self.assertIn(f"brain_stale:{name}", decision.reason_codes)
                self.assertIsNone(decision.brain_purpose)  # 等作废提交后再按新版本思考
        trip = replace(operation, source_versions=versions(itinerary_version=3))
        rebooked = self.decide(runtime(versions=versions(itinerary_version=4)), facts(cognition=replace(BRAIN_ON, operation=trip)))
        self.assertIn("brain_stale:itinerary_version", rebooked.reason_codes)
        stale = DueItem("journey:jn-1", DueKind.JOURNEY, T0 - timedelta(minutes=1), itinerary_version=3)
        travel = ActivityRef("travel", "leg:jn-1:2", T0 - timedelta(hours=1), T0 + timedelta(hours=1))
        reconcile = self.decide(runtime(travel, versions=versions(itinerary_version=4)), facts([stale]))  # 旧行程的到站不执行：宠物不能同时在两地
        self.assertEqual((reconcile.action, silence_of(reconcile)), (HeartbeatAction.RECOVER, SilenceReason.STATE_INCONSISTENT))
        self.assertEqual([intent.kind for intent in reconcile.task_intents], [IntentKind.RECONCILE.value])
        fresh = self.decide(runtime(versions=versions(dna_version=2)), facts())
        self.assertIs(fresh.action, HeartbeatAction.REQUEST_BRAIN)
        self.assertIn(":1.1.2.1.1:", fresh.task_intents[0].dedupe_key)

    def test_expired_thinking_and_tasks_go_to_recovery(self):
        expired = InFlightBrain("op-3", "life_plan", versions(), T0 - timedelta(minutes=5), T0 - timedelta(seconds=1))
        decision = self.decide(runtime(), facts(cognition=replace(BRAIN_ON, operation=expired)))
        self.assertEqual((decision.action, silence_of(decision)), (HeartbeatAction.RECOVER, SilenceReason.TASK_STUCK))
        self.assertEqual([(intent.kind, intent.source_ref) for intent in decision.task_intents], [(IntentKind.RECOVER_TASK.value, "brain:op-3")])
        self.assertIsNone(decision.brain_purpose)
        self.assertIs(SilenceReason.TASK_STUCK.kind, SilenceKind.FAULT)
        lease = self.decide(runtime(), facts(next_review_at=T0 + timedelta(hours=1)), events=[wake(WakeKind.task_expired, "task:wt_1", T0, 7)])
        self.assertEqual([(intent.kind, intent.source_ref) for intent in lease.task_intents], [(IntentKind.RECOVER_TASK.value, "task:wt_1")])
        self.assertEqual(lease.consumed_event_ids, ("ev-task_expired-7",))
        stuck = DueItem("journey:jn-9", DueKind.JOURNEY, T0 - timedelta(hours=1), attempts=5)
        healthy = DueItem("reply:conv-a", DueKind.REPLY, T0 - timedelta(minutes=1), commitment=True)
        mixed = self.decide(runtime(), facts([stuck, healthy]))  # 卡住的交给恢复，健康的承诺照样兑现
        self.assertEqual(mixed.action, HeartbeatAction.RECOVER)
        self.assertEqual({(intent.kind, intent.source_ref) for intent in mixed.task_intents},
                         {(IntentKind.RECOVER_TASK.value, "journey:jn-9"), (IntentKind.DELIVER_REPLY.value, "reply:conv-a")})

    def test_idle_review_timing_and_decision_interval(self):
        later = T0 + timedelta(minutes=40)
        waiting = self.decide(runtime(), facts(next_review_at=later, last_decision_at=T0 - timedelta(minutes=5)))
        self.assertEqual((waiting.action, silence_of(waiting), waiting.next_check_at), (HeartbeatAction.CONTINUE, SilenceReason.NO_NEW_DECISION, later))
        suggested = facts(next_review_at=later, last_decision_at=T0 - timedelta(minutes=5), latest_suggestion_at=T0 - timedelta(minutes=1))
        too_soon = self.decide(runtime(), suggested)  # 家人的新建议让复查提前，但离上次决定不到 15 分钟
        self.assertEqual(too_soon.next_check_at, T0 + timedelta(minutes=10))
        self.assertTrue({ReasonCode.OWNER_SUGGESTION.value, ReasonCode.DECISION_INTERVAL.value} <= set(too_soon.reason_codes))
        ready = T0 + timedelta(minutes=10)
        events = [wake(WakeKind.suggestion_received, f"suggestion:sg-{index}", ready, index) for index in range(1, 4)]
        thinking = self.decide(runtime(as_of=ready), suggested, events=events, now=ready)  # 三位家人各提一次，也只合成一次决定
        self.assertEqual((thinking.action, thinking.brain_purpose), (HeartbeatAction.REQUEST_BRAIN, "life_plan"))
        [intent] = thinking.task_intents
        self.assertEqual((intent.kind, intent.deadline_at), (IntentKind.BRAIN_DECIDE.value, ready + POLICY.brain_deadline))
        self.assertEqual(thinking.next_check_at, ready + POLICY.brain_deadline)
        self.assertEqual([next_review_at(T0, POLICY, seconds) for seconds in (None, 60, 7200, 10 ** 6)],
                         [T0 + timedelta(minutes=15), T0 + timedelta(minutes=15), T0 + timedelta(hours=2), T0 + timedelta(hours=6)])
        # 没想成之后的重试安排：禁调下限与只读复查分开。硬性恢复时刻原样保留，不被复查上限截短
        self.assertEqual(retry_plan(T0, POLICY).not_before, T0 + timedelta(minutes=15))
        self.assertEqual(retry_plan(T0, POLICY, dependency=True).not_before, T0 + timedelta(minutes=5))
        self.assertEqual(retry_plan(T0, POLICY, dependency=True, retry_after=T0 - timedelta(hours=1)).not_before, T0 + timedelta(minutes=5))
        far = retry_plan(T0, POLICY, retry_after=T0 + timedelta(hours=20))
        self.assertEqual((far.not_before, far.check_at), (T0 + timedelta(hours=20), T0 + timedelta(hours=6)))
        self.assertEqual([far.allows(T0 + timedelta(hours=hours)) for hours in (6, 19, 20)], [False, False, True])
        enough = self.decide(runtime(), facts(outings_today=2, outings_per_day=2))  # 明天 08:30 才再出门：看门狗 6 小时后先看一眼
        self.assertEqual((silence_of(enough), enough.next_check_at), (SilenceReason.ENOUGH_TODAY, T0 + POLICY.max_check_interval))
        self.assertIn(ReasonCode.WATCHDOG.value, enough.reason_codes)

    def test_brain_unavailable_uses_rules_or_defers(self):
        wait = HeartbeatPolicy(brain_fallback="wait")
        exhausted = CognitionFacts(enabled=True, availability=BrainAvailability.EXHAUSTED, window_resets_at=T0 + timedelta(hours=12))
        cases = [
            ("关闭", CognitionFacts(), ReasonCode.BRAIN_DISABLED, SilenceReason.NO_NEW_DECISION, T0 + timedelta(minutes=15)),
            ("额度用完", exhausted, ReasonCode.BRAIN_EXHAUSTED, SilenceReason.BUDGET_DEFERRED, T0 + timedelta(hours=6)),
            ("今天剩 0 次", replace(BRAIN_ON, remaining_today=0, window_resets_at=T0 + timedelta(hours=2)), ReasonCode.BRAIN_EXHAUSTED,
             SilenceReason.BUDGET_DEFERRED, T0 + timedelta(hours=2)),
            ("依赖故障", CognitionFacts(enabled=True, availability=BrainAvailability.UNAVAILABLE, retry_after=T0 + timedelta(minutes=3)),
             ReasonCode.BRAIN_UNAVAILABLE, SilenceReason.DEPENDENCY_UNAVAILABLE, T0 + timedelta(minutes=3)),
            ("依赖故障、不知何时恢复", CognitionFacts(enabled=True, availability=BrainAvailability.UNAVAILABLE), ReasonCode.BRAIN_UNAVAILABLE,
             SilenceReason.DEPENDENCY_UNAVAILABLE, T0 + timedelta(minutes=5)),
        ]
        for label, cognition, code, silence, next_check in cases:
            with self.subTest(label):
                rule = self.decide(runtime(), facts(cognition=cognition))
                self.assertEqual((rule.action, rule.brain_purpose), (HeartbeatAction.APPLY_RULE, None))
                self.assertEqual([intent.kind for intent in rule.task_intents], [IntentKind.RULE_LIFE_PLAN.value])
                self.assertTrue({code.value, ReasonCode.RULE_FALLBACK.value} <= set(rule.reason_codes))  # 如实记为规则，不冒充模型
                deferred = self.decide(runtime(), facts(cognition=cognition), policy=wait)
                self.assertEqual((deferred.action, silence_of(deferred), deferred.next_check_at, deferred.task_intents),
                                 (HeartbeatAction.DEFER, silence, next_check, ()))
        self.assertIs(SilenceReason.BUDGET_DEFERRED.kind, SilenceKind.DEFERRED)
        self.assertIs(SilenceReason.DEPENDENCY_UNAVAILABLE.kind, SilenceKind.FAULT)
        self.assertIs(SilenceReason.ASLEEP.kind, SilenceKind.NORMAL)
        rolled_over = replace(exhausted, window_resets_at=T0 - timedelta(minutes=1))  # 重置时刻已过：交给额度预占判断
        self.assertIs(self.decide(runtime(), facts(cognition=rolled_over)).action, HeartbeatAction.REQUEST_BRAIN)
        recovered = replace(BRAIN_ON, availability=BrainAvailability.UNAVAILABLE, retry_after=T0 - timedelta(seconds=1))
        self.assertIs(self.decide(runtime(), facts(cognition=recovered)).action, HeartbeatAction.REQUEST_BRAIN)
        # 额度要等 20 小时：到了只读复查时刻仍然不请求大脑，也不会因为“看了一眼”就把禁调时间当成已经到期
        long_wait = replace(BRAIN_ON, availability=BrainAvailability.EXHAUSTED, window_resets_at=T0 + timedelta(hours=20))
        at_check = T0 + timedelta(hours=4)  # 香港 16:00，仍在出门时段内
        still = self.decide(runtime(as_of=at_check), facts(cognition=long_wait), now=at_check, policy=wait)
        self.assertEqual((still.action, silence_of(still), still.task_intents), (HeartbeatAction.DEFER, SilenceReason.BUDGET_DEFERRED, ()))
        # 额度被调高之后，同一时刻的复查按最新事实重新判断：这时才重新请求大脑
        raised = self.decide(runtime(as_of=at_check), facts(cognition=replace(BRAIN_ON, remaining_today=3)), now=at_check, policy=wait)
        self.assertIs(raised.action, HeartbeatAction.REQUEST_BRAIN)

    def test_residents_live_without_an_owner(self):
        station = runtime(household_id=None, scene_ref="station:st-1")
        resident = self.decide(station, facts())
        self.assertEqual((resident.action, [intent.kind for intent in resident.task_intents]), (HeartbeatAction.APPLY_RULE, [IntentKind.RULE_LIFE_PLAN.value]))
        self.assertIn(ReasonCode.RESIDENT_RULE_LIFE.value, resident.reason_codes)
        self.assertIs(self.decide(station, facts(), policy=HeartbeatPolicy(resident_brain=True)).action, HeartbeatAction.REQUEST_BRAIN)
        at_work = runtime(ActivityRef("work", "visit:vs-r", T0 - timedelta(hours=3), T0 - timedelta(minutes=1)), household_id="hh-new")
        wage = DueItem("journey:jn-r", DueKind.JOURNEY, T0 - timedelta(minutes=1), commitment=True)
        self.assertIs(self.decide(at_work, facts([wage])).action, HeartbeatAction.APPLY_RULE)  # 打工途中被领养：工钱照样结算一次
        awaiting = self.decide(runtime(ActivityRef("not_activated", "station:st-1"), household_id="hh-new"), facts())
        self.assertEqual((awaiting.action, silence_of(awaiting), awaiting.task_intents), (HeartbeatAction.CONTINUE, SilenceReason.NOT_ACTIVATED, ()))

    def test_one_pet_is_evaluated_once_for_many_members(self):
        replies = [DueItem(f"reply:conv-{who}", DueKind.REPLY, T0 - timedelta(seconds=10), commitment=True) for who in ("mom", "brother", "dad")]
        events = [wake(WakeKind.message_received, "message:m-1", T0, 1), wake(WakeKind.message_received, "message:m-9", T0, 1, pet="pet-b", event_id="b-1")]
        decisions = evaluate_all([runtime(), runtime(pet_id="pet-b")], events, POLICY, T0, facts={PET: facts(replies), "pet-b": facts()})
        self.assertEqual(set(decisions), {PET, "pet-b"})
        mine = decisions[PET]
        self.assertEqual(mine.action, HeartbeatAction.APPLY_RULE)
        self.assertEqual(sorted(intent.source_ref for intent in mine.task_intents), ["reply:conv-brother", "reply:conv-dad", "reply:conv-mom"])
        self.assertIsNone(mine.brain_purpose)  # 三位家人各有一段私聊承诺，宠物的生活只有一份
        self.assertEqual((mine.consumed_event_ids, decisions["pet-b"].consumed_event_ids), (("ev-message_received-1",), ("b-1",)))
        with self.assertRaises(ValueError):
            evaluate_all([runtime(), runtime()], [], POLICY, T0)

    def test_events_are_deduplicated_and_future_ones_kept(self):
        events = [
            wake(WakeKind.message_received, "message:m-1", T0 - timedelta(seconds=5), 1, event_id="e1"),
            wake(WakeKind.message_received, "message:m-1", T0 - timedelta(seconds=5), 1, event_id="e1"),
            wake(WakeKind.activity_due, "leg:jn-1:1", T0 - timedelta(seconds=3), 2, event_id="e2"),
            wake(WakeKind.activity_due, "leg:jn-1:1", T0 - timedelta(seconds=2), 3, event_id="e3"),
            wake(WakeKind.suggestion_received, "suggestion:sg-1", T0 + timedelta(minutes=7), 4, event_id="e4"),
            wake(WakeKind.message_received, "message:m-9", T0, 5, pet="pet-b", event_id="e5"),
        ]
        merged = merge_events(PET, events, T0)
        self.assertEqual([event.event_id for event in merged.effective], ["e1", "e3"])
        self.assertEqual((merged.consumed_ids, [event.event_id for event in merged.pending]), (("e1", "e2", "e3"), ["e4"]))
        self.assertEqual((merged.duplicates, merged.foreign), (2, 1))
        decision = self.decide(runtime(), facts(next_review_at=T0 + timedelta(hours=1), last_decision_at=T0 - timedelta(minutes=5)), events=events)
        self.assertEqual(decision.consumed_event_ids, ("e1", "e2", "e3"))  # 还没生效的与别的宠物的事件都不确认
        self.assertEqual(decision.next_check_at, T0 + timedelta(minutes=7))  # 到那条事件生效时再看
        self.assertTrue({ReasonCode.DUPLICATE_EVENTS.value, ReasonCode.FOREIGN_EVENTS.value, ReasonCode.FUTURE_EVENTS.value} <= set(decision.reason_codes))
        with self.assertRaises(ValueError):
            merge_events(PET, [WakeEvent("x", PET, "not_a_kind", T0, "r", 1)], T0)
        with self.assertRaises(ValueError):
            merge_events(PET, [wake(WakeKind.message_received, "message:m-2", T0.replace(tzinfo=None), 1)], T0)

    def test_scheduler_loop_never_spins(self):
        clock = FakeClock(datetime(2026, 9, 21, 16, 0, tzinfo=UTC))  # 香港 9 月 22 日 00:00，大脑关闭，按规则生活
        state, heart = runtime(as_of=clock.now_utc()), facts(cognition=CognitionFacts())
        end = clock.now_utc() + timedelta(hours=48)
        count = rules = 0
        while clock.now_utc() < end:
            now = clock.now_utc()
            decision = self.decide(replace(state, as_of=now), heart, now=now)
            count += 1
            rules += any(intent.kind == IntentKind.RULE_LIFE_PLAN.value for intent in decision.task_intents)
            self.assertIsNone(decision.brain_purpose)
            state, heart = apply(state, heart, decision, now)
            clock.advance(decision.next_check_at - now)
        self.assertLess(count, 48 * 4)  # 48 小时里有界：白天每 15 分钟一次决定＋一次复查，夜里只在边界醒来
        self.assertEqual(rules, 2 * 36)  # 两天各 9 小时出门时段，每 15 分钟一次规则决定
        night = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
        past = [  # 过去的边界不会被当成“马上再查”
            (runtime(ActivityRef("travel", "leg:jn-x", night - timedelta(hours=5), night - timedelta(hours=3)), as_of=night), facts()),
            (runtime(as_of=night), facts(next_review_at=night - timedelta(hours=6))),
            (runtime(as_of=night), facts([DueItem("journey:jn-y", DueKind.JOURNEY, night - timedelta(hours=2), retry_after=night - timedelta(hours=1))])),
        ]
        for state, heart in past:
            decision = self.decide(state, heart, now=night)
            self.assertGreater(decision.next_check_at - night, timedelta(seconds=30))

    def test_unreliable_clock_blocks_settlement(self):
        due = DueItem("journey:jn-1", DueKind.JOURNEY, T0 - timedelta(minutes=1), commitment=True)
        events = [wake(WakeKind.message_received, "message:m-1", T0, 1)]
        regressed = self.decide(runtime(), facts([due], last_evaluated_at=T0 + timedelta(minutes=10)), events=events)
        self.assertEqual((regressed.action, silence_of(regressed), regressed.task_intents), (HeartbeatAction.RECOVER, SilenceReason.CLOCK_UNHEALTHY, ()))
        self.assertEqual((regressed.consumed_event_ids, regressed.next_check_at), ((), T0 + POLICY.follow_up))
        self.assertIn(ReasonCode.CLOCK_REGRESSED.value, regressed.reason_codes)
        clock, monitor = FakeClock(T0), ClockMonitor()
        monitor.sample(clock)
        clock.jump_wall(timedelta(hours=48))
        reading = monitor.sample(clock)
        jumped = self.decide(runtime(as_of=reading.now_utc), facts([due]), now=reading.now_utc, clock_health=reading.health)
        self.assertEqual((jumped.action, jumped.task_intents), (HeartbeatAction.RECOVER, ()))  # 时钟跳变不会让工钱提前结算
        self.assertIn(ReasonCode.CLOCK_JUMPED.value, jumped.reason_codes)
        signal = [wake(WakeKind.clock_unhealthy, "clock:worker-1", T0, 9, event_id="c1"), wake(WakeKind.message_received, "message:m-2", T0, 10, event_id="m2")]
        self.assertEqual(self.decide(runtime(), facts([due]), events=signal).consumed_event_ids, ("c1",))
        self.assertIs(self.decide(runtime(as_of=T0 + timedelta(minutes=5)), facts([due])).action, HeartbeatAction.RECOVER)  # 投影比 now 还新
        self.assertIs(self.decide(runtime(as_of=T0 + timedelta(seconds=10)), facts([due])).action, HeartbeatAction.APPLY_RULE)  # 容忍度内

    def test_overdue_activity_is_reconciled_after_grace(self):
        stroll = ActivityRef("local_activity", "journey:jn-s", T0 - timedelta(minutes=40), T0 - timedelta(minutes=1))
        grace = self.decide(runtime(stroll), facts())
        self.assertEqual((grace.action, silence_of(grace), grace.next_check_at), (HeartbeatAction.CONTINUE, SilenceReason.LIVING, T0 + timedelta(minutes=1)))
        late_now = T0 + timedelta(minutes=5)
        late = self.decide(runtime(stroll, as_of=late_now), facts(), now=late_now)
        self.assertEqual((late.action, silence_of(late), late.next_check_at), (HeartbeatAction.RECOVER, SilenceReason.STATE_INCONSISTENT, late_now + POLICY.follow_up))
        self.assertEqual([(intent.kind, intent.source_ref) for intent in late.task_intents], [(IntentKind.RECONCILE.value, "journey:jn-s")])
        for activity in (None, ActivityRef("unknown", None)):  # 不知道 TA 在做什么：对账，不去猜
            unknown = self.decide(runtime(activity), facts())
            self.assertEqual((unknown.action, unknown.task_intents[0].kind), (HeartbeatAction.RECOVER, IntentKind.RECONCILE.value))
            self.assertIn(ReasonCode.ACTIVITY_UNKNOWN.value, unknown.reason_codes)
        retrying = DueItem("journey:jn-s", DueKind.JOURNEY, T0 - timedelta(minutes=1), attempts=1, retry_after=T0 + timedelta(minutes=7))
        handled = self.decide(runtime(stroll, as_of=late_now), facts([retrying]), now=late_now)  # 结束边界已在处理（退避中）：不对账
        self.assertEqual((handled.action, handled.next_check_at), (HeartbeatAction.CONTINUE, T0 + timedelta(minutes=7)))

    def test_maintenance_pauses_everything(self):
        due = DueItem("reply:conv-a", DueKind.REPLY, T0 - timedelta(minutes=1), commitment=True)
        expired = [wake(WakeKind.task_expired, "task:wt_2", T0, 3)]
        paused = self.decide(runtime(), facts([due], maintenance=True), events=expired)
        self.assertEqual((paused.action, silence_of(paused), paused.task_intents), (HeartbeatAction.DEFER, SilenceReason.MAINTENANCE, ()))
        self.assertEqual((paused.next_check_at, paused.consumed_event_ids), (T0 + POLICY.dependency_recheck, ()))  # 事件留到维护结束
        self.assertIs(SilenceReason.MAINTENANCE.kind, SilenceKind.DEFERRED)
        resumed = self.decide(runtime(), facts([due]), events=expired)
        self.assertEqual({intent.kind for intent in resumed.task_intents}, {IntentKind.DELIVER_REPLY.value, IntentKind.RECOVER_TASK.value})

    def test_minimal_state_and_derivations(self):
        minimal = self.decide(runtime(pending_commitment_deadline=T0 - timedelta(seconds=1)))  # 只有共享 RuntimeState，没有 HeartbeatFacts
        self.assertEqual([(intent.kind, intent.source_ref) for intent in minimal.task_intents], [(IntentKind.SETTLE_DUE.value, "commitment:earliest")])
        idle = self.decide(runtime(cognition_status="quiet"))  # 最小事实不启用大脑，走规则生活
        self.assertEqual([intent.kind for intent in idle.task_intents], [IntentKind.RULE_LIFE_PLAN.value])
        self.assertIn(ReasonCode.BRAIN_DISABLED.value, idle.reason_codes)
        operation = InFlightBrain("op-4", "life_plan", versions(), T0, T0 + timedelta(seconds=90))
        heart = facts([DueItem("reply:conv-a", DueKind.REPLY, T0 + timedelta(minutes=5), commitment=True),
                       DueItem("journey:jn-1", DueKind.JOURNEY, T0 + timedelta(minutes=1))], replace(BRAIN_ON, operation=operation))
        self.assertEqual(commitment_deadline(heart), T0 + timedelta(minutes=5))
        statuses = [cognition_status(heart, T0), cognition_status(replace(heart, cognition=replace(heart.cognition, operation=replace(operation, running=True))), T0),
                    cognition_status(facts(cognition=CognitionFacts()), T0), cognition_status(facts(), T0),
                    cognition_status(facts(cognition=replace(BRAIN_ON, availability=BrainAvailability.UNAVAILABLE)), T0)]
        self.assertEqual(statuses, ["queued", "running", "disabled", "quiet", "backoff"])
        for bad in (dict(brain_fallback="guess"), dict(min_delay=timedelta(0)), dict(max_intents=0)):
            with self.assertRaises(ValueError):
                HeartbeatPolicy(**bad)
        with self.assertRaises(ValueError):
            evaluate(runtime(), [], POLICY, T0.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            evaluate(runtime(pet_id=""), [], POLICY, T0)
        with self.assertRaises(ValueError):
            facts([DueItem("journey:jn-1", DueKind.JOURNEY, T0.replace(tzinfo=None))])


if __name__ == "__main__":
    unittest.main()
