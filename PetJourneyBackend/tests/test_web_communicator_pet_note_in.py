"""`pet_note_in`：TA 的一条消息写进家庭频道，或写进某位家人和 TA 的私聊（到站自拍用；A 的 web_communicator）。不联网、0 次付费调用。

钉的是：
  - 不给 user_id：家庭频道、user_id='*'、带 household_id——与泛化前同义（到站原来就这样发）；
  - 给某位家人：进这位家人的私聊（channel='private'、household_id 为空），**不进家庭频道**；
  - 这位家人已被移出家庭：不写，返回 False（同一事务里复核）；
  - 同一件事只写一次；
  - 只跳过重复：NOT NULL 违例当场报错，不像 INSERT OR IGNORE 那样悄悄不写、调用方还以为「已经发过」；
  - 带着没画完的照片：显示 processing。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from task_budget_helpers import open_storage

from app.utils import utcnow
from app.web_communicator.service import FAMILY, WebCommunicatorService
from app.web_platform.uow import unit_of_work

STAMP = "2026-09-24T05:00:00+00:00"


class PetNoteInTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "notes.sqlite3"))
        self.communicator = WebCommunicatorService(self.storage)
        with self.storage.connect() as conn:  # 外键是开着的（repositories/base.py:40）：先造用户、宠物、家庭
            for user_id in ("user-1", "user-gone"):
                conn.execute("INSERT INTO users (user_id, created_at) VALUES (?, ?)", (user_id, STAMP))
            conn.execute("INSERT INTO pets (pet_id, name, pet_type, dna_json, created_at) VALUES ('pet-1', '年糕', 'cat', '{}', ?)", (STAMP,))
            conn.execute("INSERT INTO web_households (household_id, created_by, created_at) VALUES ('hh-1', 'user-1', ?)", (STAMP,))
            conn.execute("INSERT INTO web_household_pets (pet_id, household_id, joined_at, via) VALUES ('pet-1', 'hh-1', ?, 'adoption')", (STAMP,))
            for user_id, status in (("user-1", "active"), ("user-gone", "removed")):
                conn.execute("INSERT INTO web_household_members (household_id, user_id, role, status, joined_at) VALUES ('hh-1', ?, 'caregiver', ?, ?)",
                             (user_id, status, STAMP))

    def note(self, **overrides) -> bool:
        kwargs = {"pet_id": "pet-1", "household_id": "hh-1", "text": "我到新家啦", "dedupe_key": "arrival:pet-1", "now": utcnow()}
        kwargs.update(overrides)
        with unit_of_work(self.storage) as conn:
            return self.communicator.pet_note_in(conn, **kwargs)

    def rows(self) -> list[dict]:
        with self.storage.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT user_id, channel, household_id, sender, photo_status FROM web_messages")]

    def test_without_a_member_it_is_the_family_channel_as_before(self) -> None:
        self.assertTrue(self.note())
        self.assertEqual(self.rows(), [{"user_id": FAMILY, "channel": "family", "household_id": "hh-1", "sender": "pet", "photo_status": None}])

    def test_with_a_member_it_goes_to_that_private_thread_only(self) -> None:
        self.assertTrue(self.note(user_id="user-1"))
        self.assertEqual(self.rows(), [{"user_id": "user-1", "channel": "private", "household_id": None, "sender": "pet", "photo_status": None}])

    def test_a_member_who_left_gets_nothing(self) -> None:
        self.assertFalse(self.note(user_id="user-gone"))
        self.assertEqual(self.rows(), [])

    def test_the_same_thing_is_written_once(self) -> None:
        self.assertTrue(self.note(user_id="user-1"))
        self.assertFalse(self.note(user_id="user-1"))
        self.assertEqual(len(self.rows()), 1)

    def test_a_broken_row_fails_loudly_instead_of_vanishing(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.note(user_id="user-1", text=None)
        self.assertEqual(self.rows(), [])

    def test_a_photo_still_being_drawn_shows_as_processing(self) -> None:
        self.assertTrue(self.note(user_id="user-1", photo_task_id="wt-not-done"))
        self.assertEqual(self.rows()[0]["photo_status"], "processing")


if __name__ == "__main__":
    unittest.main()
