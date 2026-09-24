"""批次二：其余五个姿态的**作废与费用**（`web_character/poses.py`）。真实装配 ＋ 假供应商，不联网、**0 次付费调用**。

登记、参考与读取那一半在 `test_web_character_poses.py`；共用装置在 `pose_chain_base.py`。

执行前与发布前各核一次**同一份判定**（`PoseService._stale_in`）：主人原照换没换、宠物还有没有家、
active 还是不是这一套；执行前另对中性站姿的字节**现算** sha256。任何一条变了就作废，不发布。
费用纪律与中性站姿相同：作废的在预占之前就停，结果不明不自动重发，额度不够不发，关掉开关就不再领取。
"""

from __future__ import annotations

import unittest

from character_fakes import opaque_png
from pose_chain_base import Denied, PoseChainBase, ReplacingIllustrator, TimeoutAfterNeutral


class PoseVoidingTests(PoseChainBase):
    def test_a_pose_for_a_set_that_is_no_longer_active_is_never_sent(self) -> None:
        self.switch_on()
        self.go_live()
        self.replace_active_set()

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1, "0 次额外发送")
        self.assertEqual({(row["state"], row["reason"]) for row in self.pose_rows()}, {("failed", "reference_changed")})
        self.assertEqual(self.pose_reservations(), [], "在预占之前就停了：0 预占")

    def test_a_pose_drawn_while_the_set_was_replaced_is_not_published(self) -> None:
        """画的时候另一套生效了：图已经画出来、钱也花了——**不发布的是"把它拿给主人看"**，费用照实记。"""
        self.switch_on()
        self.web.character.illustrator = ReplacingIllustrator(self.replace_active_set)

        self.web.character.run_pending(limit=2)  # 中性站姿 ＋ 第一个姿态

        drawn = [row for row in self.pose_rows() if row["state"] != "queued"]
        self.assertEqual(len(drawn), 1)
        self.assertEqual((drawn[0]["state"], drawn[0]["reason"], drawn[0]["rel_path"]), ("failed", "reference_changed", None))
        self.assertIsNone(self.web.character.media_path(drawn[0]["asset_id"]))
        self.assertEqual(self.pose_reservations(), [("settled", "succeeded", 1)], "发出去的那一次照实结算")

    def test_a_swapped_owner_photo_voids_the_pending_poses(self) -> None:
        """姿态的身份最终来自原照：原照换了，这一套的姿态一张都不再画（CR「换参考后旧结果不得发布」）。"""
        self.switch_on()
        self.go_live()
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_pet_profiles SET photo_ref = ? WHERE pet_id = ?",
                         (f"pets/{self.owner.user_id}/swapped.png", self.pet_id))

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual({(row["state"], row["reason"]) for row in self.pose_rows()}, {("failed", "reference_changed")})

    def test_a_pet_without_a_household_gets_no_poses(self) -> None:
        self.switch_on()
        self.go_live()
        with self.app.state.storage.connect() as conn:
            conn.execute("DELETE FROM web_household_pets WHERE pet_id = ?", (self.pet_id,))

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual({(row["state"], row["reason"]) for row in self.pose_rows()}, {("failed", "pet_has_no_household")})

    def test_a_neutral_file_changed_on_disk_is_not_used(self) -> None:
        """绑定的是**读出来的字节现算**的 sha256，不是库里记的那一列——文件被换过，就不拿它当参考。"""
        self.switch_on()
        self.go_live()
        (self.web.character.root / self.neutral()["rel_path"]).write_bytes(opaque_png())

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual({(row["state"], row["reason"]) for row in self.pose_rows()}, {("failed", "reference_changed")})


class PoseCostDisciplineTests(PoseChainBase):
    def test_an_unconfirmed_pose_is_reported_as_unknown_and_never_resent(self) -> None:
        self.switch_on()
        self.web.character.illustrator = TimeoutAfterNeutral()

        self.web.character.run_pending(limit=6)
        calls = self.web.character.illustrator.calls
        self.web.character.run_pending()

        self.assertEqual(self.web.character.illustrator.calls, calls, "结果不明的不自动重发——那会二次计费")
        self.assertEqual([item["status"] for item in self.state()["poses"]], ["unknown"] * 5,
                         "要如实说「还没确认」，不能说成「没画成」")
        self.assertEqual({status for status, _, _ in self.pose_reservations()}, {"unknown"})
        self.assertEqual({task["status"] for task in self.pose_tasks()}, {"failed"}, "当场进终态，不排回去")

    def test_turning_the_switch_off_stops_claiming_queued_poses(self) -> None:
        """关掉就是不再为它花钱：已经排上的留在队里、照实显示 `queued`，不领取。"""
        self.switch_on()
        self.go_live()
        self.web.character.poses.enabled = False

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual({row["state"] for row in self.pose_rows()}, {"queued"})
        self.assertEqual([item["status"] for item in self.state()["poses"]], ["queued"] * 5)

    def test_a_budget_denied_pose_is_not_sent_and_not_retried(self) -> None:
        self.switch_on()
        self.go_live()
        self.web.character.reserve = lambda operation_id, pet_id, units: Denied()

        self.web.character.run_pending(limit=5)

        self.assertEqual(self.illustrator.calls, 1)
        self.assertEqual({(row["state"], row["reason"]) for row in self.pose_rows()}, {("failed", "budget_denied")})
        self.assertEqual({task["status"] for task in self.pose_tasks()}, {"failed"})


if __name__ == "__main__":
    unittest.main()
