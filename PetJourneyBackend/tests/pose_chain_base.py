"""批次二姿态链路两组用例共用的装置与替身。非测试模块。

**真实装配 ＋ 假供应商**（见 `character_fakes` 抬头），不联网、**0 次付费调用**。
拆成两个文件只是为了守 `arch_gate` 的每文件 30 个 def/class 上限：
`test_web_character_poses.py` 管登记、参考与读取，`test_web_character_pose_gates.py` 管作废与费用。
"""

from __future__ import annotations

from character_fakes import FakeCharacterIllustrator
from web_base import LUNCH_UTC, FakeClock, tiny_png, WebPlatformTestBase

from app.web_character import prompts
from app.web_character.model import POSE_KIND

EXTRA = list(prompts.EXTRA_POSES)


class Denied:
    status = "denied"
    reason = "limit_reached"


class ReplacingIllustrator(FakeCharacterIllustrator):
    """画第二张（第一个姿态）时，世界变了：另一套形象生效了。图照画出来——调用真的发出去了。"""

    def __init__(self, replace) -> None:
        super().__init__()
        self._replace = replace

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        image = super().render(prompt, reference, size=size, background=background)
        if self.calls == 2:
            self._replace()
        return image


class TimeoutAfterNeutral(FakeCharacterIllustrator):
    """中性站姿正常画出；之后每一次都**超时**——发出去了、没等到响应，可能已经计费。"""

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        self.fail_reason = "timeout" if self.calls >= 1 else None
        return super().render(prompt, reference, size=size, background=background)


class PoseChainBase(WebPlatformTestBase):
    """一位主人、一个家、一只带原照的猫。**开关默认关**；要测"打开之后"的用例自己调 `switch_on()`。"""

    def setUp(self) -> None:
        super().setUp()
        # 时钟装在**上传之前**：额度按日计（整套 6 张正好吃满默认的每宠每日上限），
        # 有的用例要推到第二天；晚装的话，setUp 里排上的任务 run_after 会落在假时钟的"未来"，领取不到。
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("pose-owner")
        self.illustrator = FakeCharacterIllustrator()
        self.web.character.illustrator = self.illustrator
        # 先建家那只**不带照片**：带照片的上传会当场排队，那会让每一条的任务数与调用次数都多算一只
        first = self.owner.upload_pet("先建家", "cat", photo=None)
        self.assertEqual(first.status_code, 201, first.text)
        self.household_id = self.web.households.memberships(self.owner.user_id)[0].household_id
        created = self.owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=self.household_id)
        self.assertEqual(created.status_code, 201, created.text)
        self.pet_id = created.json()["pet_id"]

    # ---- 动作 ----
    def switch_on(self) -> None:
        self.web.character.poses.enabled = True

    def go_live(self) -> None:
        """只跑中性站姿那一个任务，让这一套生效。"""
        self.web.character.run_pending(limit=1)
        self.assertIsNotNone(self.active(), "前提：中性站姿已经生效")

    def replace_active_set(self) -> None:
        """另一套形象生效了（比如主人调整形象后新的一套通过了）。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_pet_character_active SET set_id = 'cs-another-set', revision = revision + 1 "
                         "WHERE pet_id = ?", (self.pet_id,))

    # ---- 读 ----
    def query(self, sql: str, params: tuple = ()):
        with self.app.state.storage.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def active(self):
        rows = self.query("SELECT * FROM web_pet_character_active WHERE pet_id = ?", (self.pet_id,))
        return rows[0] if rows else None

    def neutral(self):
        return self.query("SELECT * FROM web_pet_characters WHERE pet_id = ? AND pose = 'neutral_full' "
                          "ORDER BY revision DESC LIMIT 1", (self.pet_id,))[0]

    def pose_rows(self):
        return self.query("SELECT * FROM web_pet_characters WHERE pet_id = ? AND pose != 'neutral_full' ORDER BY rowid",
                          (self.pet_id,))

    def pose_tasks(self):
        return self.query("SELECT * FROM web_tasks WHERE kind = ?", (POSE_KIND,))

    def pose_reservations(self) -> list[tuple]:
        rows = self.query("SELECT r.status, r.outcome, r.actual_units FROM web_budget_reservations r "
                          "JOIN web_tasks t ON r.operation_id LIKE 'character:' || t.task_id || ':%' WHERE t.kind = ?",
                          (POSE_KIND,))
        return [tuple(row) for row in rows]

    def state(self) -> dict:
        response = self.owner.get(f"/pets/{self.pet_id}/character")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()
