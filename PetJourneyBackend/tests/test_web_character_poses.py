"""批次二：其余五个姿态的**登记、参考与读取**（`web_character/poses.py`）。真实装配 ＋ 假供应商，不联网、**0 次付费调用**。

作废与费用那一半在 `test_web_character_pose_gates.py`；共用装置在 `pose_chain_base.py`。

用户 2026-09-24 决定：后端全套做完，**额外姿态的自动生成开关默认关**。所以这里第一条就钉「关着时什么都不变」，
其余用例在各自开头显式打开开关——它们测的是"打开之后链路对不对"，不是"应该打开"。

规范（P《世界角色导演模式》§6-4／§6-5）里本文件对应的几条：

  - 登记与切 active 在**同一个事务**里，而且只在真的切过去时登记；
  - 参考是**同一套已生效的中性站姿**，压到灰底上再发，不是主人原照；
  - **缺的姿态只能回落到同一套的中性站姿，绝不回落到旧套的那张**。
"""

from __future__ import annotations

import sqlite3
import unittest
from unittest import mock

from pose_chain_base import EXTRA, PoseChainBase

from app.web_character import flatten, prompts, validate
from app.web_character.model import POSE_KIND
from app.web_platform.budget import BudgetLimit


class PoseRegistrationAndReadTests(PoseChainBase):
    # ---- ① 开关关着：什么都不变 ----
    def test_with_the_switch_off_nothing_changes(self) -> None:
        """默认关（用户 2026-09-24 决定）。**不新增任何付费调用**，读接口也与批次一相同。"""
        self.assertFalse(self.web.character.poses.enabled, "默认必须是关")

        self.web.character.run_pending()

        self.assertEqual(self.illustrator.calls, 1, "只画了中性站姿那一张")
        self.assertEqual((self.pose_rows(), self.pose_tasks()), ([], []))
        body = self.state()
        self.assertEqual([asset["pose"] for asset in body["active"]["assets"]], ["neutral_full"])
        self.assertEqual(body["poses"], [])

    # ---- ② 登记：中性站姿生效的那个事务里 ----
    def test_the_neutral_going_live_queues_the_five_poses_in_the_same_set(self) -> None:
        self.switch_on()

        self.go_live()

        neutral = self.neutral()
        rows = self.pose_rows()
        self.assertEqual([row["pose"] for row in rows], EXTRA)
        for row in rows:
            self.assertEqual((row["state"], row["set_id"], row["revision"]), ("queued", neutral["set_id"], neutral["revision"]))
            self.assertEqual(row["reference_digest"], neutral["sha256"], "绑定的是同一套中性站姿的那串字节")
        self.assertEqual(len(self.pose_tasks()), 5)
        self.assertEqual(self.illustrator.calls, 1, "登记不是发送：这一步一次都没多发")

    def test_a_neutral_that_does_not_go_live_queues_no_poses(self) -> None:
        """条件写入没切过去（更新的一套已经生效）：这一套不会被看到，**不为它画其余五张**。"""
        self.switch_on()
        with self.app.state.storage.connect() as conn:
            conn.execute("INSERT INTO web_pet_character_active (pet_id, set_id, revision, published_at) VALUES (?, ?, ?, ?)",
                         (self.pet_id, "cs-newer-set", 99, "2026-09-24T00:00:00+00:00"))

        self.web.character.run_pending(limit=1)

        self.assertEqual(self.active()["set_id"], "cs-newer-set", "过期的一套覆盖不了更新的")
        self.assertEqual((self.pose_rows(), self.pose_tasks()), ([], []))

    def test_if_registering_the_poses_fails_the_switch_rolls_back_too(self) -> None:
        """登记与切 active **同一个事务**：登记失败，切换也不能留下——否则这一套生效了却永远补不齐。"""
        self.switch_on()
        queue = self.web.character.tasks
        original = queue.enqueue_in

        def broken(conn, kind, *args, **kwargs):
            if kind == POSE_KIND:
                raise sqlite3.OperationalError("登记失败（测试注入）")
            return original(conn, kind, *args, **kwargs)

        with mock.patch.object(queue, "enqueue_in", broken):
            self.web.character.run_pending(limit=1)

        self.assertIsNone(self.active(), "登记没成，切换也跟着回滚")
        self.assertEqual((self.pose_rows(), self.pose_tasks()), ([], []))
        self.assertNotEqual(self.neutral()["state"], "ready", "中性站姿那一行也没有落成 ready")

    # ---- ③ 参考：同一套的中性站姿，压到灰底上再发 ----
    def test_each_pose_is_drawn_from_the_flattened_neutral_on_its_own_canvas(self) -> None:
        self.switch_on()

        self.web.character.run_pending(limit=6)

        self.assertEqual(self.illustrator.calls, 6, "中性站姿 1 张 ＋ 五个姿态")
        neutral = self.neutral()
        stored = (self.web.character.root / neutral["rel_path"]).read_bytes()
        expected_reference, gray = flatten.flatten(stored)
        self.assertEqual(gray, flatten.LIGHT, "假图的主体是深棕色，应落在浅灰上")
        by_prompt = {prompts.build_pose_prompt("cat", pose): pose for pose in EXTRA}
        drawn = set()
        for prompt, reference, size, background in zip(self.illustrator.prompts[1:], self.illustrator.references[1:],
                                                       self.illustrator.sizes[1:], self.illustrator.backgrounds[1:]):
            pose = by_prompt[prompt]
            drawn.add(pose)
            with self.subTest(pose=pose):
                self.assertEqual(reference, (expected_reference, "image/png"), "参考＝同一套中性站姿压在灰底上")
                self.assertEqual(validate.inspect(reference[0], "image/png").reason, validate.NO_ALPHA_CHANNEL,
                                 "发出去的参考图根本没有 alpha：接口把透明区当蒙版的歧义不存在")
                self.assertEqual(size, prompts.POSE_CANVAS[pose], "画幅跟着身体轮廓走")
                self.assertEqual(background, "transparent", "输出的透明仍由参数负责")
        self.assertEqual(drawn, set(EXTRA))
        # 与**服务实际读到的**原照比：上传时 GPS 之类的文本块已被剥掉，存下的不是 `tiny_png()` 那串原字节
        self.assertEqual(self.illustrator.references[0], self.web.character.reference_photo_of(self.pet_id),
                         "只有中性站姿用主人原照")
        self.assertEqual({row["state"] for row in self.pose_rows()}, {"ready"})
        self.assertEqual((self.web.character.root / neutral["rel_path"]).read_bytes(), stored, "已存资产一个字节都不动")

    # ---- ④ 读：只看 active 这一套 ----
    def test_the_state_lists_this_sets_poses_behind_the_neutral(self) -> None:
        self.switch_on()
        self.web.character.run_pending(limit=6)

        body = self.state()

        assets = body["active"]["assets"]
        self.assertEqual([asset["pose"] for asset in assets], ["neutral_full", *EXTRA])
        self.assertEqual([(item["pose"], item["status"]) for item in body["poses"]], [(pose, "ready") for pose in EXTRA])
        sleeping = assets[1]["asset_id"]
        self.assertEqual(self.owner.get(f"/media/characters/{sleeping}").status_code, 200)
        stranger = self.user("pose-stranger")
        self.assertEqual(stranger.get(f"/media/characters/{sleeping}").status_code, 404, "姿态图与站姿同样按宠物可见性保护")

    def test_a_new_set_never_borrows_the_old_sets_poses(self) -> None:
        """**§6-4 唯一不可放松的不变量**：缺的姿态只能回落到同一套的中性站姿，绝不回落到旧套的那张。"""
        self.switch_on()
        self.web.character.run_pending(limit=6)
        old_set = self.active()["set_id"]
        self.clock.advance(days=1)  # 推到第二天，与额度默认值脱钩（上限只够一套时同一天会被挡，见下一条）
        accepted, _, _ = self.web.character.regenerate(self.pet_id, self.owner.user_id)
        self.assertTrue(accepted)

        self.web.character.run_pending(limit=1)  # 新一套的中性站姿生效，它的五个姿态还在排队

        body = self.state()
        self.assertNotEqual(body["active"]["character_set_id"], old_set)
        self.assertEqual([asset["pose"] for asset in body["active"]["assets"]], ["neutral_full"],
                         "旧套那五张就在库里、也都是 ready——一张都不许借过来")
        self.assertEqual([item["status"] for item in body["poses"]], ["queued"] * 5)
        self.assertEqual(body["status"], "ready", "综合状态看中性站姿，不被排队中的姿态带偏")

    def test_a_same_day_adjustment_runs_into_a_per_pet_cap_of_one_set(self) -> None:
        """**打开开关之前要知道的算术**，不是缺陷：一整套 6 个单位（中性站姿 1 ＋ 五个姿态各 1）。
        每宠每日上限**等于一套**时，同一天再「调整形象」，新一套的中性站姿就被额度挡下，旧的一套照常显示。
        写这批用例时撞出来的——上一条原本就写在同一天，新一套死活切不过去。

        **上限在这里显式设成 6，与配置默认值脱钩**：默认值会变（用户 2026-09-24 决定调高，
        每宠 6 → 12）。调到 12 之后同一天还能再调整一次，第三套才会撞上（见下一条）——
        这条钉的是"上限÷一套的单位数＝一天能有几套"，不是某一个默认值。
        """
        self.cap_character_lane(6)
        self.switch_on()
        self.web.character.run_pending(limit=6)
        old_set = self.active()["set_id"]
        accepted, _, _ = self.web.character.regenerate(self.pet_id, self.owner.user_id)
        self.assertTrue(accepted, "排得上：额度是执行时才查的")

        self.web.character.run_pending(limit=1)

        self.assertEqual(self.active()["set_id"], old_set, "旧的一套照常显示")
        body = self.state()
        self.assertEqual((body["status"], body["candidate"]["reason"]), ("failed", "budget_denied"))
        self.assertEqual(self.illustrator.calls, 6, "被挡下的那一次没有发出去")

    def test_with_a_cap_of_two_sets_the_third_same_day_set_is_denied(self) -> None:
        """**现行默认的算术**：每宠 12 ＝ 一套 6 ＋ 再调整一次 6（P 的建议、用户 2026-09-24 定）。
        同一天第二套照常生成、照常生效，**第三套**的中性站姿才被挡下。上限同样显式写 12，不吃默认值。"""
        self.cap_character_lane(12)
        self.switch_on()
        self.web.character.run_pending(limit=6)
        self.assertTrue(self.web.character.regenerate(self.pet_id, self.owner.user_id)[0])
        self.web.character.run_pending(limit=6)
        second = self.active()["set_id"]
        self.assertEqual(self.illustrator.calls, 12, "前提：同一天两整套，一张都没被挡")
        self.assertEqual({row["state"] for row in self.pose_rows() if row["set_id"] == second}, {"ready"})

        self.assertTrue(self.web.character.regenerate(self.pet_id, self.owner.user_id)[0])
        self.web.character.run_pending(limit=1)

        self.assertEqual(self.active()["set_id"], second, "第二套照常显示")
        self.assertEqual(self.state()["candidate"]["reason"], "budget_denied", "第三套才撞上")
        self.assertEqual(self.illustrator.calls, 12, "被挡下的那一次没有发出去")

    def cap_character_lane(self, units: int) -> None:
        """把角色车道的每宠每日上限**显式**设成 `units`（照装配里的 `reserve` 同样的写法，只换上限）。"""
        ledger = self.web.character.ledger
        self.web.character.reserve = lambda operation_id, pet_id, units_: ledger.reserve(
            operation_id, provider="image", purpose="character", subject_scope=f"pet:{pet_id}", units=units_,
            limits=[BudgetLimit(f"pet:{pet_id}:character", units)])


if __name__ == "__main__":
    unittest.main()
