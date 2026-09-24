"""独立验收（工作包 Q）：`unknown` 当场按**实际发出次数**计量的新语义（Q-C31）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。

被测的是 A 于 14:02 署名交付的 `budget.py bd0312d46f7acc9b`：
落 `unknown` 时不再一律按预占全额计，改按**调用方报告的已发出次数**计（上限取预占量）；
报不出次数（`actual_units is None`）才退回保守计入预占全额。

**Q-C30 覆盖不到这条分支**——它落 unknown 时一律传 `actual_units=None`，走的恰好是没被改动的那一支。
所以本合同独立新写，不改 C30、不重跑旧合同全集。

**两个层面都要走到**：
  ① 账本层：直接对真实 `BudgetLedger` 下各种结算次序，三层用量一律按**同一 scope 的前后差额**断言；
  ② **组合链路**：正式装配 ＋ 替身生图，让**真实调用方**把次数传进来——
     只在账本方法上直接传 1 会漏掉"链路到底传没传、传得对不对"。
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import uuid
from datetime import timedelta

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, Q_ROOT, ContractResult, source_digests
from web_base import LUNCH_UTC, FakeClock

C31_SOURCES = ("app/web_platform/budget.py", "app/web_agent/brain_wiring.py", "app/web_journey/illustrations.py")
# 与正式装配同形的三层（`brain_wiring.reserve_image` ＋ 账本自动追加的不设上限用量层）
PET_SCOPE, PROVIDER_SCOPE, USAGE_SCOPE = "pet:{pet}:illustration", "provider:image:daily", "usage:image:illustration"
LAYERS = ("pet", "provider", "usage")
# Q-C35 的实现面：**两条链路都要列全**。角色那半加进来之后忘了列 ，
# 结果就是 drift 检查看不见它、证据里也不记它绑的哪一版——那是一条静默通过的检查。
C35_SOURCES = ("app/web_journey/illustrations.py", "app/web_character/service.py",
               "app/web_character/poses.py", "app/web_platform/budget.py",
               "app/web_agent/brain_wiring.py", "app/web_platform/tasks.py")


class MeteringContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql`、`_use_illustrator` 由同组的用例提供）。"""

    def _c31_usage(self, ledger, pet: str, *, at) -> dict:
        """三层用量的当前值。**只用来算差额**——全局层与用量层是所有档共用的，绝对值没有意义。"""
        rows = {"pet": ledger.usage(PET_SCOPE.format(pet=pet), now=at), "provider": ledger.usage(PROVIDER_SCOPE, now=at),
                "usage": ledger.usage(USAGE_SCOPE, now=at)}
        return {f"{name}_{field}": rows[name][field] for name in LAYERS for field in ("used", "inflight")}

    def _c31_row(self, storage, op: str) -> dict:
        with storage.connect() as conn:
            raw = conn.execute("SELECT status, outcome, actual_units, reserved_units, accounting_window "
                               "FROM web_budget_reservations WHERE operation_id = ?", (op,)).fetchone()
        return dict(zip(("status", "outcome", "actual_units", "reserved_units", "accounting_window"), tuple(raw))) if raw else {}

    def _c31_real_chain(self, clock) -> dict:
        """② 组合链路：正式装配 ＋ 替身生图，让**真实调用方**把发出次数传给账本。

        选的是**世界事件里的冒险插画**那条（没有 `scene_key`，不走照片导演的闸门）——
        宠物**没有主人照片**，所以这一次预占 2 个单位：先画一张证件照当参考，再画正图。
        让**证件照那一次超时**：真实链路会算出 `sent=1`（场景图根本没发），
        由 `_settle_calls` 把 1 传给账本。**不是我直接调 `settle(…, 1)`**——那样测不到链路传没传。
        """
        from app.web_platform.budget import BudgetLedger

        ledger = BudgetLedger(self.app.state.storage)
        # 替身要在**出发之前**换好：事件发生那一刻链路会问供应商可不可用，不可用就根本不排这张图
        art = self._use_illustrator("timeout")  # 第一次 render（证件照）就超时：已发出、结果不明
        owner, _message, task_id = self._photo_journey("q-c31-chain", clock)
        pet = owner.pet_id
        econ = "SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ?"
        before, econ_before = self._c31_usage(ledger, pet, at=clock.now), self._sql(econ, (pet,))[0][0]
        wallet_before = self._sql("SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ? AND status = 'applied'", (pet,))[0][0]

        self.web.illustrations.run_pending()
        after = self._c31_usage(ledger, pet, at=clock.now)
        rows = self._sql("SELECT operation_id, status, outcome, actual_units, reserved_units FROM web_budget_reservations "
                         "WHERE operation_id LIKE ? ORDER BY rowid", (f"illustration:{task_id}:%",))
        row = dict(zip(("operation_id", "status", "outcome", "actual_units", "reserved_units"), rows[0])) if rows else {}
        dispatched = art.dispatched

        for _ in range(3):  # 结果不明不该自动重发：再跑几轮也不多发、不多占
            clock.advance(minutes=20)
            self.web.illustrations.run_pending()
        more = self._sql("SELECT COUNT(*) FROM web_budget_reservations WHERE operation_id LIKE ?", (f"illustration:{task_id}:%",))[0][0]

        return {"task_id": task_id, "dispatched": dispatched, "row": row, "reservations": len(rows),
                "used_delta": tuple(after[f"{name}_used"] - before[f"{name}_used"] for name in LAYERS),
                "inflight_delta": tuple(after[f"{name}_inflight"] - before[f"{name}_inflight"] for name in LAYERS),
                "dispatched_after_more_rounds": art.dispatched, "reservations_after_more_rounds": more,
                "task_status": (self._sql("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,)) or [(None, None)])[0],
                "economy_rows_delta": self._sql(econ, (pet,))[0][0] - econ_before,
                "wallet_delta": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ? AND status = 'applied'",
                                          (pet,))[0][0] - wallet_before}

    def contract_c31_unknown_counts_actual_sends(self) -> ContractResult:
        """Q-C31：`unknown` 当场按实际发出次数计量；三层用量各自只多记那几次，组合链路上也如此。"""
        from app.storage import JourneyStorage
        from app.web_platform.budget import BudgetLedger, BudgetLimit
        from app.web_platform.migrations import apply_web_migrations

        guard0 = len(GUARD.attempts)
        started = source_digests(*C31_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        root = Q_ROOT / "tmp" / f"c31-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        day_one = clock.now.replace(hour=23, minute=50, second=0, microsecond=0)
        day_two = day_one + timedelta(minutes=20)  # 跨过 UTC 日界

        try:
            storage = JourneyStorage(root / "budget.sqlite3")
            apply_web_migrations(storage)
            ledger = BudgetLedger(storage)

            def layers(pet: str) -> list:
                return [BudgetLimit(PROVIDER_SCOPE, 5000), BudgetLimit(PET_SCOPE.format(pet=pet), 500)]

            def delta(before: dict, after: dict) -> dict:
                return {k: after[k] - before[k] for k in before}

            def case(label: str, *, sent, then=None, clarified=None, at=None, clarify_at=None, history_null=False) -> dict:
                """预占 2 → 落 unknown（带或不带次数）→ 可选地再查清。三层用量一律按前后差额记。"""
                pet, op, when = f"c31-{label}", f"illustration:{label}:1", at or day_one
                base = self._c31_usage(ledger, pet, at=when)
                permit = ledger.reserve(op, provider="image", purpose="illustration",
                                        limits=layers(pet), subject_scope=f"pet:{pet}", units=2, now=when)
                ledger.settle(permit, "unknown", actual_units=sent, now=when)
                after_unknown = delta(base, self._c31_usage(ledger, pet, at=when))
                row_at_unknown = self._c31_row(storage, op)
                if history_null:  # 模拟迁移前落下的旧行：那时 unknown 不写 actual_units
                    raw_conn = sqlite3.connect(root / "budget.sqlite3")  # 只改 Q 自己的一次性临时库
                    try:
                        with raw_conn:
                            raw_conn.execute("UPDATE web_budget_reservations SET actual_units = NULL WHERE operation_id = ?", (op,))
                    finally:
                        raw_conn.close()
                if then is not None:
                    ledger.settle(ledger.get(op).reservation_id, then, actual_units=clarified, now=clarify_at or when)
                return {"reserved": 2, "after_unknown": after_unknown, "row_at_unknown": row_at_unknown,
                        "after_clarified": delta(base, self._c31_usage(ledger, pet, at=when)),
                        "next_day": self._c31_usage(ledger, pet, at=day_two) if clarify_at is not None else None,
                        "row": self._c31_row(storage, op)}

            reported_one = case("reported1", sent=1)                                     # 核心：报 1 → 只记 1
            unreported = case("unreported", sent=None)                                   # 保守对照：报不出 → 记 2
            clarified_one = case("clar1", sent=1, then="succeeded", clarified=1)         # 查清仍是 1 → 不动
            clarified_two = case("clar2", sent=1, then="succeeded", clarified=2)         # 查清是 2 → 补到 2
            clarified_none = case("clar0", sent=1, then="not_sent", clarified=None)      # 查清没发出 → 回 0
            cross_day = case("crossday", sent=1, then="succeeded", clarified=2, clarify_at=day_two)
            # 历史行必须**忠实**模拟：旧代码落 unknown 时按预占全额计、且不写 actual_units。
            # 若造成"只计了 1 却记着 NULL"，那是旧代码**产生不出来**的状态——对不可能的输入断言，
            # 得到的红是我自己造的，不是实现的。所以这一档先以 sent=None 计满 2，再把列改成 NULL。
            legacy_null = case("legacy", sent=None, then="succeeded", clarified=1, history_null=True)

            # 超报封顶：报 5、预占 2 → 记 2，并且**留下可查的痕迹**（不静默吞掉）
            pet, op = "c31-over", "illustration:over:1"
            base = self._c31_usage(ledger, pet, at=day_one)
            permit = ledger.reserve(op, provider="image", purpose="illustration",
                                    limits=layers(pet), subject_scope=f"pet:{pet}", units=2, now=day_one)
            with self.assertLogs("petsoul.web.budget", level=logging.WARNING) as caught:
                ledger.settle(permit, "unknown", actual_units=5, now=day_one)
            over_report = {"after": delta(base, self._c31_usage(ledger, pet, at=day_one)),
                           "row": self._c31_row(storage, op),
                           "warned": any("more than reserved" in line for line in caught.output),
                           "warning_names_operation": any(op in line for line in caught.output)}

            # 重复查清 ＋ 并发两个查清同时到：只许调一次
            pet, op = "c31-once", "illustration:once:1"
            base = self._c31_usage(ledger, pet, at=day_one)
            permit = ledger.reserve(op, provider="image", purpose="illustration",
                                    limits=layers(pet), subject_scope=f"pet:{pet}", units=2, now=day_one)
            ledger.settle(permit, "unknown", actual_units=1, now=day_one)
            start, errors = threading.Barrier(2), []

            def clarify() -> None:
                try:
                    start.wait(timeout=10)
                    ledger.settle(ledger.get(op).reservation_id, "succeeded", actual_units=2, now=day_one)
                except Exception as exc:  # noqa: BLE001 - 线程里的异常要带回来
                    errors.append(f"{type(exc).__name__}: {exc}")

            threads = [threading.Thread(target=clarify) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
            ledger.settle(ledger.get(op).reservation_id, "succeeded", actual_units=2, now=day_one)  # 再报一次
            idempotent = {"after": delta(base, self._c31_usage(ledger, pet, at=day_one)),
                          "thread_errors": errors, "row": self._c31_row(storage, op)}
        finally:
            shutil.rmtree(root, ignore_errors=True)

        chain = self._c31_real_chain(clock)  # ② 组合链路：正式装配 ＋ 替身生图

        def used(scenario: dict, field: str = "after_unknown") -> tuple:
            return tuple(scenario[field][f"{name}_used"] for name in LAYERS)

        def inflight(scenario: dict, field: str = "after_unknown") -> tuple:
            return tuple(scenario[field][f"{name}_inflight"] for name in LAYERS)

        checks = {
            "报了发出 1 次：三层用量各只多记 1（不是预占的 2）": used(reported_one) == (1, 1, 1),
            "报了发出 1 次：在途三层都正确释放（回 0）": inflight(reported_one) == (0, 0, 0),
            "报了发出 1 次：行上如实记 1、状态是 unknown": (reported_one["row_at_unknown"]["actual_units"],
                                                          reported_one["row_at_unknown"]["outcome"]) == (1, "unknown"),
            "报不出次数：仍按预占全额保守计 2（对照，不因新语义而少记）": used(unreported) == (2, 2, 2),
            "查清仍是 1：三层都停在 1，不重复计量": used(clarified_one, "after_clarified") == (1, 1, 1),
            "查清其实发了 2：三层补到 2": used(clarified_two, "after_clarified") == (2, 2, 2),
            "查清一次都没发出：三层归零": used(clarified_none, "after_clarified") == (0, 0, 0),
            "跨 UTC 日查清：差额补在原记账窗口，新一天不受影响":
                used(cross_day, "after_clarified") == (2, 2, 2)
                and tuple(cross_day["next_day"][f"{n}_used"] for n in LAYERS) == (0, 0, 0)
                and cross_day["row"]["accounting_window"] == day_one.date().isoformat(),
            "历史行（actual_units 为 NULL）兼容：对着预占量算差额，不出负数":
                used(legacy_null, "after_clarified") == (1, 1, 1) and legacy_null["row"]["actual_units"] == 1,
            "超报封顶：报 5、预占 2 → 只记 2，行上也是 2":
                tuple(over_report["after"][f"{n}_used"] for n in LAYERS) == (2, 2, 2)
                and over_report["row"]["actual_units"] == 2,
            "超报**可观测**：留下一条点名该操作的告警，不静默吞掉":
                over_report["warned"] and over_report["warning_names_operation"],
            "重复查清与并发两个查清同时到：只调一次":
                tuple(idempotent["after"][f"{n}_used"] for n in LAYERS) == (2, 2, 2) and idempotent["thread_errors"] == [],
            # ② 组合链路：不是在账本方法上直接传 1，是让**真实调用方**把次数传进来
            "组合链路：证件照超时、场景图根本没发 → 账本只记 1": chain["used_delta"] == (1, 1, 1),
            "组合链路：确实只越过发送边界 1 次，且预占是 2": (chain["dispatched"], chain["row"]["reserved_units"]) == (1, 2),
            "组合链路：行上 outcome=unknown 且 actual_units=1（次数真的传到了账本）":
                (chain["row"]["outcome"], chain["row"]["actual_units"]) == ("unknown", 1),
            "组合链路：在途释放干净": chain["inflight_delta"] == (0, 0, 0),
            "组合链路：结果不明**不自动重发**（再跑几轮 worker 也不多发、不多占）":
                chain["dispatched_after_more_rounds"] == chain["dispatched"]
                and chain["reservations_after_more_rounds"] == 1,
            "组合链路：不动宠物的金币账与钱包": chain["economy_rows_delta"] == 0 and chain["wallet_delta"] == 0,
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C31_SOURCES),
        }
        return ContractResult(
            "Q-C31", "unknown 当场按实际发出次数计量：三层用量各只多记发出的那几次；组合链路上次数真的传到了账本",
            "用户 14:02 直派、A 署名交付 budget.py bd0312d4", LEVEL_INTEGRATION, "A（budget.settle 计量语义）",
            PASS if all(checks.values()) else FAIL,
            "预占 2、报发出 1 → 每宠/供应商/用量三层各只多记 1，在途归零，行上记 1；报不出次数仍保守记 2；"
            "查清为 1/2/not_sent 差额正确、重复与并发查清只调一次；跨日补原窗口；历史 NULL 兼容；超报封顶且有告警；"
            "正式装配上证件照超时、场景图未发时账本只记 1，且不自动重发、不动金币账",
            {"checks": checks, "reported_one": reported_one, "unreported": unreported, "clarified_one": clarified_one,
             "clarified_two": clarified_two, "clarified_none": clarified_none, "cross_day": cross_day,
             "legacy_null": legacy_null, "over_report": over_report, "idempotent": idempotent, "real_chain": chain,
             "digests_at_start": started, "digests_at_end": source_digests(*C31_SOURCES)},
            ["① 账本层：一次性临时库＋迁移＋**真实 BudgetLedger**；三层与正式装配同形"
             "（`pet:<id>:illustration` ＋ `provider:image:daily` ＋ 账本自动追加的 `usage:image:illustration`）",
             "每档先预占 2，再落 unknown（带次数／不带次数），必要时再以明确结果查清；"
             "三层用量**一律按同一 scope 的前后差额**断言——全局层与用量层所有档共用，绝对值没有意义",
             "历史行那档：**先按旧行为计满预占量**（sent=None）再把该行 `actual_units` 改成 NULL，才是迁移前旧行的忠实状态；"
             "造成「只计 1 却记 NULL」是旧代码产生不出来的状态，对它断言得到的红是自己造的",
             "超报那档：报 5、预占 2，用 `assertLogs` 捕获 `petsoul.web.budget` 的 WARNING，核对它点名了该操作",
             "并发那档：两个线程用 Barrier 对齐同时查清，另加一次重复上报",
             "② **组合链路**：正式装配 ＋ 替身生图，宠物**没有主人照片**（所以预占 2＝证件照＋场景图），"
             "让证件照那一次超时——由**真实调用方** `_settle_calls` 把发出次数传给账本，不是我直接传 1",
             "组合链路另核：再跑几轮 worker 不多发也不多占；宠物的金币流水与钱包余额前后不变",
             "**未证明**：真实供应商的计费；这里只证明本地账本的记账口径"],
            source_digests(*C31_SOURCES), len(GUARD.attempts) - guard0)


    # ---- Q-C35：付费成功但结果没写进去，重试不许再付一次 ----
    def _c35_inject_once(self, holder, name: str) -> dict:
        """把发布那一步包一层：**第一次调用时抛异常**，之后放行。

        注入点选在 `queue.fenced(claim)` 的**事务体内**——此刻付费调用**已经成功返回并结算过**，
        抛出去会让这次领取的写入整批回滚、任务排回队。造出的正是那个状态：
        **钱付了、图拿到了、记录没写成**。
        **不是让调用失败**——调用失败重试不会多付钱，那条不是本合同要验的。
        """
        real = getattr(holder, name)  # 先读：属性没了会当场炸，不会静默挂一个新属性上去
        state = {"fired": 0, "name": name}

        def wrapped(*args, **kwargs):
            if state["fired"] == 0:
                state["fired"] += 1
                raise RuntimeError(f"Q-C35 注入：{name} 第一次写入失败（付费已成功）")
            return real(*args, **kwargs)

        setattr(holder, name, wrapped)
        state["restore"] = lambda: setattr(holder, name, real)
        return state

    def _c35_reservations(self, prefix: str) -> list:
        return [dict(zip(("operation_id", "status", "outcome", "actual_units"), r)) for r in self._sql(
            "SELECT operation_id, status, outcome, actual_units FROM web_budget_reservations "
            "WHERE operation_id LIKE ? ORDER BY rowid", (f"{prefix}%",))]


    def _c35_character_case(self, label: str, clock, *, inject: bool, fail_reason: str | None = None) -> dict:
        """角色链路：一只带原照的猫上传后会排一张中性站姿；与插画同形地注入"写入失败"。

        注入点是 `web.character._publish_in`（`queue.fenced(claim)` 的事务体内）——
        与插画的 `_commit` 同一位置：付费调用**已经成功返回并结算过**，抛出去让写入整批回滚。
        """
        from character_fakes import FakeCharacterIllustrator
        from web_base import tiny_png

        web = self.web
        art = FakeCharacterIllustrator(fail_reason=fail_reason)
        art.available = True
        web.character.illustrator = art  # 先读后写：属性没了会当场炸（见 `_c35_inject_once` 同理）
        owner = self.user(f"q-c35-{label}")
        first = owner.upload_pet("先建家", "cat", photo=None)  # 不带照片的那只不会排队
        assert first.status_code == 201, first.text
        household_id = web.households.memberships(owner.user_id)[0].household_id
        created = owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=household_id)
        assert created.status_code == 201, created.text
        pet_id = created.json()["pet_id"]
        rows = self._sql("SELECT asset_id, task_id FROM web_pet_characters WHERE pet_id = ? ORDER BY rowid", (pet_id,))
        assert rows, "带原照的宠物上传之后应当排一张中性站姿"
        asset_id, task_id = rows[0]

        def snapshot() -> dict:
            state = self._sql("SELECT state, reason, rel_path FROM web_pet_characters WHERE asset_id = ?", (asset_id,))
            return {"calls": art.calls, "reservations": self._c35_reservations(f"character:{task_id}:"),
                    "state": state[0][0] if state else None, "reason": state[0][1] if state else None,
                    "rel_path": state[0][2] if state else None,
                    "task": (self._sql("SELECT status, attempts, last_error FROM web_tasks WHERE task_id = ?", (task_id,))
                             or [(None, None, None)])[0]}

        hook = self._c35_inject_once(web.character, "_publish_in") if inject else None
        try:
            web.character.run_pending(limit=1)
        finally:
            if hook is not None:
                hook["restore"]()
        first_state = snapshot()
        for _ in range(3):  # 排回队的任务有退避；推时钟让重试真的轮得到
            clock.advance(minutes=10)
            web.character.run_pending(limit=1)
        after = snapshot()
        return {"task_id": task_id, "asset_id": asset_id, "injection_fired": hook["fired"] if hook else 0,
                "first": first_state, "after_retry": after,
                "extra_sends_on_retry": after["calls"] - first_state["calls"]}

    def contract_c35_paid_result_is_reclaimed_on_retry(self) -> ContractResult:
        """Q-C35：付费调用已成功、结果却没写进去——重试时必须认领上一次的结果，**不许再付一次**。

        用户直派、A 修恢复逻辑、Q 用**禁网故障注入**复验。当前实现预期**红**：
        `illustrations.py:50` 的 `UNCONFIRMED_RESERVATION_STATUSES = ("reserved","unknown","expired")`
        **不含 `settled`**，所以"已付费且成功"的那一次不算"可能已发出"，重试会再发一次。
        """
        guard0 = len(GUARD.attempts)
        started = source_digests(*C35_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        from web_base import tiny_png

        def one_photo(label: str, *, fail_reason: str | None):
            """一位主人、一只**有原照**的宠物（所以一次尝试只发一次），下一张主动拍照命令。"""
            art = self._use_illustrator(fail_reason)
            owner = self.user(f"q-c35-{label}")
            owner.upload_pet("年糕", "cat", photo=tiny_png())
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            created = self._photo_request(owner, owner.pet_id, "home", key=f"q-c35-{label}")
            assert created.status_code == 200, created.text
            task_id = created.json()["task_id"]
            self._park_other_tasks(task_id)
            return owner, task_id, art

        def illustration_case(label: str, *, inject: bool, fail_reason: str | None = None) -> dict:
            owner, task_id, art = one_photo(label, fail_reason=fail_reason)
            hook = self._c35_inject_once(web.illustrations, "_commit") if inject else None
            try:
                web.illustrations.run_pending()
            finally:
                if hook is not None:
                    hook["restore"]()
            first = {"dispatched": art.dispatched, "reservations": self._c35_reservations(f"illustration:{task_id}:"),
                     "task": (self._sql("SELECT status, attempts, last_error FROM web_tasks WHERE task_id = ?", (task_id,))
                              or [(None, None, None)])[0],
                     "illustration": (self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))
                                      or [("-",)])[0][0],
                     "rel_path": (self._sql("SELECT rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))
                                  or [(None,)])[0][0]}
            for _ in range(3):  # 排回队的任务有退避；推时钟让重试真的轮得到（此处没有 worker 线程在跑）
                clock.advance(minutes=10)
                web.illustrations.run_pending()
            after = {"dispatched": art.dispatched, "reservations": self._c35_reservations(f"illustration:{task_id}:"),
                     "task": (self._sql("SELECT status, attempts, last_error FROM web_tasks WHERE task_id = ?", (task_id,))
                              or [(None, None, None)])[0],
                     "illustration": (self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))
                                      or [("-",)])[0][0],
                     "rel_path": (self._sql("SELECT rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))
                                  or [(None,)])[0][0]}
            return {"task_id": task_id, "injection_fired": hook["fired"] if hook else 0,
                    "first": first, "after_retry": after,
                    "extra_sends_on_retry": after["dispatched"] - first["dispatched"]}

        paid = illustration_case("paid", inject=True)                       # 付费成功 → 写入失败 → 重试
        not_sent = illustration_case("notsent", inject=False,               # 对照：**根本没发出去**
                                     fail_reason="provider_error")
        role_paid = self._c35_character_case("rolepaid", clock, inject=True)  # 角色链路同形

        def settled_ok(rows: list) -> bool:
            return bool(rows) and rows[0]["status"] == "settled" and rows[0]["outcome"] == "succeeded"

        checks = {
            # —— 前提：先证明"确实付过费、且写入确实失败了"，否则下面的断言什么也不是 ——
            "注入确实命中（发布那一步真的抛了一次）": paid["injection_fired"] == 1,
            "第一次确实发出过付费调用（替身计数 ≥ 1）": paid["first"]["dispatched"] >= 1,
            "第一次确实**结算成功**（钱付了：settled / succeeded）": settled_ok(paid["first"]["reservations"]),
            "第一次的结果确实没写进去（插画没落到 ready）": paid["first"]["illustration"] != "ready",
            # —— 目标行为（A 修之前预期红）——
            "重试**没有再付一次**（发送次数不变）": paid["extra_sends_on_retry"] == 0,
            "重试只留一笔预占（没有为重试再占一次）": len(paid["after_retry"]["reservations"]) == 1,
            "重试认领了上一次已经付费的结果（最终 ready）": paid["after_retry"]["illustration"] == "ready",
            # —— 正向对照：确实没发出去的那一类，重试照常再发（修复不能做成"一律不重试"）——
            "对照：确实没发出（not_sent）时，第一次不计费":
                bool(not_sent["first"]["reservations"])
                and not_sent["first"]["reservations"][0]["outcome"] == "not_sent",
            "对照：确实没发出时，重试**照常再发**": not_sent["extra_sends_on_retry"] >= 1,
            # —— 角色链路：与插画同形，同样四条前提 ＋ 两条目标 ——
            "角色：注入确实命中": role_paid["injection_fired"] == 1,
            "角色：第一次确实发出过付费调用": role_paid["first"]["calls"] >= 1,
            "角色：第一次确实**结算成功**": settled_ok(role_paid["first"]["reservations"]),
            "角色：第一次的结果确实没写进去（没落到 ready）": role_paid["first"]["state"] != "ready",
            "角色：重试**没有再付一次**": role_paid["extra_sends_on_retry"] == 0,
            "角色：重试只留一笔预占": len(role_paid["after_retry"]["reservations"]) == 1,
            # —— 已付费却认领不了时的**现状记录**：不重付是达成了，但那张图被丢弃 ——
            # **让"认领"这件事本身可判**：发布出来的必须是**第一次那张**（文件名带 `-1`），
            # 不是重画的 `-2`。没有这一条的话，"最终 ready"修前修后都绿，什么也分不出来。
            "插画：发布的是**第一次**那张（相对路径带 -1）":
                (paid["after_retry"]["rel_path"] or "").endswith("-1.png"),
            "角色：发布的是**第一次**那张（相对路径带 -1）":
                (role_paid["after_retry"]["rel_path"] or "").endswith("-1.png"),
            # 与"没有新预占"分开：这一条看的是**这个任务名下真正计过的量**有没有涨
            "两条链路：这个任务计过的单位数没有增加（不是只看预占条数）":
                sum(int(r["actual_units"] or 0) for r in paid["after_retry"]["reservations"])
                == sum(int(r["actual_units"] or 0) for r in paid["first"]["reservations"])
                and sum(int(r["actual_units"] or 0) for r in role_paid["after_retry"]["reservations"])
                == sum(int(r["actual_units"] or 0) for r in role_paid["first"]["reservations"]),
            "两条链路都没有把未认领的付费结果当成功发布":
                paid["after_retry"]["illustration"] in ("ready", "failed")
                and role_paid["after_retry"]["state"] in ("ready", "failed"),
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动":
                started == source_digests(*C35_SOURCES),
        }
        return ContractResult(
            "Q-C35", "付费调用已成功、结果没写进去：重试必须认领上一次的结果，不许再付一次（插画 ＋ 角色两条链路）",
            "用户直派（A 修恢复、Q 禁网故障注入复验）", LEVEL_INTEGRATION, "A（插画链路的结果恢复）",
            PASS if all(checks.values()) else FAIL,
            "注入发布失败后：第一次确实发出并结算成功、结果没落库；重试不再发第二次、不再多占一笔、"
            "并认领上一次的结果落到 ready；而确实没发出的那一类重试照常再发",
            {"checks": checks, "paid_then_write_failed": paid, "not_sent_control": not_sent,
             "character_paid_then_write_failed": role_paid, "digests_at_start": started},
            ["一位主人、一只**带原照**的宠物（所以一次尝试只发一次），走正式接口 POST /pets/{pet}/photo-request",
             "**故障注入在发布那一步**（`illustrations._commit`）：第一次调用抛异常——"
             "此刻付费调用**已经成功返回并结算过**，抛出去让这次领取的写入整批回滚、任务排回队",
             "**注入的是「写入失败」不是「调用失败」**：调用失败重试不会多付钱，那条不是本合同要验的",
             "推时钟让退避过去，再跑几轮 worker，核对重试有没有再发一次付费调用",
             "**前提断言**：注入命中、第一次确实发出过、第一次确实 settled/succeeded、结果确实没落 ready",
             "**正向对照**：另一档用 `provider_error`（确实没发出去）——它的重试**必须**照常再发，"
             "否则修复就成了「一律不重试」",
             "**角色链路同形**：注入 `web_character._publish_in`（同样在 `queue.fenced(claim)` 事务体内），"
             "带原照的宠物上传后会排一张中性站姿，四条前提与两条目标断言与插画一一对应",
             "**记录而非要求**：已付费却认领不了时，达成的是「不重复付费」，代价是**那张付过钱的图被丢弃**——"
             "两件事要分开看，别让「钱没多花、测试全绿」盖住「磁盘上还躺着一张没人认领的图」",
             "**未覆盖**：重复失败时的认领幂等（第二次也发布失败 → 第三次仍应认领而不是回到付费）；"
             "小票被删／图被改的两条负例；账本用量增量单独断言——待 A 交付后一并补"],
            source_digests(*C35_SOURCES),
            len(GUARD.attempts) - guard0)


    # ---- Q-C36：认领这条路的四个边界 ----
    def _c36_inject(self, holder, name: str, times: int) -> dict:
        """把发布那一步包一层：**前 `times` 次调用抛异常**，之后放行。"""
        real = getattr(holder, name)  # 先读后写：属性没了会当场炸
        state = {"fired": 0}

        def wrapped(*args, **kwargs):
            if state["fired"] < times:
                state["fired"] += 1
                raise RuntimeError(f"Q-C36 注入：{name} 第 {state['fired']} 次写入失败（付费已成功）")
            return real(*args, **kwargs)

        setattr(holder, name, wrapped)
        state["restore"] = lambda: setattr(holder, name, real)
        return state

    def _c36_photo(self, label: str, *, fail_reason: str | None = None):
        """一位主人、一只**带原照**的宠物（一次尝试只发一次），下一张主动拍照命令。"""
        from web_base import tiny_png

        art = self._use_illustrator(fail_reason)
        owner = self.user(f"q-c36-{label}")
        owner.upload_pet("年糕", "cat", photo=tiny_png())
        owner.move_in()
        assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
        created = self._photo_request(owner, owner.pet_id, "home", key=f"q-c36-{label}")
        assert created.status_code == 200, created.text
        body = created.json()
        self._park_other_tasks(body["task_id"])
        return owner, body["task_id"], body["request_id"], art

    def _c36_state(self, task_id: str, art) -> dict:
        rows = self._sql("SELECT status, rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))
        return {"dispatched": art.dispatched, "reservations": self._c35_reservations(f"illustration:{task_id}:"),
                "illustration": rows[0][0] if rows else "-", "rel_path": rows[0][1] if rows else None,
                "task": (self._sql("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,))
                         or [(None, None)])[0]}

    def _c36_receipt_of(self, task_id: str, attempt: int) -> "Path":
        """那一次尝试的小票路径：图是 `<id>-<attempt>.png`，小票在同一个 stem 上。"""
        from pathlib import Path as _Path

        row = self._sql("SELECT illustration_id, user_id FROM web_illustrations WHERE task_id = ?", (task_id,))
        illustration_id, user_id = row[0]
        root = _Path(self.settings.web_private_media_dir)
        return root / "illustrations" / user_id / f"{illustration_id}-{attempt}.receipt.json"

    def contract_c36_reclaim_edge_cases(self) -> ContractResult:
        """Q-C36：认领这条路的四个边界——重画仍认领、无可认领时照旧付费、小票/图不对时不认领不重付、丢租约。

        这四条 A 有自己的用例并全绿；**那是它的自证，不是独立验收**。本合同用**禁网故障注入**各走一遍。
        """
        guard0 = len(GUARD.attempts)
        started = source_digests(*C35_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web

        def rounds(n: int = 3, *, limit: int | None = None) -> None:
            for _ in range(n):
                clock.advance(minutes=10)
                web.illustrations.run_pending() if limit is None else web.illustrations.run_pending(limit=limit)

        # ① 认领后发布**又**失败 → 任务终态 → 主人重画 → 第三次**仍然认领**（不付费）
        owner, task_id, request_id, art = self._c36_photo("redraw")
        hook = self._c36_inject(web.illustrations, "_commit", times=2)
        try:
            web.illustrations.run_pending()
            rounds()
        finally:
            hook["restore"]()
        before_redraw = self._c36_state(task_id, art)
        redraw = owner.post(f"/pets/{owner.pet_id}/photo-requests/{request_id}/retry-image")
        rounds()
        redraw_claims = {"injections": hook["fired"], "before_redraw": before_redraw, "redraw_http": redraw.status_code,
                         "after": self._c36_state(task_id, art)}

        # ② 没有可认领的东西时，重画**照旧**是一次新的付费尝试（防"修成一律不重画"）
        owner2, task2, request2, art2 = self._c36_photo("nothing", fail_reason="timeout")
        web.illustrations.run_pending()
        rounds()
        before2 = self._c36_state(task2, art2)
        self._use_illustrator(None)  # 重画这次供应商正常
        art2b = self.web.illustrations.illustrator
        redraw2 = owner2.post(f"/pets/{owner2.pet_id}/photo-requests/{request2}/retry-image")
        rounds()
        nothing_to_claim = {"before_redraw": before2, "redraw_http": redraw2.status_code,
                            "after": self._c36_state(task2, art2b), "second_art_dispatched": art2b.dispatched}

        # ③ 小票没了 / 图被改：都不认领、**也不重付**，如实落"没画成"，图仍在磁盘
        def broken(label: str, *, drop_receipt: bool) -> dict:
            owner3, task3, _req3, art3 = self._c36_photo(label)
            hook3 = self._c36_inject(web.illustrations, "_commit", times=1)
            try:
                web.illustrations.run_pending()
            finally:
                hook3["restore"]()
            receipt = self._c36_receipt_of(task3, 1)
            image = receipt.with_name(receipt.name.replace(".receipt.json", ".png"))
            existed = {"receipt": receipt.is_file(), "image": image.is_file()}
            if drop_receipt:
                receipt.unlink()
            else:
                image.write_bytes(image.read_bytes() + b"Q-C36-tampered")  # 只改字节：sha256 对不上
            rounds()
            return {"existed_before": existed, "image_still_on_disk": image.is_file(),
                    "after": self._c36_state(task3, art3)}

        no_receipt = broken("noreceipt", drop_receipt=True)
        tampered = broken("tampered", drop_receipt=False)

        # ④ 丢租约：画的时候把时钟推过租期（120 秒），围栏拒绝这一次提交；**每轮只跑 1 个**才留得住中间状态
        owner4, task4, _req4, art4 = self._c36_photo("lease")
        jumped = {"done": False}

        def jump(index: int, phase: str) -> None:
            if phase == "exit" and not jumped["done"]:
                jumped["done"] = True
                clock.advance(minutes=5)  # 远超 120 秒租期

        art4.on_call = jump
        web.illustrations.run_pending(limit=1)
        lease_first = self._c36_state(task4, art4)
        rounds(limit=1)
        lease_lost = {"clock_jumped": jumped["done"], "first": lease_first, "after": self._c36_state(task4, art4)}

        def only_one_paid(case: dict, first_key: str = "before_redraw") -> bool:
            return case["after"]["dispatched"] == case[first_key]["dispatched"] == 1

        checks = {
            # ① 重画仍认领
            "①注入确实连抛两次、任务确实进了终态": redraw_claims["injections"] == 2
                and redraw_claims["before_redraw"]["task"][0] == "failed",
            "①重画请求被接受": redraw_claims["redraw_http"] == 200,
            "①重画后**仍然认领**：没有再付一次": only_one_paid(redraw_claims),
            "①重画后只留一笔预占，且发布的是第一次那张":
                len(redraw_claims["after"]["reservations"]) == 1
                and (redraw_claims["after"]["rel_path"] or "").endswith("-1.png"),
            # ② 无可认领时重画照旧付费
            "②前提：第一次超时（结果不明、预占记 unknown）、自动重试没有重发":
                before2["dispatched"] == 1 and before2["illustration"] != "ready"
                and any(r["outcome"] == "unknown" for r in before2["reservations"]),
            "②无可认领时，重画**真的再画了一张**（不能修成一律不重画）":
                nothing_to_claim["second_art_dispatched"] >= 1,
            "②那一次重画确实另起了一笔预占（是一次新的付费尝试，不是白跑）":
                len(nothing_to_claim["after"]["reservations"]) > len(before2["reservations"]),
            # ③ 小票没了 / 图被改
            "③前提：两档在破坏之前，小票与图都确实存在":
                all(case["existed_before"] == {"receipt": True, "image": True} for case in (no_receipt, tampered)),
            "③小票没了：不认领、**不重付**，如实落没画成":
                no_receipt["after"]["dispatched"] == 1 and no_receipt["after"]["illustration"] != "ready",
            "③图被改（sha256 对不上）：不认领、**不重付**":
                tampered["after"]["dispatched"] == 1 and tampered["after"]["illustration"] != "ready",
            "③两档的图都**仍然留在磁盘上**（不重复付费做到了，不浪费没做到——这是记录不是要求）":
                no_receipt["image_still_on_disk"] and tampered["image_still_on_disk"],
            # ④ 丢租约
            "④前提：确实在画的当口推过了租期": lease_lost["clock_jumped"],
            "④丢租约后**认领**上一次那张：没有再付一次": lease_lost["after"]["dispatched"] == 1,
            "④丢租约后最终发布的是第一次那张": (lease_lost["after"]["rel_path"] or "").endswith("-1.png")
                and lease_lost["after"]["illustration"] == "ready",
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C35_SOURCES),
        }
        return ContractResult(
            "Q-C36", "认领这条路的四个边界：重画仍认领、无可认领时照旧付费、小票/图不对时不认领不重付、丢租约也认领",
            "用户直派（A 修恢复、Q 禁网故障注入复验）", LEVEL_INTEGRATION, "A（已付费结果的认领）",
            PASS if all(checks.values()) else FAIL,
            "①连抛两次后重画仍认领、不付费、发布 -1 那张；②无可认领时重画真的再画一张；"
            "③小票被删或图被改时不认领也不重付、图仍在磁盘；④丢租约后认领而不是重画",
            {"checks": checks, "redraw_still_claims": redraw_claims, "nothing_to_claim": nothing_to_claim,
             "receipt_missing": no_receipt, "image_tampered": tampered, "lease_lost": lease_lost,
             "digests_at_start": started},
            ["每档一位新主人、一只**带原照**的宠物（一次尝试只发一次），走正式接口 POST /pets/{pet}/photo-request",
             "①在 `illustrations._commit` **连抛两次**（两次尝试都付了钱却没写进去）→ 任务进终态 →"
             "走正式入口 `POST /pets/{pet}/photo-requests/{id}/retry-image` 重画 → 核对第三次仍认领",
             "②第一次用超时替身（结果不明、自动重试不重发）→ 重画时换成正常替身 → 核对它**真的再画了一张**",
             "③注入一次失败之后，分别**删掉小票**与**改掉图的字节**（sha256 对不上），再跑重试",
             "④在替身发送**之后**把时钟推 5 分钟（远超 120 秒租期）让围栏拒绝这一次提交；"
             "**每轮只跑 1 个任务**——默认一轮跑 5 个，同一轮里下一次循环就会把它回收掉，中间状态留不下来",
             "**未覆盖**：角色链路的这四个边界（本合同只做插画）；角色的「图被改」有 sha256 与图片校验两道挡，"
             "只改字节两道都会拦，要分开验得单独拆某一道——那是 A 的单元层用例在做的事"],
            source_digests(*C35_SOURCES), len(GUARD.attempts) - guard0)
