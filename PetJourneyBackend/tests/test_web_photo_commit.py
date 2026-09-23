"""拍照命令的提交边界：队列／插画登记要和 visit 更新、`photo_taken` 事件同生共死（COORD-C-ATOMIC，方案 B）。

现在 `photo_request` 在写事务**之外**先把任务排出去，写事务才做 visit 版本检查与事件落库。
版本冲突或租约被接管时事务整体回滚，但**任务与插画记录已经留在库里**——
镜头没响，队列里却多了一张要画的照片，`photo_taken` 事件永远不会出现。

这里先复现那份残留，再守住修好之后的几条：
队列 ＋ visit ＋ 事件一起提交／一起回滚；同一次拍照只排一张；
`captured_at` 是**主人按下那一刻**，不是到店时刻、也不是任务执行时刻；正常路径照常。

假生图、假地图，不联网、不产生付费调用。
"""

from __future__ import annotations

import traceback
import unittest

from app.utils import iso
from app.web_journey.errors import JourneyError
from app.web_platform.lease import LeaseLost
from app.web_platform.uow import lane_fence
from app.web_providers import WebProviders
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class PhotoCommitBase(WebPlatformTestBase):
    settle_on_read = True  # 出发之后任务进程要写攻略；拍照之后一律直接查库，不再跑后台

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        web = self.web
        web.providers = WebProviders(enabled=True, chat=web.providers.chat, geo=None, illustrator=self.illustrator, meter=None)
        web.illustrations.illustrator = self.illustrator
        self.owner = self.user("photo-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.journeys = web.journeys
        with self.app.state.storage.connect() as conn:  # 探针的登记表：没装探针时也要查得到（应当是空的）
            conn.execute("CREATE TABLE IF NOT EXISTS photo_queue (source_key TEXT PRIMARY KEY, captured_at TEXT NOT NULL, task_id TEXT NOT NULL)")

    # ---- 到店 ----
    def arrive(self) -> str:
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()
        self.clock.advance(minutes=7)
        return self.owner.get("/journey/map").json()["current_visit_id"]

    def photo_activity(self, visit_id: str) -> str:
        visit = self.owner.get(f"/visits/{visit_id}").json()
        return next(a["activity_id"] for a in visit["activities"] if a["kind"] == "take_photo")

    def take_photo(self, visit_id: str):
        return self.journeys.act(self.owner.user_id, visit_id, self.photo_activity(visit_id), self.clock.now)

    # ---- 同事务登记的探针（真实实现是 A 的 `request_photo_in`；这里只验旅程这一侧的契约） ----
    def wire_probe(self) -> list[dict]:
        """装上同事务登记：**只用调用方给的那个连接**写，不另开、不自己提交。形状＝要请 A 实现的那个。"""
        seen: list[dict] = []

        def photo_request_in(conn, visit, journey, *, captured_at, source_key):
            seen.append({"captured_at": captured_at, "source_key": source_key, "in_transaction": bool(conn.in_transaction),
                         "place": visit.place["name"], "city": journey.city})
            task_id = f"task-{len(seen)}"
            conn.execute("INSERT OR IGNORE INTO photo_queue (source_key, captured_at, task_id) VALUES (?, ?, ?)",
                         (source_key, iso(captured_at), task_id))
            return task_id

        self.journeys.photo_request_in = photo_request_in
        self.journeys.photo_generation_on = lambda visit, journey: True
        return seen

    # ---- 查库（不经过 GET，避免顺手跑一轮后台） ----
    def rows(self, sql: str, *params) -> list:
        with self.app.state.storage.connect() as conn:
            return [tuple(r) for r in conn.execute(sql, params)]

    def queued(self) -> list:
        return self.rows("SELECT source_key, captured_at FROM photo_queue")

    def photo_tasks(self) -> list:
        return self.rows("SELECT dedupe_key FROM web_tasks WHERE dedupe_key LIKE 'illustration:photo:%'")

    def illustrations(self) -> list:
        return self.rows("SELECT source_event_id FROM web_illustrations WHERE source_event_id LIKE 'photo:%'")

    def photo_events(self) -> list:
        return self.rows("SELECT event_key, occurred_at FROM web_world_events WHERE kind = 'photo_taken'")

    def nothing_left(self, why: str) -> None:
        self.assertEqual(self.queued(), [], f"{why}：登记要跟着一起回滚")
        self.assertEqual(self.photo_tasks(), [], f"{why}：队列里不该留下要画的照片")
        self.assertEqual(self.illustrations(), [], f"{why}：插画记录也不该留下")
        self.assertEqual(self.photo_events(), [], f"{why}：更不该有 photo_taken 事件")


class PhotoResidueTests(PhotoCommitBase):
    """反例：提交被拒之后，队列与插画不能留下残留。"""

    def test_a_version_conflict_leaves_no_photo_task_behind(self) -> None:
        visit_id = self.arrive()
        self.wire_probe()
        self.journeys.repo.update_visit = lambda visit, version, conn=None: False  # 店里的状态刚被别处更新过

        with self.assertRaises(JourneyError) as rejected:
            self.take_photo(visit_id)

        self.assertEqual(rejected.exception.reason, "version_conflict")
        self.nothing_left("版本冲突整笔回滚")

    def test_a_lost_lease_leaves_no_photo_task_behind(self) -> None:
        """围栏只对 `act` 自己那段写事务失效——不然更早的推进就先被挡下，这条会变成空转的通过。"""
        visit_id = self.arrive()
        self.wire_probe()
        fired: list[str] = []

        def taken_over(conn):
            if "act" in [f.name for f in traceback.extract_stack()]:
                fired.append("act")
                raise LeaseLost("world", "taken_over")

        with lane_fence(taken_over):
            with self.assertRaises(LeaseLost):
                self.take_photo(visit_id)

        self.assertEqual(fired, ["act"], "前提：围栏确实在拍照那段写事务里拦下了")
        self.nothing_left("租约被接手，整笔回滚")

    def test_without_the_same_transaction_hook_the_photo_path_is_refused(self) -> None:
        """这次本该真的生成照片，却没装配同事务登记：在动业务数据之前就拒绝，不退回"先排队再写库"的两段写。"""
        visit_id = self.arrive()
        self.journeys.photo_request_in = None
        self.journeys.photo_generation_on = lambda visit, journey: True

        with self.assertRaises(JourneyError) as refused:
            self.take_photo(visit_id)

        self.assertEqual(refused.exception.reason, "photo_not_wired")
        self.nothing_left("没装配就拒绝")


class PhotoContractTests(PhotoCommitBase):
    """接口契约：同一个连接、真实按下时刻、稳定来源键；正常路径与幂等。"""

    def test_the_hook_is_called_inside_the_write_transaction(self) -> None:
        visit_id = self.arrive()
        seen = self.wire_probe()

        self.take_photo(visit_id)

        self.assertEqual(len(seen), 1, "拍一次就调一次")
        self.assertTrue(seen[0]["in_transaction"], "必须用写事务里的那个连接，不能另开、也不能留在事务外")
        self.assertEqual(seen[0]["source_key"], f"photo:{visit_id}", "来源键要和 photo_taken 的事件键同源")

    def test_captured_at_is_the_command_time_not_the_arrival_time(self) -> None:
        visit_id = self.arrive()
        seen = self.wire_probe()
        visit = self.journeys.repo.visit(visit_id)
        self.clock.advance(minutes=9)  # 到店之后又待了一会儿，主人这时才说"拍一张"
        pressed = self.clock.now

        self.take_photo(visit_id)

        self.assertEqual(seen[0]["captured_at"], pressed, "拍摄时间＝主人按下的那一刻")
        self.assertNotEqual(seen[0]["captured_at"], visit.starts_at, "不能拿到店时刻冒充拍摄时间")
        self.assertEqual(self.queued(), [(f"photo:{visit_id}", iso(pressed))], "落到队列里的也是那一刻")
        self.assertEqual([e[1] for e in self.photo_events()], [iso(pressed)], "事件时间与拍摄时间同源")

    def test_the_normal_path_still_takes_the_photo(self) -> None:
        visit_id = self.arrive()
        self.wire_probe()

        after = self.take_photo(visit_id)

        done = next(a for a in after.activities if a["kind"] == "take_photo")
        self.assertEqual(done["state"], "done")
        self.assertEqual([e[0] for e in self.photo_events()], [f"photo:{visit_id}"])

    def test_the_same_visit_never_queues_two_photos(self) -> None:
        visit_id = self.arrive()
        seen = self.wire_probe()

        self.take_photo(visit_id)
        self.take_photo(visit_id)  # 连点第二次

        self.assertEqual(len(seen), 1, "已经拍过就不再排第二张")
        self.assertEqual(len(self.photo_events()), 1)


if __name__ == "__main__":
    unittest.main()
