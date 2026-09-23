"""收藏（明信片）与攻略手账的“重画”服务能力：归属与状态判断、同事务重排、连点两次不重复发起。

这一层**还没有 HTTP 入口**——路由、权限与契约归 I（见本窗口日志的接口需求清单）。
这里验的是服务能力本身：一次性临时库 ＋ 真实 `WebCollectionService` / `TravelGuideService` / `IllustrationService`；
不联网、不调供应商、无付费调用。
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.web_collection.service import WebCollectionService
from app.web_journey.guides import TravelGuideService
from app.web_journey.illustrations import IllustrationService
from app.web_platform.tasks import WebTaskQueue
from app.utils import iso
from task_budget_helpers import open_storage

NOW = datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)
OWNER, OTHER, PET = "u-owner", "u-other", "pet-1"


class RedrawEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.storage = open_storage(str(root / "redraw.sqlite3"))
        self.queue = WebTaskQueue(self.storage)
        self.collection = WebCollectionService(self.storage)
        self.guides = TravelGuideService(self.storage)
        self.illustrations = IllustrationService(self.storage, root / "media", self.queue)
        self.illustrations.on_retrying = self.retry_started
        self.task_id = self.failed_task("postcard")
        self.ticket = f"{self.task_id}#1"  # 重画凭据：任务号 ＋ 当时看到的那次失败（attempts=1）

    # ---- 装配与造数（都走各服务自己的写入口或真实队列）----
    def retry_started(self, task_id: str, conn=None) -> None:
        """CR-A9 要 B 接的那两行的等价物：重排事务里把两处展示状态一起改回“处理中”。"""
        self.collection.image_retry_started(task_id, conn=conn)
        self.guides.image_retry_started(task_id, conn=conn)

    def failed_task(self, name: str) -> str:
        """一个真实的、已经进终态的插画任务（队列里 failed，插画记录 failed）。"""
        task, _ = self.queue.enqueue("illustration", f"dedupe:{name}", {"pet_id": PET})
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET status = 'failed', attempts = 1, last_error = 'image timeout' WHERE task_id = ?", (task.task_id,))
            conn.execute("INSERT INTO web_illustrations (illustration_id, user_id, pet_id, source_event_id, task_id, status, created_at, updated_at) "
                         "VALUES (?, ?, ?, ?, ?, 'failed', ?, ?)",
                         (f"il-{name}", OWNER, PET, f"src:{name}", task.task_id, iso(NOW), iso(NOW)))
        return task.task_id

    def postcard(self, *, status: str = "unknown", user_id: str = OWNER, pet_id: str = PET,
                 kind: str = "postcard", item_id: str = "it-1", task_id: str | None = None) -> str:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_collection_items (item_id, user_id, pet_id, kind, title, tradable, bound_to_pet, source_event_id, obtained_at, "
                "image_status, image_task_id) VALUES (?, ?, ?, ?, '明信片', 0, 1, ?, ?, ?, ?)",
                (item_id, user_id, pet_id, kind, f"src:{item_id}", iso(NOW), status, task_id or self.task_id))
        return item_id

    def guide(self, *, status: str = "unknown", pet_id: str = PET, guide_id: str = "gd-1") -> str:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_travel_guides (guide_id, user_id, pet_id, journey_id, city, destination_title, title, summary, stops_json, "
                "owner_tips_json, composed_by, created_at, image_status, image_task_id) "
                "VALUES (?, ?, ?, ?, '香港', '海边', '手账', '摘要', '[]', '[]', 'template', ?, ?, ?)",
                (guide_id, OWNER, pet_id, f"jn-{guide_id}", iso(NOW), status, self.task_id))
        return guide_id

    def status_of(self, table: str, key_column: str, key: str) -> str:
        with self.storage.connect() as conn:
            return conn.execute(f"SELECT image_status FROM {table} WHERE {key_column} = ?", (key,)).fetchone()["image_status"]

    # ---- 状态门槛：只有“结束了又没出图”的才给重画 ----
    def test_only_an_unresolved_postcard_offers_its_task(self) -> None:
        for status, expected in (("unknown", True), ("failed", True), ("processing", False), ("ready", False)):
            with self.subTest(status=status):
                item = self.postcard(status=status, item_id=f"it-{status}")
                got = self.collection.image_retrying(OWNER, PET, item)
                self.assertEqual(got == self.ticket, expected, f"{status} 的明信片是否该给重画：{expected}")

    def test_only_an_unresolved_guide_offers_its_task(self) -> None:
        for status, expected in (("unknown", True), ("failed", True), ("processing", False), ("ready", False)):
            with self.subTest(status=status):
                guide = self.guide(status=status, guide_id=f"gd-{status}")
                self.assertEqual(self.guides.image_retrying(PET, guide) == self.ticket, expected)

    # ---- 归属：别人的、别的宠物的、已经用掉的，都不给 ----
    def test_it_refuses_what_this_family_member_should_not_touch(self) -> None:
        mine = self.postcard(item_id="it-mine")
        others_pet = self.postcard(item_id="it-other-pet", pet_id="pet-2")
        others_memory = self.postcard(item_id="it-memory", kind="shared_memory", user_id=OTHER)
        self.assertEqual(self.collection.image_retrying(OWNER, PET, mine), self.ticket, "自己家的明信片可以重画")
        self.assertIsNone(self.collection.image_retrying(OWNER, PET, others_pet), "别的宠物的不行")
        # 归属判断的依据是传进来的 pet_id（路由从鉴权过的路径参数取），不是藏品自己说了算：
        # 同一件藏品配上它真正的宠物就能重画，配上别的宠物就不行。
        self.assertEqual(self.collection.image_retrying(OWNER, "pet-2", others_pet), self.ticket)
        self.assertIsNone(self.collection.image_retrying(OWNER, PET, others_memory), "别的家人的“一起听/看”回忆不行")
        self.assertIsNone(self.guides.image_retrying("pet-2", self.guide()), "别的宠物的攻略不行")

    def test_a_consumed_item_is_not_redrawable(self) -> None:
        item = self.postcard(item_id="it-used")
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_collection_items SET consumed_at = ? WHERE item_id = ?", (iso(NOW), item))
        self.assertIsNone(self.collection.image_retrying(OWNER, PET, item))

    # ---- 只读：查一次不许改任何状态 ----
    def test_looking_up_the_entry_writes_nothing(self) -> None:
        item, guide = self.postcard(), self.guide()
        self.collection.image_retrying(OWNER, PET, item)
        self.guides.image_retrying(PET, guide)
        self.assertEqual(self.status_of("web_collection_items", "item_id", item), "unknown")
        self.assertEqual(self.status_of("web_travel_guides", "guide_id", guide), "unknown")
        self.assertEqual(self.queue.get(self.task_id).status, "failed", "光是查一下不能把任务排回去")

    # ---- 重排：同一个事务，连点两次不会发起第二次 ----
    def test_the_redraw_requeues_and_flips_both_displays_in_one_transaction(self) -> None:
        item, guide = self.postcard(), self.guide()
        self.assertEqual(self.illustrations.retry(self.collection.image_retrying(OWNER, PET, item)), "requeued")

        self.assertEqual(self.queue.get(self.task_id).status, "queued")
        self.assertEqual(self.status_of("web_collection_items", "item_id", item), "processing")
        self.assertEqual(self.status_of("web_travel_guides", "guide_id", guide), "processing", "同一个任务的手账图一起回到处理中")
        self.assertIsNone(self.collection.image_retrying(OWNER, PET, item), "顺序连点：第二次查不到任务号")
        self.assertIsNone(self.guides.image_retrying(PET, guide))

    def test_two_simultaneous_requests_both_pass_the_lookup_but_only_one_requeues(self) -> None:
        """**防重复发起的最终保护不在查询，而在重排事务里的条件更新**。

        查询是只读的，挡不住并发：两个请求完全可能同时查到同一个任务号。真正保证"只发起一次"的是
        `retry_failed` 的 `WHERE status = 'failed'`——只有一方能把任务从 failed 改回 queued，
        另一方拿到 `already_queued`（应当回当前状态，不能说成"新尝试已创建"）。
        """
        item, guide = self.postcard(), self.guide()
        looked_up: list[str | None] = []
        outcomes: list[str] = []
        lock, start = threading.Lock(), threading.Barrier(2)

        def click() -> None:
            found = self.collection.image_retrying(OWNER, PET, item)
            with lock:
                looked_up.append(found)
            start.wait(timeout=10)  # 两边都已经查到任务号，再同时去重排
            result = self.illustrations.retry(found)
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=click) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "不该卡住")

        self.assertEqual(looked_up, [self.ticket, self.ticket], "并发下两个请求都查到同一张凭据——查询本身挡不住")
        self.assertEqual(sorted(outcomes), ["already_queued", "requeued"], "但只有一方真的排了新尝试")
        with self.storage.connect() as conn:
            task = conn.execute("SELECT status, attempts, max_attempts FROM web_tasks WHERE task_id = ?", (self.task_id,)).fetchone()
        self.assertEqual((task["status"], task["max_attempts"] - task["attempts"]), ("queued", 1), "只放宽了一次，不是两次")
        self.assertEqual(self.status_of("web_collection_items", "item_id", item), "processing")
        self.assertEqual(self.status_of("web_travel_guides", "guide_id", guide), "processing")

    def test_a_late_duplicate_request_does_not_redraw_the_next_failure(self) -> None:
        """跨执行周期的交错：两个请求都查到**第一次失败**，第一个重排、后台又失败了一次，第二个才迟到。

        这时任务的状态**又变回 `failed`**。只看 `status='failed'` 的话，迟到的那个重复请求会被当成
        "主人看到新失败之后又点了一次"，白发起一次可能付费的尝试。它对应的是更早那次失败，应当被挡下来。
        """
        item = self.postcard()
        first = self.collection.image_retrying(OWNER, PET, item)
        late = self.collection.image_retrying(OWNER, PET, item)  # 同一时刻的第二个请求，看到的是同一次失败
        self.assertEqual(first, late)

        self.assertEqual(self.illustrations.retry(first), "requeued")
        claim = self.queue.claim_next("worker-1", ["illustration"])  # 后台真的跑了一轮
        self.queue.fail_claim(claim, "image timeout", retryable=False)  # 又失败了：status 回到 failed
        with self.storage.connect() as conn:
            self.collection.image_failed(claim.task_id, conn=conn, outcome="unknown")

        self.assertEqual(self.illustrations.retry(late), "stale_attempt", "迟到的重复请求对应的是上一次失败，不能当成新的一次重画")
        with self.storage.connect() as conn:
            task = conn.execute("SELECT status, attempts, max_attempts FROM web_tasks WHERE task_id = ?", (self.task_id,)).fetchone()
        self.assertEqual((task["status"], task["max_attempts"] - task["attempts"]), ("failed", 0), "没有被多放宽一次")

        # 正常对照：主人**看到新的失败之后**再点一次，是合法的重画
        fresh = self.collection.image_retrying(OWNER, PET, item)
        self.assertNotEqual(fresh, late, "重新查询拿到的是新那次失败的凭据")
        self.assertEqual(self.illustrations.retry(fresh), "requeued")

    def test_it_reports_why_a_redraw_did_not_start_a_new_attempt(self) -> None:
        """`retry` 要能区分"已经在排队"和"确实不能重试"，调用方才不会一律回"新尝试已创建"。"""
        self.assertEqual(self.illustrations.retry("wt_does_not_exist"), "not_retryable", "任务号不存在")
        self.assertEqual(self.illustrations.retry(self.task_id), "requeued")
        self.assertEqual(self.illustrations.retry(self.task_id), "already_queued", "已经排着了，不是新尝试")
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET status = 'succeeded' WHERE task_id = ?", (self.task_id,))
        self.assertEqual(self.illustrations.retry(self.task_id), "not_retryable", "已经画好了，没有可重试的东西")

    def test_a_failed_display_update_rolls_the_requeue_back(self) -> None:
        item, guide = self.postcard(), self.guide()

        def broken(task_id: str, conn=None) -> None:
            raise RuntimeError("展示状态写不进去")

        self.illustrations.on_retrying = broken
        with self.assertRaises(RuntimeError):
            self.illustrations.retry(self.task_id)
        self.assertEqual(self.queue.get(self.task_id).status, "failed", "任务不能单独排回去")
        self.assertEqual(self.status_of("web_collection_items", "item_id", item), "unknown")
        self.assertEqual(self.status_of("web_travel_guides", "guide_id", guide), "unknown")

    # ---- 历史尝试记录原样保留 ----
    def test_the_previous_attempt_records_are_kept(self) -> None:
        item = self.postcard()
        with self.storage.connect() as conn:  # 上一次尝试留下的本地预占记录（结果不明）
            conn.execute(
                "INSERT INTO web_budget_reservations (reservation_id, operation_id, provider, purpose, subject_scope, accounting_window, scope_pairs_json, "
                "reserved_units, status, outcome, created_at, expires_at, updated_at) "
                "VALUES ('rs-1', ?, 'image', 'illustration', ?, '2026-09-23', '[]', 1, 'unknown', 'unknown', ?, ?, ?)",
                (f"illustration:{self.task_id}:1", f"pet:{PET}", iso(NOW), iso(NOW), iso(NOW)))
        self.illustrations.retry(self.collection.image_retrying(OWNER, PET, item))
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT operation_id, status, outcome FROM web_budget_reservations").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(f"illustration:{self.task_id}:1", "unknown", "unknown")],
                         "重画不回写、不删除上一次的记录——对账要看得见它")


if __name__ == "__main__":
    unittest.main()
