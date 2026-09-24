"""同连接读的授权复核 `households.generated_photos_in(conn, pet_id)`（CR-B-to-I，归 I）。

为什么要有它：付费生图的最终写入在一个写事务里完成。如果这时另开连接去读"还能不能生成照片"，
读到的是**事务外**的旧值——主人刚撤销的许可看不见，图照样会被发布出去。这正是协调方 08:40 在
`candidate-0829` 快照上复现的那条缺口（场景响应后、写入前撤权，新图仍以 ready 发布）。

这里验三件事：
  ① 它的语义——家庭显式设置优先、没设过沿用建家人的个人选择、没家庭一律 False；
     （**2026-09-24 更正**：这里原先写的是「和组合根的 `generated_photos_of` **同源**」。
      `generated_photos_of` 已随取消逐次授权询问被摘除，全仓只剩注释提到它，
      **再写"同源"会让人去找一个不存在的对照物**。本条现在直接对着库里那一列验，
      见 `stored()`——对照物不依赖任何接线是否还在。）
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

    def stored(self) -> int | None:
        """直接读库里那一列，**不经过任何接线**。"""
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT generated_photos FROM web_households WHERE household_id = ?",
                               (self.household_id(),)).fetchone()
        return None if row is None else row["generated_photos"]

    # ---- ① 与库里的落值一致 ----
    def test_it_agrees_with_the_stored_household_setting_in_every_case(self) -> None:
        """三种情形逐个比对：默认、家庭显式打开、家庭显式关闭。

        **对照物换过一次**：这里原先比的是组合根接上去的 `illustrations.opted_in`。
        2026-09-23 用户取消逐次询问后，那条接线被摘掉，`opted_in` 落回服务里的默认
        `lambda …: False`——**再拿它当对照，这条用例就成了"一个恒假值和另一个值比"**，
        既测不出同源，也不会立刻红得明显。改成直接读库里那一列：
        **对照物不再依赖任何接线是否还在。**
        """
        for label, prepare, expected in (
            ("默认（家庭没设过，沿用建家人的个人选择）", lambda: None, None),
            ("主人开启个人设置", lambda: self.owner.patch("/settings", {"generated_photos": True}), None),
            ("家庭显式打开", lambda: self.owner.patch(f"/households/{self.household_id()}/settings",
                                                {"generated_photos": True}), 1),
            ("家庭显式关闭", lambda: self.owner.patch(f"/households/{self.household_id()}/settings",
                                                {"generated_photos": False}), 0),
        ):
            prepare()
            if expected is None:
                continue  # 家庭没显式设过：回落到个人偏好，落库值为 NULL，不在本条的比对范围内
            self.assertEqual(self.stored(), expected, f"{label}：前提——库里应当是这个值")
            self.assertEqual(self.consent(), bool(expected),
                             f"{label}：同连接版本必须与库里的落值一致")

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
            # 对照组：**另开一个连接**问同一个问题。原先这里用的是组合根的
            # `illustrations.opted_in`（它内部就是"自己开一个连接"），那条接线 2026-09-23 被摘掉后
            # 恒为假，拿它当对照等于让这条断言永远成立。现在直接另开连接，
            # **对照的本质没变（同事务 vs 事务外），但不再依赖任何接线是否还在。**
            with self.app.state.storage.connect() as other:
                outside = self.households.generated_photos_in(other, self.owner.pet_id)

        self.assertFalse(inside, "同连接版本要看见本事务里刚写下的撤销")
        self.assertTrue(outside, "对照：另开连接此刻还读不到这次未提交的撤销——正因为如此，写事务里必须用同连接版本")
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
