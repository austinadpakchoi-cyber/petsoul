"""独立验收（工作包 Q）：三个图片消费者的"任务先入队、记录后插"竞态收口在同一个写事务里（Q-C29）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。

三个消费者（都在真实装配里接着同一套判断 `photo_display.settled_photo`）：
  通讯器家庭消息（`_photo_at_insert`）、旅行攻略（`guides.create`）、邮局明信片（`collection._post_office`）。
三种到达次序各自验一遍：
  ① 记录先插：插的时候任务还在排队 → 记录先写"正在画"，worker 随后回调把它改成终态；
  ② worker 先到：插之前任务已经走到终态 → 回调命中 0 行，插的那一刻必须**在同一个写事务里**读到终态并直接写对；
  ③ 读到"正在画"之后 worker 才来抢写锁：证明中间**没有缝**——读与插不在同一个事务里的话，
     worker 会挤在中间、回调命中 0 行，记录就永远停在"正在画"。
另有正常次序对照，以及 unknown 与 failed **不能混成一个取值**。

**不手补任何回调**：`image_outcome_in`／`illustration_outcome_in` 一律用正式装配接上的那一份。
观察点与次序控制只在测试进程内包一层壳，不改共享业务源码。
**数据库锁异常不作为证明**：worker 线程必须自己跑完、不抛异常，记录必须真的走到终态。
"""

from __future__ import annotations

import json
import threading

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from runtime_contract_media import StagedIllustrator
from web_base import LUNCH_UTC, FakeClock

C29_SOURCES = ("app/web_communicator/service.py", "app/web_journey/guides.py", "app/web_collection/service.py",
               "app/web_journey/photo_display.py", "app/web_journey/illustrations.py", "app/web_platform/uow.py",
               "app/web_agent_wiring.py", "app/web_platform/budget.py")

CONSUMERS = ("message", "guide", "postcard")
ORDERS = ("insert_first", "worker_first", "lock_wait")
# 每个消费者的记录落在哪张表、状态列叫什么、图地址列叫什么
TABLES = {"message": ("web_messages", "photo_status", "photo_url", "photo_task_id"),
          "guide": ("web_travel_guides", "image_status", "image_url", "image_task_id"),
          "postcard": ("web_collection_items", "image_status", "image_url", "image_task_id")}


class ConsumerContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由同组的用例提供）。"""

    def _c29_row(self, consumer: str, task_id: str) -> dict:
        table, status_col, url_col, key_col = TABLES[consumer]
        rows = self._sql(f"SELECT {status_col}, {url_col} FROM {table} WHERE {key_col} = ?", (task_id,))
        return {"exists": bool(rows), "status": rows[0][0] if rows else None, "has_url": bool(rows[0][1]) if rows else False}

    def _c29_pet_of(self, task_id: str) -> str | None:
        """这个任务是替哪只宠物画的——用来核对任务号确实属于本轮这只，不是串到同趟别的消费者。"""
        rows = self._sql("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,))
        return json.loads(rows[0][0]).get("pet_id") if rows else None

    def _c29_task(self, task_id: str) -> dict:
        """这一个任务现在怎么样：任务状态、尝试次数、插画状态、这个任务名下的预占。

        **预占条数不等于发送次数**：一次尝试可以发出多次（没有主人照片时先画证件照再画场景图）。
        发送次数按 `_render` 前后替身 `dispatched` 的差额记到具体任务名下，见 `counting_render`。"""
        rows = self._sql("SELECT status, attempts, last_error FROM web_tasks WHERE task_id = ?", (task_id,))
        art = self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))
        sent = self._sql("SELECT operation_id, status, outcome, actual_units FROM web_budget_reservations "
                         "WHERE operation_id LIKE ? ORDER BY rowid", (f"illustration:{task_id}:%",))
        return {"task_status": rows[0][0] if rows else None, "attempts": rows[0][1] if rows else None,
                "last_error": rows[0][2] if rows else None,  # 重试时这里会说明是哪种失效（例如领取过期）
                "illustration": art[0][0] if art else None, "reservations": len(sent),
                "reservation_rows": [dict(zip(("operation_id", "status", "outcome", "actual_units"), r)) for r in sent]}

    def contract_c29_image_consumers_insert_in_one_transaction(self) -> ContractResult:
        """Q-C29：三个消费者插记录时，读当前图片状态与插入这一行必须在**同一个写事务**里，三种到达次序都不留缝。"""
        guard0 = len(GUARD.attempts)
        started = source_digests(*C29_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web

        import app.web_collection.service as collection_mod
        import app.web_journey.guides as guides_mod

        real = {"message": web.communicator.illustration_request, "guide": web.guides.image_request,
                "postcard": web.collection.selfie_request,
                "guide_settled": guides_mod.settled_photo, "postcard_settled": collection_mod.settled_photo,
                "message_settled": web.communicator._photo_at_insert, "render": web.illustrations._render}
        wiring = {"message_outcome_in": web.communicator.illustration_outcome_in is not None,
                  "guide_outcome_in": web.guides.image_outcome_in is not None,
                  "postcard_outcome_in": web.collection.image_outcome_in is not None}
        seen: dict = {}

        def note(consumer: str, key: str, value) -> None:
            seen.setdefault(consumer, {})[key] = value

        def run_worker() -> None:
            web.illustrations.run_pending()

        def sends_of(state: dict, task_id: str | None) -> int:
            """这个任务到此刻为止真的发出过几次——`_render` 还没返回时按实时基准算。"""
            if task_id is not None and state.get("render_task") == task_id:
                return state["art"].dispatched - state["render_base"]
            return state["sends"].get(task_id, 0)

        def counting_render(state: dict):
            """包住 `_render`：这一次是替哪个任务画的，就把**这一次真的越过发送边界几次**记到那个任务名下。

            一次尝试可以发出**多次**（没有主人照片时先画证件照再画场景图），所以"预占 1 条、attempts=1"
            **不等于**"只发出过一次"。要证明"插记录没多发"，只能按这个任务自己的发送边界算。
            """
            original = real["render"]  # 一律包最初那一份：重复安装不会层层嵌套

            def wrapped(task, **kwargs):
                # 记一个基准，使得"这个任务至今发出几次" == art.dispatched - base，**画到一半也读得准**：
                # ③ 那一档 worker 正卡在 render 里面等放行，`_render` 还没返回，只看返回后累加会少算。
                state["render_task"] = task.task_id
                state["render_base"] = state["art"].dispatched - state["sends"].get(task.task_id, 0)
                try:
                    return original(task, **kwargs)
                finally:
                    state["sends"][task.task_id] = state["art"].dispatched - state["render_base"]
                    state["render_task"] = None

            return wrapped

        def make_request(consumer: str, order: str, target: str | None, state: dict):
            """包住"请求生图"这一步：任务号一拿到，就按这一轮要验的次序把 worker 安排进来。"""
            original = real[consumer]

            def wrapped(*args, **kwargs):
                task_id = original(*args, **kwargs)
                if not task_id or (target is not None and target != consumer):
                    return task_id
                note(consumer, "task_id", task_id)  # 绑**这一次实际返回的**任务号，不按全表最新 rowid 去猜
                note(consumer, "pet_matches", self._c29_pet_of(task_id) == state.get("pet_id"))
                note(consumer, "task_at_request", self._c29_task(task_id))
                note(consumer, "row_before_insert", self._c29_row(consumer, task_id))
                if order == "worker_first":
                    run_worker()  # 插记录之前 worker 就已经跑完：回调必然命中 0 行
                    note(consumer, "task_before_insert", self._c29_task(task_id))
                elif order == "lock_wait":
                    state["thread"] = threading.Thread(target=state["body"], daemon=True)
                    state["thread"].start()
                    state["rendered"].wait(timeout=20)  # 等它把图画出来、正要去拿写锁
                state["task_id"] = task_id
                return task_id

            return wrapped

        def make_settled(consumer: str, order: str, state: dict):
            """包住消费者**在自己写事务里**读当前状态这一步：只观察，外加在 lock_wait 那一轮放 worker 进来抢锁。"""
            original = real[f"{consumer}_settled"]

            def wrapped(*args, **kwargs):
                value = original(*args, **kwargs)
                note(consumer, "settled_in_tx", value if value is None else list(value))
                note(consumer, "sends_at_insert", sends_of(state, seen.get(consumer, {}).get("task_id")))
                if order == "lock_wait" and state.get("thread") is not None and not state.get("released"):
                    state["released"] = True
                    state["proceed"].set()           # 放 worker 去写——此刻写锁在消费者手上，它只能等
                    state["thread"].join(timeout=0.6)
                    note(consumer, "worker_still_waiting_for_write_lock", state["thread"].is_alive())
                return value

            return wrapped

        def install(order: str, target: str | None, outcomes: tuple) -> dict:
            state: dict = {"rendered": threading.Event(), "proceed": threading.Event(), "error": None, "released": False,
                           "sends": {}}

            def gate(nth: int, phase: str) -> None:
                if phase == "exit" and order == "lock_wait":
                    state["rendered"].set()
                    state["proceed"].wait(timeout=20)

            art = StagedIllustrator(*outcomes, on_call=gate)
            from app.web_providers import WebProviders

            current = web.providers
            web.providers = WebProviders(enabled=True, chat=current.chat, geo=current.geo, illustrator=art, meter=current.meter)
            web.illustrations.illustrator = art
            state["art"] = art

            def body() -> None:
                try:
                    run_worker()
                except BaseException as exc:  # noqa: BLE001 - 线程里的异常要带回来，不能悄悄吞掉
                    state["error"] = f"{type(exc).__name__}: {exc}"

            state["body"] = body
            for consumer in CONSUMERS:
                setattr(*{"message": (web.communicator, "illustration_request"), "guide": (web.guides, "image_request"),
                          "postcard": (web.collection, "selfie_request")}[consumer],
                        make_request(consumer, order, target, state))
            web.illustrations._render = counting_render(state)
            web.communicator._photo_at_insert = make_settled("message", order, state)
            guides_mod.settled_photo = make_settled("guide", order, state)
            collection_mod.settled_photo = make_settled("postcard", order, state)
            return state

        def restore(*, render: bool = True) -> None:
            """次序钩子在一趟走完就撤；**任务级发送观察器要留到 `finalize` 补跑完**——
            正常次序那一档真正的发送就发生在补跑里，先撤掉就会把它记成 0（工具前提问题，不是实现少发）。"""
            if render:
                web.illustrations._render = real["render"]
            web.communicator.illustration_request, web.guides.image_request = real["message"], real["guide"]
            web.collection.selfie_request, web.communicator._photo_at_insert = real["postcard"], real["message_settled"]
            guides_mod.settled_photo, collection_mod.settled_photo = real["guide_settled"], real["postcard_settled"]

        def trip(label: str, *, order: str, target: str | None = None, outcomes: tuple = (None, None, None)) -> dict:
            """一趟真实的澳门轮渡：出发写攻略、途中奇遇发家庭消息、到访结束寄明信片——三个消费者一趟都会经过。"""
            from app.schemas import EconomyTransactionType

            state = install(order, target, outcomes)
            try:
                owner = self.user(label)
                owner.upload_pet("年糕", "cat")
                owner.move_in()
                state["pet_id"] = owner.pet_id
                assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
                web.economy.apply(owner.pet_id, 300, EconomyTransactionType.web_reward, f"q-c29:{owner.pet_id}",
                                  reason="Q 合同船票", source="q.contract")
                assert owner.post("/journey/depart", {"destination_key": "macau_ferry"}).status_code == 200
                for minutes in (180, 180, 180):
                    # **不变量**：推时钟之前，不许有 worker 线程还握着领取。
                    # 光靠"记得在循环里 join"是记忆，写成断言才是检查——这一条一旦破，
                    # 症状是别处的 attempts=2（领取过期后重试），排查要绕一大圈才回到这里。
                    assert state.get("thread") is None or not state["thread"].is_alive(),                         "推时钟前仍有 worker 线程在跑：它的领取会被这一跳推过期（租约 120 秒走注入时钟）"
                    clock.advance(minutes=minutes)
                    self.run_background(clock.now)
                    # **worker 线程必须在推下一次时钟之前收干净。** 任务领取的租约是 120 秒
                    # （`DEFAULT_LEASE_SECONDS`，走的是注入的时钟），而这里一跳就是 180 分钟——
                    # 线程若还卡在写锁上跨过这一跳，它的领取当场过期、这一次尝试被判失效并重试：
                    # 于是同一个任务出现 attempts=2、两笔各自成功的预占。那是**测试推时钟造成的**，
                    # 不是产品重复计费。只在满载进程里偶发（线程慢一点就撞上），单独跑往往看不见。
                    if state.get("thread") is not None and state["thread"].is_alive():
                        state["proceed"].set()
                        state["thread"].join(timeout=20)
                if state.get("thread") is not None:
                    state["proceed"].set()
                    state["thread"].join(timeout=20)
            finally:
                restore(render=False)  # 观察器留着，交给 observed_trip 收尾
            return state

        def finalize(state: dict, rounds: int = 1) -> dict:
            """把这一趟里三个消费者各自落成什么样取下来。`rounds`>1 用来等队列把"确定没画成"那档重试用尽。

            **三个快照要先全部取完再补跑**：`run_pending()` 一轮会把同趟**所有**待办任务都跑掉，
            边取边跑的话，后面那个消费者的"补跑之前"其实已经被前一个消费者的补跑推进过了。
            """
            snaps: dict = {}
            for consumer in CONSUMERS:
                got = seen.get(consumer)
                if not got:
                    continue
                task_id = got.get("task_id")  # 绑 make_request 的实际返回；按全表最新 rowid 取会串到别的消费者
                snaps[consumer] = (got, task_id, self._c29_task(task_id) if task_id else None,
                                   sends_of(state, task_id) if task_id else 0)
            for _ in range(rounds):  # 把还没跑的那一档补跑完；已经终态的再跑一次也不该多发
                run_worker()
                if rounds > 1:
                    clock.advance(minutes=10)
            out: dict = {}
            for consumer, (got, task_id, before, sends_before) in snaps.items():
                if not task_id:
                    out[consumer] = {**got, "covered": False}
                    continue
                out[consumer] = {**got, "covered": True, "task_id": task_id, "worker_error": state["error"],
                                 "task_before_final_round": before, "task": self._c29_task(task_id),
                                 "row": self._c29_row(consumer, task_id),
                                 # 这个任务自己的发送次数：插记录那一刻、补跑之前、全部跑完
                                 "sends_at_insert": got.get("sends_at_insert"), "sends_before_final_round": sends_before,
                                 "sends_total": sends_of(state, task_id)}
            return out

        def observed_trip(label: str, *, order: str, target: str | None = None,
                          outcomes: tuple = (None, None, None), rounds: int = 1) -> dict:
            state = trip(label, order=order, target=target, outcomes=outcomes)
            try:
                return finalize(state, rounds)
            finally:
                web.illustrations._render = real["render"]

        results: dict = {}
        try:
            for order in ORDERS:
                targets = CONSUMERS if order == "lock_wait" else (None,)
                for target in targets:
                    seen.clear()
                    for consumer, cell_value in observed_trip(f"q-c29-{order}-{target or 'all'}",
                                                              order=order, target=target).items():
                        if target is None or target == consumer:
                            results.setdefault(consumer, {})[order] = cell_value
            # 正常对照：什么次序都不安排，整趟照常走完
            seen.clear()
            control = observed_trip("q-c29-control", order="control")
            # unknown 与 failed：worker 先到，两种结局落到记录上必须是两个取值
            seen.clear()
            unknown = observed_trip("q-c29-unknown", order="worker_first", outcomes=("timeout",) * 6)
            seen.clear()
            failed = observed_trip("q-c29-failed", order="worker_first", outcomes=("rejected",) * 8, rounds=4)
        finally:
            restore()

        def cell(consumer: str, order: str) -> dict:
            return results.get(consumer, {}).get(order) or {}

        covered = {consumer: sorted(order for order in ORDERS if cell(consumer, order).get("covered")) for consumer in CONSUMERS}
        checks = {
            "三个消费者的同连接终态口径都由正式装配接上": all(wiring.values()),
            "三种到达次序都真的各走到了（没有一格是空的）": all(covered[c] == sorted(ORDERS) for c in CONSUMERS),
            "① 记录先插：插的时候任务确实还在排队": all(cell(c, "insert_first").get("task_at_request", {}).get("task_status") == "queued"
                                                      for c in CONSUMERS),
            "① 记录先插：worker 回调把它改成终态（不是留在正在画）": all(cell(c, "insert_first").get("row", {}).get("status") == "ready"
                                                                    and cell(c, "insert_first")["row"]["has_url"] for c in CONSUMERS),
            "② worker 先到：插之前任务已经终态，且插之前那一行还不存在":
                all(cell(c, "worker_first").get("task_before_insert", {}).get("illustration") == "ready"
                    and cell(c, "worker_first").get("row_before_insert", {}).get("exists") is False for c in CONSUMERS),
            "② worker 先到：插的那一刻在同一个写事务里读到了终态，直接写对": all(
                cell(c, "worker_first").get("row", {}).get("status") == "ready" and cell(c, "worker_first")["row"]["has_url"]
                and cell(c, "worker_first").get("settled_in_tx") not in (None, []) for c in CONSUMERS),
            "③ 读到正在画之后 worker 只能等写锁（确实还没写进去）": all(
                cell(c, "lock_wait").get("worker_still_waiting_for_write_lock") is True for c in CONSUMERS),
            "③ 放开写锁之后 worker 自己跑完、没有抛异常": all(cell(c, "lock_wait").get("worker_error") is None for c in CONSUMERS),
            "③ 放开之后记录走到终态（不会永远停在正在画）": all(cell(c, "lock_wait").get("row", {}).get("status") == "ready"
                                                              and cell(c, "lock_wait")["row"]["has_url"] for c in CONSUMERS),
            # **一笔预占、一次尝试**——注意这不等于"只发出过一次"：一次尝试可以发出多次
            # （没有主人照片时先画证件照再画场景图）。所以"没多发"另用发送边界断言。
            "这个任务整趟只有一笔预占、一次尝试（没有被重新排队）": all(
                cell(c, o).get("task", {}).get("reservations") == 1 and cell(c, o).get("task", {}).get("attempts") == 1
                for c in CONSUMERS for o in ORDERS),
            "任务号是这一次请求实际返回的那个，且确实属于这只宠物": all(
                cell(c, o).get("task_id") and cell(c, o).get("pet_matches") is True for c in CONSUMERS for o in ORDERS),
            # 插记录只读不发。**只有在 worker 没有同时在发的那两档，发送差额才说明得了问题**：
            #   ① 记录先插：插的那一刻该任务 0 次发送，补跑之前仍是 0——插这一步自己没发过；
            #   ② worker 先到：插之前已经发完，插之后一次都没再发（下一条）。
            # ③ 那一档 worker 正处在**同一次尝试**的中途（证件照画完接着画场景图），
            #   这时的差额是 worker 的、不是消费者的，所以那一档不用差额断言，
            #   改由"只有一笔预占、一次尝试、没有重新排队"覆盖。
            "① 记录先插：插的那一刻这个任务一次都没发过，补跑之前仍然没发": all(
                cell(c, "insert_first").get("sends_at_insert") == 0
                and cell(c, "insert_first").get("sends_before_final_round") == 0 for c in CONSUMERS),
            "每一格都看到替身真的发出过（正向对照，不从账本反推发送）": all(
                cell(c, o).get("sends_total", 0) >= 1 for c in CONSUMERS for o in ORDERS),
            "worker 先到那档：插之前就已经发完，插之后一次都没再发": all(
                cell(c, "worker_first").get("sends_at_insert", 0) >= 1
                and cell(c, "worker_first").get("sends_total") == cell(c, "worker_first").get("sends_at_insert")
                for c in CONSUMERS),
            "正常次序对照：三个消费者整趟照常走完并出图": sorted(control) == sorted(CONSUMERS)
                and all(control[c].get("covered") and control[c]["row"]["status"] == "ready" for c in CONSUMERS),
            # 两趟都必须**三个消费者各一条**：只写 `for c in unknown` 的话，一条都没取到时 all() 会空集通过
            "结果没确认那趟：三个消费者各有一条，且都落 unknown、都没有图":
                sorted(unknown) == sorted(CONSUMERS) and all(unknown[c].get("covered") for c in CONSUMERS)
                and all(unknown[c]["row"]["status"] == "unknown" and not unknown[c]["row"]["has_url"] for c in CONSUMERS),
            "确定没画成那趟：三个消费者各有一条，且都落 failed":
                sorted(failed) == sorted(CONSUMERS) and all(failed[c].get("covered") for c in CONSUMERS)
                and all(failed[c]["row"]["status"] == "failed" for c in CONSUMERS),
            "unknown 与 failed 不是同一个取值": all(
                unknown[c]["row"]["status"] != failed[c]["row"]["status"] for c in CONSUMERS if c in unknown and c in failed)
                and sorted(unknown) == sorted(failed) == sorted(CONSUMERS),
            "跑完这一轮期间实现没有被改动": started == source_digests(*C29_SOURCES),
        }
        return ContractResult(
            "Q-C29", "三个图片消费者：读当前状态与插记录在同一个写事务里，三种到达次序都不留缝",
            "COORD-Q-EXECUTE-C25-C29、CR-C12", LEVEL_INTEGRATION, "A（消费者同事务收口）＋ B（同连接终态口径装配）",
            PASS if all(checks.values()) else FAIL,
            "通讯器家庭消息／旅行攻略／邮局明信片三个消费者，在①记录先插 ②worker 先到 ③读到正在画后 worker 等写锁 三种次序下"
            "都走到终态；插记录不多发调用、不重排任务；正常次序对照照常走完；unknown 与 failed 是两个取值",
            {"checks": checks, "wiring": wiring, "covered": covered, "orders": results,
             "control": control, "unknown": unknown, "failed": failed,
             "digests_at_start": started, "digests_at_end": source_digests(*C29_SOURCES)},
            ["一位主人一只宠物，坐船去澳门：出发写攻略、途中奇遇发家庭消息、到访结束寄明信片，三个消费者一趟都经过",
             "把三处“请求生图”与三处“在自己写事务里读当前状态”各包一层壳（只在测试进程内），用来安排到达次序并记录实际取值",
             "① 记录先插：确认插的时候任务还在排队，之后跑 worker，记录应由回调改成终态",
             "② worker 先到：任务号一拿到就把 worker 跑完（此时那一行还不存在，回调必然命中 0 行），再让消费者插",
             "③ 读到正在画之后，在消费者**仍持有写事务**时放 worker 去写：确认它还在等锁；提交后它自己跑完、记录到终态",
             "每一轮都核对：任务号是这次请求实际返回的那个且属于这只宠物；只有一笔预占、一次尝试；worker 线程没有抛异常",
             "发送次数按**这个任务自己的发送边界**记（包住 `_render`，画到一半也读得准），不从账本反推；"
             "①②两档用发送差额断言「插这一步没发过」，③那一档 worker 正处在同一次尝试中途，差额是 worker 的，"
             "**该档不用差额断言**，改由「一笔预占、一次尝试、没有重新排队」覆盖",
             "**一笔预占／一次尝试 ≠ 只发出过一次**：一次尝试可含多次发送，所以「没多发」单独按发送边界断言",
             "正常次序对照跑一趟；另跑超时与当场被拒两趟，核对 unknown 与 failed 是两个不同取值",
             "**数据库锁异常不作为证明**；**不手补** image_outcome_in／illustration_outcome_in，用正式装配接上的那一份"],
            source_digests(*C29_SOURCES), len(GUARD.attempts) - guard0)


CONTRACTS = ("c29_image_consumers_insert_in_one_transaction",)
