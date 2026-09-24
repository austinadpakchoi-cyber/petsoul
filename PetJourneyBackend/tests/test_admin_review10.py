"""第十批：按 c84a 的后台审查意见（docs/coordination/CR-ADMIN-RELAY-COST-2026-09-24.md）优化。

ADM-HEALTH-02：执行者状态按运行配置判——按配置关着不是故障；应该在跑却心跳过期（或根本没登记）才报失联。
正反例照审查意见：off＋过期租约＝配置关闭；开着＋过期租约＝仍报失联，不能一律掩盖。系统运行、运营首页、宠物运行三处同一口径。
"""

from __future__ import annotations

import os
import unittest
from datetime import timedelta
from unittest import mock

from admin_base import AdminTestBase

from app.utils import iso, utcnow
from app.web_admin import labels as L
from app.web_admin.lanes import lane_state, runner_configured


class LaneStateRuleTests(unittest.TestCase):
    def test_configuration_decides_before_the_lease(self):
        self.assertFalse(runner_configured("off", 30))
        self.assertFalse(runner_configured("embedded", 0), "每轮间隔 ≤ 0 也是不跑")
        self.assertTrue(runner_configured("embedded", 30))
        self.assertTrue(runner_configured("worker", 30), "交给独立进程跑也是「该在跑」")
        self.assertEqual(lane_state(False, False), "configured_off")
        self.assertEqual(lane_state(False, True), "configured_off")
        self.assertEqual(lane_state(True, True), "healthy")
        self.assertEqual(lane_state(True, False), "lost")


class LaneStateApiTests(AdminTestBase):
    def lease(self, name: str, *, alive: bool) -> None:
        now = utcnow()
        expires = now + timedelta(minutes=5) if alive else now - timedelta(minutes=30)
        with self.app.state.storage.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO web_worker_leases (name, holder, pid, host, role, started_at, heartbeat_at, expires_at, "
                         "last_tick_at, last_ok_at, last_error, ticks) VALUES (?, 'test', 1, 'test-host', 'embedded', ?, ?, ?, ?, ?, NULL, 3)",
                         (name, iso(now - timedelta(hours=1)), iso(expires - timedelta(minutes=3)), iso(expires),
                          iso(expires - timedelta(minutes=3)), iso(expires - timedelta(minutes=3))))
            conn.commit()

    def states(self) -> tuple[dict, dict, dict, dict]:
        owner = self.owner()
        system = {w["name"]: w for w in owner.get("/system").json()["workers"]}
        overview = owner.get("/overview").json()
        lanes = overview["runtime"]["lanes"]
        modes = owner.get("/pets-runtime").json()["modes"]
        late = next(m for m in overview["metrics"] if m["key"] == "pets.heartbeat_late")
        return system, lanes, modes, late

    def test_configured_off_with_an_old_lease_is_not_a_fault(self):
        self.app.state.settings.web_world_runner = "off"
        self.lease("world", alive=False)
        system, lanes, modes, late = self.states()
        self.assertEqual((system["world"]["state"], system["world"]["registered"]), ("configured_off", True),
                         "按配置关着：旧心跳保留供查询，但不是故障")
        self.assertEqual((system["cognition"]["state"], system["cognition"]["registered"]), ("configured_off", False),
                         "没登记的那条线也列出来")
        self.assertEqual(lanes["world"]["state"], "configured_off")
        self.assertEqual((modes["world_state"], modes["world_configured"]), ("configured_off", False))
        self.assertIsNone(late["value"])
        self.assertIn("按配置关着", late["note"])

    def test_configured_on_with_an_expired_lease_is_still_reported(self):
        self.app.state.settings.web_world_runner = "embedded"
        self.lease("world", alive=False)
        system, lanes, modes, late = self.states()
        self.assertEqual(system["world"]["state"], "lost", "开着＋过期租约：照样报失联，不能因为「可能是有意关的」就掩盖")
        self.assertEqual((system["cognition"]["state"], system["cognition"]["registered"]), ("lost", False), "该在跑却从没登记：失联")
        self.assertEqual((lanes["world"]["state"], modes["world_state"]), ("lost", "lost"))
        self.assertIsInstance(late["value"], int, "该跑的时候照样算「心跳过点」——那正是要暴露的故障")

    def test_configured_on_with_a_live_lease_is_healthy(self):
        self.app.state.settings.web_world_runner = "worker"
        self.lease("world", alive=True)
        self.lease("cognition", alive=True)
        system, lanes, modes, _ = self.states()
        self.assertEqual({w["state"] for w in system.values()}, {"healthy"})
        self.assertEqual((lanes["cognition"]["state"], modes["cognition_state"]), ("healthy", "healthy"))


class RelayReceiptTests(AdminTestBase):
    """ADM-COST-01：逐次回执的幂等导入与四块汇总。数据是用例里手写的合成回执（不是任何真实调用），只为验规则。"""

    CLIENTS = {"PETSOUL_ADMIN_RELAY_CLIENTS": "petsoul-image-local"}

    def receipt(self, event: str, **overrides) -> dict:
        base = {"relay_instance": "relay-local", "relay_event_id": event, "client_id": "petsoul-image-local", "project_id": "petsoul",
                "environment": "local", "purpose": "illustration", "provider": "image", "endpoint": "/v1/images/generations",
                "requested_model": "image-model-test", "started_at_utc": "2026-09-24T01:00:00+00:00",
                "completed_at_utc": "2026-09-24T01:00:20+00:00", "http_status": 200, "dispatch_outcome": "succeeded",
                "input_text_tokens": 120, "output_tokens": 0, "images_returned": 1, "usage_present": True, "usage_source": "response",
                "cost_state": "unpriced"}
        base.update(overrides)
        return base

    def test_import_is_closed_until_a_petsoul_client_is_configured(self):
        owner = self.owner()
        with mock.patch.dict(os.environ, {"PETSOUL_ADMIN_RELAY_CLIENTS": ""}):
            refused = owner.post("/costs/relay-receipts/import", {"records": [self.receipt("e1")], "source_note": "测试导入回执"})
            self.assert_admin_error(refused, 503, "NOT_CONFIGURED")
            self.assertIn("okeymind", refused.json()["error"]["message"], "写明为什么不给默认白名单")
            body = owner.get("/costs/consumption").json()
        self.assertFalse(body["capability"]["enabled"])
        self.assertEqual((body["sync"]["receipts"], body["days"]), (0, []), "没接入就是空的，不造数")

    def test_idempotent_import_whitelist_conflicts_and_four_blocks(self):
        owner = self.owner()
        records = [self.receipt("e1", cost_state="estimated", estimated_amount="0.04", currency="usd", price_version="relay-price-v1"),
                   self.receipt("e2", client_id="okeymind"),
                   self.receipt("e3", dispatch_outcome="maybe"),
                   self.receipt("e4", dispatch_outcome="unknown", usage_present=False, cost_state="unknown", images_returned=None)]
        with mock.patch.dict(os.environ, self.CLIENTS):
            first = owner.post("/costs/relay-receipts/import", {"records": records, "source_note": "导入本地中转回执（测试）"}).json()
            second = owner.post("/costs/relay-receipts/import", {"records": records, "source_note": "同一批再导一次"}).json()
            changed = owner.post("/costs/relay-receipts/import",
                                 {"records": [dict(records[0], output_tokens=999)], "source_note": "同号内容变了"}).json()
            body = owner.get("/costs/consumption").json()
        self.assertEqual((first["inserted"], first["rejected"]), (2, 2), "okeymind 的与不合规的都拒收")
        self.assertEqual((second["inserted"], second["duplicates"], second["rejected"]), (0, 2, 2), "同一批再导一次：一条都不多记")
        self.assertEqual((changed["inserted"], changed["conflicts"]), (0, 1), "同号内容变了：记成冲突")
        with self.app.state.storage.connect() as conn:
            kept = conn.execute("SELECT output_tokens FROM admin_relay_receipts WHERE relay_event_id = 'e1'").fetchone()["output_tokens"]
            reasons = [r["reason"] for r in conn.execute("SELECT reason FROM admin_relay_import_issues WHERE kind = 'rejected'")]
        self.assertEqual(kept, 0, "冲突不覆盖原来的回执")
        self.assertTrue(any("okeymind" in r for r in reasons) and any("dispatch_outcome" in r for r in reasons), reasons)
        sync = body["sync"]
        self.assertEqual((sync["receipts"], sync["unattributed"], sync["unpriced"], sync["unknown_outcome"], sync["no_usage"], sync["conflicts"]),
                         (2, 2, 1, 1, 1, 1))
        day = body["days"][0]
        self.assertEqual(day["estimated"], {"USD": "0.04"}, "只有带价格版本的才算估算，币种分开")
        self.assertEqual((day["unpriced"], day["billed"], day["unbilled"], day["pending"]), (1, {}, 2, 1), "没有账单就是未知，不补 0")
        self.assertEqual((day["measured"]["dispatches"], day["measured"]["succeeded"], day["measured"]["images"]), (2, 1, 1))
        self.assertFalse(day["model_confirmed"], "只有请求时写的模型：标成没确认，不冒充供应商确认的")
        self.assertEqual(len(owner.get("/audit?action=cost.relay_import").json()["entries"]), 3)

    def test_attribution_follows_the_operation_id_only(self):
        from app.web_platform.budget import BudgetLedger, BudgetLimit

        BudgetLedger(self.app.state.storage).reserve("op-relay-1", provider="image", purpose="illustration",
                                                    limits=[BudgetLimit("provider:image:daily", 100)])
        owner = self.owner()
        with mock.patch.dict(os.environ, self.CLIENTS):
            owner.post("/costs/relay-receipts/import", {"records": [self.receipt("a1", operation_id="op-relay-1"), self.receipt("a2", operation_id="op-none")],
                                                        "source_note": "按操作号对账"})
            body = owner.get("/costs/consumption").json()
        self.assertEqual(body["sync"]["unattributed"], 1, "对上额度账操作号的才算已归属；对不上的单列，不凭时间猜")

    def test_reading_and_importing_are_separate_permissions(self):
        sre = self.staff("relay-sre", ["sre"])  # provider.read，没有 cost.manage
        sre.login_ok()
        with mock.patch.dict(os.environ, self.CLIENTS):
            self.assertEqual(sre.get("/costs/consumption").status_code, 200)
            self.assert_admin_error(sre.post("/costs/relay-receipts/import", {"records": [self.receipt("p1")], "source_note": "运维想导入"}),
                                    403, "FORBIDDEN")
        support = self.staff("relay-support", ["support"])
        support.login_ok()
        self.assert_admin_error(support.get("/costs/consumption"), 403, "FORBIDDEN")


class ResidentEntryTests(AdminTestBase):
    """ADM-RESIDENT-04：居民名单带出这位居民在「内容发布」里已建的档案内容，居民页的「编辑档案」直接去那一条。"""

    def test_the_list_links_each_resident_to_its_content_item(self):
        editor = self.staff("entry-editor", ["content_editor"])
        editor.login_ok()
        created = editor.post("/content", {"content_type": "resident", "slug": "adopt-lan", "title": "小岚的文案",
                                           "body": {"personality": "慢热", "dream": "看海"}})
        self.assertEqual(created.status_code, 201, created.text)
        rows = {r["candidate_id"]: r for r in editor.get("/residents").json()["residents"]}
        item = rows["adopt-lan"]["content_item"]
        self.assertEqual((item["item_id"], item["status"], item["live_revision"]), (created.json()["item"]["item_id"], "draft", None))
        self.assertTrue(all(r["content_item"] is None for key, r in rows.items() if key != "adopt-lan"), "没建过的就是 null")


class IdPhotoAdminTests(AdminTestBase):
    """A 的证件照（CR-6C2B-IDPHOTO）接进后台：真实上传流程 ＋ 假生图服务（0 次付费调用）造一张没通过校验的证件照，
    看宠物页、系统运行的任务线、每天生成多少照片三处都认得它，且不给任何文件路径。"""

    def test_a_refused_id_photo_is_visible_in_plain_words_everywhere(self):
        import json

        from character_fakes import transparent_png
        from id_photo_chain_base import IdPhotoIllustrator
        from web_base import LUNCH_UTC, FakeClock, tiny_png

        from app.web_admin import labels as L

        FakeClock(LUNCH_UTC).install(self)
        owner = self.user("idp-owner")
        self.web.character.illustrator = IdPhotoIllustrator(photo=transparent_png(96, 144))  # 拍成了全身：胸口没到底
        self.web.character.transparency_requested = True
        first = owner.upload_pet("先建家", "cat", photo=None)
        household_id = self.web.households.memberships(owner.user_id)[0].household_id
        created = owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=household_id)
        self.assertEqual((first.status_code, created.status_code), (201, 201), created.text)
        pet_id = created.json()["pet_id"]
        self.web.character.id_photo.run_pending()

        support = self.staff("idp-support", ["support"])
        support.login_ok()
        body = support.get(f"/pets/{pet_id}/belongings").json()
        photo = body["character"]["id_photo"]
        self.assertIsNone(photo["active"], "没通过校验就没有生效的证件照")
        self.assertEqual([(t["revision"], t["state"], t["reason"]) for t in photo["takes"]], [(1, "failed", "photo_not_to_bottom")])
        self.assertIn("头和上半身", L.CHARACTER_REASON["photo_not_to_bottom"])
        raw = json.dumps(body["character"], ensure_ascii=False)
        self.assertNotIn("rel_path", raw)
        self.assertNotIn(".png", raw, "只给状态，不给任何文件路径")

        owner_staff = self.owner()
        tasks = owner_staff.get("/system").json()["tasks"]
        self.assertIn(("pet_id_photo", "failed"), {(r["kind"], r["status"]) for r in tasks["counts"]})
        self.assertEqual({r["kind"] for r in tasks["counts"]} - set(L.TASK_KIND), set(), "任务线上的每种任务都有说法")
        failure = next(r for r in tasks["recent_failures"] if r["kind"] == "pet_id_photo")
        self.assertIn("头和上半身", L.error_label(failure["last_error"]), failure["last_error"])

        images = owner_staff.get("/usage/images-daily").json()
        self.assertIn("id_photo", images["purposes"], "证件照一列总在")
        today = next(d for d in images["days"] if d["day"] == images["today"])
        self.assertEqual(today["purposes"]["id_photo"]["calls"], 1, "发出去画了一张（假供应商），按一次调用记")


class GapSweepTests(AdminTestBase):
    """只读排查找到的缺口：死信投递、AI 思考的退避原因、藏品照片的用途、驾照还没签发、公告链接。都走真实的领域写入口。"""

    def test_dead_letters_are_counted_and_listed_on_the_system_page(self):
        from datetime import timedelta

        from app.web_platform.outbox import MAX_ATTEMPTS, Outbox

        outbox = Outbox(self.app.state.storage)
        now = utcnow()
        with self.app.state.storage.connect() as conn:
            outbox.add_in(conn, event_id="ev-dead-1", aggregate_id="agg-dead", kind="test.dead", effective_at=now,
                          payload={"secret": "不该出现在后台"}, consumers=["collection"], now=now)
            conn.commit()
        for attempt in range(MAX_ATTEMPTS):
            at = now + timedelta(hours=attempt + 1)
            [item] = outbox.claim(["collection"], at)
            outbox.failed(item, "下游一直报错", at)
        body = self.owner().get("/system").json()["outbox"]
        collection = next(c for c in body["consumers"] if c["consumer"] == "collection")
        self.assertEqual((collection["dead_letter"], collection["pending"], body["dead_total"]), (1, 0, 1),
                         "试满次数的那条单独数成死信，不再混进「其他」看不见")
        self.assertEqual((body["dead"][0]["attempts"], body["dead"][0]["last_error"]), (MAX_ATTEMPTS, "下游一直报错"))
        self.assertNotIn("不该出现在后台", str(body), "只给种类与错误，不给投递内容")
        self.assertIn("dead_letter", L.OUTBOX_STATUS)

    def test_brain_backoff_reasons_read_as_plain_words(self):
        user = self.user("gap-brain")
        user.adopt_and_move_in("adopt-lan")
        runtime = self.app.state.web.projector.runtime
        now = utcnow()
        runtime.record_backoff(user.pet_id, now, review_at=now + timedelta(minutes=10), reason="brain:timeout")
        rows = {r["pet_id"]: r for r in self.owner().get("/pets-runtime").json()["pets"]}
        heartbeat = rows[user.pet_id]["heartbeat"]
        self.assertEqual((heartbeat["silence_reason"], heartbeat["silence_label"]), ("brain:timeout", "AI 思考：模型超时没回"))

    def test_keepsake_photos_are_not_called_unused(self):
        from app.web_admin.diagnosis import _surfaces

        user = self.user("gap-keepsake")
        user.adopt_and_move_in("adopt-lan")
        collection = self.app.state.web.collection
        with self.app.state.storage.connect() as conn:
            collection._grant(conn, user_id=user.user_id, pet_id=user.pet_id, kind="license_photo", item_key=None, title="领证合影",
                              tradable=False, bound=True, source_event_id="license:test", now=utcnow())
            conn.commit()
        collection.attach_image(user.pet_id, "license_photo", "license:test", "task-keepsake-1")
        with self.app.state.storage.connect() as conn:
            [surface] = _surfaces(conn, "task-keepsake-1")
        self.assertEqual((surface["kind"], surface["item_kind"]), ("keepsake", "license_photo"),
                         "领证合影是藏品里的照片，不能说成「没找到用在哪里」")
        self.assertIn(surface["kind"], L.PHOTO_SURFACE)

    def test_a_licensed_row_without_a_licence_reads_as_pending(self):
        user = self.user("gap-driver")
        user.adopt_and_move_in("adopt-lan")
        now = iso(utcnow())
        with self.app.state.storage.connect() as conn:  # 旧版留下的形状：记成考过了、却没有驾驶证（与 web_driving 的写法相同）
            conn.execute("INSERT INTO web_driving (pet_id, user_id, stage, licensed_at, mastery_json, updated_at) VALUES (?, ?, 'licensed', ?, '{}', ?)",
                         (user.pet_id, user.user_id, now, now))
            conn.commit()
        support = self.staff("gap-support", ["support"])
        support.login_ok()
        driving = support.get(f"/pets/{user.pet_id}/belongings").json()["driving"]
        self.assertEqual(driving["stage"], "license_pending", "与玩家那一侧同一个判断，不说成「拿到驾照」")
        self.assertEqual(self.app.state.web.driving.stage(user.pet_id), "license_pending")

    def test_announcement_links_must_stay_on_this_site(self):
        editor = self.staff("gap-editor", ["content_editor"])
        editor.login_ok()
        base = {"title": "维护通知", "body": "今晚维护", "severity": "notice", "audience": "all"}
        backslash = chr(92)
        for link in ("//evil.example/x", "/" + backslash + "evil.example", "/a b", "/a" + chr(1), "https://evil.example"):
            issues = editor.post("/content/validate", {"content_type": "announcement", "slug": "gap-link", "title": "链接校验",
                                                       "body": {**base, "link": link}}).json()["issues"]
            self.assertEqual([i["field"] for i in issues], ["link"], f"{link!r} 会跳到别的网站或带着看不见的字符，要拒绝")
        for link in ("/", "/communicator", "/announcements?from=notice"):
            issues = editor.post("/content/validate", {"content_type": "announcement", "slug": "gap-link", "title": "链接校验",
                                                       "body": {**base, "link": link}}).json()["issues"]
            self.assertEqual(issues, [], link)


if __name__ == "__main__":
    unittest.main()
