"""DNA 行为画像：同一份 DNA 决定说话方式，也决定作息、出门频率、路线兴趣与工作倾向（对齐说明 §2）。"""

from __future__ import annotations

import unittest
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

from app.web_agent.life import choose
from app.web_agent.profile import derive_profile
from web_base import FakeClock, WebPlatformTestBase

HK = timezone(timedelta(hours=8))


class ProfileUnitTests(unittest.TestCase):
    def test_sleep_rhythm_follows_dna(self) -> None:
        owl = derive_profile("活泼，爱熬夜看窗外")
        self.assertEqual((owl.sleep_start, owl.wake, owl.night_owl), (time(1, 30), time(9, 30), True))
        early = derive_profile("每天早起叫我")
        self.assertEqual((early.sleep_start, early.wake), (time(22, 0), time(6, 0)))
        self.assertEqual((derive_profile("温和").sleep_start, derive_profile("温和").wake), (time(23, 30), time(7, 30)))

    def test_outings_routes_and_jobs_follow_dna(self) -> None:
        homebody = derive_profile("恋家、慢热")
        social = derive_profile("爱热闹、好奇")
        self.assertEqual((homebody.outings_per_day, social.outings_per_day), (1, 3))
        self.assertGreater(homebody.route_interest["local:stroll"], 1)
        self.assertLess(homebody.route_interest["long"], 1)
        self.assertGreater(social.route_interest["local:city_trip"], 1)
        reader = derive_profile("安静，最喜欢趴在书堆里")
        self.assertEqual(reader.job_affinity.get("bookstore"), 2.0)

    def test_job_affinity_changes_which_work_the_pet_picks(self) -> None:
        options = [SimpleNamespace(destination_key=k, fee=0) for k in ("work:bookstore", "work:cafe_helper", "work:florist", "work:post_office")]
        picks = [choose(options, 5, "steady", suggested=set(), worked_today=False, long_trip_ok=set(), roll=r / 200,
                        job_affinity={"bookstore": 4.0}) for r in range(200)]
        self.assertGreater(picks.count("work:bookstore"), 90, "喜欢书的更常去书店")


class ScheduleIntegrationTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(datetime(2026, 9, 23, 0, 40, tzinfo=HK).astimezone(timezone.utc)).install(self)

    def test_night_owl_is_awake_after_midnight_while_others_sleep(self) -> None:
        owl = self.user("owl-pet")
        owl.adopt_and_move_in("adopt-lan")
        owl.put(f"/pets/{owl.pet_id}/dna", {"personality": "爱熬夜的夜猫子"})
        sleeper = self.user("sleep-pet")
        sleeper.adopt_and_move_in("adopt-pudding")
        now = self.clock.now
        self.assertFalse(self.web.moments.build(owl.pet_id, now).asleep, "夜猫子凌晨还醒着")
        self.assertTrue(self.web.moments.build(sleeper.pet_id, now).asleep)
        sent = owl.post(f"/communicator/{owl.pet_id}/messages", {"client_message_id": "owl-night-1", "text": "还没睡？"}).json()
        self.assertIsNone(sent["status_note"], "醒着就很快回")
        waiting = sleeper.post(f"/communicator/{sleeper.pet_id}/messages", {"client_message_id": "sleep-night-1", "text": "还没睡？"}).json()
        self.assertEqual(waiting["status_note"], "TA 睡着啦，醒来会看到。")


if __name__ == "__main__":
    unittest.main()
