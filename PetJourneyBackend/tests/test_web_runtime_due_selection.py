"""按到期取宠物：唤醒来源齐全、不漏调度、不绕过上限、也不造成另一种饥饿（CR-B6）。

`next_check_at` 原来只写不读，每 30 秒把所有宠物重算一遍，而且每只要算两遍。
换成"按到期取"必须同时保证：
  - 唤醒来源齐全（due / never / changed / reply / suggestion ＋ 看门狗兜底），否则会漏调度；
  - **旧评估不得确认它没读到的新版本**，否则它会把别人刚立起的唤醒信号抹掉；
  - 新来的和已有的**共用同一个上限与同一条轮转**，既不能绕过上限，也不能简单截断把后面的饿死。

用真实装配与真实库，假时钟；不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.utils import iso
from app.web_runtime.heartbeat_policy import HeartbeatPolicy
from web_base import FakeClock, WebPlatformTestBase

HK = timezone(timedelta(hours=8))  # 这批夹具的宠物住在 Asia/Hong_Kong
LOCAL_NOON = datetime(2026, 9, 22, 12, 0, tzinfo=HK)


class DueSelectionTests(WebPlatformTestBase):
    """CR-B6：按 next_check_at 取该看的宠物，并且五个唤醒来源齐全、不漏调度。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LOCAL_NOON.astimezone(timezone.utc)).install(self)
        self.owner = self.user("due-selection-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        self.projector = self.web.projector
        self.watchdog = HeartbeatPolicy().max_check_interval

    def due(self) -> dict[str, str]:
        """和正式装配同一个调用法：带上 roster，否则还没有运行记录的新宠物会整个看不见。"""
        return dict(self.projector.runtime.due_pets(self.clock.now, watchdog=self.watchdog, roster=[self.pet]))

    def evaluate_once(self) -> None:
        """跑一轮 shadow：这只宠物被评估、写下 next_check_at 与 last_evaluated_at。"""
        self.assertIsNotNone(self.web.shadow, "前提：这个环境开着心跳 shadow")
        self.web.shadow.run(self.clock.now)

    def next_check_at(self) -> datetime:
        row = self.projector.runtime.row(self.pet)
        self.assertTrue(row.get("next_check_at"), f"前提：上一轮排了下次检查时刻：{row}")
        return datetime.fromisoformat(row["next_check_at"])

    def test_a_pet_that_was_never_evaluated_is_picked_up(self) -> None:
        self.assertEqual(self.due().get(self.pet), "never", "没评估过的必须排上")

    def test_a_pet_with_a_future_check_is_left_alone(self) -> None:
        self.evaluate_once()
        self.assertGreater(self.next_check_at(), self.clock.now, "前提：下次检查排在以后")

        self.assertNotIn(self.pet, self.due(), "还没到点、也没有新事情：这一轮不用再看它")

    def test_a_pet_whose_check_came_due_is_picked_up(self) -> None:
        self.evaluate_once()
        self.clock.now = self.next_check_at() + timedelta(seconds=1)

        self.assertEqual(self.due().get(self.pet), "due", "到点了就要看")

    def test_a_pet_untouched_past_the_watchdog_is_picked_up(self) -> None:
        """看门狗兜底：万一唤醒来源漏了什么，也不会有宠物被饿死。"""
        self.evaluate_once()
        self.clock.now = self.clock.now + self.watchdog + timedelta(minutes=1)

        self.assertEqual(self.due().get(self.pet), "watchdog")

    def test_a_change_to_the_runtime_row_wakes_the_pet(self) -> None:
        """撤权、改 DNA、换成员、活动变化都会动这一行：动过就要重新看一遍。"""
        self.evaluate_once()
        self.clock.now = self.clock.now + timedelta(seconds=30)
        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.projector.runtime.bump_in(conn, self.pet, "privacy_epoch", self.clock.now)

        self.assertEqual(self.due().get(self.pet), "changed", "版本变了就不能等到原定时刻")

    def test_a_queued_reply_wakes_the_pet(self) -> None:
        """回复承诺是**兜底**来源：上一轮排好下次检查之后才进来的消息，不能等到那个时刻才被看见。
        所以这里把行状态直接摆成"刚评估过、下次检查还早"，再让一条回复到点。"""
        self.clock.now = datetime(2026, 9, 23, 2, 0, tzinfo=HK).astimezone(timezone.utc)  # 香港凌晨，TA 睡着
        self.evaluate_once()
        self.owner.post(f"/communicator/{self.pet}/messages", {"client_message_id": "due-sel-0001", "text": "醒了叫我"})
        self.clock.now = self.clock.now + timedelta(minutes=1)
        with self.web.journeys.storage.connect() as conn:
            conn.execute("UPDATE web_entity_runtime SET last_evaluated_at = ?, updated_at = ?, next_check_at = ? WHERE pet_id = ?",
                         (iso(self.clock.now), iso(self.clock.now), iso(self.clock.now + timedelta(hours=3)), self.pet))
            conn.execute("UPDATE web_pending_replies SET due_at = ? WHERE pet_id = ?", (iso(self.clock.now), self.pet))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM web_pending_replies WHERE pet_id = ?", (self.pet,)).fetchone()[0], 1,
                             "前提：确实排了一条回复")

        self.assertEqual(self.due().get(self.pet), "reply", "有到点的回复承诺就要看，不能干等下次检查")

    def test_a_new_suggestion_wakes_the_pet(self) -> None:
        self.evaluate_once()
        self.clock.now = self.clock.now + timedelta(seconds=30)
        self.assertIsNotNone(self.web.life.suggest(self.owner.user_id, self.pet, self.owner.home_id, "local:stroll", self.clock.now))

        self.assertEqual(self.due().get(self.pet), "suggestion", "家人刚提的建议要当轮看到，不能等下次检查")

    def test_a_pet_in_maintenance_is_left_alone(self) -> None:
        self.evaluate_once()  # 先有运行记录行，才谈得上"被暂停"
        with self.web.journeys.storage.connect() as conn:
            changed = conn.execute("UPDATE web_entity_runtime SET maintenance = 1 WHERE pet_id = ?", (self.pet,)).rowcount
        self.assertEqual(changed, 1, "前提：暂停标记确实写上了")
        self.clock.now = self.clock.now + self.watchdog + timedelta(minutes=1)  # 连看门狗都过了也不该排它

        self.assertNotIn(self.pet, self.due(), "管理员暂停了这只宠物就别再排它")

    def test_no_pet_is_left_behind_across_half_a_day(self) -> None:
        """不漏调度：按到期取连跑 12 小时，这只宠物在看门狗窗口内一定被看过。

        **证明范围**：这是**假时钟的隔离模拟**（单只宠物、无并发命令、无真实负载），
        只证明"选谁"这套规则自身不会饿死宠物；**不能替代完整自然昼夜的 shadow 对照**，那个由 I 安排候选环境。
        下面那条"评估次数远少于扫描轮数"也只是**评估次数**之比，**不等于**整轮数据库成本同比下降
        （每轮仍要跑一次候选查询）。
        """
        self.evaluate_once()
        # 假时钟只推墙上时间、不推单调时钟，时钟健康监视器会（正确地）把每轮 30 秒判成"大幅前跳"，
        # 于是每轮都要 RECOVER。那是假时钟的产物，不是这条用例要验的东西——每轮重新建立参照点。
        # 真实进程里一轮 30 秒的墙上差与单调差基本相等，不会被判异常；前跳本身另有用例专门验。
        reanchor = lambda: self.projector.clock_monitor.reanchor(self.projector.clock)  # noqa: E731
        reanchor()
        scans = evaluated = 0
        last_seen = self.clock.now
        longest_gap = timedelta(0)
        for _ in range(12 * 60 * 2):  # 12 小时 × 每 30 秒一轮（跨过两个看门狗窗口）
            self.clock.now = self.clock.now + timedelta(seconds=30)
            reanchor()
            scans += 1
            picked = self.due()
            if self.pet in picked:
                self.web.shadow.run(self.clock.now)
                evaluated += 1
                longest_gap = max(longest_gap, self.clock.now - last_seen)
                last_seen = self.clock.now
        longest_gap = max(longest_gap, self.clock.now - last_seen)

        self.assertLessEqual(longest_gap, self.watchdog + timedelta(minutes=1), f"最长有 {longest_gap} 没被看过，超过看门狗窗口")
        self.assertGreater(evaluated, 0, "一整天里总得看过几次")
        self.assertLess(evaluated, scans // 4, f"被评估的轮次要显著少于总轮次：{evaluated} / {scans}（只是评估次数之比）")

    # ---- 旧评估不得抹掉新变化的唤醒信号 ----
    def bump_privacy(self) -> None:
        with self.web.journeys.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.projector.runtime.bump_in(conn, self.pet, "privacy_epoch", self.clock.now)

    def test_a_stale_evaluation_cannot_confirm_versions_it_never_read(self) -> None:
        """交错顺序：评估读到旧状态 → 新命令递增 privacy_epoch → 旧评估才写回来。

        旧评估必须被整个作废。否则它会把 `last_evaluated_at` 推到自己那个旧时刻、
        把 `updated_at` 覆盖成更早的值，`due_pets` 的 `changed` 就从成立变成不成立，
        那条新变化的唤醒信号被抹掉，下一次检查要等到六小时后的看门狗。
        """
        from app.web_runtime.heartbeat_policy import evaluate

        self.evaluate_once()
        read_at = self.clock.now
        state, facts = self.projector.snapshot(self.pet, read_at)          # ① 评估读到的旧状态
        decision = evaluate(state, (), HeartbeatPolicy(), read_at, facts=facts)

        self.clock.now = read_at + timedelta(seconds=30)
        self.bump_privacy()                                                # ② 新命令改了版本
        self.assertEqual(self.due().get(self.pet), "changed", "前提：这条新变化确实立起了唤醒信号")

        moved = self.projector.runtime.record_evaluation(                  # ③ 旧评估现在才写回来
            self.pet, decision, read_at, expected=state.versions)

        self.assertEqual(list(moved), ["privacy_epoch"], "旧评估要被如实判成作废，并说出是哪个版本变了")
        self.assertEqual(self.due().get(self.pet), "changed", "唤醒信号不能被旧评估抹掉")
        row = self.projector.runtime.row(self.pet)
        self.assertGreater(row["updated_at"], row["last_evaluated_at"], "行上的“动过”标记必须还在")

    def test_the_same_interleaving_through_the_real_shadow_round(self) -> None:
        """同一个交错，走真实的 shadow 一轮：注入点放在 record_evaluation 被调用的那一瞬间。"""
        self.evaluate_once()
        self.clock.now = self.next_check_at() + timedelta(seconds=1)
        before = dict(self.projector.runtime.row(self.pet))
        original = self.projector.runtime.record_evaluation
        injected: list[int] = []

        def bump_then_record(pet_id, decision, now, **kwargs):
            if not injected:  # 只在第一次写回之前插进去，模拟"算完之后、写回之前"世界变了
                injected.append(1)
                self.bump_privacy()
            return original(pet_id, decision, now, **kwargs)

        self.projector.runtime.record_evaluation = bump_then_record
        self.web.shadow.run(self.clock.now)
        self.projector.runtime.record_evaluation = original

        self.assertEqual(injected, [1], "前提：注入确实发生了")
        self.assertEqual(self.web.shadow.last.stale, 1, f"这一轮要如实记成作废一条：{self.web.shadow.last}")
        after = dict(self.projector.runtime.row(self.pet))
        self.assertEqual(after["last_evaluated_at"], before["last_evaluated_at"], "作废的那次不能把自己记成“评估过了”")
        self.assertEqual(after["next_check_at"], before["next_check_at"], "也不能用旧事实改写下次检查时刻")
        self.assertGreaterEqual(after["updated_at"], before["updated_at"], "“动过”标记只能往前，不能被写回旧时刻")
        # 这一轮仍然该看它。具体理由是 due 还是 changed 取决于哪一条先命中，
        # 要点是**它没有被判成"六小时后再说"**。
        self.assertIn(self.pet, self.due(), "下一轮必须还排得到它，不能等到看门狗")

    def test_an_evaluation_that_read_the_current_world_is_written_down(self) -> None:
        """对照组：没有人插进来改东西时，评估照常写下，别把"作废"修成"永远写不进去"。"""
        self.evaluate_once()
        self.assertEqual(self.web.shadow.last.stale, 0, "没有交错就不该有作废")
        self.assertTrue(self.projector.runtime.row(self.pet).get("last_evaluated_at"), "结论要真的写下来")
        self.assertNotIn(self.pet, self.due(), "写下之后这一轮就不用再看它了")

    # ---- 新旧候选共用同一个上限与轮转 ----
    def newcomers(self, count: int) -> list[str]:
        """还没有运行记录的宠物编号。这一组用例验的是"选谁"这套规则本身，所以用合成编号，跑得快也确定。"""
        return [f"PJ-NEW{index:04d}" for index in range(count)]

    def test_new_pets_do_not_bypass_the_round_limit(self) -> None:
        roster = self.newcomers(5)

        picked = self.projector.runtime.due_pets(self.clock.now, watchdog=self.watchdog, roster=roster, limit=2)

        self.assertEqual(len(picked), 2, f"五只新宠物也要守 limit=2，不能绕过去：{picked}")
        self.assertTrue(all(why == "never" for _pet, why in picked))

    def test_every_new_pet_gets_its_turn_across_rounds(self) -> None:
        """共用上限之后不能变成另一种饥饿：按游标轮转，连续几轮里每一只都要排到。"""
        roster = self.newcomers(5)
        after, seen = "", set()

        for _ in range(3):  # 5 只、每轮 2 只：三轮足够全部排到
            picked = self.projector.runtime.due_pets(self.clock.now, watchdog=self.watchdog, roster=roster, after=after, limit=2)
            self.assertLessEqual(len(picked), 2, "每一轮都要守上限")
            seen.update(pet_id for pet_id, _why in picked)
            if picked:
                after = picked[-1][0]

        self.assertEqual(seen, set(roster), f"这些一直没排上：{set(roster) - seen}")

    def test_an_already_due_pet_is_not_starved_by_newcomers(self) -> None:
        """另一侧的饥饿：一堆新宠物不能把"已经到点"的老宠物一直挤掉。"""
        self.evaluate_once()
        self.clock.now = self.next_check_at() + timedelta(seconds=1)
        roster = [self.pet, *self.newcomers(5)]
        after, seen = "", set()

        for _ in range(4):
            picked = self.projector.runtime.due_pets(self.clock.now, watchdog=self.watchdog, roster=roster, after=after, limit=2)
            seen.update(pet_id for pet_id, _why in picked)
            if picked:
                after = picked[-1][0]

        self.assertIn(self.pet, seen, "到点的那只也要轮得到，不能被新宠物一直挤掉")


if __name__ == "__main__":
    unittest.main()
