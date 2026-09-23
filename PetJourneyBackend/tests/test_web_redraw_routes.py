"""收藏与攻略的"重画"入口（CR-A10 的路由这一层，归 I）。

服务层的归属与状态判断由 A 的 `test_web_redraw_entries.py` 覆盖，完整闭环（重画 → 出图）由 A 补 API 层用例。
这里只验**路由该管的事**：谁能调、不能调的给什么、没有可重画的东西时给什么、以及它确实把任务重新排了队。
替身生图，不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from app.routers.web._shared import redraw
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class RedrawRouteTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("redraw-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        # 给一张参考照：没有参考照时每次重画要先画证件照再画正图＝两次调用，计数就说不清了。
        # 有参考照之后"一次重画＝一次付费调用"，用调用次数证明"没多排一次"才成立。
        self.web.illustrations.reference_photo_of = lambda pet_id: (b"reference-photo", "image/png")

    def collection_retry(self, item_id: str, who=None, pet_id: str | None = None):
        user = who or self.owner
        return user.post(f"/collection/{pet_id or self.owner.pet_id}/items/{item_id}/retry-image")

    def guide_retry(self, guide_id: str, who=None, pet_id: str | None = None):
        user = who or self.owner
        return user.post(f"/guides/{pet_id or self.owner.pet_id}/{guide_id}/retry-image")

    # ---- 没有可重画的东西 ----
    def test_collection_retry_is_404_when_there_is_nothing_to_redraw(self) -> None:
        response = self.collection_retry("it-doesnotexist")

        self.assertEqual(response.status_code, 404, response.text)

    def test_guide_retry_is_404_when_there_is_nothing_to_redraw(self) -> None:
        response = self.guide_retry("gd-doesnotexist")

        self.assertEqual(response.status_code, 404, response.text)

    # ---- 权限：不是这家的人，一律 404（不泄露存在与否）----
    def test_an_outsider_cannot_redraw_someone_elses_collection(self) -> None:
        stranger = self.user("redraw-stranger")
        stranger.adopt_and_move_in("adopt-mochi")

        response = self.collection_retry("it-whatever", who=stranger, pet_id=self.owner.pet_id)

        self.assertEqual(response.status_code, 404, response.text)

    def test_an_outsider_cannot_redraw_someone_elses_guide(self) -> None:
        stranger = self.user("redraw-stranger2")
        stranger.adopt_and_move_in("adopt-mochi")

        response = self.guide_retry("gd-whatever", who=stranger, pet_id=self.owner.pet_id)

        self.assertEqual(response.status_code, 404, response.text)

    # ---- 必须带 CSRF ----
    def test_both_routes_require_csrf(self) -> None:
        for path in (f"/collection/{self.owner.pet_id}/items/it-x/retry-image",
                     f"/guides/{self.owner.pet_id}/gd-x/retry-image"):
            response = self.owner.client.post(f"/api/v1/web{path}")  # 不带 X-CSRF-Token
            self.assertEqual(response.status_code, 403, f"{path}：{response.text}")

    # ---- 成功路径：真的把任务重新排了队 ----
    def test_a_failed_collection_image_can_be_requeued(self) -> None:
        item_id, task_id = self.failed_collection_image()

        response = self.collection_retry(item_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.web.illustrations.tasks.get(task_id).status, "queued", "任务要回到排队中")
        item = next(i for i in response.json() if i["item_id"] == item_id)
        self.assertEqual(item["image_status"], "processing", "页面上要变成正在画")

    def test_clicking_redraw_twice_returns_the_current_state_not_404(self) -> None:
        """连点两次：第二次对象还在（只是已经在画了），应当回当前状态，**不是 404**。
        "没多排一次"用**替身调用次数**证明，不用 attempts 是否变化——后者证明不了有没有真的又画一次。"""
        item_id, task_id = self.failed_collection_image()
        calls_before = len(self.illustrator.prompts)
        self.assertEqual(self.collection_retry(item_id).status_code, 200)

        again = self.collection_retry(item_id)

        self.assertEqual(again.status_code, 200, again.text)
        item = next(i for i in again.json() if i["item_id"] == item_id)
        self.assertEqual(item["image_status"], "processing", "还是在画，不是新的一次尝试")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts) - calls_before, 1, "只发生了一次替身调用，第二次点击没有再发起")

    def test_a_guide_image_can_be_redrawn(self) -> None:
        guide_id, task_id = self.failed_guide_image()
        calls_before = len(self.illustrator.prompts)

        response = self.guide_retry(guide_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.web.illustrations.tasks.get(task_id).status, "queued")
        guide = next(g for g in response.json() if g["guide_id"] == guide_id)
        self.assertEqual(guide["image_status"], "processing")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts) - calls_before, 1, "重画只发生一次替身调用")

    def test_an_unconfirmed_image_can_be_redrawn(self) -> None:
        """结果没确认（unknown）同样给重画入口——它和"确定没画成"是两回事，但都该能重画。"""
        item_id, task_id = self.failed_collection_image(reason="timeout")
        with self.app.state.storage.connect() as conn:
            status = conn.execute("SELECT image_status FROM web_collection_items WHERE item_id = ?", (item_id,)).fetchone()["image_status"]
        self.assertEqual(status, "unknown", "前提：这件停在「结果没确认」")

        response = self.collection_retry(item_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.web.illustrations.tasks.get(task_id).status, "queued")

    def test_concurrent_clicks_share_one_ticket_and_start_one_attempt(self) -> None:
        """五个家人同时点"重画"：**固定交错**，让五个请求都在任何人改动之前读到同一份失败凭据，
        然后证明只产生一次逻辑尝试、一次额度预占、一次替身调用。

        不固定交错的话，线程很可能是排着队跑的——那证明不了"并发拿到同一凭据"这件事。
        """
        import threading

        item_id, task_id = self.failed_collection_image()
        calls_before = len(self.illustrator.prompts)
        reservations_before = self.reservations(task_id)
        original = self.web.collection.image_retrying
        gate = threading.Barrier(5, timeout=30)
        tickets: list[str | None] = []
        lock = threading.Lock()

        def read_then_wait(user_id: str, pet_id: str, item: str):
            ticket = original(user_id, pet_id, item)
            with lock:
                tickets.append(ticket)
            gate.wait()  # 五个都读完了再往下走：此刻它们手上是同一份凭据
            return ticket

        self.web.collection.image_retrying = read_then_wait
        self.addCleanup(lambda: setattr(self.web.collection, "image_retrying", original))
        results: list[tuple[int, str | None]] = []

        def click() -> None:
            try:
                response = self.collection_retry(item_id)
                outcome = (response.status_code, None)
            except BaseException as exc:  # noqa: BLE001 - 线程里的异常要收上来，不能悄悄吞掉
                outcome = (-1, f"{type(exc).__name__}: {exc}")
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=click) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)

        self.assertFalse([t for t in threads if t.is_alive()], "所有线程都要跑完，不能有卡住的")
        self.assertEqual(len(results), 5, f"五个请求都要有结果：{results}")
        self.assertEqual([r[1] for r in results], [None] * 5, f"线程里不能有异常：{results}")
        self.assertEqual({r[0] for r in results}, {200}, results)
        self.assertEqual(len(tickets), 5, tickets)
        self.assertEqual(len(set(tickets)), 1, f"五个请求确实拿到同一份失败凭据：{tickets}")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts) - calls_before, 1, "只产生一次替身调用")
        self.assertEqual(self.reservations(task_id) - reservations_before, 1, "只新增一份额度预占")

    def test_a_late_duplicate_request_is_not_a_new_redraw(self) -> None:
        """**服务层**：迟到的重复请求——中间已经又跑过一轮又失败了，拿着旧凭据再点不算新的一次重画。

        这一条直接调 `illustrations.retry(旧凭据)`，不走路由：路由每次都会现查一份新凭据，
        造不出"手上拿着过期凭据"的情形。所以它验的是服务层的围栏，不是 HTTP 那一层。
        """
        item_id, task_id = self.failed_collection_image()
        stale = self.web.collection.image_retrying(self.owner.user_id, self.owner.pet_id, item_id)
        self.assertEqual(self.collection_retry(item_id).status_code, 200)
        self.illustrator.fail_reason = "daily_cap"
        self.web.illustrations.run_pending()  # 又失败了一次
        self.illustrator.fail_reason = None
        calls_before = len(self.illustrator.prompts)

        self.assertEqual(self.web.illustrations.retry(stale), "stale_attempt", "旧凭据对应的是更早那次失败")

        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts), calls_before, "迟到的那次没有再发生替身调用")

    # ---- 已经画好的：回当前状态，且**什么都不能变**（A 在 CR-A10 里指定的五组不变断言）----
    def test_redrawing_a_ready_postcard_changes_nothing(self) -> None:
        """对一张**已经画好**的明信片点"重画"：200 ＋ 状态仍 ready，并且五样东西一个都不许动。

        只断言状态码是不够的——200 也可能是"已经又排了一次队"。所以逐项钉死：
        图还是那张图、尝试次数没涨、没多占一份额度、没再调一次替身、任务仍然是成功。

        **各项的实际作用范围（实测，别把它们当等效）**：`image_url` 是按插图编号生成的固定地址，
        重画会覆盖同一个编号，**地址不会变**——所以①防的是"图被清掉或换成别人的图"，
        **不防**"又画了一次"。真正能抓住"多排一次"的是②③④⑤。
        变异验证（独立进程里把已成功的任务硬推回队列，不改业务源码）确认②最先报红：attempts 2 != 1。
        """
        item_id, task_id = self.ready_collection_image()
        before = self.task_row(task_id)
        image_before = self.postcard_image(item_id)
        calls_before = len(self.illustrator.prompts)
        reservations_before = self.reservations(task_id)

        response = self.collection_retry(item_id)

        self.assertEqual(response.status_code, 200, response.text)
        item = next(i for i in response.json() if i["item_id"] == item_id)
        self.assertEqual(item["image_status"], "ready", "已经画好的，状态原样返回")
        self.web.illustrations.run_pending()  # 给"偷偷又排了一次队"一个暴露的机会
        after = self.task_row(task_id)
        self.assertEqual(self.postcard_image(item_id), image_before, "① 图片不变")
        self.assertEqual(after["attempts"], before["attempts"], "② attempts 不变")
        self.assertEqual(after["max_attempts"], before["max_attempts"], "② max_attempts 不变")
        self.assertEqual(self.reservations(task_id), reservations_before, "③ 额度预占条数不变")
        self.assertEqual(len(self.illustrator.prompts), calls_before, "④ 替身调用次数不变")
        self.assertEqual(after["status"], "succeeded", "⑤ 任务状态仍然是 succeeded")

    def test_redrawing_a_ready_guide_changes_nothing(self) -> None:
        """攻略手账走同一条规则：已经画好的重画 → 200 ＋ 原状态，五项同样不许变。"""
        guide_id, task_id = self.failed_guide_image(reason=None, expected="ready")
        before = self.task_row(task_id)
        calls_before = len(self.illustrator.prompts)
        reservations_before = self.reservations(task_id)
        with self.app.state.storage.connect() as conn:
            image_before = conn.execute("SELECT image_url FROM web_travel_guides WHERE guide_id = ?", (guide_id,)).fetchone()["image_url"]
        self.assertTrue(image_before, "前提：画好了就该有图")

        response = self.guide_retry(guide_id)

        self.assertEqual(response.status_code, 200, response.text)
        guide = next(g for g in response.json() if g["guide_id"] == guide_id)
        self.assertEqual(guide["image_status"], "ready")
        self.web.illustrations.run_pending()
        after = self.task_row(task_id)
        with self.app.state.storage.connect() as conn:
            image_after = conn.execute("SELECT image_url FROM web_travel_guides WHERE guide_id = ?", (guide_id,)).fetchone()["image_url"]
        self.assertEqual(image_after, image_before, "① 图片不变")
        self.assertEqual((after["attempts"], after["max_attempts"]), (before["attempts"], before["max_attempts"]), "② 尝试次数不变")
        self.assertEqual(self.reservations(task_id), reservations_before, "③ 额度预占条数不变")
        self.assertEqual(len(self.illustrator.prompts), calls_before, "④ 替身调用次数不变")
        self.assertEqual(after["status"], "succeeded", "⑤ 任务状态仍然是 succeeded")

    def test_a_ticket_that_cannot_be_retried_is_refused(self) -> None:
        """`not_retryable`（任务号不存在 / 已画好 / 已作废）必须明确拒绝，不能当成"排队中"。"""
        from app.web_platform.errors import WebAPIError

        with self.assertRaises(WebAPIError) as refused:
            redraw(self.web, "wt_nonexistent#0", "failed", "可以重画的明信片")

        self.assertEqual(refused.exception.status_code, 404)

    # ---- 工具 ----
    def reservations(self, task_id: str) -> int:
        """这个生图任务到目前为止产生了几份额度预占。"""
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_budget_reservations WHERE operation_id LIKE ?",
                                (f"illustration:{task_id}:%",)).fetchone()["n"]

    def task_row(self, task_id: str) -> dict:
        """生图任务当前这一行：状态与尝试次数都在这里。"""
        with self.app.state.storage.connect() as conn:
            return dict(conn.execute("SELECT status, attempts, max_attempts FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone())

    def postcard_image(self, item_id: str) -> str | None:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT image_url FROM web_collection_items WHERE item_id = ?", (item_id,)).fetchone()["image_url"]

    def ready_collection_image(self) -> tuple[str, str]:
        """造一件**已经画好**的明信片：同一条路子，只是这次不让它失败。"""
        item_id, task_id = self.failed_collection_image(reason=None)
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT image_status, image_url FROM web_collection_items WHERE item_id = ?", (item_id,)).fetchone()
        self.assertEqual(row["image_status"], "ready", "前提：这张确实已经画好了")
        self.assertTrue(row["image_url"], "前提：画好了就该有图")
        return item_id, task_id

    def failed_guide_image(self, reason: str | None = "daily_cap", expected: str = "failed") -> tuple[str, str]:
        """造一份攻略并跑一次生图：默认让它画不成，`reason=None` 就是画成功。
        （这条用例只验路由，所以直接写一行攻略记录，不绕整条攻略生成链。）"""
        self.illustrator.fail_reason = reason
        task_id = self.web.illustrations.request_image(self.owner.user_id, self.owner.pet_id, "redraw:guide", style="journal",
                                                      title="手账", lines=["一行"], city="香港")
        self.assertIsNotNone(task_id)
        guide_id = "gd-redraw-0001"
        with self.app.state.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_travel_guides (guide_id, user_id, pet_id, journey_id, city, destination_title, title, summary, "
                "stops_json, owner_tips_json, composed_by, image_status, image_task_id, created_at) "
                "VALUES (?, ?, ?, 'jn-redraw-0001', '香港', '码头', '手账', NULL, '[]', '[]', 'template', 'processing', ?, ?)",
                (guide_id, self.owner.user_id, self.owner.pet_id, task_id, self.clock.now.isoformat()))
        self.web.illustrations.run_pending()
        with self.app.state.storage.connect() as conn:
            status = conn.execute("SELECT image_status FROM web_travel_guides WHERE guide_id = ?", (guide_id,)).fetchone()["image_status"]
        self.assertEqual(status, expected, f"前提：这份手账图这时候应当是 {expected}")
        self.illustrator.fail_reason = None
        return guide_id, task_id

    def failed_collection_image(self, reason: str = "daily_cap") -> tuple[str, str]:
        """造一件"画失败了的明信片"：真实收藏记录 + 真实生图任务。reason=timeout 时停在「结果没确认」。"""
        self.illustrator.fail_reason = reason  # 不会自动重试
        task_id = self.web.illustrations.request_image(self.owner.user_id, self.owner.pet_id, "redraw:card", style="selfie",
                                                       place="码头", city="香港", scene="坐着")
        self.assertIsNotNone(task_id)
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.web.collection.keepsake(conn, user_id=self.owner.user_id, pet_id=self.owner.pet_id, kind="postcard",
                                         title="明信片", note="测试用", source_event_id="redraw:card", now=self.clock.now)
        self.web.collection.attach_image(self.owner.pet_id, "postcard", "redraw:card", task_id)
        self.web.illustrations.run_pending()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT item_id, image_status FROM web_collection_items WHERE source_event_id = 'redraw:card'").fetchone()
        self.illustrator.fail_reason = None
        return row["item_id"], task_id


if __name__ == "__main__":
    unittest.main()
