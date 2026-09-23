"""worker 里的规则照片导演接入：readiness → direct(rule, 0 次文本调用) → delivery → render。

三条硬规矩（COORD-A-DIRECTOR-NOW）：
  1. 目标场景缺必需项 → **hold**：0 次图片预占、0 次发送，**绝不回落旧模板**；
  2. 没有 `scene_key` 的历史路径**行为一字不变**（邮筒自拍、手账图、冒险插画都走老路，不是 hold）；
  3. 交付只允许显式丢 `negative_prompt`（方舟没有这个参数），其余语义丢失要看得见。

一次性临时库 ＋ 真实队列与插画服务 ＋ 真实 `app.web_photo_director`；替身生图，不联网、无付费。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.image_provider.models import GeneratedImage
from app.utils import iso
from app.web_journey.illustrations import IllustrationService
from app.web_platform.budget import BudgetLedger, BudgetLimit
from app.web_platform.tasks import WebTaskQueue
from app.web_platform.uow import unit_of_work
from task_budget_helpers import open_storage

SHOT_AT = datetime(2026, 9, 23, 1, 20, tzinfo=timezone.utc)  # 香港当地 09:20
OWNER, PET, HOUSE, SOURCE = "u-1", "pet-1", "hh-1", "photo:vi-1"
PNG = b"\x89PNG\r\n\x1a\nfake-owner-photo"


class RecordingIllustrator:
    available = True
    provider_label = "测试生图"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.sizes: list[str] = []

    def render(self, prompt, reference=None, size="2048x2048") -> GeneratedImage:
        self.prompts.append(prompt)
        self.sizes.append(size)
        return GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\nfake", mime_type="image/png", model="fake", provider="fake", source="url")


class PhotoDirectorWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.storage = open_storage(str(root / "director.sqlite3"))
        self.queue = WebTaskQueue(self.storage)
        self.ledger = BudgetLedger(self.storage)
        self.illustrator = RecordingIllustrator()
        self.illustrations = IllustrationService(self.storage, root / "media", self.queue)
        self.illustrations.illustrator = self.illustrator
        self.illustrations.opted_in = lambda user_id, pet_id=None: True
        self.illustrations.can_view_pet = lambda user_id, pet_id: True
        self.illustrations.character_of = lambda pet_id: ("cat", "小岚", None)
        self.illustrations.reference_photo_of = lambda pet_id: (PNG, "image/png")  # 主人原照，不用画证件照
        # 测试注入：代表 I 接线后会给出的参考照来源。**不注入就是来源不明**，目标场景会 hold（见对应反例）。
        self.illustrations.reference_origin_of = lambda pet_id: "owner_original"
        # 测试注入：代表 B 接线后"执行这一刻重新读这次到访的代数"。不注入就是没有这道闸 → hold（见反例）。
        self.illustrations.event_revision_of = lambda source_key: 0
        self.illustrations.reserve = lambda operation_id, pet_id, units: self.ledger.reserve(
            operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}", units=units,
            limits=[BudgetLimit("provider:image:daily", 50)])
        self.illustrations.settle = lambda permit, outcome, actual_units=None: self.ledger.settle(permit, outcome, actual_units=actual_units)

    # ---- 造数 ----
    def register(self, **extras) -> str:
        with unit_of_work(self.storage) as conn:
            return self.illustrations.request_photo_in(
                conn, OWNER, PET, SOURCE, place="信德中心", city="香港", scene="在店里靠窗的位置坐着",
                captured_at=SHOT_AT, **extras)

    def full_facts(self, **overrides) -> dict:
        """C 经 B 应当带上的那一组事实（键名见 A 的 CR：household_id / place_id / place_timezone / scene_facts）。"""
        facts = {"scene_key": "cafe", "household_id": HOUSE, "place_id": "amap:B0TEST",
                 "place_timezone": "Asia/Hong_Kong", "revision": 0, "event_origin": "world_event",
                 "scene_facts": [self.fact("at_cafe")]}
        facts.update(overrides)
        return facts

    @staticmethod
    def fact(token: str) -> dict:
        return {"fact_id": f"f-{token}", "token": token, "pet_id": PET, "household_id": HOUSE,
                "event_id": SOURCE, "verified": True}

    def reservations(self, task_id: str) -> list[tuple]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations "
                                "WHERE operation_id LIKE ? ORDER BY rowid", (f"illustration:{task_id}:%",)).fetchall()
        return [(r["status"], r["outcome"], r["actual_units"]) for r in rows]

    def task_row(self, task_id: str):
        with self.storage.connect() as conn:
            return conn.execute("SELECT status, last_error FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()

    def illustration_status(self, task_id: str) -> str:
        with self.storage.connect() as conn:
            return conn.execute("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,)).fetchone()["status"]

    # ---- 1. 没有 scene_key 的历史路径：一字不变 ----
    def test_a_request_without_a_scene_key_keeps_the_existing_template_path(self) -> None:
        task_id = self.register()
        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1, "照常出图，不是 hold")
        self.assertIn("在店里靠窗的位置坐着", self.illustrator.prompts[0], "走的是原来的 build_selfie_prompt")
        self.assertEqual(self.task_row(task_id)["status"], "succeeded")
        self.assertEqual(self.illustration_status(task_id), "ready")

    # ---- 2. 目标场景、事实齐全：走导演 ----
    def test_a_target_scene_with_complete_facts_is_compiled_by_the_rule_director(self) -> None:
        task_id = self.register(**self.full_facts())
        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1)
        prompt = self.illustrator.prompts[0]
        self.assertNotIn("在店里靠窗的位置坐着", prompt, "导演接管之后不再用旧模板那句写死的场景")
        self.assertEqual(self.illustrator.sizes, ["2048x2048"])
        self.assertEqual(self.task_row(task_id)["status"], "succeeded")
        self.assertEqual(self.illustration_status(task_id), "ready")
        self.assertEqual(self.reservations(task_id), [("settled", "succeeded", 1)], "有主人原照：一次调用、按 1 结算")

    # ---- 3. 缺必需项：hold，0 预占 0 发送，不回落 ----
    def test_missing_required_facts_hold_before_any_reservation(self) -> None:
        """这一条是整批的重点：hold 必须发生在**预占之前**，否则会留下一笔占掉额度的空预占。"""
        task_id = self.register(**self.full_facts(scene_facts=[]))  # 少了 at_cafe 这条已核验事实
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "**0 次预占**——不能占掉额度又什么都没画")
        row = self.task_row(task_id)
        self.assertEqual(row["status"], "failed", "进终态")
        self.assertTrue(row["last_error"].startswith("image director_hold:"), f"原因要看得见：{row['last_error']}")
        self.assertEqual(self.illustration_status(task_id), "failed", "如实显示没有图，不冒充已发送")

    def test_a_missing_timezone_holds_instead_of_guessing(self) -> None:
        task_id = self.register(**self.full_facts(place_timezone=None))
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "不猜时区，宁可不生成")
        self.assertEqual(self.reservations(task_id), [])
        self.assertTrue(self.task_row(task_id)["last_error"].startswith("image director_hold:"))

    def test_a_hold_is_not_retried_automatically(self) -> None:
        task_id = self.register(**self.full_facts(scene_facts=[]))
        self.illustrations.run_pending()
        self.assertEqual(self.task_row(task_id)["status"], "failed")

        self.illustrations.run_pending()  # 再跑一轮

        self.assertEqual(self.illustrator.prompts, [], "缺的是事实，自动重试不会让它变有")
        self.assertEqual(self.reservations(task_id), [])

    # ---- 4. 来源不明的参考照不许冒名 ----
    def test_a_reference_of_unknown_origin_holds_instead_of_claiming_owner_original(self) -> None:
        """装配没给参考照来源时，不能把它当成"主人原照"报给导演——来源不明就 hold。"""
        self.illustrations.reference_origin_of = lambda pet_id: None
        task_id = self.register(**self.full_facts())
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertTrue(self.task_row(task_id)["last_error"].startswith("image director_hold:"))

    # ---- 5. 目标场景缺身份参考：预占前 hold，不先花钱画证件照 ----
    def test_a_target_scene_without_an_identity_reference_holds_before_paying_for_a_portrait(self) -> None:
        self.illustrations.reference_photo_of = lambda pet_id: None
        self.illustrations.portrait_saver = lambda pet_id, data, mime: True  # 接上了也不许用
        task_id = self.register(**self.full_facts())
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "**不先付费画一张证件照再把自己补成 ready**")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertTrue(self.task_row(task_id)["last_error"].startswith("image director_hold:"))

    # ---- 6. 登记之后、出图之前版本变了：导演自己拒 ----
    def test_versions_moving_between_registration_and_execution_are_refused(self) -> None:
        """版本代数不是自比的假零：登记时的快照与执行时的当前值不一致，就说明中途变过。"""
        from app.web_platform.runtime_epochs import bump_in

        task_id = self.register(**self.full_facts())
        with unit_of_work(self.storage) as conn:
            bump_in(conn, PET, "privacy_epoch", SHOT_AT)  # 排队期间用途授权换代
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "中途变过就不出图")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertTrue(self.task_row(task_id)["last_error"].startswith("image director_hold:"))

    # ---- 7. 虚构题材不能记成世界事件 ----
    def test_a_fictional_theme_registered_as_a_world_event_is_refused(self) -> None:
        """主人选的虚构题材记成 `world_event`，等于断言"世界上真的发生过一次飞行"——导演会拒。"""
        task_id = self.register(**self.full_facts(
            scene_key="flight_adventure", narrative="fictional_adventure",
            scene_facts=[self.fact("flight_adventure")], event_origin="world_event"))
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertTrue(self.task_row(task_id)["last_error"].startswith("image director_hold:"))

    def test_a_fictional_theme_from_an_owner_command_is_accepted(self) -> None:
        """同一个题材，来路记成"主人按下的拍照命令"就是合法的——这才是它真实的来路。"""
        self.register(**self.full_facts(
            scene_key="flight_adventure", narrative="fictional_adventure",
            scene_facts=[self.fact("flight_adventure")], event_origin="owner_directed"))
        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1, "虚构题材照常出图，只是来路要如实")

    # ---- 8. 参考照来源要贯穿到真正交给导演的输入 ----
    def test_the_injected_reference_origin_reaches_the_director_inputs(self) -> None:
        """执行阶段不能把已有基准照改称"主人原图"：装配说它是我们自己生成的，就得原样传下去。"""
        from app.web_journey import photo_director_bridge as bridge

        self.illustrations.reference_origin_of = lambda pet_id: "original_companion"
        seen = {}
        original = bridge.DIRECTOR.direct

        def capture(context, access):
            seen["origin"] = context.identity.origin
            seen["source"] = context.references[0].source
            return original(context, access)

        bridge.DIRECTOR.direct = capture
        self.addCleanup(lambda: setattr(bridge.DIRECTOR, "direct", original))

        self.register(**self.full_facts())
        self.illustrations.run_pending()

        self.assertEqual(seen.get("origin"), "original_companion", "不能被执行阶段改写成 owner_original")
        self.assertEqual(seen.get("source"), "generated_canonical", "来源标记也要跟着对上")

    def test_a_hold_reason_carries_the_missing_item(self) -> None:
        """只给大类的话，"物种不支持"和"事实不齐"在主人那边长得一样，运维分不开。"""
        task_id = self.register(**self.full_facts(scene_facts=[]))
        self.illustrations.run_pending()

        self.assertIn("required_fact:at_cafe", self.task_row(task_id)["last_error"], "缺哪条事实要看得见")

    def test_a_missing_event_origin_holds_with_its_own_reason(self) -> None:
        """登记方没声明这次拍照的来路：**"不知道"不能自动变成"世界上真的发生过"**。

        原因码单列 `event_origin_missing`——"登记方忘了声明来路"（接线问题）与"事实不齐"（数据问题）
        是两回事，混成一个 `inputs_missing` 运维只能靠猜。
        """
        task_id = self.register(**self.full_facts(event_origin=None))
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertIn("event_origin_missing", self.task_row(task_id)["last_error"])

    def test_a_missing_event_revision_reader_holds_instead_of_faking_the_fence(self) -> None:
        """没接"执行时重读代数"的读口时，两边都回读 payload 会永远相等——那是伪装的围栏，所以 hold。"""
        self.illustrations.event_revision_of = None
        task_id = self.register(**self.full_facts())
        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertIn("event_revision_unwired", self.task_row(task_id)["last_error"])

    def test_an_event_corrected_while_queued_is_refused(self) -> None:
        """排队期间这次到访被更正过（代数变了）：这组事实是在旧那一代上采的，不能照着出图。"""
        task_id = self.register(**self.full_facts(revision=3))
        self.illustrations.event_revision_of = lambda source_key: 4  # 执行这一刻读到的是新代数

        self.illustrations.run_pending()

        self.assertEqual(self.illustrator.prompts, [], "0 次发送")
        self.assertEqual(self.reservations(task_id), [], "0 次预占")
        self.assertIn("event_revision_changed", self.task_row(task_id)["last_error"])

    def test_an_unchanged_event_revision_still_renders(self) -> None:
        """正常对照：代数没变就照常出图，别把闸做成永远拦。"""
        self.register(**self.full_facts(revision=3))
        self.illustrations.event_revision_of = lambda source_key: 3

        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1)

    # ---- 9. 拍摄时刻按当地时间换算 ----
    def test_the_capture_time_is_converted_to_the_place_local_wall_time(self) -> None:
        from app.web_journey.photo_director_bridge import local_capture_time

        payload = {"captured_at": iso(SHOT_AT), "place_timezone": "Asia/Hong_Kong"}
        local = local_capture_time(payload)
        self.assertEqual(local.hour, 9, "香港当地 09:20，不是 UTC 的 01:20，也不是宿主机时区")
        self.assertIsNotNone(local.utcoffset())
        self.assertIsNone(local_capture_time({"captured_at": iso(SHOT_AT)}), "没有时区就是没有，不猜")
        self.assertIsNone(local_capture_time({"captured_at": "2026-09-23T09:20:00", "place_timezone": "Asia/Hong_Kong"}),
                          "拍摄时刻不带偏移就是来源不明：不猜 UTC、也不用宿主机时区")


if __name__ == "__main__":
    unittest.main()
