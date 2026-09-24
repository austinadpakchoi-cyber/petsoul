"""公开动态不重复刷同一句（6c2b 2026-09-24 实测：秋秋 02:18、05:18 各发了一条一字不差的动态）。

规则：同一位作者 3 天内一字不差、而且这次没有照片 → 不再发；到访本身照常记在行程里。带照片的是新内容，照常发；过了 3 天照常发。
测这条规则时把选句函数固定成一句（文案本身有几种说法，见下面的 `PostVarietyTests`）。

另：6c2b 同日又报「至少 7 只**不同**宠物在发同一句」——文案改为按「哪只宠物、哪次到访」固定地选一种说法，
并去掉那句没核实的「{城市}的风很舒服」。
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from types import SimpleNamespace

import app.web_social.service as social_service
from app.web_social.service import REPEAT_WINDOW, VISIT_LINES, WORK_LINES, visit_post_text
from web_base import LUNCH_UTC, PREFIX, WebPlatformTestBase


class NoRepeatPostTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.pet_id = self.client.get(f"{PREFIX}/public/residents").json()[0]["pet_id"]
        self.web.social.public_posts_of = lambda pet_id: True
        self.web.social.on_post_media_public = lambda url: None
        self.seq = 0
        original = social_service.visit_post_text
        social_service.visit_post_text = lambda **kw: f"在{kw['place']}待了一会儿{kw['extra']}。"  # 固定成一句：只测「不重复」这条规则
        self.addCleanup(setattr, social_service, "visit_post_text", original)

    def visit_ended(self, at, place: str = "海边小码头", photo: str | None = None) -> None:
        self.seq += 1
        activities = [{"kind": "take_photo", "state": "done", "photo_url": photo}] if photo else []
        self.web.social.on_world_event(SimpleNamespace(
            kind="visit_ended", occurred_at=at, source_event_id=f"jn-test{self.seq}:visit_ended",
            visit=SimpleNamespace(visit_id=f"vi-{self.seq}", place={"name": place}, activities=activities),
            journey=SimpleNamespace(pet_id=self.pet_id, user_id="sys-planet-residents", destination_key="local:stroll", title="散步", city="香港")))

    def texts(self) -> list[str]:
        with self.app.state.storage.connect() as conn:
            return [r["text"] for r in conn.execute("SELECT text FROM web_posts WHERE author_pet_id = ? ORDER BY created_at", (self.pet_id,))]

    def test_the_same_sentence_within_three_days_is_posted_once(self) -> None:
        self.visit_ended(LUNCH_UTC)
        self.visit_ended(LUNCH_UTC + timedelta(hours=3))
        self.assertEqual(len(self.texts()), 1, "三小时后一字不差的同一句不再发")

    def test_after_three_days_it_may_be_said_again(self) -> None:
        self.visit_ended(LUNCH_UTC)
        self.visit_ended(LUNCH_UTC + REPEAT_WINDOW + timedelta(minutes=1))
        self.assertEqual(len(self.texts()), 2)

    def test_a_different_place_is_a_different_post(self) -> None:
        self.visit_ended(LUNCH_UTC)
        self.visit_ended(LUNCH_UTC + timedelta(hours=3), place="街角咖啡店")
        self.assertEqual(len(self.texts()), 2)

    def test_a_post_with_a_photo_is_new_content(self) -> None:
        self.visit_ended(LUNCH_UTC)
        self.visit_ended(LUNCH_UTC + timedelta(hours=3), photo="/api/v1/web/media/postcards/pc-test")
        self.assertEqual(len(self.texts()), 2, "同一句但带了照片：照常发")


class PostVarietyTests(unittest.TestCase):
    def test_different_pets_at_the_same_place_do_not_all_say_the_same_thing(self) -> None:
        texts = {visit_post_text(work=False, title="散步", place="家附近的星球小路", extra="", seed=f"PJ-{n:08d}:jn-a{n}:visit_ended")
                 for n in range(8)}
        self.assertGreaterEqual(len(texts), 3, "8 只宠物去同一个地方，至少要有 3 种说法")
        self.assertTrue(all("家附近的星球小路" in t for t in texts), "地点照实写")

    def test_the_same_visit_always_reads_the_same(self) -> None:
        seed = "PJ-12345678:jn-abc:visit_ended"
        self.assertEqual(visit_post_text(work=True, title="在花店帮忙", place="花店", extra="", seed=seed),
                         visit_post_text(work=True, title="在花店帮忙", place="花店", extra="", seed=seed), "重放同一件事不换说法")

    def test_no_line_invents_weather_or_crowds(self) -> None:
        for line in VISIT_LINES + WORK_LINES:
            with self.subTest(line=line):
                for invented in ("风", "天气", "人多", "人少", "晴", "雨"):
                    self.assertNotIn(invented, line, "只说去了哪里、做了什么，不补没核实的细节")


if __name__ == "__main__":
    unittest.main()
