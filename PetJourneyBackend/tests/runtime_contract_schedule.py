"""独立验收（工作包 Q）的调度合同：公平轮转（Q-C16）、失败退避的调用上界（Q-C17）、同一只宠物同一时刻只有一个决定者（Q-C18）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、真实装配、替身模型（一律失败或按脚本出提案），不联网、不产生付费调用。

三条都走真实的两条后台线：认知线那一步就是装配时挂上去的 `brain_life`，世界线那一步就是规则生活 `life.run`。
"""

from __future__ import annotations

from datetime import timedelta

from runtime_contract_boundary import StubBrain
from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeChat

WIRING_SRC, LIFE_SRC = "app/web_agent/brain_wiring.py", "app/web_agent/life.py"
BRAIN_SRC, POLICY_SRC = "app/web_agent/brain_life.py", "app/web_runtime/heartbeat_policy.py"
RUNTIME_SRC = "app/web_agent/runtime_view.py"


class ScheduleContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由 RuntimeContractCases 提供）。"""

    def _round_job(self):
        """认知线里真正跑的那一步（装配时挂上去的 brain_life），不是测试自己复制的一份。"""
        return dict(self.web.cognition.jobs)["brain_life"]

    def _household(self, label: str, pets: int = 1) -> tuple:
        """一位开了“模型回信”的主人，家里 pets 只宠物都已入住。返回 (主人, [pet_id...])。"""
        owner = self.user(label)
        first = owner.upload_pet("年糕", "cat").json()["pet_id"]
        owner.move_in()
        assert owner.patch("/settings", {"model_replies": True}).status_code == 200
        household_id = owner.get("/households").json()[0]["household_id"]
        ids = [first]
        for index in range(1, pets):
            added = owner.upload_pet(f"小{index}", "cat", household_id=household_id)
            assert added.status_code in (200, 201), added.text
            pet_id = added.json()["pet_id"]
            moved = owner.post("/onboarding/move-in", {"pet_id": pet_id})
            assert moved.status_code == 200, moved.text
            ids.append(pet_id)
        return owner, ids

    def _use_model(self, chat: FakeChat) -> FakeChat:
        """把“模型已配置、可用”这件事按装配时的同一条线接上替身：供应商、心跳读到的可用性、决策用的适配器。

        心跳要先认为大脑可用才会 REQUEST_BRAIN（`projector.model_available` 读的就是供应商的 available），
        所以这三处都要换，缺一不可。换的是环境（哪个供应商），不是被测的判断逻辑。
        """
        from app.web_agent.decision import ChatModelAdapter
        from app.web_providers import WebProviders

        current = self.web.providers
        providers = WebProviders(enabled=True, chat=chat, geo=current.geo, illustrator=current.illustrator, meter=current.meter)
        self.web.providers = providers
        self.web.brain_life.projector.model_available = lambda: bool(getattr(providers.chat, "available", False))
        self.web.brain_life.brain.model = ChatModelAdapter(chat)
        return chat

    def _failing_model(self, reason: str = "http_503") -> FakeChat:
        """模型已配置、可用，但每次调用都失败（不联网）。返回替身，用 `.calls` 数真实调用次数。"""
        from app.web_providers import ChatUnavailable

        return self._use_model(FakeChat(error=ChatUnavailable(reason)))

    def _watch_considers(self) -> list[str]:
        """记下每一轮真的替哪几只宠物想过（顺序保留），不改变行为。"""
        life = self.web.brain_life
        seen: list[str] = []
        original = life.consider

        def consider(pet_id: str, now=None):
            seen.append(pet_id)
            return original(pet_id, now)

        life.consider = consider
        self.addCleanup(lambda: setattr(life, "consider", original))
        return seen

    def _runtime(self, pet_id: str) -> dict:
        """这只宠物的运行记录。还没有这一行时按“什么都没写过”返回，调用方才好直接比。"""
        names = ("last_decision_by", "last_decision_at", "next_review_at", "silence_reason")
        row = self._sql(f"SELECT {', '.join(names)} FROM web_entity_runtime WHERE pet_id = ?", (pet_id,))
        return dict(zip(names, row[0])) if row else dict.fromkeys(names)

    def _reservation_count(self, pet_id: str) -> int:
        """这只宠物一共占过几次额度（名字要和生图合同的 _reservations 区开，两个混入类在同一个测试类里）。"""
        return int(self._sql("SELECT COUNT(*) FROM web_budget_reservations WHERE subject_scope = ?", (f"pet:{pet_id}",))[0][0])

    def contract_c16_fair_rotation(self) -> ContractResult:
        """Q-C16：宠物比一轮的上限多、而且想不成的时候，轮转必须公平——没有谁永远排不到。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        life = self.web.brain_life
        keep_mode = life.mode
        life.mode = "live"
        chat = self._failing_model()
        owner, pets = self._household("q-c16-owner", pets=6)
        seen = self._watch_considers()
        limit, rounds = 2, 4  # 一轮最多想 2 只、6 只宠物：4 轮足够让每只都轮到一次
        job = self._round_job()
        per_round: list[list[str]] = []
        try:
            for _ in range(rounds):
                before = len(seen)
                job(clock.now, limit=limit)
                per_round.append(seen[before:])
                clock.advance(seconds=30)  # 任务进程的一轮
        finally:
            life.mode = keep_mode

        first_pass = seen[:len(pets)]
        starved = [pet for pet in pets if pet not in seen]
        observed = {"pets": len(pets), "limit": limit, "rounds": rounds, "considered_total": len(seen),
                    "distinct_considered": len(set(seen)), "per_round_sizes": [len(r) for r in per_round],
                    "starved": len(starved), "no_repeat_before_first_pass": len(set(first_pass)) == len(first_pass),
                    "model_calls": len(chat.calls),
                    "backoff_written": sum(1 for pet in pets if self._runtime(pet).get("next_review_at"))}
        checks = {
            "每轮不超过上限": all(size <= limit for size in observed["per_round_sizes"]),
            "4 轮之内每只都轮到过": starved == [],
            "第一圈里没有谁被想第二次": observed["no_repeat_before_first_pass"],
            "想不成的都记下了下次再看的时刻": observed["backoff_written"] == len(pets),
        }
        return ContractResult(
            "Q-C16", "一轮的上限小于宠物数、而且持续想不成时，轮转仍然公平（没有谁永远排不到）", "CR-B1、A18",
            LEVEL_INTEGRATION, "I（brain_wiring 的认知线一步）", PASS if all(checks.values()) else FAIL,
            f"{rounds} 轮之内 {len(pets)} 只全部被想过，每轮不超过 {limit} 只", {"checks": checks, **observed},
            ["一个家里 6 只宠物都入住、开“模型回信”，决策模型换成一律失败的替身（不联网）",
             f"调用认知线真正那一步 brain_life，每轮上限 {limit}，连跑 {rounds} 轮，每轮之间时钟 +30 秒",
             "记录每一轮替哪几只想过（不改变行为），核对有没有谁一直排不到"],
            source_digests(WIRING_SRC, BRAIN_SRC, POLICY_SRC), len(GUARD.attempts) - guard0)

    def contract_c17_failure_backoff(self) -> ContractResult:
        """Q-C17：模型持续失败时，单位时间里真实调用次数要有上界；额度用完后进退避，而不是继续预占、继续调。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        life = self.web.brain_life
        keep_mode = life.mode
        life.mode = "live"
        chat = self._failing_model()
        owner, (pet,) = self._household("q-c17-owner", pets=1)
        job = self._round_job()
        rounds = 60  # 任务进程 30 秒一轮：半小时
        try:
            for _ in range(rounds):
                job(clock.now, limit=5)
                clock.advance(seconds=30)
            throttled = {"rounds": rounds, "minutes": rounds // 2, "model_calls": len(chat.calls),
                         "reservations": self._reservation_count(pet), "runtime": self._runtime(pet)}

            # 把这只宠物今天的额度用光（走装配时真正在用的那个预占函数），再跑一轮
            filled = [type(life.reserve(f"q-c17-fill:{i}", "life_plan", pet)).__name__ for i in range(12)]
            calls_before, reservations_before = len(chat.calls), self._reservation_count(pet)
            clock.advance(hours=2)  # 退避时间早过了：如果不看额度，这一轮就会再调一次
            job(clock.now, limit=5)
            cognition = life.projector.facts(pet, clock.now).cognition
            exhausted = {"fill_results": filled, "model_calls_added": len(chat.calls) - calls_before,
                         "reservations_added": self._reservation_count(pet) - reservations_before,
                         "availability": cognition.availability.value, "remaining_today": cognition.remaining_today,
                         "window_resets_at": str(cognition.window_resets_at), "runtime": self._runtime(pet)}
        finally:
            life.mode = keep_mode

        checks = {
            "持续失败时调用次数远少于轮数": throttled["model_calls"] < rounds,
            "半小时里真实调用不超过 8 次": throttled["model_calls"] <= 8,
            "每次想不成都记下了下次再看的时刻": bool(throttled["runtime"]["next_review_at"]),
            "想不成不写“谁决定的”": throttled["runtime"]["last_decision_by"] is None,
            "额度用完后一次都不调": exhausted["model_calls_added"] == 0,
            # 额度用完之后正确的做法是**根本不请求大脑**（心跳如实说成 EXHAUSTED），而不是每轮再预占一次、被拒一次
            "心跳如实把额度用完说成 exhausted 并给出重置时刻": exhausted["availability"] == "exhausted"
                and exhausted["remaining_today"] == 0 and exhausted["window_resets_at"] not in ("None", ""),
            "额度用完后不再继续占额度": exhausted["reservations_added"] == 0,
        }
        return ContractResult(
            "Q-C17", "模型持续失败时的调用上界；额度用完后进退避而不是接着调", "CR-B2、A19", LEVEL_INTEGRATION,
            "I（brain_life 退避 ＋ 额度）", PASS if all(checks.values()) else FAIL,
            "半小时 60 轮里真实调用 ≤ 8 次；额度用完后新增调用 0 次、新增预占 0 次，心跳如实说成 exhausted",
            {"checks": checks, "throttled": throttled, "after_quota_used_up": exhausted},
            ["一只宠物、开“模型回信”，决策模型换成一律失败的替身（不联网）",
             "连跑 60 轮认知线（每轮之间 +30 秒，合计半小时），数真实调用次数",
             "再用装配时真正在用的预占函数把这只宠物当天的额度用光，时钟 +2 小时后再跑一轮",
             "核对：这一轮没有发出任何调用、没有再占额度，心跳把大脑可用性如实说成 exhausted 并带上窗口重置时刻"],
            source_digests(BRAIN_SRC, WIRING_SRC, POLICY_SRC), len(GUARD.attempts) - guard0)

    def contract_c18_single_decider(self) -> ContractResult:
        """Q-C18：模型刚说“今天在家”，世界线的规则生活不能转头把 TA 送出门；记下的决定者要和真的出门的那次对得上。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        life = self.web.brain_life
        keep_mode, keep_brain = life.mode, life.brain
        life.mode, life.brain = "live", StubBrain("stay")
        self._use_model(FakeChat())  # 让心跳认为大脑可用；真正出提案的是上面那个替身决策器
        owner, (pet,) = self._household("q-c18-owner", pets=1)
        trips = "SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?"
        try:
            self._round_job()(clock.now, limit=5)
            decided = {"runtime": self._runtime(pet), "journeys": self._sql(trips, (pet,))[0][0]}
            within: list[dict] = []
            for minutes in (1, 7, 14):  # 决定间隔是 15 分钟：这段时间里规则生活不该替 TA 再决定一次
                clock.now = clock.now + timedelta(minutes=minutes - (within[-1]["at_minute"] if within else 0))
                self.web.ticker.tick(clock.now)
                within.append({"at_minute": minutes, "journeys": self._sql(trips, (pet,))[0][0],
                               "last_decision_by": self._runtime(pet)["last_decision_by"]})
            clock.advance(minutes=20)  # 过了决定间隔：规则生活可以自己决定，但记录必须跟着改
            self.web.ticker.tick(clock.now)
            after = {"journeys": self._sql(trips, (pet,))[0][0], "runtime": self._runtime(pet),
                     "active": self._sql("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ? AND lifecycle = 'active'", (pet,))[0][0]}
        finally:
            life.mode, life.brain = keep_mode, keep_brain

        went_out_later = after["journeys"] > 0
        checks = {
            "模型的“留在家”被记成一次真的决定": decided["runtime"]["last_decision_by"] == "model" and decided["journeys"] == 0,
            "15 分钟内规则生活不再替 TA 决定": all(step["journeys"] == 0 for step in within),
            "15 分钟内决定者一直是模型": all(step["last_decision_by"] == "model" for step in within),
            "任何时刻最多一段行程": after["active"] <= 1,
            "过了间隔之后：出门了就要改成规则决定，没出门就还是模型": (after["runtime"]["last_decision_by"] == "rule") if went_out_later
                else (after["runtime"]["last_decision_by"] == "model"),
        }
        return ContractResult(
            "Q-C18", "同一只宠物同一时刻只有一个决定者；运行记录里的决定者与真的出门那次一致", "CR-B3、A18",
            LEVEL_INTEGRATION, "I（brain_life ＋ 规则生活 life.run）", PASS if all(checks.values()) else FAIL,
            "15 分钟内不出门、决定者一直是模型；之后出门的话决定者改成规则", {"checks": checks, "after_brain": decided, "within_interval": within,
                                                                        "after_interval": after, "went_out_later": went_out_later},
            ["一只宠物、开“模型回信”，替身决策器一律选“留在家”（不调用真实模型）",
             "跑一轮认知线：模型决定留在家，运行记录写下 last_decision_by=model",
             "在 +1 / +7 / +14 分钟各跑一轮世界线（里面就是规则生活 life.run），核对没有被送出门",
             "再 +20 分钟跑一轮世界线：过了决定间隔，核对“出门了就记规则决定”"],
            source_digests(BRAIN_SRC, LIFE_SRC, RUNTIME_SRC, WIRING_SRC), len(GUARD.attempts) - guard0)

    # ---- Q-C22：租约失效必须让**整轮**停下来（CR-C8）----
    def contract_c22_round_really_stops(self) -> ContractResult:
        """Q-C22：租约失效之后，同一轮里**后续本应处理的宠物**与**后续本应执行的任务**都不再被处理。

        与 Q-C14 不重复：Q-C14 验的是被接管那一件事本身（业务写不进去、已发出的费用照记、正常租约对照），
        **这一条验的是"整轮停住"**——C 写明它的 `round_stopped` 只覆盖 `consider` 一层，
        直接调 `consider` 的脚本证明不了后面的宠物和任务有没有继续跑。
        """
        import sqlite3

        from runtime_contract_boundary import StubBrain

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web, life = self.web, self.web.brain_life
        keep_mode, keep_brain = life.mode, life.brain

        def steal(name: str) -> None:
            """把租约行的持有者改成别人（不动时钟）。只写 Q 自己的一次性临时库。"""
            conn = sqlite3.connect(self.settings.database_path)
            try:
                with conn:
                    conn.execute("UPDATE web_worker_leases SET holder = 'q-c22-rival' WHERE name = ?", (name,))
            finally:
                conn.close()

        # 甲：认知线——一轮里有 4 只宠物要想，第一只想到一半租约被接管
        owner, pets = self._household("q-c22-cognition", pets=4)
        self._use_model(FakeChat())
        seen = self._watch_considers()
        stolen: list[str] = []
        life.mode = "live"
        life.brain = StubBrain("local:cafe", thinking=lambda: (stolen.append("x"), steal("cognition"))[0] if not stolen else None)
        try:
            web.cognition.tick(clock.now)
        finally:
            life.mode, life.brain = keep_mode, keep_brain
        runtime_rows = self._sql("SELECT COUNT(*) FROM web_entity_runtime WHERE pet_id IN ({}) AND (last_decision_by IS NOT NULL "
                                 "OR next_review_at IS NOT NULL OR silence_reason IS NOT NULL)".format(",".join("?" * len(pets))), tuple(pets))[0][0]
        cognition = {"pets": len(pets), "considered": len(seen), "distinct": len(set(seen)),
                     "journeys": self._sql("SELECT COUNT(*) FROM web_journeys WHERE pet_id IN ({})".format(",".join("?" * len(pets))), tuple(pets))[0][0],
                     "runtime_rows_written": runtime_rows, "lease_stolen": len(stolen)}

        # 乙：世界线——在到期结算那一步丢租约，排在后面的任务不许再跑
        owner2, pet2 = self._brain_owner("q-c22-world", coins=0)
        journey_id = owner2.post(f"/journey/depart?pet_id={pet2}", {"destination_key": "work:florist"}).json()["journey_id"]
        clock.now = web.journeys.repo.get(journey_id).completes_at + timedelta(minutes=1)
        ran: list[str] = []
        # 队首放一步“这一轮进行中把 world 租约让给别人”，队尾放一个只记一笔的哨兵。
        # 不能在跑轮之前改：那样 tick 一开始就拿不到租约、整轮直接跳过，证明不了“中途丢了之后后面不再跑”。
        web.ticker.jobs.insert(0, ("q-c22-steal", lambda now: steal("world")))
        web.ticker.jobs.append(("q-sentinel", lambda now: ran.append("sentinel")))
        try:
            web.ticker.tick(clock.now)
            blocked = {"sentinel_ran": "sentinel" in ran,
                       "salary_rows": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"web:job:{journey_id}",))[0][0]}
            # 正常租约对照：把租约还回去，同一轮必须一路跑到最后那个任务
            web.ticker.jobs = [job for job in web.ticker.jobs if job[0] != "q-c22-steal"]
            conn = sqlite3.connect(self.settings.database_path)
            try:
                with conn:
                    conn.execute("DELETE FROM web_worker_leases WHERE name = 'world'")
            finally:
                conn.close()
            ran.clear()
            clock.advance(minutes=1)
            web.ticker.tick(clock.now)
            control = {"sentinel_ran": "sentinel" in ran,
                       "salary_rows": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"web:job:{journey_id}",))[0][0]}
        finally:
            web.ticker.jobs = [job for job in web.ticker.jobs if job[0] not in ("q-sentinel", "q-c22-steal")]

        checks = {
            "认知线：租约真的被接管了": cognition["lease_stolen"] == 1,
            "认知线：只想了第一只，后面的宠物不再处理": cognition["considered"] == 1,
            "认知线：一趟行程都没建": cognition["journeys"] == 0,
            "认知线：后续宠物一行运行记录都没写": cognition["runtime_rows_written"] == 0,
            "世界线：排在后面的任务不再执行": blocked["sentinel_ran"] is False,
            "世界线：到期结算也没写进去": blocked["salary_rows"] == 0,
            "正常租约对照：同一轮一路跑到最后那个任务": control["sentinel_ran"] is True,
            "正常租约对照：到期结算照常入账": control["salary_rows"] == 1,
        }
        return ContractResult(
            "Q-C22", "租约失效让整轮停住：后续宠物与后续任务都不再处理；租约正常时同一轮跑到最后", "CR-C8、CR-A4、A08",
            LEVEL_INTEGRATION, "B（brain_wiring 轮内）＋ C／I（ticker 与 uow 围栏）", PASS if all(checks.values()) else FAIL,
            "认知线只处理了第一只、0 行程、0 运行记录；世界线的哨兵任务没跑、工钱 0 条；正常租约对照两样都走完",
            {"checks": checks, "cognition_lane": cognition, "world_lane_blocked": blocked, "world_lane_control": control},
            ["甲：一个家里 4 只宠物都要想；替身决策器在**第一只**的模型调用里把 cognition 租约的持有者改成别人（不动时钟）",
             "甲：跑一轮认知线，核对只想了第一只、后面三只连运行记录都没写、一趟行程都没建",
             "乙：另一只宠物打工到期；世界线队首插一步“本轮进行中把 world 租约让给别人”，队尾挂一个只记一笔的哨兵任务",
             "乙：跑一轮，核对哨兵没跑、工钱没入账",
             "乙的正常对照：把租约行删掉让本进程重新拿到，再跑一轮——哨兵必须跑到、工钱必须入账",
             "**与 Q-C14 的分工**：C14 验被接管那一件事本身（含费用事实保留），这一条只验“整轮停住”"],
            source_digests(WIRING_SRC, "app/web_agent/ticker.py", "app/web_platform/uow.py", "app/web_journey/settlement.py"),
            len(GUARD.attempts) - guard0)


CONTRACTS = ("c16_fair_rotation", "c17_failure_backoff", "c18_single_decider", "c22_round_really_stops")
