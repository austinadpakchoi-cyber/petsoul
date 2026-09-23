"""同连接读的授权复核 `households.generated_photos_in(conn, pet_id)`（CR-B-to-I，归 I）。

为什么要有它：付费生图的最终写入在一个写事务里完成。如果这时另开连接去读"还能不能生成照片"，
读到的是**事务外**的旧值——主人刚撤销的许可看不见，图照样会被发布出去。这正是协调方 08:40 在
`candidate-0829` 快照上复现的那条缺口（场景响应后、写入前撤权，新图仍以 ready 发布）。

这里验三件事：
  ① 它和组合根的 `generated_photos_of` **同源**——家庭显式设置优先、没设过沿用建家人的个人选择、没家庭一律 False；
  ② 它**只在传进来的连接上读**，不另开连接、不 BEGIN、不 commit；
  ③ 因此它能在**同一个写事务里**看见刚写下的撤销，而另开连接的版本看不见。

A 用来接 `illustrations.consent_in` 的就是它。本文件不改任何生图实现。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class ConsentSameConnectionTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("consent-conn-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.households = self.web.households

    def consent(self) -> bool:
        """同连接版本（各开一个只读连接来问，等价于普通读场景）。"""
        with self.app.state.storage.connect() as conn:
            return self.households.generated_photos_in(conn, self.owner.pet_id)

    def household_id(self) -> str:
        return self.households.household_of_pet(self.owner.pet_id)

    # ---- ① 同源 ----
    def test_it_agrees_with_the_composition_root_in_every_case(self) -> None:
        """三种情形逐个比对：默认、家庭显式打开、家庭显式关闭。两边必须**始终相同**。"""
        opted_in = self.web.illustrations.opted_in  # 组合根接上去的那个（现在委托到 generated_photos_in）
        for label, prepare in (
            ("默认（家庭没设过，沿用建家人的个人选择）", lambda: None),
            ("主人开启个人设置", lambda: self.owner.patch("/settings", {"generated_photos": True})),
            ("家庭显式打开", lambda: self.owner.patch(f"/households/{self.household_id()}/settings", {"generated_photos": True})),
            ("家庭显式关闭", lambda: self.owner.patch(f"/households/{self.household_id()}/settings", {"generated_photos": False})),
        ):
            prepare()
            self.assertEqual(self.consent(), bool(opted_in(self.owner.user_id, self.owner.pet_id)),
                             f"{label}：同连接版本与组合根必须给出同一个答案")

    def test_a_resident_without_a_household_never_gets_photos(self) -> None:
        """没有家庭的居民（还没被领养的）一律 False，不看任何人的个人设置。"""
        with self.app.state.storage.connect() as conn:
            self.assertFalse(self.households.generated_photos_in(conn, "PJ-NOBODY"))
            self.assertFalse(self.households.generated_photos_in(conn, None), "pet_id 为空也不能当成有授权")

    # ---- ②③ 同一个写事务里看得见刚写下的撤销 ----
    def test_it_sees_a_withdrawal_made_in_the_same_transaction(self) -> None:
        """在一个写事务里先撤销、再复核：**必须读到撤销后的值**。

        这是整条修复的关键。对照组是组合根那个另开连接的版本——在同一时刻它**读不到**这次还没提交的撤销。
        """
        self.owner.patch(f"/households/{self.household_id()}/settings", {"generated_photos": True})
        self.assertTrue(self.consent(), "前提：现在是允许的")

        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE web_households SET generated_photos = 0 WHERE household_id = ?", (self.household_id(),))
            inside = self.households.generated_photos_in(conn, self.owner.pet_id)
            outside = self.web.illustrations.opted_in(self.owner.user_id, self.owner.pet_id)

        self.assertFalse(inside, "同连接版本要看见本事务里刚写下的撤销")
        self.assertTrue(outside, "对照：另开连接的版本此刻还读不到——正因为如此，写事务里必须用同连接版本")
        self.assertFalse(self.consent(), "提交之后两边都应当是撤销后的值")

    def test_it_does_not_start_or_finish_a_transaction(self) -> None:
        """它不能自己 BEGIN / commit：调用方的事务还得由调用方收尾。

        做法：在一个已经开着的写事务里调它，调用之后事务**必须仍然开着**（`in_transaction` 为真），
        并且调用方随后回滚时，事务里的改动要能整笔撤销。
        """
        self.owner.patch(f"/households/{self.household_id()}/settings", {"generated_photos": True})
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE web_households SET generated_photos = 0 WHERE household_id = ?", (self.household_id(),))
            self.households.generated_photos_in(conn, self.owner.pet_id)
            self.assertTrue(conn.in_transaction, "调完之后事务还得开着——它不许替调用方提交")
            conn.rollback()

        self.assertTrue(self.consent(), "回滚之后授权要回到撤销之前的样子，说明它没有偷偷提交过")


if __name__ == "__main__":
    unittest.main()
