"""TA 在外面遇到的朋友：真实宠物要同一时间同一地点才算遇到；拉黑的不相遇；星球居民明确标注。"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class FriendTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.web.friends.roll = lambda *parts: 0.99  # 默认不认识星球居民，单测真实相遇
        self.a = self.user("friend-a")
        self.a.adopt_and_move_in("adopt-lan")
        self.b = self.user("friend-b")
        self.b.adopt_and_move_in("adopt-pudding")

    def both_go_to_the_cafe(self) -> None:
        self.a.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=1)
        self.b.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)  # 两只都在店里
        self.a.get("/journey/map")
        self.b.get("/journey/map")
        self.run_background()  # 相遇与新鲜事由任务进程投递（slow 通道，可能调模型）

    def news(self, owner) -> list[str]:
        return [m["text"] for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if m.get("topic") == "news"]

    def test_pets_at_the_same_place_at_the_same_time_become_friends(self) -> None:
        self.both_go_to_the_cafe()
        friends_a, friends_b = self.a.get("/friends").json(), self.b.get("/friends").json()
        self.assertEqual([(f["kind"], f["friend_id"], f["closeness"]) for f in friends_a], [("pet", self.b.pet_id, "初识")])
        self.assertEqual([f["friend_id"] for f in friends_b], [self.a.pet_id])
        self.assertTrue(any("遇到了" in t for t in self.news(self.a)))
        self.assertTrue(any("遇到了" in t for t in self.news(self.b)))

    def test_no_meeting_when_blocked_or_owner_keeps_things_private(self) -> None:
        with self.app.state.storage.connect() as conn:
            conn.execute("INSERT INTO web_blocks (user_id, blocked_user_id, created_at) VALUES (?, ?, ?)", (self.b.user_id, self.a.user_id, "2026-09-22T00:00:00+00:00"))
        self.both_go_to_the_cafe()
        self.assertEqual(self.a.get("/friends").json(), [])

    def test_planet_residents_are_clearly_residents(self) -> None:
        self.web.friends.roll = lambda *parts: 0.0
        self.a.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        self.a.get("/journey/map")
        self.run_background()
        friends = self.a.get("/friends").json()
        self.assertEqual([f["kind"] for f in friends], ["resident"])
        self.assertTrue(any("星球居民" in t for t in self.news(self.a)))


if __name__ == "__main__":
    unittest.main()
