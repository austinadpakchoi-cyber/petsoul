"""运营暂停一只宠物之后，**规则生活也不能替 TA 做决定**。

背景：后台的「暂停」写 `web_entity_runtime.maintenance`。心跳与认知线本来就看这一列
（`due_pets` 直接排除、`heartbeat_policy` 给 maintenance 安静原因），但**规则生活这条路原先不看**——
于是按下暂停之后，宠物照样会被送出门。运营以为按了就不动了，结果 TA 照样出门，
**那比不给这个按钮更糟**。

这份用例的形状有意如此：**每一条都先有一个"不暂停就真的出门"的对照**。
没有那个对照，"没出门"可能只是因为这一轮本来就不会出门——那样的断言永远绿，等于没写。
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

import app.web_agent.life as life_mod
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class LifeMaintenanceTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("maintenance-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        # 让规则生活这一轮**一定**想出门（掷骰恒为 0）：只有这样"被拦住"才说明是闸起了作用
        patch = mock.patch.object(life_mod, "_roll", lambda *parts: 0.0)
        patch.start()
        self.addCleanup(patch.stop)

    def pause(self) -> None:
        """照后台的写法：只写 maintenance 这一列。"""
        with self.web.journeys.storage.connect() as conn:
            changed = conn.execute(
                "INSERT INTO web_entity_runtime (pet_id, maintenance, updated_at) VALUES (?, 1, ?) "
                "ON CONFLICT(pet_id) DO UPDATE SET maintenance = 1, updated_at = excluded.updated_at",
                (self.pet, "2026-09-22T04:00:00+00:00")).rowcount
        self.assertEqual(changed, 1, "前提：暂停标记确实写上了")

    def went_out(self) -> bool:
        return self.web.journeys.repo.active_for_pet(self.pet) is not None

    def decision_slots(self) -> int:
        with self.web.journeys.storage.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM web_pet_decisions WHERE pet_id = ?", (self.pet,)).fetchone()["n"])

    def test_without_the_pause_it_really_does_go_out(self) -> None:
        """对照组。这一条要是红了，下面两条就都不算数——它们的"没出门"会变得毫无意义。"""
        self.web.life.run(self.clock.now)

        self.assertTrue(self.went_out(), "前提不成立：这一轮本来就不会出门，那“被拦住”就证明不了什么")

    def test_a_paused_pet_is_not_sent_out_by_the_rule_engine(self) -> None:
        self.pause()

        self.web.life.run(self.clock.now)

        self.assertFalse(self.went_out(), "运营暂停了这只宠物，规则生活不该还把 TA 送出门")

    def test_the_pause_does_not_burn_this_slot(self) -> None:
        """闸要放在最前面：再往下就会占掉这个时段的决定名额，
        那会让恢复之后的这半小时白白不出门——暂停不该偷走 TA 的时间。"""
        self.pause()

        self.web.life.run(self.clock.now)

        self.assertEqual(self.decision_slots(), 0, "被暂停的这一轮不该记下任何决定")

    def test_resuming_lets_it_go_out_again(self) -> None:
        """恢复之后要真的能回来——闸不能把宠物永久关在家里。"""
        self.pause()
        self.web.life.run(self.clock.now)
        self.assertFalse(self.went_out(), "前提：暂停期间确实没出门")

        with self.web.journeys.storage.connect() as conn:
            conn.execute("UPDATE web_entity_runtime SET maintenance = 0 WHERE pet_id = ?", (self.pet,))
        self.web.life.run(self.clock.now)

        self.assertTrue(self.went_out(), "恢复之后规则生活要能照常替 TA 决定")

    def test_every_gate_uses_the_one_shared_predicate(self) -> None:
        """三处闸必须是**同一份实现**（`RuntimeStore.paused` / `paused_pets`，与 `due_pets` 同一列同一条件）。

        各处自己读一次那一列，改一次就要记得改三处——今天已经在别处吃过这个亏。
        到点回复与主动消息那两处由 I 补，但调的是这里同一个谓词。
        """
        runtime = self.web.projector.runtime
        self.pause()

        self.assertTrue(runtime.paused(self.pet), "谓词本身要认得出暂停")
        self.assertIn(self.pet, runtime.paused_pets(), "成批那一版要给出同一个答案")
        self.assertTrue(self.web.projector.facts(self.pet, self.clock.now).maintenance, "心跳读的是同一列")
        # 绑定方法每次取属性都是新对象，所以比相等（同函数、同实例即相等），不比同一性
        self.assertEqual(self.web.life.paused, runtime.paused, "规则生活接的就是这个谓词，不是自己抄的一份")
        self.assertNotIn(self.pet, dict(runtime.due_pets(self.clock.now, watchdog=timedelta(hours=6), roster=[self.pet])),
                         "候选查询与谓词同一口径：被暂停的不进候选")

    def test_the_predicate_says_no_when_nothing_is_paused(self) -> None:
        """对照：没暂停时谓词必须是假，否则上面那些断言可能只是恒真。"""
        runtime = self.web.projector.runtime

        self.assertFalse(runtime.paused(self.pet))
        self.assertEqual(runtime.paused_pets(), set())
        self.assertFalse(runtime.paused("PJ-NOBODY"), "不存在的宠物不算被暂停")


if __name__ == "__main__":
    unittest.main()
