"""独立验收（工作包 Q）的可靠性合同：额度账本与付费调用边界。非测试模块（不以 test 开头），discover 不收集。

这里的用例不复用 A 或 I 的测试辅助，自己建库、自己断言前提，用来独立复核，而不是重跑别人的用例。
"""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
import uuid

from runtime_contract_harness import (BLOCKED, FAIL, GUARD, LEVEL_INTEGRATION, LEVEL_UNIT, PASS, Q_ROOT, ContractResult,
                                      source_digests)
from web_base import LUNCH_UTC, FakeClock

BUDGET_TABLES = ("web_budget_reservations", "web_budget_counters")


class ReliabilityContractCases:
    """与 web_base.WebPlatformTestBase 组合使用；只用一次性临时库，不碰任何共享数据。"""

    def contract_c9_budget_without_tables(self) -> ContractResult:
        """缺表反例（独立复核 A 的 BudgetWithoutMigrationTests）：
        ① 迁移之后两张额度表确实存在；② 在临时库里删掉之后确实不存在；③ 预占被拒且一次付费调用都没发出。"""
        from app.storage import JourneyStorage
        from app.web_platform.budget import BudgetLedger, BudgetLimit
        from app.web_platform.migrations import apply_web_migrations
        from app.web_providers.meter import ProviderMeter

        guard0 = len(GUARD.attempts)
        root = Q_ROOT / "tmp" / f"c9-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        calls: list[str] = []

        def paid_call(label: str) -> str:  # 付费调用替身：只要被调用就记一笔（本用例期望一次都不被调用）
            calls.append(label)
            return label

        try:
            storage = JourneyStorage(root / "probe.sqlite3")
            applied = apply_web_migrations(storage)
            with storage.connect() as conn:
                after_migration = sorted(r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)", BUDGET_TABLES))
                for table in BUDGET_TABLES:
                    conn.execute(f"DROP TABLE {table}")
                after_drop = sorted(r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)", BUDGET_TABLES))
            ledger = BudgetLedger(storage)
            outcome = ledger.reserve("q-c9-op-0001", provider="llm", purpose="brain",
                                     limits=[BudgetLimit("pet:q-c9:brain", 2), BudgetLimit("purpose:brain", 4)], units=1)
            denied = type(outcome).__name__ == "BudgetDenied"
            if not denied:  # 按 A 交接的接法：只有预占成功才允许真的调用
                paid_call("llm")
            expired = ledger.expire_stale()

            def usage_rows() -> int:
                with storage.connect() as conn:
                    return conn.execute("SELECT COUNT(*) FROM web_provider_usage WHERE provider = 'llm'").fetchone()[0]

            usage_after_denied = usage_rows()  # 被拒的预占不应该留下任何计量
            meter = ProviderMeter(storage, {"llm": 1})
            allows = [meter.allow("llm"), meter.allow("llm")]
            observed = {"migrations_applied": len(applied), "tables_after_migration": after_migration, "tables_after_drop": after_drop,
                        "reserve_result": type(outcome).__name__, "denied_scope": getattr(outcome, "scope", None),
                        "denied_reason": getattr(outcome, "reason", None), "paid_calls": calls, "expire_stale": expired,
                        "ledger_available": ledger.available(), "usage_rows_after_denied_reserve": usage_after_denied,
                        "provider_cap_allows": allows, "usage_rows_after_two_allows": usage_rows()}
        except sqlite3.Error as exc:
            return ContractResult("Q-C9", "缺表时额度账本明确报错、不放行付费调用", "A14、CR-A（缺表前提）", LEVEL_UNIT, "A（额度账本）", BLOCKED,
                                  "能在临时库上建库、跑迁移、删表", f"{type(exc).__name__}: {exc}", [], source_digests("app/web_platform/budget.py"),
                                  len(GUARD.attempts) - guard0)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        ok = (after_migration == sorted(BUDGET_TABLES) and after_drop == [] and denied
              and observed["denied_reason"] == "ledger_unavailable" and not calls and expired == 0
              and observed["ledger_available"] is False and usage_after_denied == 0 and allows == [True, False]
              and observed["usage_rows_after_two_allows"] == 1)
        return ContractResult(
            "Q-C9", "缺表时额度账本明确报错、不放行付费调用（前提逐条断言）", "A14、CR-A（缺表前提）", LEVEL_UNIT, "A（额度账本）",
            PASS if ok else FAIL,
            "迁移后两张表都在；临时库删表后都不在；reserve 返回 BudgetDenied(ledger_unavailable)；付费调用 0 次；被拒的预占不留计量（0 行）；"
            "expire_stale=0；available()=False；供应商每日上限仍然原子（[True, False]，放行的那次才计 1 行）",
            observed,
            ["新建一次性临时库并跑完整 web 迁移", "查 sqlite_master 断言两张额度表存在", "DROP 掉这两张表并再查一次，断言确实不存在",
             "调 BudgetLedger.reserve（按 A 的接法：被拒就不调用付费替身）", "查 expire_stale / available / web_provider_usage",
             "用 cap=1 的 ProviderMeter 连续 allow 两次"],
            source_digests("app/web_platform/budget.py", "app/web_providers/meter.py", "app/web_platform/migrations/m0050_budget.py"),
            len(GUARD.attempts) - guard0)

    # ---- Q-C20：lane_fence 的叠加语义（CR-C10）----
    def contract_c20_fence_stacking(self) -> ContractResult:
        """Q-C20：围栏是叠加的——内层不解除外层，`None` 也不解除；块异常退出后外层照旧生效；两道都过才写得进去。

        判定本身用**进程内变异**自证：把 `lane_fence` 临时换回"内层覆盖外层"的旧语义，前三条必须变红。
        只在这个测试进程里替换函数，**不改任何共享实现**（与 C 07:33、Q 06:55 同一做法）。
        """
        from app.web_platform import uow as uow_mod
        from app.web_platform.lease import LeaseLost

        guard0 = len(GUARD.attempts)
        storage = self.app.state.storage
        with storage.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS q_c20_probe (label TEXT)")  # 只用 Q 自己的表，不碰业务表
        seen: list[str] = []
        real_lane_fence = uow_mod.lane_fence

        def lease_down(conn) -> None:  # 外层：这一任期的租约已经没了
            seen.append("lease")
            raise LeaseLost("world", "taken_over")

        def version_ok(conn) -> None:  # 内层：自己那道复核是过的
            seen.append("version")

        def write(label: str) -> str:
            try:
                with uow_mod.unit_of_work(storage) as conn:
                    conn.execute("INSERT INTO q_c20_probe (label) VALUES (?)", (label,))
                return "written"
            except LeaseLost as lost:
                return f"blocked:{lost.reason}"
            except Exception as exc:  # noqa: BLE001 - 任何别的异常都要如实报出来，不吞
                return f"error:{type(exc).__name__}"

        def probe() -> dict:
            """四条判定各跑一次，返回观察值。写入目标是 Q 自己的表。"""
            seen.clear()
            with real_lane_fence(lease_down):
                with uow_mod.lane_fence(version_ok):
                    nested = write("nested")
                nested_seen = list(seen)
                with uow_mod.lane_fence(None):
                    none_inner = write("none-inner")
                try:
                    with uow_mod.lane_fence(version_ok):
                        raise RuntimeError("q-c20 内层块里抛异常退出")
                except RuntimeError:
                    pass
                after_raise = write("after-raise")
            with real_lane_fence(version_ok):  # 正常路径对照：两道都过
                with uow_mod.lane_fence(version_ok):
                    both_ok = write("both-ok")
                outer_only = write("outer-only")  # 内层退出后只剩外层，仍要写得进去
            return {"nested": nested, "nested_seen": nested_seen, "none_inner": none_inner,
                    "after_raise": after_raise, "both_ok": both_ok, "outer_only": outer_only}

        normal = probe()

        # 变异：换回旧语义（内层直接覆盖外层），前三条应当变红
        @contextlib.contextmanager
        def overriding_fence(check):
            token = uow_mod._FENCE.set(check)  # 旧写法：不管外面装了什么，直接顶掉
            try:
                yield
            finally:
                uow_mod._FENCE.reset(token)

        @contextlib.contextmanager
        def leaking_fence(check):
            if check is not None:  # 另一种旧写法：装上就不还原，块退出后外层那道回不来
                uow_mod._FENCE.set(check)
            yield

        uow_mod.lane_fence = overriding_fence
        try:
            mutated = probe()
        finally:
            uow_mod.lane_fence = real_lane_fence
        uow_mod.lane_fence = leaking_fence
        try:
            leaked = probe()
        finally:
            uow_mod.lane_fence = real_lane_fence
        restored = probe()

        checks = {
            "嵌套叠加：内层过了外层仍挡得住": normal["nested"].startswith("blocked:"),
            "嵌套叠加：外层那道确实执行过": "lease" in normal["nested_seen"],
            "None 不解除外层": normal["none_inner"].startswith("blocked:"),
            "内层块异常退出后外层照旧生效": normal["after_raise"].startswith("blocked:"),
            "正常路径对照：两道都过就写得进去": normal["both_ok"] == "written",
            "正常路径对照：内层退出后只剩外层也写得进去": normal["outer_only"] == "written",
            # 两种旧写法各能判别不同的判据，分开说：
            # ①「内层覆盖外层」只让前两条变红（第三条靠的是块退出时的还原，那一版也还原，所以判别不了）；
            # ②「装上不还原」才让第三条变红。两个变异都不改共享实现，只在本测试进程里替换。
            "变异自证①内层覆盖外层：嵌套与 None 两条变红": mutated["nested"] == "written" and mutated["none_inner"] == "written",
            "变异自证①：外层那道确实被顶掉了（没执行）": mutated["nested_seen"] == ["version"],
            "变异自证②装上不还原：异常退出那条变红": leaked["after_raise"] == "written",
            "变异自证：正常路径都不受影响（不是一律放行造成的假阳）": mutated["both_ok"] == "written" and mutated["outer_only"] == "written"
                and leaked["both_ok"] == "written" and leaked["outer_only"] == "written",
            "恢复后与变异前一致": {k: v for k, v in restored.items() if k != "nested_seen"}
                == {k: v for k, v in normal.items() if k != "nested_seen"},
        }
        return ContractResult(
            "Q-C20", "lane_fence 叠加：内层与 None 都不解除外层，异常退出后外层仍在；两道都过才写得进去", "CR-C10、CR-A4",
            LEVEL_UNIT, "C（web_platform/uow.py）", PASS if all(checks.values()) else FAIL,
            "前三条被挡下、后两条写得进去；换回旧语义后前三条变红", {"checks": checks, "normal": normal, "mutated_overriding": mutated, "mutated_leaking": leaked, "restored": restored},
            ["在一次性临时库里建一张 Q 自己的探针表，写入只往这张表写，不碰业务表",
             "外层装一道必定失败的租约检查，内层依次装：通过的检查 / None / 在块里抛异常后退出",
             "四条判定各写一次，记录被挡下还是写进去，以及外层那道有没有真的执行过",
             "正常路径对照：外层也换成通过的检查，嵌套时与内层退出后各写一次",
             "变异自证①：在**这个测试进程里**把 lane_fence 换成“内层覆盖外层”的旧写法——嵌套与 None 两条必须变红",
             "变异自证②：再换成“装上不还原”的旧写法——异常退出那条必须变红。两个变异都不改共享实现",
             "换回真实实现后再跑一遍，确认与变异前完全一致"],
            source_digests("app/web_platform/uow.py", "app/web_platform/lease.py"), len(GUARD.attempts) - guard0)

    # ---- Q-C21：借车券的核销与行程同事务（CR-C9）----
    def contract_c21_voucher_same_transaction(self) -> ContractResult:
        """Q-C21：走真实收藏服务的 `consume_in` 与正式装配——用券出发不扣租车费、券确实核销；核销之后任何一步出错，券和行程一起回滚。"""
        from app.web_platform.uow import unit_of_work

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        collection = web.collection
        real_consume_in = collection.consume_in
        cases: dict = {}

        def voucher_rows(pet_id: str) -> list:
            rows = self._sql("SELECT kind, consumed_at FROM web_collection_items WHERE pet_id = ? AND kind = 'car_voucher'", (pet_id,))
            return [{"kind": r[0], "consumed": bool(r[1])} for r in rows]

        def run(label: str, *, fail_after_consume: bool) -> None:
            owner = self.user(f"q-c21-{label}")
            owner.upload_pet("年糕", "cat")
            owner.move_in()
            from app.schemas import EconomyTransactionType

            web.economy.apply(owner.pet_id, 200, EconomyTransactionType.web_reward, f"q-grant:{owner.pet_id}",
                              reason="Q 合同备用旅费", source="q.contract")
            with unit_of_work(self.app.state.storage) as conn:  # 用真实收藏服务发券（与驾校发券同一个写法）
                collection.keepsake(conn, user_id=owner.user_id, pet_id=owner.pet_id, kind="car_voucher",
                                    title="借车券", note="Q 合同", source_event_id=f"q-c21:{label}", now=clock.now)
            web.journeys.can_drive = lambda pet_id: True  # 驾照由驾校模块发，这里只放行“会开车”这一条前置
            balance_before = web.economy.wallet(owner.pet_id).balance

            if fail_after_consume:  # 核销之后、同一个事务还没提交时出错
                def boom(conn, pet_id, kind, now=None):
                    real_consume_in(conn, pet_id, kind, now)  # 先真的核销
                    raise RuntimeError("q-c21 注入：核销之后、提交之前出错")

                collection.consume_in = boom
            try:
                response = owner.post("/journey/depart", {"destination_key": "local:drive_trip"})
                status, body = response.status_code, (response.json() if response.status_code == 200 else None)
            except Exception as exc:  # noqa: BLE001 - 注入的故障会一路抛到路由外
                status, body = type(exc).__name__, None
            finally:
                collection.consume_in = real_consume_in
            cases[label] = {"http": status, "journeys": self._sql("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?", (owner.pet_id,))[0][0],
                            "coins_spent": balance_before - web.economy.wallet(owner.pet_id).balance,
                            "travel_fee_rows": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ? AND type = 'web_travel_fee'",
                                                         (owner.pet_id,))[0][0],
                            "vouchers": voucher_rows(owner.pet_id), "journey_id": (body or {}).get("journey_id")}

        run("normal", fail_after_consume=False)
        run("fails_after_consume", fail_after_consume=True)
        ok, bad = cases["normal"], cases["fails_after_consume"]
        checks = {
            "用券出发成功": ok["http"] == 200 and ok["journeys"] == 1,
            "用券出发不扣租车费": ok["coins_spent"] == 0 and ok["travel_fee_rows"] == 0,
            "券确实被核销了": ok["vouchers"] == [{"kind": "car_voucher", "consumed": True}],
            "核销之后出错：行程没建出来": bad["journeys"] == 0,
            "核销之后出错：券跟着一起回滚（仍然可用）": bad["vouchers"] == [{"kind": "car_voucher", "consumed": False}],
            "核销之后出错：钱一分没动": bad["coins_spent"] == 0 and bad["travel_fee_rows"] == 0,
        }
        return ContractResult(
            "Q-C21", "借车券：用券出发不扣租车费且券真的核销；核销之后任一步出错，券与行程一起回滚", "CR-C9、A07",
            LEVEL_INTEGRATION, "C（journey.depart）＋ A（collection.consume_in）＋ I（凭证装配）",
            PASS if all(checks.values()) else FAIL, "正常：出发成功、0 扣费、券已核销；注入故障：0 行程、券仍可用、0 扣费",
            {"checks": checks, "cases": cases},
            ["新账号、新宠物，用**真实收藏服务**在一个写事务里发一张借车券（与驾校发券同一个写法）",
             "走正式接口 POST /journey/depart {destination_key: local:drive_trip}（正式装配，不打任何替身）",
             "故障组：把 `collection.consume_in` 包一层——先调真实实现完成核销，紧接着抛异常（只在测试进程里替换）",
             "逐项核对：HTTP 结果、行程条数、钱包变化、旅费流水、券的 consumed_at"],
            source_digests("app/web_journey/service.py", "app/web_collection/service.py", "app/web_credentials_wiring.py"),
            len(GUARD.attempts) - guard0)

    def contract_c30_budget_reconcile_after_clarification(self) -> ContractResult:
        """Q-C30：unknown／expired 之后**被明确查清**时，用量按差额回正到实际发出数，且落在**原来那个记账窗口**。

        本批只验「事后查清有没有回正路径」（A 的 `budget.py feaed33b…` 小批）。
        **不在本批范围**：unknown **当场**仍记 `actual_units=NULL`、仍按预占全额保守计入——
        那是「当场记多少」的另一项未解决设计项，协调方已指定另列小批；这里只如实记录现状，不据此判本批失败。
        """
        import threading
        from datetime import timedelta

        from app.storage import JourneyStorage
        from app.web_platform.budget import BudgetLedger, BudgetLimit
        from app.web_platform.migrations import apply_web_migrations

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        root = Q_ROOT / "tmp" / f"c30-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        day_one = clock.now.replace(hour=23, minute=50, second=0, microsecond=0)
        day_two = day_one + timedelta(minutes=20)  # 跨过 UTC 日界

        def layers(pet: str) -> list:
            # 与正式装配同形（brain_wiring.py 第 84-87 行）：每宠一层、全局一层，两层都要跟着回正
            return [BudgetLimit(f"pet:{pet}:illustration", 50), BudgetLimit("provider:image:daily", 500)]

        try:
            storage = JourneyStorage(root / "budget.sqlite3")
            apply_web_migrations(storage)
            ledger = BudgetLedger(storage)

            def used(pet: str, *, at) -> dict:
                pet_layer = ledger.usage(f"pet:{pet}:illustration", now=at)
                return {"pet": pet_layer["used"], "inflight_pet": pet_layer["inflight"],
                        "global": ledger.usage("provider:image:daily", now=at)["used"]}

            def delta(before: dict, after: dict) -> dict:
                return {key: after[key] - before[key] for key in ("pet", "global")} | {"inflight_pet": after["inflight_pet"]}

            def case(label: str, *, first: str, then: str | None, actual: int | None, clarify_at=None) -> dict:
                """预占 2 → 先落一个不确定的结果 → 再被明确查清。两层用量一律看**同一 scope 的前后差额**。

                全局那一层（`provider:image:daily`）是**所有档共用**的，看绝对值会把别档的用量算进来——
                与正式装配同形就必须按差额断言（Q-C14 踩过这个坑）。
                """
                pet, op = f"c30-{label}", f"illustration:{label}:1"
                base = used(pet, at=day_one)
                permit = ledger.reserve(op, provider="image", purpose="illustration",
                                        limits=layers(pet), units=2, now=day_one)
                if first == "expired":  # 到期没人结算：expire_stale 标成 expired，保守计入已用
                    ledger.expire_stale(now=day_one + timedelta(seconds=400))
                else:
                    ledger.settle(permit, first, actual_units=None, now=day_one)
                after_first = delta(base, used(pet, at=day_one))
                with storage.connect() as conn:  # 只采集：查清之前那一刻这行长什么样
                    early = conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations "
                                         "WHERE operation_id = ?", (op,)).fetchone()
                row_at_first = dict(zip(("status", "outcome", "actual_units"), tuple(early))) if early else {}
                if then is not None:
                    # `settle` 认的是**预占编号**，不是操作编号：查清那一次要先按操作编号取回这条预占
                    ledger.settle(ledger.get(op).reservation_id, then, actual_units=actual, now=clarify_at or day_one)
                # `BudgetReservation` 只带状态，不带 outcome / actual_units：那两列直接读库
                with storage.connect() as conn:
                    raw = conn.execute("SELECT status, outcome, actual_units, accounting_window FROM web_budget_reservations "
                                       "WHERE operation_id = ?", (op,)).fetchone()
                row = dict(zip(("status", "outcome", "actual_units", "accounting_window"), tuple(raw))) if raw else {}
                next_day = delta({"pet": 0, "global": 0, "inflight_pet": 0}, used(pet, at=day_two))
                return {"reserved_units": 2, "after_first": after_first, "row_at_first": row_at_first,
                        "after_clarified": delta(base, used(pet, at=day_one)),
                        "next_day_window": next_day if clarify_at is not None else None,
                        "row": row}

            unknown_clarified = case("unknownok", first="unknown", then="succeeded", actual=1)
            expired_clarified = case("expiredok", first="expired", then="succeeded", actual=1)
            failed_but_sent = case("failedsent", first="unknown", then="failed", actual=1)
            clarified_not_sent = case("notsent", first="unknown", then="not_sent", actual=None)
            still_unclear = case("unclear", first="unknown", then="succeeded", actual=None)
            cross_day = case("crossday", first="unknown", then="succeeded", actual=1, clarify_at=day_two)

            # 重复 ＋ 并发查清：只许调一次
            pet, op = "c30-once", "illustration:once:1"
            once_base = used(pet, at=day_one)
            permit = ledger.reserve(op, provider="image", purpose="illustration", limits=layers(pet), units=2, now=day_one)
            ledger.settle(permit, "unknown", now=day_one)
            ledger.reserve("illustration:onceother:1", provider="image", purpose="illustration",
                           limits=layers("c30-once-other"), units=3, now=day_one)
            start = threading.Barrier(2)
            errors: list[str] = []

            def clarify() -> None:
                try:
                    start.wait(timeout=10)
                    ledger.settle(ledger.get(op).reservation_id, "succeeded", actual_units=1, now=day_one)
                except Exception as exc:  # noqa: BLE001 - 线程里的异常要带回来，不能悄悄吞掉
                    errors.append(f"{type(exc).__name__}: {exc}")

            threads = [threading.Thread(target=clarify) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
            ledger.settle(ledger.get(op).reservation_id, "succeeded", actual_units=1, now=day_one)  # 再报一次：仍然只许调一次
            idempotent = {"used": delta(once_base, used(pet, at=day_one)), "thread_errors": errors,
                          "other_operation_untouched": ledger.usage("pet:c30-once-other:illustration", now=day_one),
                          "other_status": ledger.get("illustration:onceother:1").status}

            # 现状记录（**不在本批范围，不作断言**）。写成**自带绑定的实测值**而不是一句话：
            # 一句"actual_units 留空"会在实现改了之后变成错话，而合同照样全绿——
            # 记录只在它被测到的那一版上成立，所以把那一版的指纹和测到的数一起带上。
            on_the_spot = {"budget_py": source_digests("app/web_platform/budget.py")["app/web_platform/budget.py"],
                           "measured_settle_call": "settle(outcome='unknown', actual_units=None)  # 本合同只走这一条路径",
                           "used_delta_right_after_unknown": unknown_clarified["after_first"],
                           "row_right_after_unknown": unknown_clarified["row_at_first"],
                           "note": "以上为**本轮实测**：落 unknown 当场的两层用量增量与该行取值。"
                                   "属「当场记多少」那一项，本批未派、不作断言。"
                                   "**本合同从不以 actual_units≠None 落 unknown**，所以它覆盖不到那条分支的行为。"}
        finally:
            shutil.rmtree(root, ignore_errors=True)

        checks = {
            "unknown 查清为只发出 1 次：两层用量都从 2 回到 1":
                unknown_clarified["after_first"]["pet"] == unknown_clarified["after_first"]["global"] == 2
                and unknown_clarified["after_clarified"]["pet"] == unknown_clarified["after_clarified"]["global"] == 1,
            "expired 那一档同理：两层都回到 1":
                expired_clarified["after_first"]["pet"] == 2
                and expired_clarified["after_clarified"]["pet"] == expired_clarified["after_clarified"]["global"] == 1,
            "确定没画成但已知发出 1 次：记 1（失败不等于没发出）":
                failed_but_sent["after_clarified"]["pet"] == failed_but_sent["after_clarified"]["global"] == 1,
            "查清确实一次都没发出：归零（不回归对照）":
                clarified_not_sent["after_clarified"]["pet"] == clarified_not_sent["after_clarified"]["global"] == 0,
            "说不清（不给实际发出数）：维持保守的 2，不能因为回正反而少记":
                still_unclear["after_clarified"]["pet"] == still_unclear["after_clarified"]["global"] == 2,
            "跨 UTC 日查清：差额补在**原来那个记账窗口**，新一天不受影响":
                cross_day["after_clarified"]["pet"] == 1 and cross_day["next_day_window"]["pet"] == 0
                and cross_day["next_day_window"]["global"] == 0,
            "重复查清与并发两个查清同时到：只调一次":
                idempotent["used"]["pet"] == idempotent["used"]["global"] == 1 and idempotent["thread_errors"] == [],
            "不碰当天别的操作：另一笔 3 个单位的预占一动不动":
                idempotent["other_operation_untouched"]["inflight"] == 3 and idempotent["other_status"] == "reserved",
            "回正不二次扣在途：这一笔的在途回到 0，没有被扣成负数":
                unknown_clarified["after_clarified"]["inflight_pet"] == 0
                and expired_clarified["after_clarified"]["inflight_pet"] == 0,
            "查清之后这条预占如实记下确认计量": unknown_clarified["row"]["actual_units"] == 1
                and unknown_clarified["row"]["outcome"] == "succeeded",
        }
        return ContractResult(
            "Q-C30", "unknown／expired 被查清后按差额回正到实际发出数，落在原记账窗口；说不清就维持保守值",
            "COORD-Q-C30-BOUNDED、A 账本回正小批", LEVEL_UNIT, "A（budget.settle 迟到结算差额回正）",
            PASS if all(checks.values()) else FAIL,
            "unknown／expired 查清为发出 1 次 → 两层用量从 2 回到 1；确定没画成但发出过仍记 1；查清没发出归零；"
            "不给实际数则维持 2；跨 UTC 日补在原窗口；重复与并发查清只调一次；不碰别的操作、不二次扣在途",
            {"checks": checks, "unknown_clarified": unknown_clarified, "expired_clarified": expired_clarified,
             "failed_but_sent": failed_but_sent, "clarified_not_sent": clarified_not_sent, "still_unclear": still_unclear,
             "cross_day": cross_day, "idempotent": idempotent, "out_of_scope_observation": on_the_spot},
            ["一次性临时库＋迁移，用**真实的** BudgetLedger；两层额度与正式装配同形（每宠一层＋全局一层）",
             "每档都先预占 2 个单位，再落一个不确定的结果（unknown，或到期后 expire_stale 标成 expired）",
             "然后以明确结果查清：succeeded/actual_units=1、failed/actual_units=1、not_sent、以及**不给** actual_units",
             "跨日那档：23:50 预占并落 unknown，次日 00:10 才查清——核对差额补在**原窗口**、新一天为 0",
             "重复查清＋两个线程同时查清（Barrier 对齐）：核对只调一次、两个线程都没抛异常",
             "同一天另起一笔 3 个单位的预占作旁证：回正不得碰到它",
             "**不在本批范围**：「当场记多少」是另一项设计项。本合同只把**那一版的实测值连同其指纹**记在 "
             "out_of_scope_observation 里，不作断言、不据此判本批失败",
             "**覆盖边界**：本合同落 unknown 时**一律传 actual_units=None**，因此**覆盖不到**"
             "「以 actual_units≠None 落 unknown」那条分支——该分支的行为改动，本合同会安静地继续绿",
             "**未证明**：真实供应商的计费；这里只证明本地账本的记账口径",
             "**顺带记下的接线现状**：`settle` 认的是预占编号而非操作编号，查清方必须先按操作编号取回这条预占"],
            source_digests("app/web_platform/budget.py", "app/web_agent/brain_wiring.py", "app/web_journey/illustrations.py"),
            len(GUARD.attempts) - guard0)
