"""I 的接入围栏：任务被接管后，旧领取的外部调用结果整批作废——插画记录、家庭来信里的图都不改；新领取的结果与任务完成一起提交。"""

from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone

from app.schemas.runtime_internal import StaleClaim
from app.web_providers import WebProviders
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat, FakeIllustrator

HK_2AM = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)  # 香港 02:00：默认作息里 TA 在睡觉，私聊进待回复队列


class CrashingChat(FakeChat):
    def complete(self, messages, **kwargs):
        raise SystemExit("领取之后、回复之前进程被杀")


class BlockingChat(FakeChat):
    """第一次调用挂住，直到放行（模拟旧 worker 卡在模型上）。"""

    def __init__(self) -> None:
        super().__init__(["旧 worker 晚到的回复"])
        self.entered, self.release = threading.Event(), threading.Event()

    def complete(self, messages, **kwargs):
        self.entered.set()
        self.release.wait(timeout=30)
        return super().complete(messages, **kwargs)


class IllustrationFenceTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        web = self.web
        web.providers = WebProviders(enabled=True, chat=web.providers.chat, geo=None, illustrator=self.illustrator, meter=None)
        web.illustrations.illustrator = self.illustrator
        self.owner = self.user("fence-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})

    def row(self, query: str, params: tuple):
        with self.app.state.storage.connect() as conn:
            return conn.execute(query, params).fetchone()

    def test_a_taken_over_worker_cannot_publish_its_late_image(self) -> None:
        illustrations = self.web.illustrations
        queue = illustrations.tasks
        task_id = illustrations.request_image(self.owner.user_id, self.owner.pet_id, "fence:selfie", style="selfie", place="码头", city="香港", scene="坐着")
        self.assertIsNotNone(task_id)
        with self.app.state.storage.connect() as conn:  # 一条等着这张图的家庭来信
            conn.execute("INSERT INTO web_messages (message_id, user_id, pet_id, sender, text, created_at, available_at, composed_by, photo_status, photo_task_id, channel) "
                         "VALUES ('msg-fence', '*', ?, 'pet', '拍了张照片', ?, ?, 'event', 'processing', ?, 'family')",
                         (self.owner.pet_id, self.clock.now.isoformat(), self.clock.now.isoformat(), task_id))
        old = queue.claim_next("worker-old", ["illustration"], lease_seconds=60)
        self.clock.advance(minutes=5)  # 旧 worker 卡在生图上，租期过了，被新 worker 接管
        new = queue.claim_next("worker-new", ["illustration"], lease_seconds=60)
        self.assertEqual((new.task_id, new.claim_generation > old.claim_generation), (task_id, True))
        task = queue.get(task_id)
        with self.assertRaises(StaleClaim):
            illustrations.run_claimed(task, old, queue)
        self.assertEqual(self.row("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))["status"], "processing", "旧领取的结果不写库")
        self.assertEqual(self.row("SELECT photo_status FROM web_messages WHERE message_id = 'msg-fence'", ())["photo_status"], "processing", "也不改来信")
        # ---- 这一段的断言换过一次（2026-09-24「成功结果恢复」派单，A 实现、我核过实现再改的）----
        #
        # **围栏那一半没有变，就在上面三条**：旧领取抛 `StaleClaim`、插画记录不写、来信不改。
        # 变的是**被拒绝的东西是什么**——被拒的是旧领取的**提交**，而它**已经付钱画出来的那张图**
        # 不再作废：新领取凭小票认领它（`illustrations.py:257-263`「凭小票认领那张图，**不预占、不发送**」，
        # 按上一次的领取代数找，落盘后缀 `-{代数}` 与预占编号末尾同源）。
        #
        # **「提交被拒」与「那张图被认领」不矛盾**：前者挡的是并发写坏数据，后者省的是第二次付费。
        # 原先第 72 行断言后缀是**新领取**的代数——那等于把「新领取自己重画一张、再付一次钱」写成期望，
        # 正是这次要消灭的重复付费。**旧断言红得对，我改的是它钉错了的那件事，不是让它变绿。**
        sent = len(self.illustrator.prompts)
        self.assertGreaterEqual(sent, 1, "前提：旧领取真的调过一次供应商——它是 0 的话下面那句『没再调』毫无意义")
        illustrations.run_claimed(task, new, queue)
        ready = self.row("SELECT status, rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))
        self.assertEqual(ready["status"], "ready")
        self.assertTrue(ready["rel_path"].endswith(f"-{old.claim_generation}.png"), "发布的是旧领取已经付过钱的那张")
        self.assertEqual(len(self.illustrator.prompts), sent, "新领取认领那张就够了，不该再付一次钱")
        self.assertEqual(self.row("SELECT photo_status FROM web_messages WHERE message_id = 'msg-fence'", ())["photo_status"], "ready")
        self.assertEqual(queue.get(task_id).status, "succeeded", "结果与任务完成同一个事务提交")

    def test_the_same_attempt_never_pays_twice_for_one_image(self) -> None:
        illustrations = self.web.illustrations
        queue = illustrations.tasks
        task_id = illustrations.request_image(self.owner.user_id, self.owner.pet_id, "fence:budget", style="selfie", place="码头", city="香港", scene="坐着")
        claim = queue.claim_next("worker-budget", ["illustration"], lease_seconds=60)
        task = queue.get(task_id)
        illustrations.run_claimed(task, claim, queue)
        calls = len(self.illustrator.prompts)
        self.assertGreaterEqual(calls, 1)
        with self.assertRaises(StaleClaim):
            illustrations.run_claimed(task, claim, queue)  # 同一次领取重放
        self.assertEqual(len(self.illustrator.prompts), calls, "同一次领取重放：额度已结算，不再发一次付费生图")
        with self.app.state.storage.connect() as conn:
            rows = conn.execute("SELECT operation_id, status, reserved_units, outcome FROM web_budget_reservations").fetchall()
        self.assertEqual([(r["status"], r["outcome"]) for r in rows], [("settled", "succeeded")], "一次领取一条预占记录")
        self.assertTrue(rows[0]["operation_id"].startswith(f"illustration:{task_id}:"))

    def test_retrying_a_failed_image_keeps_attempts_monotonic(self) -> None:
        illustrations = self.web.illustrations
        self.illustrator.fail_reason = "http_500"
        task_id = illustrations.request_image(self.owner.user_id, self.owner.pet_id, "fence:retry", style="selfie", place="码头", city="香港", scene="坐着")
        for _ in range(3):
            illustrations.run_pending()
            self.clock.advance(minutes=20)
        self.assertEqual(illustrations.tasks.get(task_id).status, "failed")
        attempts = illustrations.tasks.get(task_id).attempts
        self.illustrator.fail_reason = None
        illustrations.retry(task_id)
        self.assertEqual(self.row("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))["status"], "processing")
        illustrations.run_pending()
        task = illustrations.tasks.get(task_id)
        self.assertEqual(task.status, "succeeded")
        self.assertGreater(task.attempts, attempts, "重画不把次数清零，领取代数保持单调")


class PendingReplyFenceTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(HK_2AM).install(self)
        self.owner = self.user("reply-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.sent = self.owner.post(f"/communicator/{self.owner.pet_id}/messages", {"client_message_id": "fence-reply-0001", "text": "晚安呀"}).json()

    def use_chat(self, chat) -> None:
        self.web.providers.chat = chat
        self.web.communicator.chat = chat
        self.owner.patch("/settings", {"model_replies": True})

    def replies(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM web_messages WHERE reply_to = ? AND sender = 'pet'", (self.sent["message_id"],)).fetchone()[0]

    def pending(self):
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT delivered_message_id, outcome FROM web_pending_replies WHERE owner_message_id = ?", (self.sent["message_id"],)).fetchone()

    def test_a_crash_after_claiming_is_recovered_once_the_claim_expires(self) -> None:
        self.assertIsNone(self.pending()["delivered_message_id"], "TA 睡着：进了待回复队列")
        self.use_chat(CrashingChat())
        self.clock.advance(hours=6)  # 香港 08:00，TA 醒了
        with self.assertRaises(SystemExit):
            self.web.communicator.deliver_due(self.clock.now)
        self.assertTrue(self.pending()["delivered_message_id"].startswith("claim-"))
        self.use_chat(FakeChat(["醒啦，看到你的消息了。"]))
        self.web.communicator.deliver_due(self.clock.now)
        self.assertEqual(self.replies(), 0, "领取还没过期：不抢")
        self.clock.advance(minutes=6)
        self.web.communicator.deliver_due(self.clock.now)
        self.web.communicator.deliver_due(self.clock.now)
        self.assertEqual(self.replies(), 1, "过期后重新领取，恰好回复一次")
        self.assertEqual(self.pending()["outcome"], "delivered")

    def test_a_late_reply_from_a_taken_over_claim_is_discarded(self) -> None:
        slow = BlockingChat()
        self.use_chat(slow)
        self.clock.advance(hours=6)
        old = threading.Thread(target=self.web.communicator.deliver_due, args=(self.clock.now,))
        old.start()
        try:
            self.assertTrue(slow.entered.wait(timeout=10), "旧 worker 卡在模型上")
            self.web.communicator.chat = FakeChat(["新 worker 的回复"])
            self.web.providers.chat = self.web.communicator.chat
            self.clock.advance(minutes=6)  # 旧领取的期限过了
            self.assertEqual(self.web.communicator.deliver_due(self.clock.now), 1, "新 worker 接手并回复")
        finally:
            slow.release.set()
            old.join(timeout=30)
        self.assertEqual(self.replies(), 1, "旧 worker 晚到的回复按领取令牌作废，只有一条")
        with self.app.state.storage.connect() as conn:
            texts = [r[0] for r in conn.execute("SELECT text FROM web_messages WHERE reply_to = ?", (self.sent["message_id"],))]
        self.assertEqual(texts, ["新 worker 的回复"])

    def test_a_removed_member_gets_no_reply_after_the_fact(self) -> None:
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        token = self.owner.post(f"/households/{household_id}/invites", {"role": "caregiver"}).json()["token"]
        member = self.user("reply-member")
        member.post("/invites/accept", {"token": token})
        asked = member.post(f"/communicator/{self.owner.pet_id}/messages", {"client_message_id": "fence-reply-0002", "text": "我是妈妈，睡了吗"}).json()
        self.owner.delete(f"/households/{household_id}/members/{member.user_id}")
        self.use_chat(FakeChat(["醒啦。"]))
        self.clock.advance(hours=6)
        self.web.communicator.deliver_due(self.clock.now)
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT delivered_message_id, outcome FROM web_pending_replies WHERE owner_message_id = ?", (asked["message_id"],)).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM web_messages WHERE reply_to = ?", (asked["message_id"],)).fetchone()[0]
        self.assertEqual((row["outcome"], count), ("suppressed", 0), "发布前复核：已移除的家人不再收到回复")
        self.assertEqual(self.replies(), 1, "还在家庭里的家人照常收到回复")
        from app.schemas.web.social import MessageTopic  # 主动消息同样复核（CR-Q6）

        posted = self.web.communicator.post_pet_message(member.user_id, self.owner.pet_id, "今天天气很好呀", topic=MessageTopic.news,
                                                        composed_by="template", now=self.clock.now, dedupe_key="fence-news-0001")
        self.assertFalse(posted, "已经不是家人了：主动消息也不发布")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM web_messages WHERE user_id = ?", (member.user_id,)).fetchone()[0], 1,
                             "库里只剩他自己发过的那一条")


class GetIsPureTests(WebPlatformTestBase):
    """工钱、到家、排队回复都已到期而后台没跑时，连着读页面不能推进世界、不能调模型（只允许记已读位置）。"""

    settle_on_read = False  # 明确：这组用例就是验证读接口本身不写业务

    ALLOWED = {"web_message_reads"}

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.chat = FakeChat(["我在花店忙着呢。"])
        self.web.providers.chat = self.chat
        self.web.communicator.chat = self.chat
        self.owner = self.user("pure-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})

    def fingerprint(self) -> dict:
        import hashlib

        with self.app.state.storage.connect() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            return {t: hashlib.sha1(repr([tuple(row) for row in conn.execute(f"SELECT * FROM {t}")]).encode("utf-8")).hexdigest() for t in tables}

    def test_reading_pages_does_not_advance_the_world_or_call_the_model(self) -> None:
        journey = self.owner.post("/journey/depart", {"destination_key": "work:florist"}).json()
        self.owner.post(f"/communicator/{self.owner.pet_id}/messages", {"client_message_id": "pure-msg-0001", "text": "干活累不累？"})
        self.clock.advance(hours=4)  # 工钱、到家、排队回复都到期了，后台一直没跑
        calls_before = len(self.chat.calls)
        before = self.fingerprint()
        paths = [f"/home?pet_id={self.owner.pet_id}", f"/journey/map?pet_id={self.owner.pet_id}", f"/visits/{journey['planned_visit_id']}",
                 f"/timeline?pet_id={self.owner.pet_id}", f"/jobs?pet_id={self.owner.pet_id}", f"/communicator/{self.owner.pet_id}/messages",
                 f"/credentials?pet_id={self.owner.pet_id}", f"/collection?pet_id={self.owner.pet_id}", "/circle/feed"]
        for index in range(36):
            self.assertEqual(self.owner.get(paths[index % len(paths)]).status_code, 200)
        after = self.fingerprint()
        changed = {t for t in after if after[t] != before.get(t)}
        self.assertEqual(changed - self.ALLOWED, set(), "读接口只允许留下已读痕迹")
        self.assertEqual(len(self.chat.calls), calls_before, "读页面不调模型")
        home = self.owner.get(f"/home?pet_id={self.owner.pet_id}").json()
        self.assertTrue(home["catching_up"], "还没结算：明确告诉前端世界正在更新")
        self.assertEqual(home["presence"], "at_home", "位置按时间推算：已经过了回家时间")
        self.assertTrue(self.owner.get(f"/journey/map?pet_id={self.owner.pet_id}").json()["catching_up"])
        self.run_background()  # 任务进程跑起来
        settled = self.owner.get(f"/home?pet_id={self.owner.pet_id}").json()
        self.assertFalse(settled["catching_up"])
        self.assertEqual(settled["wallet"]["balance"], home["wallet"]["balance"] + 16, "结算之后工资才进账")


class IdempotencyRecoveryTests(WebPlatformTestBase):
    """回执写回之前进程挂了：同一个 Idempotency-Key 不能永远卡在“处理中”，也不能变成两份业务（验收 CR-Q5）。"""

    settle_on_read = True

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("idem-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def placeholder(self, minutes_ago: int) -> None:
        """把这次请求的回执改回“处理中”，并把时间往前拨，模拟写回执之前进程挂了。"""
        stamp = (self.clock.now - timedelta(minutes=minutes_ago)).isoformat()
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_idempotency_keys SET status = 'in_progress', response_json = NULL, updated_at = ?", (stamp,))

    def journeys(self) -> list:
        with self.app.state.storage.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT journey_id FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,))]

    def fees(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM economy_transactions WHERE pet_id = ? AND type = 'web_travel_fee'",
                                (self.owner.pet_id,)).fetchone()["n"]

    def test_a_lost_receipt_does_not_stick_at_in_progress_or_double_the_business(self) -> None:
        key = "idem-depart-0001"
        first = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.placeholder(minutes_ago=0)  # 刚刚开始处理：同键重试要明确告诉客户端“还在处理中”
        busy = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
        self.assert_envelope(busy, 409, "IDEMPOTENCY_IN_PROGRESS")
        self.placeholder(minutes_ago=10)  # 占位很久没写回结果：这次接手重跑
        again = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["journey_id"], first.json()["journey_id"], "同键同请求重放原来那一趟（行程编号由幂等键算出）")
        self.assertEqual(len(self.journeys()), 1, "没有变成两趟行程")
        self.assertEqual(self.fees(), 1, "旅费只扣一次")
        # 另一个键、TA 又确实在路上：这时才是领域侧的冲突
        other = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key="idem-depart-0001-b")
        self.assertEqual(other.status_code, 409, other.text)
        self.assertEqual(other.json()["error"]["details"]["reason"], "already_traveling")

    def test_same_key_different_payload_is_still_a_conflict(self) -> None:
        key = "idem-depart-0002"
        self.assertEqual(self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key).status_code, 200)
        self.placeholder(minutes_ago=10)
        self.assert_envelope(self.owner.post("/journey/depart", {"destination_key": "local:stroll"}, key=key), 409, "IDEMPOTENCY_KEY_REUSED")


if __name__ == "__main__":
    unittest.main()
