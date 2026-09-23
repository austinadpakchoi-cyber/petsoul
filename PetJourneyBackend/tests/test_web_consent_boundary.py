"""撤权边界：主人在生图过程中收回“生成照片”授权，之后会发生什么。

四个场景对应协调方在 candidate-0829 上的独立复现
（E:/petsoul-audit/coordination-audit/image-revocation-20260923/FINDING.md）：
  1. 许可不变（对照）——**修复前就应该通过**；
  2. 开工前撤权 —— 不能停在“处理中”；
  3. 证件照响应后、场景调用前撤权 —— 第二次调用不能再发；
  4. 场景响应后、写入前撤权 —— 这次的新图不能发布。

走真实 HTTP 家庭设置入口、真实组合根与队列，**只有生图供应商是替身**；不联网、不产生真实付费。

三层说法不能互相冒充（本文件的断言按这三层分开写）：
  - 事实层：已经发出的远端调用**撤不回**，也撤不回可能已产生的费用；
  - 本地费用层：已发出／已拿到结果的按**实际次数**结算，**不得退成 `not_sent`**；
  - 展示层：本次新图不发布、页面显示 `failed`（无图）＋ 诊断说明，**不冒充 `unknown`**。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class HookedIllustrator(FakeIllustrator):
    """替身生图：可以在**某一次调用返回之后**触发回调，用来精确制造“两次调用之间撤权”。

    `after_call[n]` 在第 n 次调用（从 1 开始）返回之前执行。进程内确定性注入，
    不是真实的并发供应商事务，也不是网络测试。
    """

    def __init__(self) -> None:
        super().__init__()
        self.after_call: dict[int, callable] = {}

    def render(self, prompt, reference=None, size="2048x2048"):
        result = super().render(prompt, reference, size)
        hook = self.after_call.get(len(self.prompts))
        if hook is not None:
            hook()
        return result


class ConsentBoundaryTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = HookedIllustrator()
        self.web.illustrations.illustrator = self.illustrator  # 唯一的替换：供应商换成替身

    # ---- 场景辅助 ----
    def owner_with_photos(self):
        owner = self.user("consent-owner")
        owner.adopt_and_move_in("adopt-lan")
        self.household_id = owner.get("/onboarding").json()["households"][0]["household_id"]
        self.assertTrue(owner.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.owner = owner
        return owner

    def revoke(self) -> None:
        """走正式家庭设置入口收回“生成照片”授权（与协调方探针同一条路）。"""
        response = self.owner.patch(f"/households/{self.household_id}/settings", {"generated_photos": False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.web.illustrations.opted_in(self.owner.user_id, self.owner.pet_id), "撤权后授权必须已经为假")

    def cafe_adventure(self) -> None:
        owner = self.owner
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)

    def message(self) -> dict:
        return next(m for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]
                    if "咖啡馆小侦探" in m["text"])

    def row(self, sql: str, params: tuple):
        with self.web.illustrations.storage.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def task_of(self, message: dict) -> str:
        return self.row("SELECT photo_task_id FROM web_messages WHERE message_id = ?", (message["message_id"],))["photo_task_id"]

    def reservations(self, task_id: str) -> list[tuple]:
        """这个任务的本地预占：(状态, 结果口径, 实际计量单位)。"""
        with self.web.illustrations.storage.connect() as conn:
            rows = conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations WHERE operation_id LIKE ? "
                                "ORDER BY rowid", (f"illustration:{task_id}:%",)).fetchall()
        return [(r["status"], r["outcome"], r["actual_units"]) for r in rows]

    def illustration(self, task_id: str):
        return self.row("SELECT status, rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))

    def start_photo(self) -> str:
        """走完一次真实冒险，排上生图任务，返回任务号（还没执行）。"""
        self.cafe_adventure()
        message = self.message()
        self.assertEqual(message["photo_status"], "processing", "刚排队时是处理中")
        self.message_id = message["message_id"]
        return self.task_of(message)

    def settled(self) -> str:
        return self.row("SELECT status FROM web_tasks WHERE task_id = ?", (self.task_id,))["status"]

    def privacy_epoch(self) -> int:
        row = self.row("SELECT privacy_epoch FROM web_entity_runtime WHERE pet_id = ?", (self.owner.pet_id,))
        return int(row["privacy_epoch"]) if row else 0

    # ---- 1. 正常许可（对照）：修复前就应该通过 ----
    def test_with_permission_unchanged_the_photo_is_produced_and_published(self) -> None:
        self.owner_with_photos()
        self.task_id = self.start_photo()

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "没有参考照片：证件照＋场景图两次替身调用")
        self.assertEqual(self.settled(), "succeeded")
        self.assertEqual(self.illustration(self.task_id)["status"], "ready")
        done = self.message()
        self.assertEqual(done["photo_status"], "ready")
        self.assertEqual(self.owner.get(done["photo_url"].removeprefix("/api/v1/web")).status_code, 200)
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 2)], "两次都发出了，按 2 结算")

    # ---- 2. 开工前撤权：不能停在“处理中” ----
    def test_revoking_before_the_worker_starts_does_not_leave_it_processing_forever(self) -> None:
        self.owner_with_photos()
        self.task_id = self.start_photo()

        self.revoke()
        self.web.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "一次都不该发出去")
        self.assertEqual(self.reservations(self.task_id), [], "没发出去就不该有预占")
        self.assertNotEqual(self.message()["photo_status"], "processing", "不能永远停在“正在画”")
        self.assertEqual(self.message()["photo_status"], "failed", "如实显示没有图；不冒充 unknown（那表示可能已发送）")
        self.assertEqual(self.illustration(self.task_id)["status"], "failed")
        self.assertNotEqual(self.settled(), "queued", "也不能排回队列自动重试")

    # ---- 3. 两次调用之间撤权：第二次不能再发 ----
    def test_revoking_between_the_two_calls_blocks_the_second_one(self) -> None:
        self.owner_with_photos()
        self.task_id = self.start_photo()
        self.illustrator.after_call[1] = self.revoke  # 证件照已经回来了，场景图还没发

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1, "撤权之后不能再发第二次可能付费的调用")
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 1)],
                         "第一次确实发出去了：按 1 结算，不能退成 not_sent")
        self.assertEqual(self.message()["photo_status"], "failed")
        self.assertEqual(self.illustration(self.task_id)["status"], "failed")

    # ---- 4. 最终写入前撤权：这次的新图不能发布 ----
    def test_revoking_after_the_last_response_does_not_publish_the_new_photo(self) -> None:
        self.owner_with_photos()
        self.task_id = self.start_photo()
        self.illustrator.after_call[2] = self.revoke  # 场景图已经回来了，还没写库

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "两次都已经发出去了，这是既成事实")
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 2)],
                         "已发出的照留：按 2 结算，不因为不发布就退回")
        record = self.illustration(self.task_id)
        self.assertNotEqual(record["status"], "ready", "撤权之后不能把这次的新图发布出去")
        done = self.message()
        self.assertEqual(done["photo_status"], "failed")
        self.assertIsNone(done["photo_url"], "不给图的地址")


    # ---- 5. 同连接授权读口：它挡的是“授权不成立、但版本代数没动”的那一格 ----
    def test_the_same_connection_consent_check_blocks_publication_on_its_own(self) -> None:
        """`consent_in` 不是版本围栏的重复品。

        版本围栏（`privacy_epoch`）挡的是"这次尝试当中用途授权变过"；
        `consent_in` 在同一个写事务里直接问"现在还允许吗"，挡的是代数没动、但授权本来就不成立的那一格。
        这里用**显式的测试注入**钉住这条分支；**正式接线归 B（CR-A14），测试注入不替代正式装配**——
        装配上那条用例由 B 补（I 已落地 `households.generated_photos_in(conn, pet_id)`，全仓只有这一份实现）。
        """
        self.owner_with_photos()
        self.task_id = self.start_photo()
        before = self.privacy_epoch()
        self.web.illustrations.consent_in = lambda conn, user_id, pet_id: False  # 测试替身：同连接复核说“不行”

        self.web.illustrations.run_pending()

        self.assertEqual(self.privacy_epoch(), before, "这一格的前提就是代数没动——动了就变成在测版本围栏了")
        self.assertEqual(len(self.illustrator.prompts), 2, "两次都已经发出去了")
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 2)], "已发出的照留，不退成 not_sent")
        self.assertNotEqual(self.illustration(self.task_id)["status"], "ready", "同连接复核说不行，就不发布这次的新图")
        self.assertEqual(self.message()["photo_status"], "failed")


if __name__ == "__main__":
    unittest.main()
