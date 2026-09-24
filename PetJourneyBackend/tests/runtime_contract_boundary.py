"""独立验收（工作包 Q）的提交边界合同：自主决策的最终提交（Q-C12）与后台线租约在真实业务入口的围栏（Q-C14）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、真实装配、替身决策器，不调用任何真实模型、不联网。

另外两条：Q-C12b 只改时区的旧请求不得撤销已完成的撤权；Q-C13 一次逻辑决策的编号与恢复（真实 BrainLife ＋ 真实额度账本，只换远端模型）。

Q-C12 的注入点都取**真实业务入口**：撤权走正式接口 `PATCH /settings {"model_replies": false}`，改 DNA 走 `PUT /pets/{id}/dna`，
活动变化走家人自己 `POST /journey/depart`。这是为了同时回答两件事：最终提交那一道复核挡不挡得住，以及**正式接口有没有真的
产生那道复核所依赖的版本变化**——只按内部 `bump_in` 注入是证明不了后者的。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import timedelta

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeChat

BRAIN_SRC, JOURNEY_SRC = "app/web_agent/brain_life.py", "app/web_journey/service.py"
RUNTIME_SRC, UOW_SRC = "app/web_agent/runtime_view.py", "app/web_platform/uow.py"
LEASE_SRC, TICKER_SRC = "app/web_platform/lease.py", "app/web_agent/ticker.py"
IDENTITY_SRC = "app/web_identity/service.py"


class StubBrain:
    """替身决策器：不调用任何真实模型，按脚本出提案。thinking 模拟“模型还在想的时候世界变了”。"""

    def __init__(self, prefer: str, thinking=None) -> None:
        self.prefer = prefer  # "stay" 或目的地前缀（例如 "local:"）
        self.thinking = thinking
        self.calls: list[str] = []
        self.offered: list[str] = []

    def propose(self, request, permit=None, limits=None):  # noqa: ARG002 - 与 Brain.propose 同签名
        from app.schemas.runtime_internal import BrainProposal
        from app.web_agent.decision import destination_key_of
        from app.web_agent.decision.outcomes import CallRecord, DecisionResult

        self.calls.append(request.operation_id)
        self.offered = [destination_key_of(offer) for offer in request.offers]
        if self.thinking is not None:
            self.thinking()
        stay = self.prefer == "stay"
        chosen = None if stay else next((o for o in request.offers if destination_key_of(o).startswith(self.prefer)), None)
        proposal = BrainProposal(operation_id=request.operation_id, source_versions=request.expected_versions, composed_by="model",
                                 intent_summary="Q 合同替身提案", selected_offer_id=None if chosen is None else chosen.offer_id,
                                 continue_current=chosen is None, model_ref="q-stub")
        # 如实记一次“已经发出并成功返回”的调用：提案被拒也不能把它抹掉（已发出的模型调用照实计量）
        return DecisionResult(outcome=proposal, calls=(CallRecord(attempt=1, kind="decision", outcome="succeeded", requested_model="q-stub"),))


class SimulatedCrash(BaseException):
    """模拟进程在模型调用中途被杀：BaseException 不会被业务代码的 except Exception 接住。"""


class ScriptedModel:
    """远端模型替身。只换这一层，Brain 与额度账本都是真的。

    - mode="crash"：请求**已经发出去**之后进程就没了（结果不明，绝不能当作没发生）；
    - mode="not_sent"：请求**确定没离开本机**（例如没配置、被本地限流挡下），这是唯一能证明“没发出”的情形。
    `calls` 记的是进了 complete() 几次；`dispatched` 记的是真的越过发送边界几次。两者分开，判定各取所需。
    """

    available = True
    provider_label = "Q 合同替身模型"
    max_call_seconds = 5.0

    def __init__(self, mode: str = "crash") -> None:
        self.mode = mode
        self.calls = 0
        self.dispatched = 0

    def complete(self, messages, *, max_tokens: int):  # noqa: ARG002 - 与 ModelAdapter.complete 同签名
        from app.schemas.runtime_internal import DecisionFailureCode
        from app.web_agent.decision.ports import ModelCallError

        self.calls += 1
        if self.mode == "not_sent":
            raise ModelCallError(DecisionFailureCode.provider_error, "not_sent", "q-not-sent")
        self.dispatched += 1
        raise SimulatedCrash("killed while the model call was in flight")


class BoundaryContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由 RuntimeContractCases 提供）。"""

    def _brain_owner(self, label: str, coins: int = 60):
        """一位开了“模型回信”的主人＋一只住进家的宠物＋够用的星币。返回 (主人, pet_id)。"""
        from app.schemas import EconomyTransactionType

        owner = self.user(label)
        pet = owner.upload_pet("年糕", "cat").json()["pet_id"]
        owner.move_in()
        assert owner.pet_id == pet, "入住的应当就是刚上传的那只"
        # **断言结果，不依赖「这一步有没有产生变化」**：模型回信默认开了之后这是同值写入，
        # 不换代、也不会顺带把 web_entity_runtime 那一行建出来（旧写法就是靠那个副作用）。
        prefs = owner.patch("/settings", {"model_replies": True})
        assert prefs.status_code == 200 and prefs.json()["model_replies"], "这一步之后模型回信必须是开着的"
        if coins:
            self.web.economy.apply(owner.pet_id, coins, EconomyTransactionType.web_reward, f"q-grant:{owner.pet_id}",
                                   reason="Q 合同备用旅费", source="q.contract")
        return owner, owner.pet_id

    def _runtime_row(self, pet_id: str) -> dict:
        row = self._sql("SELECT last_decision_by, next_review_at, silence_reason FROM web_entity_runtime WHERE pet_id = ?", (pet_id,))
        # next_review_at 返回原值（不是 bool）：判「有没有新增或改变」要比较取值本身。
        # **行不存在时三个键都给 None，不给空字典**：「没有行」就等于「什么都没记过」，
        # 比较语义不变而且更严——接管那轮若错写了 next_review_at，非 None ≠ None 照样红。
        # 空字典会让调用方按键取值直接 KeyError，那是探针坏了，不是被测对象错了。
        return ({"last_decision_by": row[0][0], "next_review_at": row[0][1], "silence_reason": row[0][2]} if row
                else {"last_decision_by": None, "next_review_at": None, "silence_reason": None})

    def _epochs(self, pet_id: str) -> dict:
        """这只宠物此刻的语义版本（最终提交那道复核就是比这几个数）。"""
        row = self._sql("SELECT runtime_epoch, activity_epoch, privacy_epoch, membership_epoch FROM web_entity_runtime WHERE pet_id = ?", (pet_id,))
        dna = self._sql("SELECT version FROM web_pet_dna WHERE pet_id = ?", (pet_id,))
        names = ("runtime_epoch", "activity_epoch", "privacy_epoch", "membership_epoch")
        return {**(dict(zip(names, row[0])) if row else dict.fromkeys(names, 0)), "dna_version": dna[0][0] if dna else 0}

    def _budget(self, pet_id: str, operation_id: str | None) -> dict:
        """这次决策的额度账面：预占状态与已计量单位。"""
        reservation = self._sql("SELECT status, outcome, reserved_units, actual_units FROM web_budget_reservations WHERE operation_id = ?",
                                (operation_id or "-",))
        counter = self._sql("SELECT SUM(used_units), SUM(inflight_units) FROM web_budget_counters WHERE scope_key = ?", (f"pet:{pet_id}:life_plan",))
        status, outcome, reserved, actual = reservation[0] if reservation else (None, None, None, None)
        return {"status": status, "outcome": outcome, "reserved_units": reserved, "actual_units": actual,
                "used_units": counter[0][0] or 0, "inflight_units": counter[0][1] or 0}

    def contract_c12_commit_boundary(self) -> ContractResult:
        """Q-C12：提案交出之后、真正写库之前世界变了，旧提案不得提交；“留在家”同样覆盖；正常路径必须能成行。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web, life = self.web, self.web.brain_life
        keep_mode, keep_brain = life.mode, life.brain
        original_resolve, runtime = web.journeys.resolve, life.projector.runtime
        original_checked = runtime.record_decision_checked
        cases: dict[str, dict] = {}

        def run(label: str, prefer: str, *, thinking=None, in_window=None, before_stay=None) -> None:
            """in_window：在 journeys.resolve（外部解析、写事务之前）注入一次；before_stay：在写“留在家”之前注入一次。"""
            owner, pet = self._brain_owner(f"q-c12-{label}")
            fired: list[str] = []
            seen: dict[str, dict] = {}

            def once(hook):
                if hook is None or fired:
                    return
                fired.append(label)
                seen["epochs_before"] = self._epochs(pet)
                hook(owner, pet)
                seen["epochs_after"] = self._epochs(pet)

            def resolve(*args, **kwargs):
                once(in_window)
                return original_resolve(*args, **kwargs)

            def checked(*args, **kwargs):
                once(before_stay)
                return original_checked(*args, **kwargs)

            web.journeys.resolve, runtime.record_decision_checked = resolve, checked
            brain = StubBrain(prefer, thinking=(lambda: thinking(owner, pet)) if thinking else None)
            life.brain = brain
            before = web.economy.wallet(pet).balance
            try:
                outcome = life.consider(pet, clock.now)
            finally:
                web.journeys.resolve, runtime.record_decision_checked = original_resolve, original_checked
            trips = self._sql("SELECT journey_id, lifecycle FROM web_journeys WHERE pet_id = ?", (pet,))
            fees = self._sql("SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ? AND type = 'web_travel_fee'", (pet,))[0][0]
            cases[label] = {"status": outcome.status, "reason": outcome.reason, "composed_by": outcome.composed_by,
                            "destination": outcome.destination_key, "offered": brain.offered, "model_calls": len(brain.calls),
                            "journeys": len(trips), "travel_fee_rows": fees, "coins_spent": before - web.economy.wallet(pet).balance,
                            "runtime": self._runtime_row(pet), "budget": self._budget(pet, outcome.operation_id),
                            "injected": bool(fired) or thinking is not None, **seen}

        revoke = lambda owner, pet: owner.patch("/settings", {"model_replies": False})  # noqa: E731 - 正式撤权接口
        try:
            life.mode = "live"
            # 1）模型还在想的时候撤权：留在家的提案也不能算数
            run("stay_revoked_thinking", "stay", thinking=revoke)
            # 2）版本比过之后、写“留在家”那条记录之前撤权
            run("stay_revoked_final", "stay", before_stay=revoke)
            # 3～6）版本比过之后、写事务之前：撤权 / 改 DNA / 家人已经把它送出门 / 机会过期
            run("depart_revoked", "local:cafe", in_window=revoke)
            run("depart_dna", "local:cafe", in_window=lambda owner, pet: owner.put(f"/pets/{pet}/dna", {"personality": "最近更爱睡懒觉"}))
            run("depart_activity", "local:cafe", in_window=lambda owner, pet: owner.post(f"/journey/depart?pet_id={pet}", {"destination_key": "work:florist"}))
            run("depart_expired", "local:cafe", in_window=lambda owner, pet: clock.advance(minutes=45))
            # 7）正常对照：什么都不注入，必须真的出发
            run("control", "local:cafe")
        finally:
            life.mode, life.brain = keep_mode, keep_brain
            web.journeys.resolve, runtime.record_decision_checked = original_resolve, original_checked

        # 只对**真的被拒**的那几只核对“被拒后的样子”：没被拒住本身由上面那几条检查负责说，不要在这里重复计一笔
        rejected = {name: case for name, case in cases.items() if case["status"] == "rejected"}
        control = cases["control"]
        checks = {
            "思考期间撤权：提案被拒": cases["stay_revoked_thinking"]["status"] == "rejected" and cases["stay_revoked_thinking"]["reason"] == "consent_withdrawn",
            "最后一刻撤权：不写“留在家”的决策记录": cases["stay_revoked_final"]["status"] == "rejected"
                and not cases["stay_revoked_final"]["runtime"]["last_decision_by"],
            "窗口内撤权：不出发": cases["depart_revoked"]["status"] == "rejected" and cases["depart_revoked"]["journeys"] == 0,
            "窗口内改 DNA：不出发": cases["depart_dna"]["status"] == "rejected" and cases["depart_dna"]["journeys"] == 0,
            "窗口内已被家人送出门：不再多一趟": cases["depart_activity"]["status"] == "rejected" and cases["depart_activity"]["journeys"] == 1,
            "窗口内机会过期：不出发": cases["depart_expired"]["status"] == "rejected" and cases["depart_expired"]["journeys"] == 0,
            "被拒后不写决定者": all(not c["runtime"]["last_decision_by"] for c in rejected.values()),
            "被拒后记了下次再看的时刻与原因": all(c["runtime"]["next_review_at"] and c["runtime"]["silence_reason"] for c in rejected.values()),
            "被拒后不扣旅行星币": all(c["coins_spent"] == 0 and c["travel_fee_rows"] == 0 for c in rejected.values()),
            "每只都只发一次调用、结算后没有在途": all(c["model_calls"] == 1 and c["budget"]["used_units"] == 1
                and c["budget"]["inflight_units"] == 0 and c["budget"]["status"] == "settled" for c in cases.values()),
            "正常对照真的出发并按规矩扣了一次旅费": control["status"] == "departed" and control["journeys"] == 1
                and control["composed_by"] == "model" and control["travel_fee_rows"] == 1 and control["coins_spent"] > 0,
            "正常对照记下决定者": control["runtime"]["last_decision_by"] == "model",
        }
        return ContractResult(
            "Q-C12", "自主决策的最终提交边界：撤权 / DNA / 活动 / 机会过期都挡得住，“留在家”与正常路径都覆盖", "CR-C1、A16、A21",
            LEVEL_INTEGRATION, "I（brain_life ＋ journey.depart ＋ runtime_view）", PASS if all(checks.values()) else FAIL,
            "全部检查为 true", {"checks": checks, "cases": cases},
            ["主人开“模型回信”，brain_life 切到 live，换成替身决策器（不调用真实模型）",
             "stay_revoked_thinking：模型思考期间调用正式接口 PATCH /settings {model_replies:false}",
             "stay_revoked_final：版本比过之后、写“留在家”记录之前用同一个正式接口撤权",
             "depart_*：在 journeys.resolve（外部解析、写事务之前）分别注入撤权 / PUT /pets/{id}/dna / 家人自己 POST /journey/depart / 时钟越过机会有效期",
             "control：不注入任何变化", "逐只核对：状态、行程数、旅费流水、决定者、下次复查时刻、额度账面（含注入前后的语义版本）"],
            source_digests(BRAIN_SRC, JOURNEY_SRC, RUNTIME_SRC, IDENTITY_SRC), len(GUARD.attempts) - guard0)

    def contract_c14_lease_fence(self) -> ContractResult:
        """Q-C14：后台线一轮跑到一半被接管时，**宠物的业务账本、钱包、世界状态**写不进去；但**已经发出的模型调用的费用事实必须保留**。

        「账本不动」只针对业务侧（工钱、旅费、行程、世界事件、运行记录）。供应商用量、额度预占与结算属于**已经发生的成本**，
        围栏回滚不能把它抹掉——否则下一任期会以为没花过钱，重新调一次。
        三段都在这个隔离测试进程里做，不改任何共享业务源码：
        A 世界线被接管 → 业务写不进去；B 认知线在模型答完之后被接管 → 业务回滚但费用保留；
        C **正常路径对照** → 租约正常时同一条路径必须真的写进去。

        **C 段的范围**：它只说明「在租约正常的情况下这条路径本来就走得通」，因此 A、B 的“写不进去”不是因为路径本身不通。
        它**没有故意关掉围栏**，所以**不能叫做对租约围栏的变异验证**。
        变异验证本来是可以做的——在这个独立测试进程里把围栏函数替换掉即可，并不需要改共享业务源码——
        **但本合同没有做**，这里只如实注明「未做租约特定的变异验证」。
        """
        from app.web_platform.lease import WorkerLease

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web, life = self.web, self.web.brain_life
        keep_mode, keep_brain = life.mode, life.brain
        salary = "SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?"
        events = "SELECT COUNT(*) FROM web_world_events WHERE journey_id = ?"

        def steal(name: str) -> None:
            """直接把租约行的持有者改成别人：不动时钟，模拟“这一轮进行中被另一个进程接管”。只写 Q 自己的一次性临时库。"""
            conn = sqlite3.connect(self.settings.database_path)
            try:
                with conn:
                    conn.execute("UPDATE web_worker_leases SET holder = 'q-rival-holder' WHERE name = ?", (name,))
            finally:
                conn.close()

        # ---- A 段：世界线到期结算被接管（租期真的过了，另一个持有者接手）----
        owner, pet = self._brain_owner("q-c14-owner", coins=0)
        journey_id = owner.post(f"/journey/depart?pet_id={pet}", {"destination_key": "work:florist"}).json()["journey_id"]
        clock.now = web.journeys.repo.get(journey_id).completes_at + timedelta(minutes=1)  # 工钱与到家都已到期（后台一直没跑）
        before_events = self._sql(events, (journey_id,))[0][0]  # 出发那条事件是 HTTP 请求里记的，不属于这一轮
        rival = WorkerLease(self.app.state.storage, "world", timedelta(seconds=90), role="worker")
        taken: list[bool] = []

        def takeover(now) -> None:  # 本轮的第一步：别的进程在这一轮进行中拿走了世界线租约
            clock.advance(minutes=10)  # 原持有者的租期（90 秒）已经过了
            taken.append(rival.acquire(clock.now))

        web.ticker.jobs.insert(0, ("q-takeover", takeover))
        try:
            web.ticker.tick(clock.now)
            during = {"salary_rows": self._sql(salary, (f"web:job:{journey_id}",))[0][0],
                      "lifecycle": web.journeys.repo.get(journey_id).lifecycle,
                      "new_world_events": self._sql(events, (journey_id,))[0][0] - before_events,
                      "lease_holder_is_rival": self._sql("SELECT holder FROM web_worker_leases WHERE name = 'world'")[0][0] == rival.holder}
            rival.release()  # 接手的进程退出：下一轮世界线重新拿到租约
            clock.advance(minutes=1)
            web.ticker.jobs = [job for job in web.ticker.jobs if job[0] != "q-takeover"]
            web.ticker.tick(clock.now)
            after = {"salary_rows": self._sql(salary, (f"web:job:{journey_id}",))[0][0],
                     "lifecycle": web.journeys.repo.get(journey_id).lifecycle}
        finally:
            web.ticker.jobs = [job for job in web.ticker.jobs if job[0] != "q-takeover"]

        # ---- B、C 段：认知线。B 在模型答完之后被接管；C 是租约正常的反向对照 ----
        def cognition_round(label: str, *, steal_during_call: bool) -> dict:
            owner2, pet2 = self._brain_owner(f"q-c14-{label}")
            brain = StubBrain("local:cafe", thinking=(lambda: steal("cognition")) if steal_during_call else None)
            life.mode, life.brain = "live", brain
            wallet_before = web.economy.wallet(pet2).balance
            runtime_before = self._runtime_row(pet2)
            # 供应商那一层是全体宠物共用的计数，必须取**本轮增量**：只看总数的话，
            # 别的宠物早先的用量会把「这一次漏记了」盖过去
            provider_before = self._sql("SELECT SUM(used_units) FROM web_budget_counters WHERE scope_key = ?",
                                        ("provider:llm:life_plan",))[0][0] or 0
            web.cognition.tick(clock.now)
            reservations = self._sql("SELECT operation_id, status, outcome FROM web_budget_reservations "
                                     "WHERE subject_scope = ? AND purpose = 'life_plan'", (f"pet:{pet2}",))
            pet_usage = self._sql("SELECT SUM(used_units) FROM web_budget_counters WHERE scope_key = ?", (f"pet:{pet2}:life_plan",))[0][0] or 0
            provider_after = self._sql("SELECT SUM(used_units) FROM web_budget_counters WHERE scope_key = ?",
                                       ("provider:llm:life_plan",))[0][0] or 0
            # 一轮认知线会替**这一轮里所有需要想一想的宠物**各走一次，所以只数编号里属于这只宠物的那些次，
            # 不能把 brain.calls 的总数当成“这只宠物被调了几次”（决策编号形如 life:<pet>:<时刻>:<随机>）
            mine = [operation for operation in brain.calls if pet2 in operation]
            return {"model_calls": len(mine), "model_calls_this_round": len(brain.calls), "runtime_before": runtime_before,
                    "journeys": self._sql("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?", (pet2,))[0][0],
                    "coins_spent": wallet_before - web.economy.wallet(pet2).balance,
                    "runtime": self._runtime_row(pet2), "open_operation_id": self._decision_row(pet2)["operation_id"],
                    "reservations": [dict(zip(("operation_id", "status", "outcome"), row)) for row in reservations],
                    "pet_used_units": pet_usage, "provider_used_before": provider_before, "provider_used_after": provider_after,
                    "provider_used_delta": provider_after - provider_before}

        try:
            self._use_model(FakeChat())  # 心跳要先认为大脑可用才会走 brain_life；真正出提案的是替身决策器
            # 先跑正常租约的反向对照，再跑被接管那一轮：租约一旦被别人拿走，这一条线后面就整轮跳过了
            control = cognition_round("control", steal_during_call=False)
            fenced = cognition_round("fenced", steal_during_call=True)
        finally:
            life.mode, life.brain = keep_mode, keep_brain

        checks = {
            "A 被接管期间不发工钱、不改行程、不记世界事件": during == {"salary_rows": 0, "lifecycle": "active", "new_world_events": 0,
                                                                    "lease_holder_is_rival": True} and taken == [True],
            "A 租约回来后下一轮如数补上": after == {"salary_rows": 1, "lifecycle": "completed"},
            "B 模型答完之后被接管：不出发": fenced["model_calls"] == 1 and fenced["journeys"] == 0,
            "B 被接管时不动钱包": fenced["coins_spent"] == 0,
            "B 被接管时不写生活决定": not fenced["runtime"]["last_decision_by"],
            "B 被接管时不写退避（那轮不属于本进程）": not fenced["runtime"]["silence_reason"]
                and fenced["runtime"]["next_review_at"] == fenced["runtime_before"]["next_review_at"],
            "B **已发出调用的费用事实保留**：预占没有被回滚": len(fenced["reservations"]) == 1
                and fenced["reservations"][0]["status"] in ("reserved", "settled", "unknown")
                and fenced["reservations"][0]["outcome"] != "not_sent",
            "B **已发出调用的费用事实保留**：每宠额度层照记": fenced["pet_used_units"] >= 1,
            "B **已发出调用的费用事实保留**：供应商层本轮增量也照记": fenced["provider_used_delta"] >= 1,
            # 先判非空再取下标：围栏若失效，被接管那轮会把预占结算掉、这里就是空列表。
            # 裸下标会抛 IndexError，合同变成 ERROR（未得到合同结论）——读起来像探针坏了，
            # 而不是「保护失效」。留一句能读的 FAIL 比一个异常有用。
            "B 决策编号留给合法执行者复用": bool(fenced["reservations"])
                and fenced["open_operation_id"] == fenced["reservations"][0]["operation_id"],
            "C 正常路径对照：同一条路径真的写进去了": control["model_calls"] == 1 and control["journeys"] == 1
                and control["runtime"]["last_decision_by"] == "model",
            "C 正常路径对照：费用也照记（两层都看，供应商层取增量）": control["pet_used_units"] >= 1
                and control["provider_used_delta"] >= 1 and len(control["reservations"]) == 1,
        }
        observed = {"rival_acquired": taken, "events_before_tick": before_events, "during": during, "after": after,
                    "fenced_round": fenced, "normal_lease_control": control}
        return ContractResult(
            "Q-C14", "被接管时业务账本 / 钱包 / 世界状态写不进去，但已发出调用的费用事实保留；租约正常时同一条路径照常写入（正常路径对照）",
            "CR-A4、A08、A09、A19", LEVEL_INTEGRATION, "B（租约围栏接入）＋ A（额度账本）", PASS if all(checks.values()) else FAIL,
            "被接管：0 工钱 / 0 新世界事件 / 行程仍 active / 不出发 / 不动钱包 / 不写决定；"
            "同时预占与供应商用量原样保留；租约正常时对照组照常出发并记账",
            {"checks": checks, **observed},
            ["A：宠物去 work:florist 打工，时钟推过收工与到家时间；在世界线这一轮的第一步让另一个持有者接管 world 租约（原租期已过）",
             "A：同一轮继续跑到期结算（真实业务入口 journeys.advance_all）；接手者退出后再跑一轮",
             "B：另一只宠物，认知线 brain_life。替身决策器在“模型正在答”的那一刻把 cognition 租约的持有者改成别人（不动时钟）",
             "B：核对业务侧（行程、钱包、运行记录）全部没写，同时核对预占、结算与供应商用量**仍然在**、决策编号仍留着",
             "C：第三只宠物走同一条认知线、租约正常——必须真的出发、真的记决定、两层额度也照常记（供应商层取本轮增量）",
             "C 的范围：只证明正常路径走得通，**不是**对围栏的变异验证（没有故意关掉围栏）；"
             "变异验证可以在本测试进程内替换围栏函数来做，不必改共享业务源码，**但本合同未做**",
             "全部在这个隔离测试进程里完成，不改任何共享业务源码"],
            source_digests(UOW_SRC, TICKER_SRC, LEASE_SRC, JOURNEY_SRC, BRAIN_SRC, "app/web_platform/budget.py"),
            len(GUARD.attempts) - guard0)

    # ---- Q-C12b：只改时区的旧请求不得撤销已经完成的撤权 ----
    def _stay_proposal(self, pet_id: str, clock) -> tuple:
        """在当前授权状态下真的走一遍自主决策（替身提案“留在家”），返回 (状态, 原因)。"""
        life = self.web.brain_life
        keep_mode, keep_brain = life.mode, life.brain
        life.mode, life.brain = "live", StubBrain("stay")
        try:
            outcome = life.consider(pet_id, clock.now)
        finally:
            life.mode, life.brain = keep_mode, keep_brain
        return outcome.status, outcome.reason

    def contract_c12b_timezone_keeps_revocation(self) -> ContractResult:
        """Q-C12b：一个只改时区的请求（读到的是撤权前的旧值）不能把已经完成的撤权改回来。

        这是 CR-Q13 修好之后的**新反例**：原来那条合同只证明“撤权会让在途提案作废”，
        证明不了“别的部分更新不会把撤权覆盖掉”。授权是部分更新接口里最怕被顺手盖回去的字段。
        """
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        identity = self.web.identity
        owner, pet = self._brain_owner("q-c12b-owner")

        # 一、串行：先撤权，再发一个只改时区的请求
        before = self._epochs(pet)["privacy_epoch"]
        assert owner.patch("/settings", {"model_replies": False}).status_code == 200
        revoked_epoch = self._epochs(pet)["privacy_epoch"]
        tz_only = owner.patch("/settings", {"timezone": "Asia/Tokyo"})
        serial = {"http": tz_only.status_code, "model_replies": tz_only.json().get("model_replies"),
                  "timezone": tz_only.json().get("timezone"), "consent": bool(self.web.brain_life.model_consent(pet)),
                  "privacy_epoch": [before, revoked_epoch, self._epochs(pet)["privacy_epoch"]],
                  "proposal": list(self._stay_proposal(pet, clock))}

        # 二、交错：只改时区的请求读到旧值之后、写回之前，主人完成撤权
        assert owner.patch("/settings", {"model_replies": True}).status_code == 200
        read_done, original_read = threading.Event(), identity._prefs_in

        def held_read(conn, user_id):
            row = original_read(conn, user_id)
            if user_id == owner.user_id and not read_done.is_set():
                read_done.set()  # 这个请求已经读到旧值了
                threading.Event().wait(0.3)  # 停在“读到旧值、还没写回”的那一刻
            return row

        identity._prefs_in = held_read
        errors = []

        def change_timezone() -> None:
            try:
                owner.patch("/settings", {"timezone": "Asia/Taipei"})
            except Exception as exc:  # noqa: BLE001 - 线程里的异常要带回来，不能吞掉
                errors.append(f"timezone: {type(exc).__name__}")

        def revoke() -> None:
            try:
                identity.set_prefs(owner.user_id, model_replies=False)  # 路由走的就是这个方法
            except Exception as exc:  # noqa: BLE001
                errors.append(f"revoke: {type(exc).__name__}")

        epoch_before_race = self._epochs(pet)["privacy_epoch"]
        writer = threading.Thread(target=change_timezone, name="q-c12b-timezone")
        writer.start()
        assert read_done.wait(5), "只改时区的那个请求没有读到旧值"
        revoker = threading.Thread(target=revoke, name="q-c12b-revoke")
        revoker.start()
        writer.join(timeout=20)
        revoker.join(timeout=20)
        identity._prefs_in = original_read
        prefs = identity.prefs(owner.user_id)
        interleaved = {"thread_errors": errors, "alive": [writer.is_alive(), revoker.is_alive()],
                       "model_replies": prefs["model_replies"], "timezone": prefs["timezone"], "consent": bool(self.web.brain_life.model_consent(pet)),
                       "privacy_epoch": [epoch_before_race, self._epochs(pet)["privacy_epoch"]],
                       "proposal": list(self._stay_proposal(pet, clock))}

        checks = {
            "只改时区不会把授权改回来（串行）": serial["model_replies"] is False and serial["consent"] is False,
            "只改时区确实改到了时区": serial["timezone"] == "Asia/Tokyo" and interleaved["timezone"] == "Asia/Taipei",
            "只改时区不算授权变化（不递增授权代数）": serial["privacy_epoch"][1] == serial["privacy_epoch"][2]
                and serial["privacy_epoch"][1] > serial["privacy_epoch"][0],
            "撤权之后提案被拒（串行）": serial["proposal"] == ["rejected", "consent_withdrawn"],
            "交错时撤权仍然生效": interleaved["model_replies"] is False and interleaved["consent"] is False,
            "交错时授权代数照样递增": interleaved["privacy_epoch"][1] > interleaved["privacy_epoch"][0],
            "交错之后提案同样被拒": interleaved["proposal"] == ["rejected", "consent_withdrawn"],
            "两个请求都正常结束": errors == [] and interleaved["alive"] == [False, False],
        }
        return ContractResult(
            "Q-C12b", "只改时区的旧请求不得撤销已经完成的撤权（部分更新的读改写必须在写事务里）", "CR-Q13、CR-C1、A16",
            LEVEL_INTEGRATION, "I／identity（set_prefs）", PASS if all(checks.values()) else FAIL,
            "两种顺序下最终都是已撤权；时区照改；只改时区不递增授权代数", {"checks": checks, "serial": serial, "interleaved": interleaved},
            ["主人开“模型回信”，用正式接口 PATCH /settings 撤权，再发一个只带 timezone 的请求",
             "交错场景：把 identity._prefs_in 包一层，让只改时区的那个请求停在“读到旧值、还没写回”的一刻",
             "在那一刻由主人完成撤权（调用路由用的同一个 set_prefs），两个线程都跑完后看最终状态",
             "两种顺序下都再走一遍自主决策（替身提案“留在家”），核对确实被拒"],
            source_digests(IDENTITY_SRC, BRAIN_SRC, RUNTIME_SRC), len(GUARD.attempts) - guard0)

    # ---- Q-C13：一次逻辑决策的编号与恢复 ----
    def _decision_row(self, pet_id: str) -> dict:
        row = self._sql("SELECT decision_operation_id, decision_started_at FROM web_entity_runtime WHERE pet_id = ?", (pet_id,))
        return {"operation_id": row[0][0], "started_at": row[0][1]} if row else {"operation_id": None, "started_at": None}

    def _life_reservations(self, pet_id: str) -> list:
        rows = self._sql("SELECT operation_id, status, outcome, reserved_units FROM web_budget_reservations "
                         "WHERE subject_scope = ? AND purpose = 'life_plan' ORDER BY rowid", (f"pet:{pet_id}",))
        return [dict(zip(("operation_id", "status", "outcome", "reserved_units"), row)) for row in rows]

    def contract_c13_decision_operation_id(self) -> ContractResult:
        """Q-C13：一次可能已经发出的调用，恢复多少次都不许重发；只有**证明没发出**之后才允许重开编号。

        判定口径（2026-09-23 06:20 收紧）：`reserved` / `expired` / `unknown` **都不能证明请求没发出去**——
        预占到期只说明“过了保留时限还没人来结清”，不说明对方没收到。所以**超过一轮决策保留时限之后**的恢复
        同样不许换编号重发。反过来，`released / not_sent`（确定没离开本机）之后必须允许重开编号、允许再发，
        否则就修成了永久卡住——本合同用另一只宠物做这个**正向对照**。

        **层级说明**：第四步只是在同一个进程里重建 BrainLife 与 RuntimeStore（证明编号存在库里、不在内存里），
        **不是进程重启验证**，这一范围不升级；跨进程重启由 Q-C19 承担。
        """
        from app.web_agent.brain_life import BrainLife
        from app.web_agent.runtime_view import RuntimeStore

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        watched = (BRAIN_SRC, RUNTIME_SRC, "app/web_platform/budget.py", "app/web_agent/brain_wiring.py")
        digests_before = source_digests(*watched)  # 运行前后各记一次：可重复 ≠ 版本一致，两件事分开说
        life = self.web.brain_life
        keep_mode, keep_brain, keep_model = life.mode, life.brain, life.brain.model
        life.mode = "live"
        crash = ScriptedModel("crash")
        life.brain.model = crash  # 只换远端模型：Brain、上下文读取、额度账本都是真的
        owner, pet = self._brain_owner("q-c13-owner")
        steps = {}

        def step(label: str, action) -> None:
            """记三件事：这一次**用的**编号、这一次之后库里**还留着的**编号、发出去几次调用。

            两者要分开：重试时沿用了旧编号（用的对），但如果紧接着把编号清掉，下一次就会开新编号、再发一次。
            """
            calls_before, sent_before = crash.calls, crash.dispatched
            opened_before = self._decision_row(pet)["operation_id"]
            try:
                outcome = action()
                result, used = [outcome.status, outcome.reason], outcome.operation_id
            except SimulatedCrash:
                result, used = ["crashed", "simulated_crash"], self._decision_row(pet)["operation_id"]
            steps[label] = {"result": result, "model_calls_added": crash.calls - calls_before,
                            "dispatched_added": crash.dispatched - sent_before,
                            "operation_id_before": opened_before, "operation_id_used": used,
                            "decision": self._decision_row(pet), "reservations": self._life_reservations(pet)}

        try:
            step("1_crash_mid_call", lambda: life.consider(pet, clock.now))
            first = steps["1_crash_mid_call"]["decision"]["operation_id"]
            step("2_retry_same_minute", lambda: life.consider(pet, clock.now))
            clock.advance(seconds=61)
            step("3_retry_next_minute", lambda: life.consider(pet, clock.now))

            rebuilt = BrainLife(brain=life.brain, journeys=life.journeys, households=life.households, residents=life.residents,
                                homes=life.homes, projector=life.projector, mode="live")
            rebuilt.reserve, rebuilt.settle, rebuilt.model_consent = life.reserve, life.settle, life.model_consent
            rebuilt.projector.runtime = RuntimeStore(self.app.state.storage)  # 新的运行记录对象，同一个库
            step("4_after_object_rebuild", lambda: rebuilt.consider(pet, clock.now))

            # 关键一步：超过一轮决策的保留时限（STALE_DECISION）。预占这时多半已经 expired——
            # 但 expired 不等于“没发出去”，所以**仍然不许换编号重发**
            clock.advance(minutes=16)
            step("5_after_stale_window", lambda: life.consider(pet, clock.now))
            after_stale_reservations = self._life_reservations(pet)

            # 正向对照：另一只宠物，模型明确“没离开本机”（not_sent）。这是唯一能证明没发出的情形，
            # 之后必须允许重开编号、允许再发一次——否则就是修成了永久卡住
            owner2, pet2 = self._brain_owner("q-c13-control")
            not_sent = ScriptedModel("not_sent")
            life.brain.model = not_sent
            control = []
            for label in ("control_1_not_sent", "control_2_allowed_again"):
                outcome = life.consider(pet2, clock.now)
                control.append({"step": label, "result": [outcome.status, outcome.reason], "operation_id_used": outcome.operation_id,
                                "model_calls_total": not_sent.calls, "dispatched_total": not_sent.dispatched,
                                "reservations": self._life_reservations(pet2)})
                clock.advance(minutes=20)  # 两次之间拉开，确保是真正的新一轮而不是同一轮重试
        finally:
            life.mode, life.brain = keep_mode, keep_brain
            life.brain.model = keep_model

        # 保留时限内的恢复与“过了保留时限”的恢复分开判，免得把已经修好的部分也一并说成不合格
        within = ("2_retry_same_minute", "3_retry_next_minute", "4_after_object_rebuild")
        stale = steps["5_after_stale_window"]
        digests_after = source_digests(*watched)
        stale_statuses = [row["status"] for row in after_stale_reservations]
        checks = {
            "崩在模型调用里也留下了编号与预占": bool(first) and steps["1_crash_mid_call"]["dispatched_added"] == 1
                and steps["1_crash_mid_call"]["reservations"][0]["status"] == "reserved",
            "保留时限内的三次恢复沿用同一个编号": [steps[name]["operation_id_used"] for name in within] == [first] * len(within),
            "保留时限内在途没结清就不清编号": all(steps[name]["decision"]["operation_id"] == first for name in within),
            "保留时限内一次都没被重发": all(steps[name]["dispatched_added"] == 0 for name in within),
            "保留时限内没有开第二笔预占": all(len(steps[name]["reservations"]) == 1 for name in within),
            "保留时限内被判成额度未放行": all(steps[name]["result"] == ["failed", "budget_denied"] for name in within),
            "**过了保留时限**仍然沿用同一个编号": stale["operation_id_used"] == first,
            "**过了保留时限**仍然一次都不重发": stale["dispatched_added"] == 0,
            "到期（expired）不当作“没发出”的证明：不因此另开一笔预占": len(stale_statuses) == 1
                and stale_statuses[0] in ("reserved", "expired", "unknown"),
            "已发出那次的费用记录一直没被回滚": all(any(row["operation_id"] == first and row["status"] != "released"
                                                       and row["outcome"] != "not_sent" for row in steps[name]["reservations"])
                                                   for name in ("1_crash_mid_call", *within, "5_after_stale_window")),
            "正向对照：确定没发出之后允许重开编号": control[1]["operation_id_used"] != control[0]["operation_id_used"],
            "正向对照：确定没发出之后允许再发一次": control[1]["model_calls_total"] == 2 and control[1]["dispatched_total"] == 0,
            "正向对照：没发出的预占整笔退回": all(row["status"] == "released" and row["outcome"] == "not_sent"
                                                for row in control[1]["reservations"]),
            "本次运行期间被测版本没有变化": digests_before == digests_after,
        }
        return ContractResult(
            "Q-C13", "可能已经发出的调用，恢复多少次都不重发；只有证明没发出之后才允许重开编号", "CR-A2、CR-Q14、A07、A19",
            LEVEL_INTEGRATION, "B（brain_life ＋ runtime_view）＋ A（额度账本）", PASS if all(checks.values()) else FAIL,
            "四次恢复（含超过保留时限那次）都沿用同一个编号、一次都不重发、只有 1 笔预占；"
            "正向对照里确定没发出之后换新编号并允许再发一次",
            {"checks": checks, "first_operation_id_present": bool(first), "steps": steps,
             "after_stale_reservations": after_stale_reservations, "control": control,
             "digests_before": digests_before, "digests_after": digests_after},
            ["开“模型回信”，BrainLife 切到 live，**只**把远端模型换成替身（Brain、上下文、额度账本都是真的）",
             "第一次思考崩在模型调用里（请求已经发出去，退避与清编号都没跑到）",
             "同一分钟重试、跨一分钟重试、重建 BrainLife 与 RuntimeStore 之后再试",
             "时钟 +16 分钟越过一轮决策的保留时限后再试：**预占多半已 expired，但这不证明没发出**，仍然不许换编号重发",
             "正向对照：另一只宠物，模型明确“没离开本机”（not_sent）→ 预占整笔退回后，必须允许重开编号、允许再发一次",
             "运行前后各记一次被测指纹：可重复与版本一致是两件事",
             "**层级**：第四步是同一进程内重建对象，不是进程重启验证"],
            digests_after, len(GUARD.attempts) - guard0)


CONTRACTS = ("c12_commit_boundary", "c12b_timezone_keeps_revocation", "c13_decision_operation_id", "c14_lease_fence")
