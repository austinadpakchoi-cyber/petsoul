"""独立验收（工作包 Q）的生图合同：结果未确认（unknown）与恢复、重画（Q-C10）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、真实装配、替身生图供应商，不联网、不产生任何付费调用。

判定落在**主人真正看得到的地方**（`GET /communicator/{pet}/messages` 与 `POST .../retry-photo`），不只看内部表：
"结果确认中"和"确认失败"如果在接口上长得一模一样，那么无论内部记得多准，主人看到的都是"没画成"。
"""

from __future__ import annotations

import sqlite3

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from web_base import LUNCH_UTC, FakeClock

ILLUS_SRC, IMAGES_SRC = "app/web_journey/illustrations.py", "app/web_providers/images.py"
COMM_SRC, SOCIAL_SRC = "app/web_communicator/service.py", "app/schemas/web/social.py"
# 主人在消息里能看到的、与"这张图怎么样了"有关的字段。比对时只看这些，不取消息原文
PHOTO_FIELDS = ("state", "photo_status", "photo_url", "status_note")


# 这些原因在请求离开本机之前就决定了，**没有越过发送边界**：没配置、本地记的每日上限已满、
# 当场被拒（4xx，服务端没开始生成）、连不上或被限流。其余（成功、超时、响应回来后才失败）都算已经发出去。
PRE_DISPATCH = frozenset({"daily_cap", "not_configured", "rejected", "provider_error"})


class StagedIllustrator:
    """替身生图：按顺序演每一次调用。None＝成功，字符串＝这次抛 ImageUnavailable(该原因)。不联网。

    **计数口径**：`entered` 是进了 render() 几次，`dispatched` 是真的越过发送边界几次（可能已计费）。
    两者不是一回事——判定一律以 `dispatched` 为准，不能把"进了 render()"当成"已经发出去"。
    """

    available = True
    provider_label = "Q 合同替身生图"

    def __init__(self, *outcomes: str | None, on_call=None) -> None:
        self.outcomes = list(outcomes)
        self.entered = 0  # 进了 render() 几次
        self.dispatched = 0  # 真的越过发送边界几次
        # on_call(第几次, "enter"/"exit")：用来在“某一次调用之前／之后”插一件事（例如主人这时候撤权）
        self.on_call = on_call

    @property
    def calls(self) -> int:
        return self.entered

    @property
    def sent(self) -> int:
        return self.dispatched

    def render(self, prompt, reference=None, size="2048x2048"):  # noqa: ARG002 - 与 Illustrator.render 同签名
        from app.image_provider.models import GeneratedImage
        from app.web_providers import ImageUnavailable

        self.entered += 1
        if self.on_call is not None:
            self.on_call(self.entered, "enter")
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if outcome is not None:
            if outcome not in PRE_DISPATCH:
                self.dispatched += 1  # 已经发出去了，只是结果不明
            raise ImageUnavailable(outcome)
        self.dispatched += 1
        image = GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\nq-fake", mime_type="image/png", model="q-stub", provider="q", source="url")
        if self.on_call is not None:
            self.on_call(self.entered, "exit")  # 响应已经回来了，但调用方还没往下走
        return image


class MediaContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由 RuntimeContractCases 提供）。"""

    def _use_illustrator(self, *outcomes: str | None) -> StagedIllustrator:
        from app.web_providers import WebProviders

        art = StagedIllustrator(*outcomes)
        current = self.web.providers
        self.web.providers = WebProviders(enabled=True, chat=current.chat, geo=current.geo, illustrator=art, meter=current.meter)
        self.web.illustrations.illustrator = art
        return art

    def _photo_journey(self, label: str, clock) -> tuple:
        """一位开了"生成照片"的主人＋一只没有照片的宠物，坐船出门一趟（船上的奇遇会排一张图）。返回 (主人, 消息, 任务号)。"""
        from app.schemas import EconomyTransactionType

        owner = self.user(label)
        owner.upload_pet("年糕", "cat")
        owner.move_in()
        assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
        self.web.economy.apply(owner.pet_id, 300, EconomyTransactionType.web_reward, f"q-grant:{owner.pet_id}", reason="Q 合同船票", source="q.contract")
        departed = owner.post("/journey/depart", {"destination_key": "macau_ferry"})
        assert departed.status_code == 200, departed.text
        clock.advance(hours=3)
        self.run_background(clock.now)
        message = next((m for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if m.get("photo_status")), None)
        assert message is not None, "坐船那趟应当排出一张图并带来一条消息"
        task_id = self._sql("SELECT photo_task_id FROM web_messages WHERE message_id = ?", (message["message_id"],))[0][0]
        self._park_other_tasks(task_id)
        return owner, message, task_id

    def _park_other_tasks(self, task_id: str) -> int:
        """把同一趟里其它的生图任务（明信片、手账）推到很久以后。

        这样这条合同里跑的每一次供应商调用都属于被观察的那一个任务——否则"这次发出去了几次"会混进别的任务，
        结论就说不准。只动 Q 自己的一次性临时库，不改业务实现。"""
        import sqlite3

        conn = sqlite3.connect(self.settings.database_path)
        try:
            with conn:
                cur = conn.execute("UPDATE web_tasks SET run_after = '2099-01-01T00:00:00+00:00' "
                                   "WHERE kind = 'illustration' AND status = 'queued' AND task_id <> ?", (task_id,))
            return cur.rowcount
        finally:
            conn.close()

    def _usage(self, ledger, clock) -> int:
        return int(ledger.usage("usage:image:illustration", now=clock.now)["used"])

    def _reservations(self, task_id: str) -> list[dict]:
        rows = self._sql("SELECT operation_id, status, outcome, reserved_units, actual_units FROM web_budget_reservations "
                         "WHERE operation_id LIKE ? ORDER BY rowid", (f"illustration:{task_id}:%",))
        names = ("operation_id", "status", "outcome", "reserved_units", "actual_units")
        return [dict(zip(names, row)) for row in rows]

    def _shown(self, owner, message_id: str) -> dict:
        """主人此刻在消息列表里看到的、与这张图有关的字段（不取消息原文）。"""
        thread = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        row = next(m for m in thread if m["message_id"] == message_id)
        return {field: row.get(field) for field in PHOTO_FIELDS}

    def _rows_of(self, task_id: str) -> dict:
        illustration = self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))
        task = self.web.illustrations.tasks.get(task_id)
        return {"illustration": illustration[0][0] if illustration else None, "task": task.status, "attempts": task.attempts}

    def contract_c10_photo_unknown_result(self) -> ContractResult:
        """Q-C10：生图超时＝结果未确认。不能展示成"确认失败"、不能自动重发；主人显式重画才是新的一次尝试。"""
        from app.web_platform.budget import BudgetLedger

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        ledger = BudgetLedger(self.app.state.storage)

        # 甲：证件照发出去了，正图超时——可能已被受理并计费，结果不明
        unknown_art = self._use_illustrator(None, "timeout")
        owner_u, message_u, task_u = self._photo_journey("q-c10-unknown", clock)
        used_before = self._usage(ledger, clock)
        self.web.illustrations.run_pending()
        unknown = {"sent": unknown_art.sent, "calls": unknown_art.calls, "usage_delta": self._usage(ledger, clock) - used_before,
                   "rows": self._rows_of(task_u), "reservations": self._reservations(task_u),
                   "outcome_of": self.web.illustrations.outcome_of(task_u), "shown": self._shown(owner_u, message_u["message_id"])}

        # 甲的下一轮：不该再发一次（超时不自动重发）
        before_calls = unknown_art.calls
        clock.advance(minutes=10)  # 领取租期早过了：如果会自动重排，这一轮就会重跑
        self.web.illustrations.run_pending()
        no_auto_retry = {"provider_calls_added": unknown_art.calls - before_calls, "sent": unknown_art.sent, "rows": self._rows_of(task_u)}

        # 乙：两次都是供应商明确失败（确定没成功），次数用完——这才是"确认没画成"
        failed_art = self._use_illustrator(None, "provider_error", "provider_error")
        owner_f, message_f, task_f = self._photo_journey("q-c10-failed", clock)
        for _ in range(3):
            clock.advance(minutes=10)
            self.web.illustrations.run_pending()
        failed = {"sent": failed_art.sent, "calls": failed_art.calls, "rows": self._rows_of(task_f), "reservations": self._reservations(task_f),
                  "outcome_of": self.web.illustrations.outcome_of(task_f), "shown": self._shown(owner_f, message_f["message_id"])}

        # 主人对甲点"重画"（正式接口）：这是**新的一次尝试**，原来那笔结果不明的记录要原样留着
        redraw_art = self._use_illustrator(None)
        before_rows = unknown["reservations"]
        retried = owner_u.post(f"/communicator/{owner_u.pet_id}/messages/{message_u['message_id']}/retry-photo")
        queued = self._rows_of(task_u)
        self.web.illustrations.run_pending()
        after_rows = self._reservations(task_u)
        redraw = {"http": retried.status_code, "after_click": queued, "rows": self._rows_of(task_u),
                  "provider_calls": redraw_art.calls, "reservations": after_rows,
                  "original_kept": [r for r in after_rows if r["operation_id"] == before_rows[-1]["operation_id"]] == [before_rows[-1]],
                  "new_operation_ids": [r["operation_id"] for r in after_rows if r["operation_id"] not in {x["operation_id"] for x in before_rows}],
                  "shown": self._shown(owner_u, message_u["message_id"])}

        checks = {
            "超时结算成 unknown，不当作没发生": unknown["reservations"][-1]["outcome"] == "unknown" and unknown["reservations"][-1]["status"] == "unknown",
            "超时那次确实发出去了、按实际次数计量": unknown["sent"] == 2 and unknown["usage_delta"] >= 2
                and unknown["reservations"][-1]["reserved_units"] == 2,
            "超时不排自动重试": unknown["rows"]["task"] == "failed",
            "下一轮不会再调一次供应商": no_auto_retry["provider_calls_added"] == 0 and no_auto_retry["rows"]["task"] == "failed",
            # 作为对照的那一条必须是"确认没画成"：任务与展示都终结在 failed，且**没有任何一笔预占停在结果不明**。
            # 不写死某一次预占该是 settled 还是 released——"供应商报错算不算已发出"由 A 的口径决定，这里只要求结论明确。
            "明确失败的那条是确认没画成": failed["rows"]["task"] == "failed" and failed["rows"]["illustration"] == "failed"
                and all(row["status"] not in ("reserved", "unknown", "expired") for row in failed["reservations"]),
            "服务层分得清未确认与确认失败": (unknown["outcome_of"], failed["outcome_of"]) == ("unknown", "failed"),
            "主人看到的也分得清（未确认 ≠ 确认失败）": unknown["shown"] != failed["shown"],
            "重画这一下是新的一次尝试": redraw["http"] == 200 and redraw["after_click"]["task"] == "queued"
                and len(redraw["new_operation_ids"]) == 1 and redraw["provider_calls"] >= 1,
            "原来那笔结果不明原样保留": redraw["original_kept"],
            "重画成功后真的出图": redraw["rows"]["illustration"] == "ready" and redraw["shown"]["photo_status"] == "ready",
        }
        return ContractResult(
            "Q-C10", "生图结果未确认：不展示成确认失败、不自动重发；显式重画是分开追踪的新尝试", "CR-A3、CR-A1、A24",
            LEVEL_INTEGRATION, "A（生图结算）＋ I（展示层字段）", PASS if all(checks.values()) else FAIL, "全部检查为 true",
            {"checks": checks, "unknown_case": unknown, "no_auto_retry": no_auto_retry, "failed_case": failed, "redraw": redraw},
            ["主人开“生成照片”，宠物坐船出门（船上的奇遇会排一张图），换成替身生图供应商（不联网、不付费）",
             "把同一趟里其它生图任务（明信片、手账）推到很久以后，让每一次调用都属于被观察的那个任务",
             "甲：证件照成功、正图超时 → 跑一轮任务，核对结算、任务终态与主人看到的字段",
             "甲：时钟 +10 分钟再跑一轮，核对没有再调一次供应商",
             "乙：两次都是供应商明确失败、次数用完 → 这才是“确认没画成”",
             "比对甲、乙两条消息上与图有关的字段（state / photo_status / photo_url / status_note，不取消息原文）",
             "对甲调用正式接口 POST /communicator/{pet}/messages/{id}/retry-photo，再跑一轮",
             "核对：新增一笔预占、原来那笔结果不明一字未改、重画后真的出图"],
            source_digests(ILLUS_SRC, IMAGES_SRC, COMM_SRC, SOCIAL_SRC), len(GUARD.attempts) - guard0)

    # ---- Q-C11：重画的事务一致性 ----
    def _failing_display_write(self):
        """与 unit_of_work 同签名的替身：任务重排照常写，改插画展示状态时抛错。用来验证两次写入真的同生共死。"""
        import contextlib

        storage = self.app.state.storage

        class Proxy:
            def __init__(self, conn) -> None:
                self._conn = conn

            def execute(self, sql, params=()):
                if sql.lstrip().upper().startswith("UPDATE WEB_ILLUSTRATIONS"):
                    raise sqlite3.OperationalError("disk I/O error (injected by Q-C11)")
                return self._conn.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        @contextlib.contextmanager
        def failing(_storage):
            with storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                yield Proxy(conn)

        return failing

    def _redraw_state(self, owner, message_id: str, task_id: str) -> dict:
        """四处放在一起看：任务、插画记录、主人看到的展示状态，以及**费用侧**的预占。

        前三项是业务/展示状态，出错时必须一起回滚；第四项是**已经发生的成本**，
        它既不能被回滚抹掉，也不能被这次失败的重画重复记一笔——所以放进同一张快照里一并比对。
        """
        rows = self._rows_of(task_id)
        return {"task": rows["task"], "illustration": rows["illustration"], "shown": self._shown(owner, message_id)["photo_status"],
                "reservations": self._reservations(task_id)}

    def contract_c11_redraw_is_all_or_nothing(self) -> ContractResult:
        """Q-C11：点"重画"时，任务重排、插画记录、消费者展示状态必须一起成、一起不成，不留中间态。"""
        from app.web_journey import illustrations as illustrations_mod

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        original_uow = illustrations_mod.unit_of_work
        cases: dict = {}

        def run(label: str, outcomes: tuple) -> None:
            self._use_illustrator(*outcomes)
            owner, message, task_id = self._photo_journey(f"q-c11-{label}", clock)
            self.web.illustrations.run_pending()
            for _ in range(3):  # 让"明确失败"那条把重试次数用完，真正终结在 failed
                clock.advance(minutes=10)
                self.web.illustrations.run_pending()
            before = self._redraw_state(owner, message["message_id"], task_id)

            illustrations_mod.unit_of_work = self._failing_display_write()  # 注入：任务重排与改展示状态之间出错
            raised = None
            try:
                owner.post(f"/communicator/{owner.pet_id}/messages/{message['message_id']}/retry-photo")
            except Exception as exc:  # noqa: BLE001 - 注入的故障会一路抛到路由外
                raised = type(exc).__name__
            finally:
                illustrations_mod.unit_of_work = original_uow
            after_failure = self._redraw_state(owner, message["message_id"], task_id)

            self._use_illustrator(None)  # 正常对照：同一个入口再点一次，这次不注入
            ok = owner.post(f"/communicator/{owner.pet_id}/messages/{message['message_id']}/retry-photo")
            queued = self._redraw_state(owner, message["message_id"], task_id)
            self.web.illustrations.run_pending()
            cases[label] = {"before": before, "raised": raised, "after_failure": after_failure,
                            "control_http": ok.status_code, "control_after_click": queued,
                            "control_final": self._redraw_state(owner, message["message_id"], task_id)}

        try:
            run("unknown", (None, "timeout"))  # 起点：结果未确认
            run("failed", (None, "rejected", "rejected"))  # 起点：确认没画成（当场被拒，没越过发送边界）
        finally:
            illustrations_mod.unit_of_work = original_uow

        rolled_back = {name: case["after_failure"] == case["before"] for name, case in cases.items()}
        checks = {
            "两种起点都终结在“没画成”": all(case["before"]["task"] == "failed" and case["before"]["illustration"] == "failed" for case in cases.values()),
            "注入异常后任务没有被重排": all(case["after_failure"]["task"] == case["before"]["task"] for case in cases.values()),
            "注入异常后插画记录没有变": all(case["after_failure"]["illustration"] == case["before"]["illustration"] for case in cases.values()),
            "注入异常后消费者展示状态也没有变": all(case["after_failure"]["shown"] == case["before"]["shown"] for case in cases.values()),
            "正常对照：重画真的另起一笔预占（没有吞掉成本）": all(len(case["control_final"]["reservations"]) > len(case["before"]["reservations"])
                                                              for case in cases.values()),
            "业务与展示一起回滚（unknown 起点）": rolled_back["unknown"],
            "业务与展示一起回滚（failed 起点）": rolled_back["failed"],
            "费用事实既没被抹掉也没被重复记": all(case["after_failure"]["reservations"] == case["before"]["reservations"]
                                                for case in cases.values()),
            "正常对照：三者一起进入处理中": all(case["control_http"] == 200 and case["control_after_click"]["task"] == "queued"
                                             and case["control_after_click"]["illustration"] == "processing"
                                             and case["control_after_click"]["shown"] == "processing" for case in cases.values()),
            "正常对照：跑完真的出图（替身产物）": all(case["control_final"]["illustration"] == "ready"
                                                  and case["control_final"]["shown"] == "ready" for case in cases.values()),
        }
        return ContractResult(
            "Q-C11", "点“重画”时业务与展示状态一起成、一起不成；已经发生的费用不被回滚抹掉", "CR-A5、A24、A19", LEVEL_INTEGRATION,
            "A（生图重画）＋ I／B（组合根与消费者接线）", PASS if all(checks.values()) else FAIL,
            "注入异常后三处都回到点之前的样子；正常对照三处一起进入处理中",
            {"checks": checks, "rolled_back": rolled_back, "cases": cases},
            ["两只宠物各排一张图：一条以“结果未确认”（超时）结束，一条以“确认没画成”（当场被拒、次数用完）结束",
             "把 illustrations 模块里的 unit_of_work 换成“改插画展示状态必失败”的替身（任务重排照常写）",
             "走正式入口 POST /communicator/{pet}/messages/{id}/retry-photo，异常抛出后核对任务、插画记录、消息展示三处",
             "撤掉注入，再点一次同一个入口作为正常对照，并跑一轮任务"],
            source_digests(ILLUS_SRC, COMM_SRC, "app/routers/web/communicator.py", "app/web_platform/tasks.py"), len(GUARD.attempts) - guard0)

    # ---- Q-C15：部分发送的计量 ----
    def contract_c15_partial_send_metering(self) -> ContractResult:
        """Q-C15：预占两个单位、只有一次越过发送边界时，计一次、退一个；一次都没越过才整笔退回。

        计数一律以替身在**发送边界**上的记录（dispatched）为准，不把进了 render() 的次数当成已发送。
        """
        from app.web_platform.budget import BudgetLedger

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        ledger = BudgetLedger(self.app.state.storage)
        cases: dict = {}

        def run(label: str, outcomes: tuple) -> None:
            art = self._use_illustrator(*outcomes)
            owner, message, task_id = self._photo_journey(f"q-c15-{label}", clock)
            used_before = self._usage(ledger, clock)
            self.web.illustrations.run_pending()
            rows = self._reservations(task_id)
            cases[label] = {"entered": art.entered, "dispatched": art.dispatched, "usage_delta": self._usage(ledger, clock) - used_before,
                            "reservations": rows, "rows": self._rows_of(task_id)}

        # 甲：没有主人的照片 → 预占 2（证件照＋正图）。证件照发出去了，正图在发送边界之前被本机的每日上限挡下
        run("one_of_two_sent", (None, "daily_cap"))
        # 乙：第一次就在发送边界之前被挡下 → 一次都没发出
        run("none_sent", ("daily_cap",))

        partial, nothing = cases["one_of_two_sent"], cases["none_sent"]
        checks = {
            "甲：预占了两个单位": partial["reservations"][0]["reserved_units"] == 2,
            "甲：只有一次越过发送边界": (partial["entered"], partial["dispatched"]) == (2, 1),
            "甲：按实际发出的一次计量，不整笔退回": partial["reservations"][0]["status"] == "settled"
                and partial["reservations"][0]["actual_units"] == 1 and partial["usage_delta"] == 1,
            "乙：一次都没越过发送边界": (nothing["entered"], nothing["dispatched"]) == (1, 0),
            "乙：整笔退回、一个单位都不计": nothing["reservations"][0]["status"] == "released"
                and nothing["reservations"][0]["outcome"] == "not_sent" and nothing["usage_delta"] == 0,
            "两条都如实显示没画成": all(case["rows"]["illustration"] == "failed" for case in cases.values()),
        }
        return ContractResult(
            "Q-C15", "部分发送的计量：发出几次算几次，一次都没发出才整笔退回", "CR-A1、A19", LEVEL_INTEGRATION, "A（生图结算）",
            PASS if all(checks.values()) else FAIL, "甲 2 进 1 发 → 计 1 退 1；乙 1 进 0 发 → 整笔退回",
            {"checks": checks, "cases": cases},
            ["主人开“生成照片”，宠物是没有照片的新伙伴（一次要画证件照＋正图，预占 2 个单位）",
             "甲：证件照越过发送边界并成功，正图在发送边界之前被每日上限挡下",
             "乙：第一次就在发送边界之前被挡下",
             "计数以替身在发送边界上的记录为准（dispatched），同时记下进 render() 的次数（entered）以便对照",
             "核对预占的结算状态、actual_units 与当日用量的增量"],
            source_digests(ILLUS_SRC, IMAGES_SRC, "app/web_platform/budget.py"), len(GUARD.attempts) - guard0)

    # ---- Q-C23：家庭“生成照片”授权在途被撤回（独立复验 A 的撤权边界小批）----
# Q-C23 `consent_revoked_in_flight` 已**退役**（2026-09-24）：它钉的"主人关掉『生成照片』→ 在途撤权 →
# 旧结果不得发布"这条规则，随用户 2026-09-23 取消逐次授权询问而**不复存在**（`photo_generation_on`
# 只剩 `bool(illustrations.available())`）。**不是改触发条件接着钉**（那是 Q-C24 的情形），是规则本身没了。
#   · 旧证据保留原指纹并标历史：`contracts-c23-after-consent-removal.json`（17 项 6 红，绑取消询问后的实现）；
#     更早的全绿证据在 `contracts-photo-bundle-20260923T0232Z.json` 之前的各轮里。
#   · **继任者是 Q-C34**（`runtime_contract_photo.py`）：接手仍然适用的那一半——
#     授权在途变化时结果不得给已失去访问权的人，现在由取图那一刻的 `can_view_pet` 承载。
#   · 删掉函数体的直接原因：它是 `illustrations.consent_in` 在全仓的**唯一读者**，挡着 A 删那两个已无人读的属性。
CONTRACTS = ("c10_photo_unknown_result", "c11_redraw_is_all_or_nothing", "c15_partial_send_metering")
