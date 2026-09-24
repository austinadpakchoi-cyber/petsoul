"""第十一批：撤下 / 放回待领养居民（用户 2026-09-25 交给运营后台）；旅行手账的配图（A 转来）。

撤下只动领养卡表的上架列（迁移 0260，玩家侧的整体用例在 test_web_resident_listing.py），后台这一侧记依据（迁移 1590）、写审计、清访客页缓存。
新权限「撤下 / 放回待领养居民」默认给内容发布（与平台负责人）；运维、客服、内容编辑没有。
"""

from __future__ import annotations

import json
import unittest

from admin_base import AdminTestBase
from web_base import PREFIX

from app.utils import iso, utcnow
from app.web_admin import labels as L


class ResidentListingAdminTests(AdminTestBase):
    def publisher(self):
        staff = self.staff("listing-publisher", ["content_publisher"])
        staff.login_ok()
        return staff

    def available_row(self, staff) -> dict:
        rows = [r for r in staff.get("/residents").json()["residents"] if r["status"] == "resident" and r["availability"] == "available"]
        self.assertTrue(rows, "前提：测试库里有还可以领养的驿站居民")
        return rows[0]

    def visitor_list(self) -> set[str]:
        return {r["pet_id"] for r in self.client.get(f"{PREFIX}/public/residents").json()}

    def test_publisher_delists_and_relists_with_reason_version_replay_and_audit(self):
        publisher = self.publisher()
        body = publisher.get("/residents").json()
        row = self.available_row(publisher)
        cid, pet_id = row["candidate_id"], row["pet_id"]
        self.assertEqual((row["listed"], row["listing"]), (True, None), "从没撤下过：在名单上、没有后台记录")
        self.assertTrue(body["listing_effects"]["delist"] and body["listing_effects"]["relist"], "对话框的影响说明由接口给")
        self.assertIn(pet_id, self.visitor_list(), "对照：撤下前访客页有 TA（这一读也把访客页缓存填上了）")

        path = f"/residents/{cid}/listing"
        first = publisher.post(path, {"listed": False, "reason": "档案要重写，先从领养名单撤下", "expected_version": 0}, key="list-op-1")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual((first.json()["listed"], first.json()["version"]), (False, 1))
        self.assertNotIn(pet_id, self.visitor_list(), "访客页当场更新：缓存由接口清掉，不等 30 秒")

        replay = publisher.post(path, {"listed": False, "reason": "档案要重写，先从领养名单撤下", "expected_version": 0}, key="list-op-1")
        self.assertEqual((replay.status_code, replay.json()["version"]), (200, 1), "同一操作号重放：拿回同一个结果，不再执行一次")
        self.assert_admin_error(publisher.post(path, {"listed": False, "reason": "再撤一次试试", "expected_version": 1}), 409, "CONFLICT")
        self.assert_admin_error(publisher.post(path, {"listed": True, "reason": "别人先改过了", "expected_version": 0}), 409, "VERSION_CONFLICT")

        listed_row = next(r for r in publisher.get("/residents").json()["residents"] if r["candidate_id"] == cid)
        self.assertEqual(listed_row["listed"], False)
        self.assertEqual((listed_row["listing"]["reason"], listed_row["listing"]["version"]), ("档案要重写，先从领养名单撤下", 1))
        self.assertTrue(listed_row["listing"]["changed_by"], "记下是谁撤下的")

        back = publisher.post(path, {"listed": True, "reason": "新档案发布了，放回领养名单", "expected_version": 1})
        self.assertEqual((back.status_code, back.json()["listed"], back.json()["version"]), (200, True, 2), back.text)
        self.assertIn(pet_id, self.visitor_list(), "放回后访客页当场出现")

        owner = self.owner()
        delists = owner.get("/audit?action=resident.delist").json()["entries"]
        relists = owner.get("/audit?action=resident.relist").json()["entries"]
        self.assertEqual([e["reason"] for e in delists if e["status"] == "succeeded"], ["档案要重写，先从领养名单撤下"],
                         "重放不多记一条成功")
        self.assertEqual([e["reason"] for e in relists if e["status"] == "succeeded"], ["新档案发布了，放回领养名单"])
        self.assertEqual(L.AUDIT_ACTION["resident.delist"], "撤下待领养居民")

    def test_an_adopted_resident_cannot_be_delisted(self):
        publisher = self.publisher()
        cid = self.available_row(publisher)["candidate_id"]
        self.user("listing-adopter").adopt_and_move_in(cid)
        refused = self.assert_admin_error(publisher.post(f"/residents/{cid}/listing", {"listed": False, "reason": "想撤下已被领养的"}), 409, "CONFLICT")
        self.assertIn("身份与经历必须连续", refused["error"]["message"])
        self.assert_admin_error(publisher.post("/residents/no-such-candidate/listing", {"listed": False, "reason": "撤下不存在的"}), 404, "NOT_FOUND")

    def test_only_the_new_permission_may_delist_and_a_reason_is_required(self):
        publisher = self.publisher()
        cid = self.available_row(publisher)["candidate_id"]
        for name, roles in (("listing-sre", ["sre"]), ("listing-support", ["support"]), ("listing-editor", ["content_editor"])):
            staff = self.staff(name, roles)
            staff.login_ok()
            self.assert_admin_error(staff.post(f"/residents/{cid}/listing", {"listed": False, "reason": "没有权限也想撤下"}), 403, "FORBIDDEN")
        short = publisher.post(f"/residents/{cid}/listing", {"listed": False, "reason": "撤"})
        self.assertEqual(short.status_code, 422, short.text)
        self.assertIn("resident.manage", L.PERMISSION)


class TravelJournalSurfaceTests(AdminTestBase):
    """A 的旅行手账（web_travel_journals）接进「照片用在哪里」：同一张图被计划页与回忆页共用，照列不去重；只给种类、页面与时间。"""

    def test_a_shared_journal_image_is_listed_once_per_page(self):
        from app.web_admin.diagnosis import _surfaces

        now = iso(utcnow())
        with self.app.state.storage.connect() as conn:
            for revision, phase in ((1, "plan"), (2, "memory")):
                conn.execute(
                    "INSERT INTO web_travel_journals (journal_id, journal_revision, plan_id, plan_revision, visual_digest, phase, event_ids_json, "
                    "template_revision, brief_version, identity_mode, identity_note, reference_revision, image_task_id, layout_json, digest, "
                    "created_at, updated_at) VALUES ('jr-1', ?, 'plan-1', 1, 'vd', ?, '[]', 't1', 'b1', 'none', NULL, NULL, 'task-journal-1', "
                    "'{}', 'dg', ?, ?)", (revision, phase, now, now))
            conn.commit()
            surfaces = _surfaces(conn, "task-journal-1")
        self.assertEqual([(s["kind"], s["phase"], s["ref"]) for s in surfaces],
                         [("travel_journal", "plan", "jr-1#1"), ("travel_journal", "memory", "jr-1#2")])
        self.assertNotIn("layout", json.dumps(surfaces, default=str), "只给种类、页面与时间，不给手账内容")
        self.assertEqual({L.PHOTO_SURFACE["travel_journal"], L.JOURNAL_PHASE["plan"], L.JOURNAL_PHASE["memory"]},
                         {"旅行手账的配图", "计划页", "回忆页"})


if __name__ == "__main__":
    unittest.main()
