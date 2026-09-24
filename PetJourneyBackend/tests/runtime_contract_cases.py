"""独立验收（工作包 Q）合同用例本体：Q-C1…Q-C7。非测试模块（不以 test 开头），discover 不收集。

每个 contract_* 方法都在一个全新的隔离 app 里执行（与 WebPlatformTestBase 组合：临时 SQLite、临时上传目录、演示线路、
旧 scheduler 关闭），用新注册的账号，模型与地图只用进程内替身，全程在 GUARD 禁网范围内。返回 ContractResult：
PASS / FAIL / BLOCKED，附期望、实际观察、复现步骤与被测源文件摘要。这里只观察与判定，不修改任何业务实现来“变绿”。

合同与世界运行方案 §18 的对应：C1=A08/A10 过期接管，C2=A08/A24 旧结果拒绝，C3=A07 半提交恢复，C4=A17 多家人多宠隔离，
C5=A16 撤权在途，C6=A12 GET 纯读，C7=A01 到站不依赖模型。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient
from runtime_contract_harness import (BLOCKED, FAIL, GUARD, LEVEL_INTEGRATION, LEVEL_PROCESS, LEVEL_UNIT, PASS, Q_ROOT, ContractResult,
                                      HangingChat, db_diff, db_snapshot, run_child, source_digests)
from runtime_contract_boundary import CONTRACTS as BOUNDARY_CONTRACTS, BoundaryContractCases
from runtime_contract_consumers import CONTRACTS as CONSUMER_CONTRACTS, ConsumerContractCases
from runtime_contract_director import CONTRACTS as DIRECTOR_CONTRACTS, DirectorContractCases
from runtime_contract_media import CONTRACTS as MEDIA_CONTRACTS, MediaContractCases
from runtime_contract_memory import MemoryPurposeContractCases
from runtime_contract_metering import MeteringContractCases
from runtime_contract_photo import CONTRACTS as PHOTO_CONTRACTS, PhotoContractCases
from runtime_contract_reclaim import ReclaimContractCases
from runtime_contract_recovery import CONTRACTS as RECOVERY_CONTRACTS, RecoveryContractCases
from runtime_contract_reliability import ReliabilityContractCases
from runtime_contract_schedule import CONTRACTS as SCHEDULE_CONTRACTS, ScheduleContractCases
from web_base import LUNCH_UTC, PREFIX, FakeClock, WebUser
from web_provider_fakes import FakeChat, FakeGeo

HK_2AM = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)  # 香港 9/23 02:00：默认作息里 TA 在睡觉
# GET 期间允许变化的表（访问/已读痕迹，不是业务推进）；其余任何表变化都算 GET 写了业务
GET_ALLOWED_WRITES = frozenset({"web_message_reads", "web_sessions"})
TASKS_SRC = "app/web_platform/tasks.py"
COMM_SRC = "app/web_communicator/service.py"
JOURNEY_SRC = "app/web_journey/service.py"


class SimulatedCrash(BaseException):
    """模拟进程在“领取已提交、结果未写”之间被杀：BaseException 不会被业务代码的 except Exception 接住。"""


class CrashChat:
    available = True
    provider_label = "Q 崩溃替身"

    def complete(self, messages, **kwargs):  # noqa: ARG002
        raise SimulatedCrash()


class RuntimeContractCases(BoundaryContractCases, MediaContractCases, PhotoContractCases, DirectorContractCases, ConsumerContractCases, MeteringContractCases, MemoryPurposeContractCases, ReclaimContractCases, ScheduleContractCases, RecoveryContractCases,
                           ReliabilityContractCases):
    """与 web_base.WebPlatformTestBase 组合使用（self.app / self.web / self.settings / self.user）。
    可靠性合同（缺表前提、额度与付费调用边界）在 runtime_contract_reliability.py 里，一起组合进来。"""

    def _result(self, cid, title, acceptance, level, owner, status, expected, observed, repro, sources, guard_before) -> ContractResult:
        return ContractResult(cid, title, acceptance, level, owner, status, expected, observed, repro, sources,
                              network_attempts=len(GUARD.attempts) - guard_before)

    def _register(self, name: str, entry: dict | None = None) -> WebUser:
        user = WebUser.__new__(WebUser)
        user.client = TestClient(self.app)
        body = {"username": name, "password": "longpassword1", **({"entry": entry} if entry else {})}
        response = user.client.post(f"{PREFIX}/auth/register", json=body)
        assert response.status_code == 201, response.text
        user.user_id, user.pet_id, user.home_id = response.json()["user"]["user_id"], None, None
        return user

    def _family(self, prefix: str) -> tuple[WebUser, str, str, str, WebUser]:
        """管理员 A：先接自己的猫入住，再领养一位居民进同一个家；再邀请 C 成为共同照顾者。返回 (A, 猫, 领养伙伴, household_id, C)。"""
        a = self.user(f"{prefix}-admin")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        household_id = a.get("/households").json()[0]["household_id"]
        companion = a.post("/adoption/adopt", {"candidate_id": "adopt-lan", "household_id": household_id})
        assert companion.status_code == 200, companion.text
        moved = a.post("/onboarding/move-in", {"pet_id": companion.json()["pet_id"]})
        assert moved.status_code == 200, moved.text
        token = a.post(f"/households/{household_id}/invites", {"role": "caregiver", "relation_hint": "妈妈", "ttl_hours": 24}).json()["token"]
        c = self._register(f"{prefix}-carer", {"kind": "invite", "invite_token": token})
        accepted = c.post("/invites/accept", {"token": token})
        assert accepted.status_code == 200, accepted.text
        return a, cat, companion.json()["pet_id"], household_id, c

    def _use_chat(self, chat, *users: WebUser) -> None:
        """换上模型替身：通讯回信、攻略、接待、明信片（经 providers.chat 读取）都用它；并替这些家人打开“模型回信”。"""
        web = self.web
        web.providers.chat = chat
        web.communicator.chat = chat
        web.guides.chat = chat
        web.reception.chat = chat
        for user in users:
            response = user.patch("/settings", {"model_replies": True})
            assert response.status_code == 200, response.text

    def _sql(self, query: str, params: tuple = ()) -> list[tuple]:
        conn = sqlite3.connect(self.settings.database_path)
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    # ---- C1 过期任务接管 ----
    def contract_c1a_queue_takeover(self) -> ContractResult:
        from app.web_platform.tasks import WebTaskQueue

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        queue = WebTaskQueue(self.app.state.storage)
        task, _ = queue.enqueue("q-probe", f"q-c1a-{uuid.uuid4().hex[:8]}", {"probe": True})
        child = run_child(
            "import json, os\nfrom datetime import datetime\nfrom pathlib import Path\n"
            "import app.web_platform.tasks as tasks\nfrom app.storage import JourneyStorage\n"
            f"tasks.utcnow = lambda: datetime.fromisoformat({LUNCH_UTC.isoformat()!r})\n"
            f"queue = tasks.WebTaskQueue(JourneyStorage(Path({str(self.settings.database_path)!r})))\n"
            "claim = getattr(queue, 'claim_next', queue.claim)('worker-killed', ['q-probe'], lease_seconds=60)\n"
            "print(json.dumps({'claimed': claim.task_id if claim else None, 'generation': getattr(claim, 'claim_generation', None)}), flush=True)\n"
            "os._exit(9)  # 领取后、完成前被杀\n",
            Q_ROOT / "tmp" / f"child-{uuid.uuid4().hex[:8]}")
        clock.advance(hours=1)
        reclaimed = getattr(queue, "claim_next", queue.claim)("worker-takeover", ["q-probe"], lease_seconds=60)
        after = queue.get(task.task_id)
        lines = [line for line in child.stdout.splitlines() if line.startswith("{")]
        killed = json.loads(lines[-1]) if lines else {"stderr": child.stderr[-300:]}
        observed = {"child_exit_code": child.returncode, "killed_worker": killed, "reclaimed_after_1h": reclaimed.task_id if reclaimed else None,
                    "status_after": after.status, "attempts_after": after.attempts, "new_generation": getattr(reclaimed, "claim_generation", None)}
        newer = killed.get("generation") is None or (observed["new_generation"] or 0) > killed["generation"]
        ok = reclaimed is not None and reclaimed.task_id == task.task_id and child.returncode == 9 and newer
        return self._result("Q-C1a", "worker 领取后被杀，租约过期后另一个 worker 能接管同一任务", "A08", LEVEL_PROCESS, "A（队列）",
                            PASS if ok else FAIL, "租约（60 秒）过期 1 小时后可被重新领取，attempts+1、领取代数递增", observed,
                            ["父进程 enqueue(q-probe)", "子进程 claim(lease 60s) 后 os._exit(9)", "父进程时钟 +1h 后 claim(worker-takeover)"],
                            source_digests(TASKS_SRC), guard0)

    def contract_c1b_reply_claim_crash(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(HK_2AM).install(self)
        a = self.user("q-c1b-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        sent = a.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c1b-msg-0001", "text": "晚安呀"}).json()
        queued = self._sql("SELECT COUNT(*) FROM web_pending_replies WHERE owner_message_id = ?", (sent["message_id"],))[0][0]
        self._use_chat(CrashChat(), a)
        clock.advance(hours=6)  # 香港 08:00，TA 已经醒了，后台开始补回复
        try:
            self.web.communicator.deliver_due(clock.now)
            crashed = False
        except SimulatedCrash:
            crashed = True
        claim = self._sql("SELECT delivered_message_id FROM web_pending_replies WHERE owner_message_id = ?", (sent["message_id"],))
        self._use_chat(FakeChat(["醒啦，看到你的消息了。"]), a)
        clock.advance(hours=2)
        self.web.communicator.deliver_due(clock.now)
        replies = self._sql("SELECT COUNT(*) FROM web_messages WHERE reply_to = ? AND sender = 'pet'", (sent["message_id"],))[0][0]
        final = self._sql("SELECT delivered_message_id FROM web_pending_replies WHERE owner_message_id = ?", (sent["message_id"],))
        state = next((m["state"] for m in a.get(f"/communicator/{cat}/messages").json()["items"] if m["message_id"] == sent["message_id"]), None)
        observed = {"queued_before": queued, "crashed_after_claim": crashed, "claim_after_crash": (claim[0][0] or "")[:6] if claim else None,
                    "replies_2h_later": replies, "pending_row_after": (final[0][0] or "")[:6] if final else None, "owner_message_state": state}
        ok = queued == 1 and crashed and replies == 1
        return self._result("Q-C1b", "待回复领取（claim-*）后进程崩溃：过期可恢复，原输入不永远卡住，只回复一次", "A10", LEVEL_INTEGRATION, "I（通讯待回复领取）",
                            PASS if ok else FAIL, "崩溃后超过租期再跑后台：这条消息得到恰好一条回复", observed,
                            ["香港 02:00 TA 睡着时发私聊 → 进待回复队列", "08:00 后台 deliver_due：领取提交后模型调用处模拟进程被杀",
                             "换正常模型，时钟再 +2h 跑 deliver_due", "统计 reply_to=这条消息 的回复数"], source_digests(COMM_SRC), guard0)

    # ---- C2 旧结果拒绝 ----
    def contract_c2_stale_results(self) -> ContractResult:
        import app.web_platform.tasks as tasks

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        queue = tasks.WebTaskQueue(self.app.state.storage)
        observed: dict = {}
        for label, late_call in (("superseded_then_old_complete", lambda t: queue.complete(t)),
                                 ("superseded_then_old_fail", lambda t: queue.fail(t, "late-error"))):
            task, _ = queue.enqueue("q-probe", f"q-c2-{label}", {})
            queue.claim("worker-old", ["q-probe"])
            queue.supersede(task.task_id, "source revoked")
            try:
                late_call(task.task_id)
                raised = None
            except Exception as exc:  # noqa: BLE001 - 拒绝方式可以是抛 LostClaim/StaleClaim
                raised = type(exc).__name__
            observed[label] = {"status_after": queue.get(task.task_id).status, "raised": raised}
        if not (hasattr(queue, "claim_next") and hasattr(queue, "fenced")):
            observed["takeover_fence"] = "缺 §2.4 的领取凭据与事务内围栏（claim_next / fenced）"
        else:
            probe = sqlite3.connect(self.settings.database_path)
            probe.execute("CREATE TABLE IF NOT EXISTS q_probe_effects (task_id TEXT, writer TEXT)")  # 只建在隔离库里的探针表
            probe.commit()
            probe.close()
            task, _ = queue.enqueue("q-fence", "q-c2-takeover", {})
            old = queue.claim_next("worker-old", ["q-fence"], lease_seconds=60)
            clock.advance(minutes=5)
            new = queue.claim_next("worker-new", ["q-fence"], lease_seconds=60)
            commits = {}
            for writer, claim in (("old", old), ("new", new)):
                try:
                    with queue.fenced(claim) as tx:
                        tx.execute("INSERT INTO q_probe_effects (task_id, writer) VALUES (?, ?)", (task.task_id, writer))
                    commits[writer] = "committed"
                except Exception as exc:  # noqa: BLE001
                    commits[writer] = type(exc).__name__
            effects = [r[0] for r in self._sql("SELECT writer FROM q_probe_effects WHERE task_id = ?", (task.task_id,))]
            observed["takeover_fence"] = {"generations": [old.claim_generation, new.claim_generation], "commit": commits, "effects": effects,
                                          "status_after": queue.get(task.task_id).status}
        fence = observed["takeover_fence"]
        stale_ok = all(v["status_after"] == "superseded" for k, v in observed.items() if k.startswith("superseded"))
        fence_ok = isinstance(fence, dict) and fence["effects"] == ["new"] and fence["commit"]["old"] != "committed" and fence["status_after"] == "succeeded"
        status = PASS if stale_ok and fence_ok else (BLOCKED if stale_ok and isinstance(fence, str) else FAIL)
        return self._result("Q-C2", "旧 worker 的迟到结果不能覆盖 superseded；接管后旧领取在同一事务里的业务写入被整体拒绝", "A08、A24", LEVEL_UNIT,
                            "A（队列）→ I（接入）", status,
                            "supersede 之后旧 complete/fail 不改变状态；接管后旧领取 fenced 抛 StaleClaim、业务写入回滚，只有新领取的写入与完成生效",
                            observed, ["enqueue → claim(worker-old) → supersede → 旧 worker 调 complete(task_id) / fail(task_id)",
                                       "claim_next(旧, 60s) → 时钟 +5 分钟 → claim_next(新) → 旧、新各自 with fenced(claim) 写一行探针"],
                            source_digests(TASKS_SRC, "app/web_platform/lease.py"), guard0)

    # ---- C3 半提交恢复 ----
    def _depart_with_lost_receipt(self, a, cat: str, key: str) -> tuple[object, str | None]:
        """出发一次，但幂等回执写入失败（业务已提交、回执丢失）。返回 (首次尝试结果, 这趟旅程编号)。"""
        store = self.app.state.web_idempotency
        real = store.storage
        steps = iter([real.connect, mock.Mock(side_effect=sqlite3.OperationalError("Q 注入：业务已提交，回执写入失败"))])
        proxy = mock.Mock(wraps=real)
        proxy.connect.side_effect = lambda: next(steps)()  # 第 1 次（占位）照常，第 2 次（写回执）失败；连接在请求所在线程里建
        store.storage = proxy
        try:
            first = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}, key=key).status_code
        except sqlite3.OperationalError:
            first = "exception"
        finally:
            store.storage = real
        rows = self._sql("SELECT journey_id FROM web_journeys WHERE pet_id = ?", (cat,))
        return first, (rows[0][0] if rows else None)

    def contract_c3a_receipt_lost(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a = self.user("q-c3a-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        key = "q-c3a-depart-0001"
        first, journey_id = self._depart_with_lost_receipt(a, cat, key)
        code = lambda r: (r.json().get("error") or {}).get("code") if r.status_code >= 400 else None  # noqa: E731
        body = lambda r: r.json() if r.status_code < 400 else (r.json().get("error") or {})  # noqa: E731
        within = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}, key=key)
        clock.advance(minutes=6)  # 超过占位 TTL（5 分钟）：上一次尝试被认为已死
        after = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}, key=key)
        after_body = body(after)
        refers = journey_id is not None and journey_id in json.dumps(after_body, ensure_ascii=False, default=str)
        journeys = [r[0] for r in self._sql("SELECT journey_id FROM web_journeys WHERE pet_id = ?", (cat,))]
        fees = sum(self._sql("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"web:travel_fee:{j}",))[0][0] for j in journeys)
        observed = {"first_attempt": first, "within_ttl": {"status": within.status_code, "code": code(within)},
                    "after_ttl": {"status": after.status_code, "code": code(after), "reason": after_body.get("details", {}).get("reason") if after.status_code >= 400 else None,
                                  "journey_id": after_body.get("journey_id") if after.status_code < 400 else None},
                    "refers_to_original_journey": refers, "journeys": len(journeys), "fee_transactions": fees,
                    "balance": self.web.economy.wallet(cat).balance}
        stuck_fixed = after.status_code != 409 or code(after) != "IDEMPOTENCY_IN_PROGRESS"
        no_double = len(journeys) == 1 and fees == 1 and observed["balance"] == 12
        linked = after.status_code == 200 and after_body.get("journey_id") == journey_id or refers
        status = PASS if stuck_fixed and no_double and linked else FAIL
        return self._result("Q-C3a", "业务已提交、幂等回执没写成：TTL 内报处理中，超时后接手且要能关联原操作，不双扣", "A07", LEVEL_INTEGRATION,
                            "I（HTTP 幂等回执）", status,
                            "TTL 内 409 IDEMPOTENCY_IN_PROGRESS；超过 TTL 后不再卡死，并且重放原结果或在响应里指回原操作（原 journey_id）；始终只有 1 趟旅程、1 条旅费",
                            observed, ["出发 local:cafe（Idempotency-Key=K），注入回执写入失败", "同键立即重试（TTL 内）",
                                       "时钟 +6 分钟后同键重试（超过 5 分钟占位 TTL）", "检查响应是否指回原行程，并统计旅程数、旅费条数与余额"],
                            source_digests("app/web_platform/idempotency.py", JOURNEY_SRC), guard0)

    def contract_c3c_key_across_lifecycle(self) -> ContractResult:
        """同一个幂等键在原旅程结束之后再重试：领域侧“一次只有一趟旅程”已经不再拦得住，键本身必须还认得这次操作。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a = self.user("q-c3c-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        key = "q-c3c-depart-0001"
        first, journey_id = self._depart_with_lost_receipt(a, cat, key)
        clock.advance(minutes=6)
        takeover = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}, key=key)
        placeholder = self._sql("SELECT status FROM web_idempotency_keys WHERE idem_key = ?", (key,))
        clock.advance(hours=1)  # TA 早已回家：领域侧的“已经在路上”不再成立
        late = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}, key=key)
        journeys = [r[0] for r in self._sql("SELECT journey_id FROM web_journeys WHERE pet_id = ?", (cat,))]
        fees = sum(self._sql("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"web:travel_fee:{j}",))[0][0] for j in journeys)
        observed = {"first_attempt": first, "original_journey": journey_id, "takeover_status": takeover.status_code,
                    "idempotency_row_after_takeover": [r[0] for r in placeholder] or "已删除",
                    "retry_after_trip_ended": {"status": late.status_code, "journey_id": late.json().get("journey_id") if late.status_code < 400 else None},
                    "journeys": len(journeys), "fee_transactions": fees, "balance": self.web.economy.wallet(cat).balance}
        ok = len(journeys) == 1 and fees == 1 and observed["balance"] == 12
        return self._result("Q-C3c", "同一个幂等键在原旅程结束后再重试：不能又出发一次、又扣一次钱", "A05、A07", LEVEL_INTEGRATION,
                            "I（HTTP 幂等回执）", PASS if ok else FAIL,
                            "同键同请求始终对应同一次操作：只有 1 趟旅程、1 条旅费、余额 12（要么重放原结果，要么冲突）", observed,
                            ["出发 local:cafe（Idempotency-Key=K），注入回执写入失败", "时钟 +6 分钟：同键重试（接手重跑，被领域规则挡住）",
                             "时钟再 +1 小时（TA 已回家）：同键再重试", "统计旅程数、旅费条数与余额"],
                            source_digests("app/web_platform/idempotency.py", JOURNEY_SRC), guard0)

    def contract_c3d_takeover_race(self) -> ContractResult:
        """接手的并发与旧执行者迟到：两个同键请求同时接手只能执行一次；卡住的旧执行者迟到写回执，不能覆盖新结果。"""
        from app.web_platform.idempotency import IdempotencyStore

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        store = IdempotencyStore(self.app.state.storage)
        payload, key, runs = {"probe": "q-c3d"}, "q-c3d-key-0001", []
        holding, released = threading.Event(), threading.Event()

        def stuck() -> dict:
            runs.append("old")
            holding.set()
            released.wait(20)
            return {"writer": "old"}

        def quick(name: str):
            def handler() -> dict:
                runs.append(name)
                return {"writer": name}
            return handler

        old = threading.Thread(target=lambda: store.run(user_id="u-q", scope="q.probe", key=key, payload=payload, handler=stuck), daemon=True)
        old.start()
        entered = holding.wait(10)
        clock.advance(minutes=6)  # 旧执行者还卡着，占位已经超过 TTL
        outcomes: dict[str, object] = {}

        def takeover(name: str) -> None:
            try:
                outcomes[name] = store.run(user_id="u-q", scope="q.probe", key=key, payload=payload, handler=quick(name)).response
            except Exception as exc:  # noqa: BLE001 - 另一个并发请求应当被 409 挡住
                outcomes[name] = type(exc).__name__
        racers = [threading.Thread(target=takeover, args=(name,), daemon=True) for name in ("new-1", "new-2")]
        for t in racers:
            t.start()
        for t in racers:
            t.join(20)
        released.set()
        old.join(20)
        replay = store.run(user_id="u-q", scope="q.probe", key=key, payload=payload, handler=quick("should-not-run"))
        takeover_runs = [n for n in runs if n in ("new-1", "new-2")]
        winner = takeover_runs[0] if takeover_runs else None  # 真正执行了的那个（不能按结果顺序猜）
        observed = {"old_executor_started": entered, "handler_runs": runs, "takeover_handler_runs": len(takeover_runs),
                    "takeover_results": {k: v for k, v in outcomes.items()},
                    "replay_after_late_old": {"response": replay.response, "replayed": replay.replayed}}
        # 并发的另一个请求拿到胜出者结果的重放是对的（不必抛异常）；要求的是“接手只真的执行一次、大家看到同一个结果”
        one_takeover = len(takeover_runs) == 1 and winner is not None and all(
            outcomes.get(n) in ({"writer": winner}, "WebAPIError") for n in ("new-1", "new-2"))
        fresh = replay.replayed and replay.response == {"writer": winner} and "should-not-run" not in runs
        return self._result("Q-C3d", "占位过期后并发接手只执行一次；卡住的旧执行者迟到写回执不能覆盖新结果", "A07、A08", LEVEL_UNIT,
                            "I（HTTP 幂等回执）", PASS if entered and one_takeover and fresh else FAIL,
                            "两个并发接手里只有一个真的执行；随后重放拿到的是接手者的结果，不是迟到旧执行者的结果", observed,
                            ["同键请求 1：handler 卡住（模拟写回执前挂起）", "时钟 +6 分钟越过占位 TTL",
                             "同键请求 2、3 并发接手", "放行旧执行者让它迟到写回执", "同键再请求一次，看重放的是谁的结果"],
                            source_digests("app/web_platform/idempotency.py"), guard0)

    def contract_c3b_salary_sink_failure(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        journeys = self.web.journeys
        title = "工钱与事件同事务；家庭来信下游失败后重试，工钱与来信都恰好一次"
        if "communicator" not in getattr(journeys, "consumers", {}):
            return self._result("Q-C3b", title, "A07、A11", LEVEL_INTEGRATION, "I", BLOCKED, "旅程事件下游可替换（consumers）",
                                "找不到 communicator 下游登记", [], source_digests(JOURNEY_SRC), guard0)
        a = self.user("q-c3b-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        sink, lane = journeys.consumers["communicator"]
        failures: list[str] = []

        def flaky(event) -> None:
            if event.kind == "work_done" and not failures:
                failures.append(event.key)
                raise RuntimeError("Q 注入：家庭来信下游第一次投递失败")
            sink.on_world_event(event)

        journeys.consumers["communicator"] = (mock.Mock(on_world_event=flaky), lane)
        salary_q, message_q = "SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", "SELECT COUNT(*) FROM web_messages WHERE source_event_id = ?"
        try:
            journey_id = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "work:florist"}).json()["journey_id"]
            balance0 = self.web.economy.wallet(cat).balance
            clock.now = journeys.repo.visit_for_journey(journey_id).ends_at + timedelta(minutes=1)
            journeys.advance_pet(cat, clock.now)
            first = {"salary": self._sql(salary_q, (f"web:job:{journey_id}",))[0][0],
                     "work_done_messages": self._sql(message_q, (f"{journey_id}:work_done",))[0][0],
                     "work_done_recorded": "work_done" in journeys.repo.applied_events(journey_id)}
            clock.advance(minutes=2)  # 过了第一次退避（30 秒）
            journeys.deliver_outbox(clock.now)
            clock.advance(minutes=30)
            journeys.advance_pet(cat, clock.now)
            journeys.deliver_outbox(clock.now)
            final = {"salary": self._sql(salary_q, (f"web:job:{journey_id}",))[0][0],
                     "work_done_messages": self._sql(message_q, (f"{journey_id}:work_done",))[0][0],
                     "balance_delta": self.web.economy.wallet(cat).balance - balance0, "lifecycle": journeys.repo.get(journey_id).lifecycle}
        finally:
            journeys.consumers["communicator"] = (sink, lane)
        observed = {"injected_failures": len(failures), "right_after_failure": first, "after_retry": final}
        ok = (bool(failures) and first == {"salary": 1, "work_done_messages": 0, "work_done_recorded": True}
              and final == {"salary": 1, "work_done_messages": 1, "balance_delta": 16, "lifecycle": "completed"})
        return self._result("Q-C3b", title, "A07、A11", LEVEL_INTEGRATION, "I（结算与 outbox）", PASS if ok else FAIL,
                            "下游失败时：工钱 1 条、事件已登记、来信 0 条；重试后：工钱仍 1 条、来信 1 条、余额只 +16、按时到家", observed,
                            ["出发 work:florist", "把家庭来信下游换成“work_done 第一次抛错”的包装", "时钟到收工后推进一次", "过退避时间后投递 outbox，再推进到家"],
                            source_digests(JOURNEY_SRC, "app/web_journey/settlement.py", "app/web_platform/outbox.py"), guard0)

    # ---- C8 接口层关联字段（CR-Q1 / CR-Q2 复核）----
    def contract_c8_api_link_fields(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a, cat, companion, _, c = self._family("q-c8")
        sent = a.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c8-admin-0001", "text": "今天在家吗"}).json()
        cafe = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}).json()["journey_id"]
        job = a.post(f"/journey/depart?pet_id={companion}", {"destination_key": "work:florist"}).json()["journey_id"]
        clock.now = self.web.journeys.repo.get(job).completes_at + timedelta(minutes=1)
        self.web.journeys.advance_all(clock.now)
        self.web.journeys.deliver_outbox(clock.now)
        ledgers = {}
        for pet in (cat, companion):
            card = next(x for x in a.get(f"/credentials?pet_id={pet}").json() if x["kind"] == "bank_card")
            ledgers[pet] = a.get(f"/credentials/{card['credential_id']}").json().get("ledger") or []
        fee = next((e for e in ledgers[cat] if e["type"] == "web_travel_fee"), None)
        wage = next((e for e in ledgers[companion] if e["type"] == "web_job_income"), None)
        items = a.get(f"/communicator/{cat}/messages").json()["items"]
        events = [m for m in items if m.get("channel") == "family" and m.get("source_event_id")]
        reply = next((m for m in items if m.get("reply_to")), None)
        owner_msgs = [m for m in items if m["sender"] == "owner"]
        checks = {
            "旅费流水带 ref_kind=journey": bool(fee) and fee.get("ref_kind") == "journey",
            "旅费流水的 ref_id 指向这趟旅程": bool(fee) and fee.get("ref_id") == cafe,
            "工资流水带 ref_kind=journey": bool(wage) and wage.get("ref_kind") == "journey",
            "工资流水的 ref_id 指向这份工作": bool(wage) and wage.get("ref_id") == job,
            "家庭来信带 source_event_id": bool(events),
            "来信的 source_event_id 指向本趟旅程的事件": bool(events) and all(m["source_event_id"].split(":")[0] in (cafe, job) for m in events),
            "同一源事件只有一条来信": len({m["source_event_id"] for m in events}) == len(events),
            "TA 的回复带 reply_to": bool(reply) and reply.get("sender") == "pet",
            "reply_to 指向家人发的那条": bool(reply) and reply.get("reply_to") == sent["message_id"],
            "家人自己的消息没有 source_event_id": all(m.get("source_event_id") is None for m in owner_msgs),
        }
        observed = {**checks, "样本": {"fee": {k: (fee or {}).get(k) for k in ("type", "ref_kind", "ref_id")},
                                     "wage": {k: (wage or {}).get(k) for k in ("type", "ref_kind", "ref_id")},
                                     "event_sources": [m["source_event_id"] for m in events][:4],
                                     "reply_to": (reply or {}).get("reply_to"), "sent": sent["message_id"]}}
        return self._result("Q-C8", "0.4.1 接口层关联字段：账本 ref_kind/ref_id、来信 source_event_id、回复 reply_to 实际下发且对应正确",
                            "CR-Q1、CR-Q2", LEVEL_INTEGRATION, "I（对外契约）", PASS if all(checks.values()) else FAIL, "全部检查为 true", observed,
                            ["家人发一条私聊（TA 在家醒着，立即回复）", "猫去 local:cafe（扣旅费）、领养伙伴去 work:florist（拿工资）",
                             "时钟推过到家时间后结算并投递", "读 /credentials/<银行卡> 的流水与 /communicator/<宠物>/messages，逐条核对关联字段"],
                            source_digests("app/schemas/web/credentials.py", "app/schemas/web/social.py", COMM_SRC, "app/web_credentials_wiring.py"), guard0)

    # ---- C4 多家人多宠隔离 ----
    def contract_c4_household_isolation(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        FakeClock(LUNCH_UTC).install(self)
        a, cat, companion, _, c = self._family("q-c4")
        outsider = self.user("q-c4-outsider")
        outsider_pet = outsider.upload_pet("隔壁猫", "cat").json()["pet_id"]
        outsider.move_in()
        mine = a.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c4-admin-0001", "text": "我是管理员"}).json()
        theirs = c.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c4-carer-0001", "text": "我是照顾者"}).json()
        journey_id = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:stroll"}).json()["journey_id"]
        seen_a = {m["message_id"] for m in a.get(f"/communicator/{cat}/messages").json()["items"]}
        seen_c = {m["message_id"] for m in c.get(f"/communicator/{cat}/messages").json()["items"]}
        replies = {row[0]: row[1] for row in self._sql("SELECT reply_to, message_id FROM web_messages WHERE reply_to IN (?, ?)",
                                                       (mine["message_id"], theirs["message_id"]))}
        family = [r[0] for r in self._sql("SELECT message_id FROM web_messages WHERE source_event_id = ?", (f"{journey_id}:departed",))]
        checks = {
            "管理员看不到照顾者的私聊": theirs["message_id"] not in seen_a and replies.get(theirs["message_id"]) not in seen_a,
            "照顾者看不到管理员的私聊": mine["message_id"] not in seen_c and replies.get(mine["message_id"]) not in seen_c,
            "出发来信只有一条": len(family) == 1,
            "两人看到同一条家庭来信": bool(family) and family[0] in seen_a and family[0] in seen_c,
            "另一只宠物仍在家": a.get(f"/home?pet_id={companion}").json()["presence"] == "at_home",
            "外人读这只宠物的家 404": outsider.get(f"/home?pet_id={cat}").status_code == 404,
            "外人读这只宠物的消息 404": outsider.get(f"/communicator/{cat}/messages").status_code == 404,
            "管理员读外人的宠物 404": a.get(f"/home?pet_id={outsider_pet}").status_code == 404,
        }
        return self._result("Q-C4", "多家人多宠：私聊各自独立、家庭来信一件事一条、外人全部 404", "A17", LEVEL_INTEGRATION, "I",
                            PASS if all(checks.values()) else FAIL, "全部检查为 true", checks,
                            ["A 建家（自己的猫＋领养居民），邀请 C 为共同照顾者；另建无关家庭 U", "A、C 各给猫发私聊", "猫出门散步",
                             "比对两人线程、家庭来信条数与 U 的访问结果"], source_digests(COMM_SRC, "app/web_household/access.py"), guard0)

    # ---- C5 撤权在途 ----
    def contract_c5_revoke_in_flight(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a, cat, _, household_id, c = self._family("q-c5")
        self._use_chat(FakeChat(["嗯嗯"]), c)
        clock.now = HK_2AM + timedelta(days=0)  # 当天香港深夜 02:00，TA 睡着：照顾者的私聊进待回复队列
        sent = c.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c5-carer-0001", "text": "悄悄跟你说一句"}).json()
        hanging = HangingChat(reply="妈妈我醒啦，你说的我都记着。")
        self._use_chat(hanging, c)
        clock.advance(hours=6)
        worker = threading.Thread(target=self.web.communicator.deliver_due, args=(clock.now,), daemon=True)
        worker.start()
        entered = hanging.entered.wait(10)
        removed = a.delete(f"/households/{household_id}/members/{c.user_id}").status_code
        hanging.release()
        worker.join(20)
        published = self._sql("SELECT composed_by FROM web_messages WHERE reply_to = ? AND sender = 'pet'", (sent["message_id"],))
        observed = {"model_call_in_flight": entered, "remove_status": removed, "worker_finished": not worker.is_alive(),
                    "replies_published_after_removal": len(published), "composed_by": [r[0] for r in published],
                    "removed_member_read_status": c.get(f"/communicator/{cat}/messages").status_code}
        ok = entered and removed == 204 and not published
        return self._result("Q-C5", "模型为某位家人生成回信期间该家人被移除：结果不发布给已撤权的人", "A16", LEVEL_INTEGRATION, "I（最终提交再校验）＋C",
                            PASS if ok else FAIL, "移除后到达的在途回信不写入该家人的私聊（记为取消/抑制）；该家人读取 404", observed,
                            ["共同照顾者 C 开“模型回信”，香港 02:00 发私聊（TA 睡着，排队）", "08:00 后台 deliver_due，模型替身挂起",
                             "挂起期间管理员移除 C", "放行模型（返回一段 model 回信），统计 reply_to=这条消息 的发布数"],
                            source_digests(COMM_SRC, "app/web_household/members.py"), guard0)

    # ---- C6 GET 纯读 ----
    def contract_c6_get_is_pure(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a = self.user("q-c6-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        chat = FakeChat(["我在花店忙着呢，晚点跟你说。"])
        self._use_chat(chat, a)
        departed = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "work:florist"}).json()
        clock.advance(minutes=40)
        a.post(f"/communicator/{cat}/messages", {"client_message_id": "q-c6-msg-0001", "text": "干活累不累？"})
        clock.now = self.web.journeys.repo.get(departed["journey_id"]).completes_at + timedelta(minutes=10)  # 工钱、到家、回复都已到期，后台没跑
        geo = FakeGeo()
        geo_calls: list[str] = []
        geo.place_near = lambda *args, **kwargs: geo_calls.append("place_near")
        geo.route = lambda *args, **kwargs: geo_calls.append("route")
        self.web.journeys.geo = geo
        model_before = len(chat.calls)
        before = db_snapshot(self.settings.database_path)
        paths = [f"/home?pet_id={cat}", f"/journey/map?pet_id={cat}", f"/visits/{departed['planned_visit_id']}", f"/timeline?pet_id={cat}",
                 f"/jobs?pet_id={cat}", f"/communicator/{cat}/messages", f"/credentials?pet_id={cat}", f"/home/place?pet_id={cat}"]
        statuses = Counter(a.get(paths[i % len(paths)]).status_code for i in range(100))
        changed = db_diff(before, db_snapshot(self.settings.database_path))
        business = {t: v for t, v in changed.items() if t not in GET_ALLOWED_WRITES}
        observed = {"gets": dict(statuses), "business_tables_changed": business, "allowed_tables_changed": sorted(set(changed) - set(business)),
                    "model_calls_during_gets": len(chat.calls) - model_before, "map_calls_during_gets": len(geo_calls)}
        ok = not business and observed["model_calls_during_gets"] == 0 and not geo_calls
        return self._result("Q-C6", "工钱/到家/回复都已到期、后台未运行时，连读 100 次 GET 不推进业务、不调模型或地图", "A12", LEVEL_INTEGRATION, "I（GET 纯读投影）",
                            PASS if ok else FAIL, f"除 {sorted(GET_ALLOWED_WRITES)} 外没有任何表变化；模型 0 次、地图 0 次（未提交的阶段应显示 catching_up）",
                            observed, ["出发 work:florist；途中发一条私聊（回复排在稍后）", "时钟越过到家时间 10 分钟，不跑后台",
                                       "对 8 个读接口轮流 GET 共 100 次", "比较前后每张表的行数与内容摘要，统计模型/地图替身调用"],
                            source_digests(JOURNEY_SRC, COMM_SRC, "app/routers/web/journey.py", "app/routers/web/home.py"), guard0)

    # ---- C7 到站不依赖模型 ----
    def contract_c7a_arrival_waits_for_model(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a = self.user("q-c7a-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        self._use_chat(FakeChat(["好的"]), a)
        journey_id = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "harbour_cafe"}).json()["journey_id"]
        hanging = HangingChat()
        self._use_chat(hanging, a)
        clock.now = self.web.journeys.repo.get(journey_id).completes_at + timedelta(minutes=1)
        worker = threading.Thread(target=self.web.journeys.advance_all, args=(clock.now,), daemon=True)
        worker.start()
        entered = hanging.entered.wait(10)
        during = {"lifecycle": self.web.journeys.repo.get(journey_id).lifecycle,
                  "returned_home_recorded": "returned_home" in self.web.journeys.repo.applied_events(journey_id)}
        hanging.release()
        worker.join(30)
        observed = {"model_called": entered, "while_model_hangs": during, "after_model_times_out": self.web.journeys.repo.get(journey_id).lifecycle}
        status = BLOCKED if not entered else PASS if during["returned_home_recorded"] else FAIL
        return self._result("Q-C7a", "到家时间已过、模型挂住：确定性的到家不等模型", "A01、R2", LEVEL_INTEGRATION, "I（事件与表达拆分）＋B",
                            status, "模型调用挂起时 returned_home 已经提交（明信片措辞之类的表达可以待处理）", observed,
                            ["开“模型回信”，出发 harbour_cafe", "换成挂起的模型替身，时钟越过到家时间", "后台线程 advance_all；模型被调用并挂起时读旅程状态",
                             "放行（模型超时）后再读"], source_digests(JOURNEY_SRC, "app/web_collection/service.py", "app/web_agent_wiring.py"), guard0)

    def contract_c7c_worker_blocked_by_model(self) -> ContractResult:
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a, cat, companion, _, _ = self._family("q-c7c")
        self._use_chat(FakeChat(["好的"]), a)
        a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "harbour_cafe"})  # 出发事件的攻略下游在 slow 通道，会调模型
        job = a.post(f"/journey/depart?pet_id={companion}", {"destination_key": "work:florist"}).json()["journey_id"]
        hanging = HangingChat()
        self._use_chat(hanging, a)
        clock.advance(minutes=5)
        cognition = getattr(self.web, "cognition", None)  # 认知线（可能调模型）；没有就退回只有一条线的旧结构
        blocked = threading.Thread(target=(cognition or self.web.ticker).tick, args=(clock.now,), daemon=True)
        blocked.start()
        entered = hanging.entered.wait(10)
        clock.now = self.web.journeys.repo.get(job).completes_at + timedelta(minutes=1)  # 另一只宠物的工钱与到家都已到期
        if cognition is not None:
            self.web.ticker.tick(clock.now)  # 世界线：认知线卡住时也要能把到期的事结算掉
        salary_q = "SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?"
        during = {"salary": self._sql(salary_q, (f"web:job:{job}",))[0][0], "lifecycle": self.web.journeys.repo.get(job).lifecycle}
        hanging.release()
        blocked.join(30)
        after = {"salary": self._sql(salary_q, (f"web:job:{job}",))[0][0], "lifecycle": self.web.journeys.repo.get(job).lifecycle}
        observed = {"two_lanes": cognition is not None, "model_call_blocking_cognition": entered, "world_lane_while_blocked": during,
                    "after_release": after}
        status = BLOCKED if not entered else PASS if during == {"salary": 1, "lifecycle": "completed"} else FAIL
        return self._result("Q-C7c", "认知线在一次模型调用上挂住时，世界线仍然把另一只宠物已到期的工钱与到家结算掉", "A01、A09、R2", LEVEL_INTEGRATION,
                            "I（推进与表达分线）＋B（心跳调度）", status,
                            "模型挂起期间，世界线跑一轮就把工钱记 1 条、旅程置为 completed（确定性推进不排在模型调用后面）", observed,
                            ["同一家两只宠物：猫去 harbour_cafe（攻略在 slow 通道调模型），领养伙伴去 work:florist",
                             "换挂起的模型替身，后台线程跑一轮认知线；模型被调用并挂住",
                             "挂住期间把时钟推到伙伴收工到家之后，在主线程跑一轮世界线，再读结算",
                             "放行模型后确认认知线也能收尾"],
                            source_digests("app/web_agent/ticker.py", "app/web_agent_wiring.py", JOURNEY_SRC), guard0)

    def contract_c7b_model_down_still_settles(self) -> ContractResult:
        from app.web_providers import ChatUnavailable

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        a = self.user("q-c7b-owner")
        cat = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        self._use_chat(FakeChat(error=ChatUnavailable("q-model-down")), a)
        journey_id = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "work:florist"}).json()["journey_id"]
        clock.now = self.web.journeys.repo.get(journey_id).completes_at + timedelta(minutes=1)
        self.web.journeys.advance_all(clock.now)
        observed = {"lifecycle": self.web.journeys.repo.get(journey_id).lifecycle,
                    "salary": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"web:job:{journey_id}",))[0][0],
                    "work_done_messages": self._sql("SELECT COUNT(*) FROM web_messages WHERE source_event_id = ?", (f"{journey_id}:work_done",))[0][0]}
        ok = observed == {"lifecycle": "completed", "salary": 1, "work_done_messages": 1}
        return self._result("Q-C7b", "模型不可用（立即报错）时，打工照样结算工钱、按时到家", "A01", LEVEL_INTEGRATION, "I",
                            PASS if ok else FAIL, {"lifecycle": "completed", "salary": 1, "work_done_messages": 1}, observed,
                            ["开“模型回信”，模型替身一律抛 ChatUnavailable", "出发 work:florist", "时钟越过到家时间后 advance_all"],
                            source_digests(JOURNEY_SRC), guard0)


CONTRACTS = ("c1a_queue_takeover", "c1b_reply_claim_crash", "c2_stale_results", "c3a_receipt_lost", "c3b_salary_sink_failure",
             "c4_household_isolation", "c5_revoke_in_flight", "c6_get_is_pure", "c7a_arrival_waits_for_model", "c7b_model_down_still_settles",
             "c7c_worker_blocked_by_model", "c3c_key_across_lifecycle", "c3d_takeover_race", "c8_api_link_fields",
             "c9_budget_without_tables", "c30_budget_reconcile_after_clarification", "c20_fence_stacking", "c21_voucher_same_transaction", *BOUNDARY_CONTRACTS, *MEDIA_CONTRACTS, *SCHEDULE_CONTRACTS, *RECOVERY_CONTRACTS, *PHOTO_CONTRACTS, *DIRECTOR_CONTRACTS, *CONSUMER_CONTRACTS, "c31_unknown_counts_actual_sends", "c32_note_purposes_do_not_leak", "c33_late_changes_and_legacy_payloads", "c35_paid_result_is_reclaimed_on_retry", "c36_reclaim_edge_cases", "c37_character_reclaim_edges", "c38_id_photo_reclaim_and_unknown")
