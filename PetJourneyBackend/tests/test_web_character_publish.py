"""世界角色的**发布闸**：什么情况下画出来了也不许发布，以及什么情况下根本不该发出去。

CR-PLAYER-CHARACTER-01 里这几条是硬的：
「GET 不出图、重启不重发、unknown 不自动重试、换参考后旧结果不得发布、原照片不覆盖」。
（CR 原文还有「或撤权」——逐次授权询问已于 2026-09-23 由用户决定取消，那一节换成了**归属**，见第②节。）
上传自动触发那一条在 `test_web_character_autostart.py`，这一套只管闸。

**用真实装配 ＋ 假供应商**（见 `character_fakes` 抬头），不联网、**0 次付费调用**。

一处如实说明：**目前没有"换一张原照"的接口**（网页侧只有建立宠物时能带照片），
所以"换参考"那几条是直接改 `web_pet_profiles.photo_ref` 来触发的。
被测的是**闸**本身——它读的就是这一列；换照片的接口将来由谁做、怎么做，不影响这道闸的正确性。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from character_fakes import FakeCharacterIllustrator, checker, opaque_png, rgb_png, two_subjects_png
from web_base import tiny_png, WebPlatformTestBase

from app.schemas.runtime_internal import StaleClaim
from app.utils import iso, utcnow


class RevokingIllustrator(FakeCharacterIllustrator):
    """画到一半世界变了（换了参考照、宠物离开了家）：图照画出来（调用真的发出去了），但**不该被发布**。"""

    def __init__(self, disturb) -> None:
        super().__init__()
        self._disturb = disturb

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        # `background` 必须收下：角色链路现在按调用请求透明底（2026-09-23）。
        # 第一版漏了它，服务一传就 TypeError，被当成普通异常重试，行卡在 running——
        # 用例红的样子像"闸没生效"，其实是替身签名没跟上。
        image = super().render(prompt, reference, size=size, background=background)
        self._disturb()
        return image


class CharacterPublishGateTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("gate-owner")
        self.illustrator = FakeCharacterIllustrator()
        self.web.character.illustrator = self.illustrator
        # 先建家那只**不带照片**：摘掉授权闸之后，带照片的上传会当场排队，
        # 那会让下面每一条的任务计数与供应商调用次数都多算一只。
        first = self.owner.upload_pet("先建家", "cat", photo=None)
        self.assertEqual(first.status_code, 201, first.text)
        self.household_id = self.web.households.memberships(self.owner.user_id)[0].household_id
        created = self.owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=self.household_id)
        self.assertEqual(created.status_code, 201, created.text)
        self.pet_id = created.json()["pet_id"]

    # ---- 辅助 ----
    def view(self):
        return self.web.character.view(self.pet_id)

    def row(self):
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_pet_characters WHERE pet_id = ? ORDER BY revision DESC LIMIT 1",
                                (self.pet_id,)).fetchone()

    def task_id(self) -> str:
        return self.row()["task_id"]

    def active_set(self):
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_pet_character_active WHERE pet_id = ?", (self.pet_id,)).fetchone()

    def leave_household(self) -> None:
        """把这只宠物从家里摘出来。**不是撤权**——逐次授权询问已取消（用户 2026-09-23 决定）；
        这一条管的是**归属**：没有家的宠物，角色不属于任何人，也没人有权读它。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("DELETE FROM web_household_pets WHERE pet_id = ?", (self.pet_id,))

    def swap_reference(self) -> None:
        """模拟「主人换了一张原照」。见模块抬头：目前没有对应接口，闸读的就是这一列。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_pet_profiles SET photo_ref = ? WHERE pet_id = ?",
                         (f"pets/{self.owner.user_id}/swapped.png", self.pet_id))

    # ---- ① 换参考：连发都不发 ----
    def test_a_reference_swapped_while_queued_is_never_sent(self) -> None:
        self.swap_reference()

        self.web.character.run_pending()

        self.assertEqual(self.illustrator.calls, 0, "参考都换了，这一版作废——**不发送**，不是发完再丢")
        view = self.view()
        self.assertEqual((view.state, view.reason), ("failed", "reference_changed"))
        self.assertIsNone(self.active_set(), "没发布过，就没有生效版本")

    def test_a_reference_swapped_after_the_image_came_back_is_not_published(self) -> None:
        """图已经画出来、费用也按实结算过，发布**之前**才发现参考换了：不发布。

        不发布的是"把它拿给主人看"，不是假装什么都没发生——已经发出去的调用撤不回来。
        """
        self.web.character.illustrator = RevokingIllustrator(self.swap_reference)

        self.web.character.run_pending()

        view = self.view()
        self.assertEqual((view.state, view.reason), ("failed", "reference_changed"))
        self.assertIsNone(self.active_set())

    # ---- ② 归属（逐次授权询问已取消，这一节取代原先的"撤权"三条）----
    def test_a_pet_that_left_its_household_mid_attempt_is_not_published(self) -> None:
        """图已经画出来、费用也按实结算过，发布**之前**才发现这只宠物已经没有家：不发布。

        摘掉授权闸时**没有把归属判断一起摘掉**——原先那道 `generated_photos_in` 顺带做了这件事
        （没有家一律 False）。没有家的宠物，角色不属于任何人，也没人有权读它。
        """
        self.web.character.illustrator = RevokingIllustrator(self.leave_household)

        self.web.character.run_pending()

        view = self.view()
        self.assertEqual((view.state, view.reason), ("failed", "pet_has_no_household"))
        self.assertIsNone(self.active_set(), "没有家就不发布")

    def test_a_published_character_survives_the_pet_leaving_later(self) -> None:
        """已经生效的形象不因为之后被移出家庭就被删——那是**读权限**的事，由路由每次请求重判。

        （要不要连同已发布资产一起撤回，是产品判断，不在本批擅自定。）
        """
        self.web.character.run_pending()
        self.assertEqual(self.view().state, "ready")

        self.leave_household()

        self.assertIsNotNone(self.active_set(), "已生效的那一套还在库里")
        asset_id = self.view().active.asset_id
        self.assertEqual(self.owner.get(f"/media/characters/{asset_id}").status_code, 404,
                         "但读不到了——`require_pet` 每次请求重判，这是权限层的事，不是删数据")

    # ---- ③ 租约被别人接手：这次结果整批作废 ----
    def test_a_stale_claim_publishes_nothing(self) -> None:
        queue = self.web.character.tasks
        mine = queue.claim_next("worker-a", ["pet_character"], lease_seconds=0.001)
        self.assertIsNotNone(mine)
        later = utcnow() + timedelta(hours=1)
        queue.recover_expired(now=later, kinds=["pet_character"])  # 租期过了，任务被回收重排
        theirs = queue.claim_next("worker-b", ["pet_character"], now=later)
        self.assertIsNotNone(theirs, "另一个 worker 接手了")

        with self.assertRaises(StaleClaim):
            self.web.character.run_claimed(queue.get(mine.task_id), mine, queue)

        self.assertIsNone(self.active_set(), "被接手之后，旧 worker 写不进任何结果")
        self.assertEqual(self.row()["state"], "queued", "也不许把状态改成它以为的样子")

    # ---- ④ 过期任务不得覆盖新形象（SQL 层的闸）----
    def test_an_older_revision_cannot_overwrite_a_newer_active(self) -> None:
        """闸做在条件 upsert 上：`WHERE excluded.revision > 现有 revision`。

        比"在 Python 里先查再写"强的地方：并发两个任务同时提交时，数据库自己就判得出谁该赢。
        """
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for revision, set_id in ((5, "cs-new"), (2, "cs-old")):
                conn.execute(
                    "INSERT INTO web_pet_character_active (pet_id, set_id, revision, published_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(pet_id) DO UPDATE SET set_id = excluded.set_id, revision = excluded.revision, "
                    "published_at = excluded.published_at WHERE excluded.revision > web_pet_character_active.revision",
                    (self.pet_id, set_id, revision, iso(utcnow())))

        active = self.active_set()
        self.assertEqual((active["set_id"], active["revision"]), ("cs-new", 5), "号小的那次覆盖不了已经生效的")

    # ---- ⑤ 结果不明：不自动重发、不说成"没画成" ----
    def test_a_timeout_is_reported_as_unknown_and_never_resent(self) -> None:
        """超时＝发出去了、没等到响应，**可能已经计费**。不能写成"没生成"，更不能自动再发一次。

        **两端一起钉**（P 提的加固，写这条时把一个设计问题逼出来了）：

        第一版 `"timeout"` **不在** `NO_RETRY_REASONS` 里，任务会被**排回去等 60 秒**，
        靠下一轮的"恢复不重发"闸短路。最终行为是对的（0 发送 0 计费），但那是**两道闸配合**才对——
        而且「排回去」本身就是 CR 说的「unknown 自动重试」。现在第一道闸自己就拦得住：
        `UNKNOWN_REASONS` 已并入 `NO_RETRY_REASONS`，任务**当场进终态**。

        两端都断言：任务进 `failed`，预占表那一行是 `unknown`（＝可能已发出、结果未确认）。
        只断言其中一端的话，另一边被改坏了看不出来。
        """
        self.web.character.illustrator = FakeCharacterIllustrator(fail_reason="timeout")

        self.web.character.run_pending()

        self.assertEqual(self.view().state, "unknown", "要如实说「还没确认」，不是「没画成」")
        calls = self.web.character.illustrator.calls
        self.web.character.run_pending()
        self.assertEqual(self.web.character.illustrator.calls, calls, "结果不明的不自动重发——那会二次计费")
        with self.app.state.storage.connect() as conn:
            task = conn.execute("SELECT status FROM web_tasks WHERE task_id = ?", (self.task_id(),)).fetchone()
            hold = conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations "
                                "WHERE operation_id LIKE ? ORDER BY rowid DESC LIMIT 1",
                                (f"character:{self.task_id()}:%",)).fetchone()
        self.assertEqual(task["status"], "failed", "另一端：任务当场进终态，不排回去——排回去就是自动重试")
        self.assertEqual((hold["status"], hold["outcome"]), ("unknown", "unknown"), "这一端：账上记着「可能已经发出」")
        self.assertEqual(hold["actual_units"], 1, "按实际发出的 1 次计入——不知道 ≠ 没发生")

    def test_a_previous_unconfirmed_attempt_is_not_resent_after_a_restart(self) -> None:
        """进程崩在调用中途：额度预占停在 `reserved`，恢复回来也不重发。"""
        task_id = self.task_id()
        permit = self.web.character.ledger.reserve(f"character:{task_id}:1", provider="image", purpose="character",
                                                   subject_scope=f"pet:{self.pet_id}", units=1)
        self.assertEqual(permit.status, "reserved")
        with self.app.state.storage.connect() as conn:
            # `lease_expired` 是**生产里的真实取值**：租期过了被回收重排时，`lease.py:236` 写的就是它。
            # 用真值而不是随手编一个字符串——代码只看真假，但下一个人读用例时该看到真实形状。
            conn.execute("UPDATE web_tasks SET last_error = 'lease_expired' WHERE task_id = ?", (task_id,))

        self.web.character.run_pending()

        self.assertEqual(self.illustrator.calls, 0, "上一次可能已经发出去了，恢复回来不许再发")
        self.assertEqual(self.view().reason, "unknown_result")

    # ---- ⑥ 额度：没拿到就不发 ----
    def test_a_budget_denial_stops_before_sending(self) -> None:
        self.web.character.reserve = lambda operation_id, pet_id, units: _Denied()

        self.web.character.run_pending()

        self.assertEqual(self.illustrator.calls, 0, "没拿到额度就不偷偷发")
        self.assertEqual(self.view().reason, "budget_denied")

    def test_a_successful_attempt_settles_exactly_one_unit(self) -> None:
        self.web.character.run_pending()

        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT status, outcome, reserved_units, actual_units FROM web_budget_reservations "
                               "WHERE operation_id LIKE ?", (f"character:{self.task_id()}:%",)).fetchone()
        self.assertEqual((row["status"], row["outcome"]), ("settled", "succeeded"))
        self.assertEqual((row["reserved_units"], row["actual_units"]), (1, 1), "一张图就是一次调用")

    def test_the_global_cap_is_the_same_counter_the_illustration_chain_uses(self) -> None:
        """**角色生图必须计进 `provider:image:daily`**——那是生图供应商本身的每日上限，两条链路花的是同一份钱。

        我第一版用了 `provider:image:character` 这个自造的档位，等于给角色开了一条**不计入总账的旁路**：
        配了 `web_image_daily_cap` 也拦不住它。P 指出我注释里一处事实错误时顺带查出来的。
        每宠那一层仍是分开的 `pet:<id>:character`，那是有意的取舍（见 `service.py` 里的说明）。
        """
        from app.web_character.service import CharacterService

        service = CharacterService(self.app.state.storage, self.web.character.root, self.web.character.tasks,
                                   per_pet_daily=3, global_daily=7)
        before = service.ledger.usage("provider:image:daily")["inflight"]

        permit = service.reserve("character:cap-probe:1", self.pet_id, 1)

        self.assertEqual(permit.status, "reserved", getattr(permit, "reason", ""))
        self.assertEqual(service.ledger.usage("provider:image:daily")["inflight"], before + 1,
                         "要落在插画链路用的那个全局计数器上，不是另起一个")
        self.assertEqual(service.ledger.usage(f"pet:{self.pet_id}:character")["inflight"], 1, "每宠那层单独一条车道")

    def test_a_not_sent_failure_releases_the_local_hold(self) -> None:
        """当场被拒（4xx）＝确定没受理：**本地预占**整笔释放。这只影响本地额度记账，
        与供应商那边收不收费无关——真实费用一律按「未验证」对待。"""
        self.web.character.illustrator = FakeCharacterIllustrator(fail_reason="rejected")

        self.web.character.run_pending()

        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT outcome FROM web_budget_reservations WHERE operation_id LIKE ?",
                               (f"character:{self.task_id()}:%",)).fetchone()
        self.assertEqual(row["outcome"], "not_sent")

    # ---- ⑥b 拿回来不透明：三种原因分开记 ----
    def test_opaque_results_are_told_apart_by_why(self) -> None:
        """三种"拿回来不透明"的处置完全不同，所以原因码必须分开（P 规范 4.2 第 6 条）：

          - 适配器**没请求**透明 → `transparency_not_requested`（改参数或换实现）；
          - 请求了、**画了棋盘格** → `checkerboard_drawn`（alpha 在上游有过、被压平了，改响应格式／端点）；
          - 请求了、**纯不透明** → `opaque_background`（参数被忽略，报能力缺失）。

        "没请求"**优先于**棋盘格：没请求透明却画出了方格，那是模型自己画的，先该问的是"你请求了吗"。
        """
        board = rgb_png(64, 96, checker(8))
        cases = [
            ("没请求 ＋ 纯不透明", False, opaque_png(), "transparency_not_requested"),
            ("没请求 ＋ 棋盘格", False, board, "transparency_not_requested"),
            ("请求了 ＋ 棋盘格", True, board, "checkerboard_drawn"),
            ("请求了 ＋ 纯不透明", True, opaque_png(), "opaque_background"),
        ]
        for name, requested, image, expected in cases:
            with self.subTest(name=name):
                self.web.character.transparency_requested = requested
                self.assertEqual(self.web.character._alpha_reason(self._verdict_reason(image)), expected)

    @staticmethod
    def _verdict_reason(image: bytes) -> str:
        from app.web_character import validate

        return validate.inspect(image, "image/png").reason

    # ---- ⑦ 校验不过：当场进终态，不在后台重画 ----
    def test_a_failed_validation_is_never_redrawn_in_the_background(self) -> None:
        """校验不过的那一张**已经画出来、钱也按实结算过了**。后台再画一次就是再花一次钱去碰运气。

        方案第 54 行：「失败或 unknown 如实落状态，**不在后台无限重画凑合格结果**」。
        所以任务要**当场进终态**，不能被排回去等 60 秒后自动重试——那是第一版的缺陷：
        校验原因码没进 `NO_RETRY_REASONS`，`retryable` 算成了 True。
        要再来一次只能由主人显式点「调整形象」。
        """
        self.web.character.illustrator = FakeCharacterIllustrator(images=[two_subjects_png()])

        self.web.character.run_pending()

        with self.app.state.storage.connect() as conn:
            task = conn.execute("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (self.task_id(),)).fetchone()
        self.assertEqual(task["status"], "failed", "必须当场进终态，不能排回去等自动重试")
        self.assertEqual(self.web.character.illustrator.calls, 1, "只发出去过一次")

    def test_only_a_provider_error_is_retried_automatically(self) -> None:
        """对照：连不上／被限流**确定没受理**，换个时间可能就成，这一类才留在自动重试里。"""
        self.web.character.illustrator = FakeCharacterIllustrator(fail_reason="provider_error")

        self.web.character.run_pending()

        with self.app.state.storage.connect() as conn:
            task = conn.execute("SELECT status FROM web_tasks WHERE task_id = ?", (self.task_id(),)).fetchone()
        self.assertEqual(task["status"], "queued", "排回去了，等下一轮再试")


    # ---- ⑦ 校验不过的那一张进不了媒体路由 ----
    def test_a_rejected_image_never_reaches_the_media_route(self) -> None:
        """校验不过的那一张**没有可读地址**：它不是「存下来但不显示」，是根本没进资产。"""
        self.web.character.illustrator = FakeCharacterIllustrator(images=[two_subjects_png()])

        self.web.character.run_pending()

        row = self.row()
        self.assertEqual((row["state"], row["reason"]), ("failed", "multiple_subjects"))
        self.assertIsNone(row["rel_path"])
        self.assertIsNone(self.web.character.media_path(row["asset_id"]))


class _Denied:
    status = "denied"
    reason = "limit_reached"


if __name__ == "__main__":
    unittest.main()
