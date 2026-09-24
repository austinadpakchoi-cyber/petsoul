"""生图闭环，走真实 API 路径（供应商用替身，不联网、不产生付费调用）。

覆盖：结果不明怎么呈现 → 主人显式重画 → 处理中 → 画好了／又一次结果不明／确定没画成；
以及谁能点重画、连点两次会不会重复发起、旧的"结果不明"会不会遮住后来的结果、重排与展示更新失败时是否一起回滚。

**跑在正式装配上**：B 已经在 `app/web_agent_wiring.py` 里接好 `on_unknown` / `on_retrying`，
所以这里**不再手工补接回调**——每个用例由 `WebPlatformTestBase` 新建一个隔离的应用实例（自己的临时库与媒体目录），
走真实的组合根，**唯一替换的是供应商**（`FakeIllustrator`）。
`test_the_formal_assembly_wires_the_unknown_callbacks` 专门守着这件事：接线被改回去时它会直接红，
而不是让下面的用例悄悄退化成"一律显示没画成"还继续通过。

**计数口径**：文中的"发送次数"一律指**替身生图被调用的次数**（`FakeIllustrator.prompts`）。
它证明的是"本进程发起了几次调用"，**不是**真实供应商收到了几次请求，更不是任何计费证据。
"""

from __future__ import annotations

import threading
import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator

RETRY = "/communicator/{pet}/messages/{message}/retry-photo"


class IllustrationApiClosureTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator  # 唯一的替换：供应商换成替身，其余全走正式组合根

    def test_the_formal_assembly_wires_the_unknown_callbacks(self) -> None:
        """正式装配必须自己接好这两个回调——本文件不再手工补接。

        接线掉了的话 `on_unknown` 是 None，插画服务会退回 `on_failed`，页面就把"还没确认"说成"没画成"；
        `on_retrying` 掉了则重画之后页面不会回到"正在画"。这两种退化都不会抛异常，所以必须在这里显式守住。
        """
        self.assertIsNotNone(self.web.illustrations.on_unknown, "组合根没接 on_unknown（见 CR-A8）")
        self.assertIsNotNone(self.web.illustrations.on_retrying, "组合根没接 on_retrying（见 CR-A8）")

    # ---- 场景辅助 ----
    def owner_with_photos(self, name: str, resident: str = "adopt-lan"):
        """每个测试账号领养不同的居民：一位居民只能被领养一次。"""
        owner = self.user(name)
        owner.adopt_and_move_in(resident)
        self.assertTrue(owner.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        return owner

    def cafe_adventure(self, owner) -> None:
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)

    def message(self, owner) -> dict:
        return next(m for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if "咖啡馆小侦探" in m["text"])

    def unresolved_message(self, owner, reason: str) -> dict:
        """走完一次真实的冒险 → 生图失败 → 返回那条带图的消息（已经进终态）。"""
        self.illustrator.fail_reason = reason
        self.cafe_adventure(owner)
        self.assertEqual(self.message(owner)["photo_status"], "processing", "刚排队时是处理中")
        self.web.illustrations.run_pending()
        return self.message(owner)

    def redraw(self, owner, message: dict):
        return owner.post(RETRY.format(pet=owner.pet_id, message=message["message_id"]))

    def row(self, sql: str, params: tuple):
        with self.web.illustrations.storage.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def task_of(self, message: dict) -> str:
        return self.row("SELECT photo_task_id FROM web_messages WHERE message_id = ?", (message["message_id"],))["photo_task_id"]

    # ---- 1. 结果不明 → API 返回 unknown → 显式重画 → 处理中 → 画好了 ----
    def test_an_unconfirmed_result_is_shown_as_unknown_and_the_owner_can_redraw_it(self) -> None:
        owner = self.owner_with_photos("closure-unknown")
        message = self.unresolved_message(owner, "timeout")

        self.assertEqual(message["photo_status"], "unknown", "超时＝可能已经受理，接口要如实说'还没确认'")
        self.assertIsNone(message["photo_url"], "没有图就不要给图的地址")
        self.assertNotEqual(message["state"], "failed", "不能把'还没确认'说成'没画成'")
        self.assertEqual(self.web.illustrations.outcome_of(self.task_of(message)), "unknown")
        self.assertEqual(len(self.illustrator.prompts), 1, "结果不明的那一次不自动重发（计的是替身被调用的次数）")

        self.illustrator.fail_reason = None
        self.assertEqual(self.redraw(owner, message).status_code, 200)
        self.assertEqual(self.message(owner)["photo_status"], "processing", "重画之后页面要跟着回到处理中")

        self.web.illustrations.run_pending()
        done = self.message(owner)
        self.assertEqual(done["photo_status"], "ready")
        self.assertTrue(done["photo_url"].startswith("/api/v1/web/media/illustrations/"))
        self.assertEqual(owner.get(done["photo_url"].removeprefix("/api/v1/web")).status_code, 200)

    # ---- 旧的 unknown 不能遮住后来的结果 ----
    def test_a_later_definite_failure_is_not_reported_as_still_unconfirmed(self) -> None:
        owner = self.owner_with_photos("closure-then-failed")
        message = self.unresolved_message(owner, "timeout")
        self.assertEqual(message["photo_status"], "unknown")

        self.illustrator.fail_reason = "rejected"  # 这次是当场被拒：确定没受理、也不会再自动重试
        self.assertEqual(self.redraw(owner, message).status_code, 200)
        self.web.illustrations.run_pending()

        after = self.message(owner)
        self.assertEqual(after["photo_status"], "failed", "这一次确定没画成，不能被上一次的'结果不明'盖住")
        self.assertEqual(self.web.illustrations.outcome_of(self.task_of(message)), "failed")
        self.assertEqual(self.redraw(owner, after).status_code, 200, "确定没画成同样可以再重画")

    def test_a_second_unconfirmed_result_stays_unconfirmed(self) -> None:
        owner = self.owner_with_photos("closure-unknown-twice")
        message = self.unresolved_message(owner, "timeout")
        self.assertEqual(self.redraw(owner, message).status_code, 200)
        self.web.illustrations.run_pending()  # 又一次超时
        self.assertEqual(self.message(owner)["photo_status"], "unknown")
        self.assertEqual(len(self.illustrator.prompts), 2, "两次尝试各调用替身一次，重画不会顺带自动重发")

    # ---- 2. 权限隔离：别人家的人点不到这个重画 ----
    def test_only_a_family_member_may_redraw_that_pet_photo(self) -> None:
        owner = self.owner_with_photos("closure-owner")
        message = self.unresolved_message(owner, "timeout")
        stranger = self.user("closure-stranger")  # 已登录，但不是这只宠物的家人

        denied = stranger.post(RETRY.format(pet=owner.pet_id, message=message["message_id"]))
        self.assertIn(denied.status_code, (401, 403, 404, 409), denied.text)
        self.assertEqual(self.message(owner)["photo_status"], "unknown", "被挡下来之后状态不许被改动")
        self.assertEqual(len(self.illustrator.prompts), 1, "外人点一下不能触发一次生图调用（替身调用次数不变）")

    # ---- 3. 连点两次不会重复发起同一次尝试 ----
    def test_clicking_redraw_twice_does_not_start_a_second_attempt(self) -> None:
        owner = self.owner_with_photos("closure-double-click")
        message = self.unresolved_message(owner, "timeout")
        self.illustrator.fail_reason = None

        self.assertEqual(self.redraw(owner, message).status_code, 200)
        second = self.redraw(owner, message)
        # CR-A10 定稿后的口径（I 已按此落地路由）：连点第二次**回当前状态**，不是 404，也不能读成"新尝试已创建"。
        self.assertEqual(second.status_code, 200, "对象还在、正在画，不该说成找不到")
        again = next(m for m in second.json()["items"] if m["message_id"] == message["message_id"])
        self.assertEqual(again["photo_status"], "processing", "回的是当前状态")
        task = self.row("SELECT status, attempts, max_attempts FROM web_tasks WHERE task_id = ?", (self.task_of(message),))
        self.assertEqual((task["status"], task["max_attempts"] - task["attempts"]), ("queued", 1), "只放宽了一次，不是两次")

        self.web.illustrations.run_pending()
        self.assertEqual(self.message(owner)["photo_status"], "ready")
        self.assertEqual(len(self.illustrator.prompts), 3, "替身调用次数：第一次 1（超时）＋重画 2（证件照＋正图）；连点没有多出第 4 次")

    def reservations(self, task_id: str) -> int:
        """这个任务在**本地**额度账本里的预占条数（每次逻辑尝试一条，与这次调用了几张图无关）。

        这是本地记账，不代表供应商侧的实际计费——真实费用一律按"未验证"对待。
        """
        with self.web.illustrations.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_budget_reservations WHERE operation_id LIKE ?",
                                (f"illustration:{task_id}:%",)).fetchone()["n"]

    def test_two_simultaneous_redraws_add_exactly_one_logical_attempt(self) -> None:
        """并发验收按**逻辑尝试**算，不按"调用次数只加一"算。

        没有参考照片时，一次重画本身就包含证件照与场景图**两次调用**。所以判据是：
        两个并发请求产生的替身调用次数，与**单次重画**的相同；账本里也只多一条预占。

        **证明范围（不要读大）**：这里的两个线程**直接调服务方法**（查询 ＋ `illustrations.retry`），
        证明的是**服务层的并发保护**——查询挡不住并发、条件更新挡得住。
        它**不是** HTTP 双请求：真正经过路由、鉴权、CSRF 的并发验收由 I 在路由层补（CR-A10 验收条件 1）。
        计数来自 `FakeIllustrator.prompts`，是**替身被调用的次数**，不代表真实供应商收到过请求，也不是计费证据。
        """
        control = self.owner_with_photos("closure-control")
        control_message = self.unresolved_message(control, "timeout")
        control_task = self.task_of(control_message)
        self.illustrator.fail_reason = None
        calls_before, reserved_before = len(self.illustrator.prompts), self.reservations(control_task)
        self.assertEqual(self.redraw(control, control_message).status_code, 200)
        self.web.illustrations.run_pending()
        single_calls = len(self.illustrator.prompts) - calls_before
        self.assertEqual(self.reservations(control_task) - reserved_before, 1, "单次重画＝一条预占")
        self.assertGreater(single_calls, 1, "没有参考照片时，一次重画本来就不止调用一次（证件照＋场景图）")

        owner = self.owner_with_photos("closure-concurrent", "adopt-mochi")
        self.illustrator.fail_reason = "timeout"
        message = self.unresolved_message(owner, "timeout")
        task_id = self.task_of(message)
        self.illustrator.fail_reason = None
        calls_before, reserved_before = len(self.illustrator.prompts), self.reservations(task_id)

        tickets: list[str | None] = []
        outcomes: list[str] = []
        lock, start = threading.Lock(), threading.Barrier(2)

        def click() -> None:
            found = self.web.communicator.illustration_retrying(owner.user_id, owner.pet_id, message["message_id"])
            with lock:
                tickets.append(found)
            start.wait(timeout=10)  # 两个请求都已经通过查询，再同时去重排
            result = self.web.illustrations.retry(found)
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=click) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())

        self.assertEqual(len(set(tickets)), 1, "两个请求都通过了查询，拿到同一张凭据")
        self.assertEqual(sorted(outcomes), ["already_queued", "requeued"], "只有一方真的排了新尝试")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts) - calls_before, single_calls, "并发两次点击的替身调用次数＝单次重画的调用次数")
        self.assertEqual(self.reservations(task_id) - reserved_before, 1, "账本里只多一条预占＝只多一次逻辑尝试")
        self.assertEqual(self.message(owner)["photo_status"], "ready")

    # ---- 4. 重排与展示更新必须一起成功或一起回滚 ----
    def test_the_requeue_and_the_display_update_roll_back_together(self) -> None:
        owner = self.owner_with_photos("closure-rollback")
        message = self.unresolved_message(owner, "timeout")
        task_id = self.task_of(message)

        def broken(task_id: str, conn=None) -> None:  # 展示状态写到一半失败（例如收藏那张表锁住了）
            raise RuntimeError("display update failed")

        self.web.collection.image_retry_started = broken
        with self.assertRaises(RuntimeError):
            self.redraw(owner, message)

        self.assertEqual(self.message(owner)["photo_status"], "unknown", "页面不能停在'处理中'，队列里却没有任务")
        self.assertEqual(self.row("SELECT status FROM web_tasks WHERE task_id = ?", (task_id,))["status"], "failed")
        self.assertEqual(self.row("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))["status"], "failed")
        self.assertEqual(len(self.illustrator.prompts), 1, "回滚之后没有发生新的调用")


if __name__ == "__main__":
    unittest.main()
