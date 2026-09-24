"""模型回信默认开启（2026-09-24，迁移 0190）。

用户：「跟宠物的聊天都是固定的，似乎 ds 没有参与」。根因有两层，这里各钉一条：

  1. 默认值原来是关——改成开；
  2. **光改读取端的默认值不够**：「主人来过」（打开页面读会话、发私信）会替没改过设置的人建出偏好行，
     建行时不写模型回信，就落到列默认值 0，从此「没选过」被读成「关」——而且发生在第一条回信**之前**。
     第一版修复只改了第 1 层，老用例「默认关闭」照样绿，就是因为这一层把默认值又盖了回去。

同时钉住**撤权照旧有效**：明确关掉的，之后怎么来访都不会被默认值盖回去；旧库补正只动确定没选过的行；
运营后台看到的授权和玩家设置页一致。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from admin_base import AdminTestBase
from app.utils import iso, parse_dt
from app.web_platform.migrations import m0190_model_replies_default_on as m0190
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeChat


class ModelRepliesDefaultTests(AdminTestBase):
    def prefs_row(self, user_id: str):
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT model_replies, timezone FROM web_user_prefs WHERE user_id = ?", (user_id,)).fetchone()

    def test_a_never_chosen_owner_stays_on_after_showing_up(self) -> None:
        owner = self.user("shows-up")
        self.assertIsNone(self.prefs_row(owner.user_id), "前提：刚注册还没有偏好行")
        self.assertTrue(owner.get("/session").json()["authenticated"])  # 打开页面就会读会话
        row = self.prefs_row(owner.user_id)
        self.assertIsNotNone(row, "对照：读会话确实替 TA 建出了偏好行——否则下面这条走的是「没有行」的分支，什么都没测")
        self.assertEqual(row["model_replies"], 1, "建行时要写默认值，不能落到列默认值 0")
        self.assertTrue(owner.get("/settings").json()["model_replies"])

    def test_the_first_message_itself_does_not_switch_it_off(self) -> None:
        """不读会话、直接发第一条：发送时的「主人来过」在回信**之前**建行，这一条必须由模型写。"""
        FakeClock(LUNCH_UTC).install(self)
        chat = FakeChat(["我在窗台上晒太阳呢。"])
        owner = self.user("first-message")
        owner.adopt_and_move_in("adopt-lan")
        self.web.communicator.chat = chat
        self.assertIsNone(self.prefs_row(owner.user_id), "前提：发消息之前还没有偏好行")
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-first-0001", "text": "在干嘛呀"})
        self.assertIsNotNone(self.prefs_row(owner.user_id), "对照：发送确实走过了建行那条路")
        self.assertEqual(len(chat.calls), 1, "没选过的主人，第一条私信就该由模型写")

    def test_an_explicit_off_survives_later_visits_and_messages(self) -> None:
        clock = FakeClock(LUNCH_UTC).install(self)
        chat = FakeChat(["不该出现"])
        owner = self.user("said-no")
        owner.adopt_and_move_in("adopt-lan")
        self.web.communicator.chat = chat
        self.assertFalse(owner.patch("/settings", {"model_replies": False}).json()["model_replies"])
        clock.advance(minutes=11)  # 越过「来过」每 10 分钟写一次的节流，让下面两次来访真的写库
        owner.get("/session")
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-no-000001", "text": "在吗"})
        self.assertEqual(chat.calls, [], "明确关掉的，来访、发消息都不能把它盖回默认的开")
        self.assertFalse(owner.get("/settings").json()["model_replies"])

    def test_the_backfill_only_touches_rows_that_never_saw_a_choice(self) -> None:
        """旧库补正（0190）：只把「来访建出来、从没改过设置」的 0 补成 1；分不清的一律不动。"""
        users = {name: self.user(f"legacy-{name}").user_id for name in ("visited", "chose", "old_era", "on")}
        with self.app.state.storage.connect() as conn:
            applied = parse_dt(conn.execute("SELECT applied_at FROM web_schema_migrations "
                                            "WHERE migration_id = '0160_agent_prefs'").fetchone()["applied_at"])
            after, before = iso(applied + timedelta(seconds=1)), iso(applied - timedelta(days=1))
            rows = {
                "visited": (0, None, after),              # 只被「来过」建出：0 是列默认值，不是选择 → 补成 1
                "chose": (0, "Asia/Hong_Kong", after),    # 改过设置（时区非空）：可能是明确关掉 → 不动
                "old_era": (0, None, before),             # 0160 之前旧代码写的行：同样可能是撤权 → 不动
                "on": (1, None, after),                   # 本来就开：保持
            }
            for name, (value, tz, updated_at) in rows.items():
                conn.execute("INSERT INTO web_user_prefs (user_id, model_replies, timezone, updated_at) VALUES (?, ?, ?, ?)",
                             (users[name], value, tz, updated_at))
            m0190._apply(conn)
        got = {name: self.prefs_row(uid)["model_replies"] for name, uid in users.items()}
        self.assertEqual(got, {"visited": 1, "chose": 0, "old_era": 0, "on": 1})

    def test_an_explicit_off_without_a_timezone_is_never_mistaken_for_never_chosen(self) -> None:
        """钉住 0190 判据的地基（Q 2026-09-24 指出）：判「从没改过设置」靠的是 `timezone IS NULL`，
        成立的前提是 `set_prefs` **不传时区也写不出 NULL**——读取层 `_prefs_in` 把空时区补成香港，合并时沿用它。
        哪天有人去掉那个补值（想让时区真正可选），这条会红；否则迁移早已跑完，判据静默变错也不会有任何东西红。"""
        owner = self.user("off-without-timezone")
        self.assertFalse(owner.patch("/settings", {"model_replies": False}).json()["model_replies"])  # 不带 timezone
        row = self.prefs_row(owner.user_id)
        self.assertIsNotNone(row["timezone"], "明确关掉的行时区不能是空的，否则会被 0190 当成「没选过」翻回开")
        with self.app.state.storage.connect() as conn:
            m0190._apply(conn)
        self.assertEqual(self.prefs_row(owner.user_id)["model_replies"], 0, "0190 不能命中明确关掉的行")

    def test_ops_sees_the_same_default_as_the_player(self) -> None:
        """后台自己读库：没有偏好行的照顾人也要显示「开启」，和玩家设置页一致，别让客服对着假信息排查。"""
        owner = self.user("ops-view")
        owner.adopt_and_move_in("adopt-lan")
        self.assertIsNone(self.prefs_row(owner.user_id), "前提：这条要测的就是「没有偏好行」")
        staff = self.staff("support-default", ["support"])
        staff.login_ok()
        self.assertTrue(staff.get(f"/users/{owner.user_id}").json()["prefs"]["model_replies"])
        self.assertTrue(staff.get(f"/pets/{owner.pet_id}/diagnosis").json()["consent"]["owner_model_replies"])


if __name__ == "__main__":
    unittest.main()
