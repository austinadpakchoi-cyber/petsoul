"""纸质卡片也要和 visit、`photo_taken` 事件同生共死，日期按 TA **当时所在地**换算（CR-C11）。

没开启"生成照片"时走的是这条路：它此前自己排队、自己写文件、自己开连接写库，
之后 `update_visit` 一旦版本冲突，就留下一张没有事件的明信片；卡片上印的还是**渲染那一刻的 UTC 日期**，
不是拍摄时刻、也不是 TA 当时所在城市的墙上日期——夜里寄出的卡片会被写成前一天。

这里先复现，再守住：卡片记录 ＋ visit ＋ 事件一起提交／一起回滚；同一个 visit 只做一张；
日期＝按下那一刻在当地的墙上日期。不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo

from app.web_journey.errors import JourneyError
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class PostcardCommitTests(WebPlatformTestBase):
    settle_on_read = True

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("postcard-commit")
        self.owner.adopt_and_move_in("adopt-lan")  # 没开 generated_photos：拍照走纸质卡片这条路
        self.journeys = self.web.journeys

    def arrive(self) -> str:
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()
        self.clock.advance(minutes=7)
        return self.owner.get("/journey/map").json()["current_visit_id"]

    def take_photo(self, visit_id: str):
        visit = self.owner.get(f"/visits/{visit_id}").json()
        activity_id = next(a["activity_id"] for a in visit["activities"] if a["kind"] == "take_photo")
        return self.journeys.act(self.owner.user_id, visit_id, activity_id, self.clock.now)

    def rows(self, sql: str, *params) -> list:
        with self.app.state.storage.connect() as conn:
            return [tuple(r) for r in conn.execute(sql, params)]

    def postcards(self) -> list:
        return self.rows("SELECT photo_id, created_at FROM web_postcards WHERE pet_id = ?", self.owner.pet_id)

    def photo_events(self) -> list:
        return self.rows("SELECT event_key FROM web_world_events WHERE kind = 'photo_taken'")

    def card_text(self, photo_id: str) -> str:
        return (self.app.state.settings.web_private_media_dir / "postcards" / self.owner.user_id / f"{photo_id}.svg").read_text(encoding="utf-8")

    # ---- 反例 ----
    def test_a_version_conflict_leaves_no_postcard_behind(self) -> None:
        visit_id = self.arrive()
        self.journeys.repo.update_visit = lambda visit, version, conn=None: False

        with self.assertRaises(JourneyError) as rejected:
            self.take_photo(visit_id)

        self.assertEqual(rejected.exception.reason, "version_conflict")
        self.assertEqual(self.postcards(), [], "版本冲突整笔回滚：卡片记录不该留下")
        self.assertEqual(self.photo_events(), [], "更不该有 photo_taken 事件")

    # ---- 日期按当时所在地 ----
    def test_the_card_date_is_the_capture_moment_in_the_local_timezone(self) -> None:
        """TA 当时所在地已经是"昨天傍晚"：卡片上要写当地那一天，不是 UTC 的今天，也不是渲染时刻。

        时区直接取到访地点自带的那一个（`visit.place["timezone"]`）——途中所在地会变，
        用出发地或 UTC 换算都会把日期写错一天。这里把地点换到檀香山（UTC-10）来制造这个差别。
        """
        visit_id = self.arrive()
        visit = self.journeys.repo.visit(visit_id)
        self.assertEqual(visit.place["timezone"], "Asia/Hong_Kong", "前提：到访地点本来就带着自己的时区")
        visit.place["timezone"] = "Pacific/Honolulu"
        self.assertTrue(self.journeys.repo.update_visit(visit, visit.version))
        pressed = self.clock.now

        self.take_photo(visit_id)

        cards = self.postcards()
        self.assertEqual(len(cards), 1)
        local_day = pressed.astimezone(ZoneInfo("Pacific/Honolulu")).strftime("%Y.%m.%d")
        self.assertNotEqual(local_day, pressed.strftime("%Y.%m.%d"), "前提：这一刻的当地日期确实和 UTC 不同一天")
        card = self.card_text(cards[0][0])
        self.assertIn(local_day, card, "卡片上要写 TA 当时所在地的那一天")
        self.assertNotIn(pressed.strftime("%Y.%m.%d"), card, "不能写成 UTC 的日期")

    def test_the_same_visit_makes_only_one_card(self) -> None:
        visit_id = self.arrive()

        self.take_photo(visit_id)
        self.take_photo(visit_id)  # 连点第二次

        self.assertEqual(len(self.postcards()), 1, "同一次到访只做一张卡片")
        self.assertEqual(len(self.photo_events()), 1)

    def test_the_normal_path_still_writes_an_honest_paper_card(self) -> None:
        visit_id = self.arrive()

        after = self.take_photo(visit_id)

        done = next(a for a in after.activities if a["kind"] == "take_photo")
        self.assertEqual(done["state"], "done")
        self.assertIn("没有照片", done["result_text"], "没开启生成照片就如实说是纸质卡片")
        self.assertEqual(len(self.postcards()), 1)
        self.assertEqual([e[0] for e in self.photo_events()], [f"photo:{visit_id}"])


if __name__ == "__main__":
    unittest.main()
