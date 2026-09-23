"""独立验收（工作包 Q）的照片接入合同：Q-C24 拍照的原子性、拍摄时刻与幂等。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。

**接线缺失就如实失败，不手补回调**（COORD-Q-PHOTO-C24-START）：`photo_request_in` 与 `photo_generation_on`
必须由正式装配接上；缺了就是 FAIL，Q 不替装配方补。
后面的 Q-C25（worker 只用导演编译结果）、Q-C26（场景事实与幂等）、Q-C27（图片额度）等各自拥有者交付后再写。
"""

from __future__ import annotations

import json
import sqlite3

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from runtime_contract_media import StagedIllustrator
from web_base import LUNCH_UTC, FakeClock

from app.utils import parse_dt

SERVICE_SRC, WIRING_SRC = "app/web_journey/service.py", "app/web_agent/photo_wiring.py"
ILLUS_SRC, POSTCARD_SRC = "app/web_journey/illustrations.py", "app/web_journey/postcards.py"
AGENT_WIRING_SRC = "app/web_agent_wiring.py"


class PhotoContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由 RuntimeContractCases 提供）。"""

    def _photo_visit(self, label: str, clock, *, generated_photos: bool):
        """一位主人 ＋ 一只宠物到店，返回 (主人, visit_id, 拍照活动号, journey_id)。生图供应商换成替身。"""
        from runtime_contract_media import StagedIllustrator

        owner = self.user(label)
        owner.upload_pet("年糕", "cat")
        owner.move_in()
        assert owner.patch("/settings", {"generated_photos": generated_photos}).status_code == 200
        art = self._use_illustrator(None, None)  # 供应商可用；是否真的生成由家庭设置决定
        journey_id = owner.post("/journey/depart", {"destination_key": "local:cafe"}).json()["journey_id"]
        clock.advance(minutes=20)
        self.run_background(clock.now)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        assert visit_id, "到店之后应当有一次到访"
        photo = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "take_photo")
        return owner, visit_id, photo["activity_id"], journey_id, art

    def _photo_state(self, journey_id: str, visit_id: str) -> dict:
        """拍照这件事在库里的四个落点，外加纸卡片分支的那一个。"""
        events = self._sql("SELECT kind, occurred_at FROM web_world_events WHERE journey_id = ? AND event_key = ?",
                           (journey_id, f"photo:{visit_id}"))
        # 事件本身只存键与时刻，data 随 outbox 一起落库（`_record_in`），所以要看事件带了什么得读 outbox 的 payload
        payloads = self._sql("SELECT payload_json FROM web_outbox WHERE event_id = ? LIMIT 1", (f"{journey_id}:photo:{visit_id}",))
        tasks = self._sql("SELECT task_id, dedupe_key FROM web_tasks WHERE kind = 'illustration' AND dedupe_key = ?",
                          (f"illustration:photo:{visit_id}",))
        illustrations = self._sql("SELECT illustration_id, status FROM web_illustrations WHERE source_event_id = ?", (f"photo:{visit_id}",))
        postcards = self._sql("SELECT COUNT(*) FROM web_postcards WHERE visit_id = ?", (visit_id,))
        return {"events": len(events), "event_occurred_at": events[0][1] if events else None,
                "event_data": payloads[0][0] if payloads else None, "tasks": len(tasks),
                "dedupe_key": tasks[0][1] if tasks else None, "illustrations": len(illustrations),
                "postcards": postcards[0][0] if postcards else 0}

    def _activity_state(self, owner, visit_id: str, activity_id: str) -> str:
        row = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["activity_id"] == activity_id)
        return row["state"]

    def contract_c24_photo_is_atomic(self) -> ContractResult:
        """Q-C24：拍一张照片时，到访活动、photo_taken 事件、插画记录、生图任务同生共死；拍摄时刻是点击那一刻；重试不另起一条。"""
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        journeys = web.journeys

        # 〇、接线必须由**正式装配**接上——缺了就是 FAIL，不手补
        wiring = {"photo_request_in": journeys.photo_request_in is not None,
                  "photo_generation_on_is_callable": callable(getattr(journeys, "photo_generation_on", None))}

        # 一、正常生成分支：四者一起出现
        owner, visit_id, activity_id, journey_id, art = self._photo_visit("q-c24-normal", clock, generated_photos=True)
        clicked_at = clock.now
        generating = bool(journeys.photo_generation_on(journeys.repo.visit(visit_id), journeys.repo.get(journey_id)))
        response = owner.post(f"/visits/{visit_id}/actions", {"activity_id": activity_id})
        normal = {"http": response.status_code, "generation_on": generating,
                  "activity": self._activity_state(owner, visit_id, activity_id), **self._photo_state(journey_id, visit_id)}
        # 同一活动再点一次：`act()` 在最开头就原样返回，不再多一条事件/任务。
        # **必须趁 TA 还在店里点**——晚了会先被 not_in_venue 挡下，那就测不到幂等这一层了
        again = owner.post(f"/visits/{visit_id}/actions", {"activity_id": activity_id})
        normal["retry_http"], normal["after_retry"] = again.status_code, self._photo_state(journey_id, visit_id)
        # 拍摄时刻：推进时钟再跑 worker，事件上的时刻不许被执行时刻盖掉
        clock.advance(minutes=37)
        web.illustrations.run_pending()
        normal["event_occurred_at_after_worker"] = self._photo_state(journey_id, visit_id)["event_occurred_at"]

        # 二、注入：提交活动时版本冲突 → 四者一起回滚
        owner2, visit2, activity2, journey2, _ = self._photo_visit("q-c24-rollback", clock, generated_photos=True)
        real_update = journeys.repo.update_visit
        journeys.repo.update_visit = lambda visit, expected_version, conn=None: False  # 事务内造版本冲突，不争锁
        try:
            failed = owner2.post(f"/visits/{visit2}/actions", {"activity_id": activity2})
            status = failed.status_code
        except Exception as exc:  # noqa: BLE001 - 注入的冲突可能一路抛到路由外
            status = type(exc).__name__
        finally:
            journeys.repo.update_visit = real_update
        rolled_back = {"http": status, "activity": self._activity_state(owner2, visit2, activity2), **self._photo_state(journey2, visit2)}

        # 三、纸卡片分支：没开"生成照片" → 不排队、不写插画，但要留下卡片与事件
        owner3, visit3, activity3, journey3, _ = self._photo_visit("q-c24-postcard", clock, generated_photos=False)
        card = owner3.post(f"/visits/{visit3}/actions", {"activity_id": activity3})
        postcard = {"http": card.status_code, "activity": self._activity_state(owner3, visit3, activity3),
                    **self._photo_state(journey3, visit3)}

        # 四、守卫：该生成却没有同事务登记可用时，必须在动任何业务数据之前拒绝（进程内摘掉一层，不是补回调）
        owner4, visit4, activity4, journey4, _ = self._photo_visit("q-c24-guard", clock, generated_photos=True)
        keep = journeys.photo_request_in
        journeys.photo_request_in = None
        try:
            guarded = owner4.post(f"/visits/{visit4}/actions", {"activity_id": activity4})
            guard_status = guarded.status_code
            guard_body = guarded.json() if guard_status != 200 else {}
        except Exception as exc:  # noqa: BLE001
            guard_status, guard_body = type(exc).__name__, {}
        finally:
            journeys.photo_request_in = keep
        guarded_state = {"http": guard_status, "reason": (guard_body.get("error") or {}).get("details", {}).get("reason")
                         or (guard_body.get("error") or {}).get("code"), "activity": self._activity_state(owner4, visit4, activity4),
                         **self._photo_state(journey4, visit4)}

        checks = {
            "正式装配接上了 photo_request_in": wiring["photo_request_in"],
            "正式装配接上了 photo_generation_on": wiring["photo_generation_on_is_callable"],
            "开了生成照片时这次确实要生成": normal["generation_on"] is True,
            "正常分支：活动、事件、插画、任务四者一起出现": normal["http"] == 200 and normal["activity"] == "done"
                and (normal["events"], normal["illustrations"], normal["tasks"]) == (1, 1, 1),
            "正常分支：事件里带的是任务号不是照片地址": '"photo_task_id"' in (normal["event_data"] or ""),
            "去重键就是 illustration:photo:<visit_id>": normal["dedupe_key"] == f"illustration:photo:{visit_id}",
            "拍摄时刻＝点击那一刻": normal["event_occurred_at"] == clicked_at.isoformat(),
            "worker 跑过之后拍摄时刻不被执行时刻盖掉": normal["event_occurred_at_after_worker"] == clicked_at.isoformat(),
            "同一活动再点一次不多一条事件/任务": normal["retry_http"] == 200
                and (normal["after_retry"]["events"], normal["after_retry"]["tasks"]) == (1, 1),
            "注入版本冲突：四者一起回滚": rolled_back["activity"] != "done"
                and (rolled_back["events"], rolled_back["illustrations"], rolled_back["tasks"]) == (0, 0, 0),
            "纸卡片分支：留下卡片与事件": postcard["http"] == 200 and postcard["activity"] == "done"
                and postcard["events"] == 1 and postcard["postcards"] == 1,
            "纸卡片分支：不排队、不写插画": (postcard["illustrations"], postcard["tasks"]) == (0, 0),
            "纸卡片分支：事件里带的是照片地址": '"photo_url"' in (postcard["event_data"] or ""),
            "该生成却没接登记时在动业务数据之前就拒绝": guard_status != 200
                and (guarded_state["events"], guarded_state["illustrations"], guarded_state["tasks"]) == (0, 0, 0)
                and guarded_state["activity"] != "done",
        }
        return ContractResult(
            "Q-C24", "拍照的活动、事件、插画、任务同生共死；拍摄时刻是点击那一刻；重试不另起一条", "COORD-C-ATOMIC、CR-C11、A07",
            LEVEL_INTEGRATION, "C（journey.act）＋ A（request_photo_in／enqueue_in）＋ B（正式接线）",
            PASS if all(checks.values()) else FAIL,
            "正常分支四者齐全且去重键稳定；注入版本冲突四者全回滚；纸卡片分支有卡片无任务；缺登记时提前拒绝",
            {"checks": checks, "wiring": wiring, "clicked_at": clicked_at.isoformat(), "normal": normal,
             "rolled_back": rolled_back, "postcard": postcard, "guarded": guarded_state},
            ["主人开“生成照片”，宠物去 local:cafe 到店，走正式接口 POST /visits/{id}/actions 点“拍一张”",
             "正常分支：核对到访活动、photo_taken 事件、web_illustrations、web_tasks 四者一起出现，去重键 illustration:photo:<visit_id>",
             "把时钟推进 37 分钟再跑 worker，核对事件上的拍摄时刻没有被执行时刻盖掉；再点一次同一活动，核对不多一条",
             "回滚组：把 repo.update_visit 包成返回 False（事务内造版本冲突，不争锁），核对四者一个都没写进去",
             "纸卡片组：不开“生成照片”，核对留下卡片与事件、但不排队也不写插画",
             "守卫组：把 photo_request_in 临时摘掉（**减一层，不是补回调**），核对在动任何业务数据之前就被拒绝",
             "**范围**：纸卡片的 SVG 写在事务外，回滚后的残留文件不算原子性失败——原子集合是那几张表（按 C 的口径）"],
            source_digests(SERVICE_SRC, WIRING_SRC, ILLUS_SRC, POSTCARD_SRC, AGENT_WIRING_SRC), len(GUARD.attempts) - guard0)

    # ---- Q-C27：图片额度的两层上限（每宠 ＋ 全局）----
    def _image_usage(self, scope_key: str, clock) -> dict:
        from app.web_platform.budget import BudgetLedger

        return BudgetLedger(self.app.state.storage).usage(scope_key, now=clock.now)

    def contract_c27_image_quota_two_layers(self) -> ContractResult:
        """Q-C27：每宠上限与全局上限**并列**，`used + inflight` 都算；一只打满不吃掉别的宠物；被拒时不发也不占。

        **单位不是张数**：没有参考照的一次请求预占 **2 个单位**（证件照 ＋ 正图），所以每宠 6 个单位 ≈ 3 张。
        判据一律按**单位**写，不写"几张"。
        """
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        settings = self.settings
        per_pet_cap = int(getattr(settings, "web_image_per_pet_daily_cap", 0) or 0)
        global_cap = int(getattr(settings, "web_image_daily_cap", 0) or 0)

        owners: dict = {}

        def new_pet(label: str) -> str:
            owner = self.user(label)
            owner.upload_pet("年糕", "cat")
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            owners[owner.pet_id] = owner
            return owner.pet_id

        def reserve(pet_id: str, tag: str, units: int = 2):
            """走**装配时真正在用的那个预占函数**，不是自己拼的。"""
            return web.illustrations.reserve(f"q-c27:{tag}", pet_id, units)

        def rows(pet_id: str) -> list:
            return [dict(zip(("operation_id", "status", "reserved_units"), r)) for r in self._sql(
                "SELECT operation_id, status, reserved_units FROM web_budget_reservations WHERE subject_scope = ? ORDER BY rowid",
                (f"pet:{pet_id}",))]

        # 一、两层确实并列：一笔预占同时记进"全局"和"这只宠物"两个计数
        pet_a = new_pet("q-c27-a")
        first = reserve(pet_a, "a1")
        pairs = self._sql("SELECT scope_pairs_json FROM web_budget_reservations WHERE operation_id = ?", ("q-c27:a1",))
        scopes = sorted({pair[1] for pair in json.loads(pairs[0][0])}) if pairs else []
        layered = {"reserved_units": getattr(first, "reserved_units", None), "scope_keys": scopes,
                   "per_pet_cap": per_pet_cap, "global_cap": global_cap}

        # 二、used + inflight 都算：这几笔一直不结算，额度照样被占住
        # 一笔占 2 个单位，第一笔已经占过了：再占满到每宠上限为止（不多占，否则最后一笔本来就该被拒）
        more = max(0, per_pet_cap // 2 - 1)
        inflight_results = [type(reserve(pet_a, f"a{i}")).__name__ for i in range(2, 2 + more)]
        pet_usage = self._image_usage(f"pet:{pet_a}:illustration", clock)
        denied = reserve(pet_a, "a-overflow")
        inflight = {"results": inflight_results, "usage": pet_usage, "denied_type": type(denied).__name__,
                    "denied_scope": getattr(denied, "scope", None), "denied_reason": getattr(denied, "reason", None),
                    "rows_after_denied": len(rows(pet_a))}

        # 三、被拒时真的一次都不发、也不新增预占（走真实生图链路，不是只看账本）
        art = self._use_illustrator(None, None)
        task_id = web.illustrations.request_image(owners[pet_a].user_id, pet_a, "q-c27:blocked", style="selfie",
                                                  place="码头", city="香港", scene="坐着")
        self._park_other_tasks(task_id)
        before_rows = len(rows(pet_a))
        web.illustrations.run_pending()
        blocked = {"dispatched": art.dispatched, "rows_added": len(rows(pet_a)) - before_rows,
                   "illustration": self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,))[0][0]}

        # 四、单宠打满不吃掉别的宠物
        pet_b = new_pet("q-c27-b")
        other = reserve(pet_b, "b1")
        isolation = {"type": type(other).__name__, "reserved_units": getattr(other, "reserved_units", None),
                     "b_usage": self._image_usage(f"pet:{pet_b}:illustration", clock)}

        # 五、全局上限也独立生效：把全局计数占满之后，一只**每宠额度还没动过**的新宠物同样被拒
        filled, index = [], 0
        while self._image_usage("provider:image:daily", clock)["inflight"] + 2 <= global_cap and index < 40:
            index += 1
            filled.append(type(reserve(new_pet(f"q-c27-fill{index}"), f"fill{index}")).__name__)
        fresh = new_pet("q-c27-fresh")
        global_denied = reserve(fresh, "fresh")
        global_layer = {"filled": len(filled), "usage": self._image_usage("provider:image:daily", clock),
                        "denied_type": type(global_denied).__name__, "denied_scope": getattr(global_denied, "scope", None),
                        "fresh_pet_usage": self._image_usage(f"pet:{fresh}:illustration", clock)}

        checks = {
            # 除了两道上限，账本还会自己加一条不设限的"供应商:用途"日用量（usage:image:illustration），所以用包含判断
            "两层上限并列（一笔预占同时记进两个计数）": {"provider:image:daily", f"pet:{pet_a}:illustration"}.issubset(set(scopes)),
            "没有参考照的一次请求预占 2 个单位（单位不是张数）": layered["reserved_units"] == 2,
            "每宠上限来自配置 web_image_per_pet_daily_cap": per_pet_cap > 0,
            "inflight 也算进额度（这几笔从没结算过）": inflight["results"] == ["BudgetReservation"] * more
                and inflight["usage"]["inflight"] == per_pet_cap and inflight["usage"]["used"] == 0,
            "每宠额度用完后被拒，且拒在这只宠物那一层": inflight["denied_type"] == "BudgetDenied"
                and inflight["denied_scope"] == f"pet:{pet_a}:illustration",
            "被拒时不新增预占行": inflight["rows_after_denied"] == per_pet_cap // 2,
            "被拒时一次都不发、如实显示没画成": blocked["dispatched"] == 0 and blocked["rows_added"] == 0
                and blocked["illustration"] == "failed",
            "一只打满不吃掉别的宠物": isolation["type"] == "BudgetReservation" and isolation["reserved_units"] == 2,
            "全局上限独立生效：每宠额度没动过的新宠物照样被拒": global_layer["denied_type"] == "BudgetDenied"
                and global_layer["denied_scope"] == "provider:image:daily"
                and global_layer["fresh_pet_usage"] == {"used": 0, "inflight": 0},
        }
        return ContractResult(
            "Q-C27", "图片额度两层并列：每宠与全局各自生效，used＋inflight 都算，被拒时不发也不占", "COORD-Q-PHOTO-NEXT、CR-A1、A19",
            LEVEL_INTEGRATION, "B／I（额度接线）＋ A（生图结算）", PASS if all(checks.values()) else FAIL,
            f"一笔预占同时记进 provider:image:daily 与 pet:<id>:illustration；每宠 {per_pet_cap} 个单位（不是张数）用完即拒；"
            "全局占满后新宠物照样被拒；被拒时 0 发送 0 新增预占",
            {"checks": checks, "layered": layered, "inflight": inflight, "blocked_dispatch": blocked,
             "isolation": isolation, "global_layer": global_layer},
            ["用**装配时真正在用的**预占函数 `web.illustrations.reserve`，不自己拼 BudgetLimit",
             "先占一笔，读 scope_pairs_json 核对它同时记进了全局与每宠两个计数",
             "再占几笔且**一直不结算**，核对 inflight 也算进额度、用完即拒，且拒在每宠那一层、不新增预占行",
             "被拒之后走真实生图链路跑一轮，核对替身供应商一次都没被调用、插画如实落 failed",
             "另一只宠物照常能占（单宠打满不吃掉别人）",
             "把全局计数占满，再拿一只**每宠额度从没动过**的新宠物去占，核对被拒在 provider:image:daily 那一层",
             "**单位不是张数**：没有参考照的一次请求占 2 个单位，判据一律按单位写"],
            source_digests("app/web_agent/brain_wiring.py", "app/web_platform/budget.py", ILLUS_SRC, "app/config.py"),
            len(GUARD.attempts) - guard0)

    # ---- Q-C26：主动拍照命令的场景事实与幂等 ----
    def _photo_request(self, owner, pet_id: str, scene: str, *, narrative: str = "daily_life", key: str | None = None):
        body = {"scene": scene, "narrative": narrative}
        return owner.post(f"/pets/{pet_id}/photo-request", body, key=key)

    def _registrations(self, pet_id: str) -> list:
        rows = self._sql("SELECT source_event_id, task_id, status FROM web_illustrations WHERE pet_id = ? AND source_event_id LIKE 'photo-request:%'"
                         " ORDER BY created_at", (pet_id,))
        return [dict(zip(("source_event_id", "task_id", "status"), r)) for r in rows]

    def contract_c26_photo_command_facts_and_idempotency(self) -> ContractResult:
        """Q-C26：home / train 要真实状态（不成立就 409 且连记录都不写）；flight 明确虚构不碰真实旅行；同 key 不多登记。

        **组合边界**（协调方点名）：首单 home 登记成功 → **只丢幂等回执**（任务与插画记录都还在）→
        离家再过 6 分钟 → 同 key 必须取回**原任务／原拍摄时刻／原地点／原叙事**，不能 409、也不能改写成"在别处拍的"。
        """
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        self._use_illustrator(None, None)  # 供应商可用；不联网

        def owner_with_pet(label: str):
            owner = self.user(label)
            owner.upload_pet("年糕", "cat")
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            return owner

        def drop_receipt(idem_key: str) -> int:
            """只丢幂等回执，别的什么都不动——模拟"业务已提交、回执没写成"。只写 Q 自己的一次性临时库。"""
            conn = sqlite3.connect(self.settings.database_path)
            try:
                with conn:
                    cur = conn.execute("DELETE FROM web_idempotency_keys WHERE idem_key = ?", (idem_key,))
                return cur.rowcount
            finally:
                conn.close()

        # 一、在家：命令成立
        a = owner_with_pet("q-c26-home")
        first = self._photo_request(a, a.pet_id, "home", key="q-c26-K1")
        home_ok = {"http": first.status_code, "body": first.json() if first.status_code == 200 else None,
                   "registrations": len(self._registrations(a.pet_id))}

        # 二、组合边界：只丢回执 → 离家 → +6 分钟 → 同 key 必须取回原登记
        dropped = drop_receipt("q-c26-K1")
        from app.schemas import EconomyTransactionType

        web.economy.apply(a.pet_id, 200, EconomyTransactionType.web_reward, f"q-c26-grant:{a.pet_id}", reason="Q 合同旅费", source="q.contract")
        departed = a.post(f"/journey/depart?pet_id={a.pet_id}", {"destination_key": "local:cafe"})
        clock.advance(minutes=6)
        resumed = self._photo_request(a, a.pet_id, "home", key="q-c26-K1")
        recovery = {"receipt_rows_deleted": dropped, "departed_http": departed.status_code,
                    "http": resumed.status_code, "body": resumed.json() if resumed.status_code == 200 else None,
                    "registrations": len(self._registrations(a.pet_id))}

        # 三、不在家却要 home：409，且连一条登记都不写
        before = len(self._registrations(a.pet_id))
        refused = self._photo_request(a, a.pet_id, "home", key="q-c26-K2")
        not_home = {"http": refused.status_code, "registrations_added": len(self._registrations(a.pet_id)) - before}

        # 四、在家却要 train：同样 409（封闭词表，认不出一律不算）
        b = owner_with_pet("q-c26-train")
        train = self._photo_request(b, b.pet_id, "train", key="q-c26-K3")
        not_train = {"http": train.status_code, "registrations": len(self._registrations(b.pet_id))}

        # 五、flight_adventure：必须显式选虚构；选了之后不碰真实旅行，但留可恢复的登记
        c = owner_with_pet("q-c26-flight")
        wrong = self._photo_request(c, c.pet_id, "flight_adventure", key="q-c26-K4")
        events_before = self._sql("SELECT COUNT(*) FROM web_world_events")[0][0]
        right = self._photo_request(c, c.pet_id, "flight_adventure", narrative="fictional_adventure", key="q-c26-K5")
        flight = {"default_narrative_http": wrong.status_code, "http": right.status_code,
                  "body": right.json() if right.status_code == 200 else None,
                  "registrations": len(self._registrations(c.pet_id)),
                  "world_events_added": self._sql("SELECT COUNT(*) FROM web_world_events")[0][0] - events_before,
                  "journeys": self._sql("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?", (c.pet_id,))[0][0],
                  "badges": self._sql("SELECT COUNT(*) FROM web_collection_items WHERE pet_id = ? AND kind LIKE '%badge%'", (c.pet_id,))[0][0],
                  "travel_fees": self._sql("SELECT COUNT(*) FROM economy_transactions WHERE pet_id = ? AND type = 'web_travel_fee'",
                                           (c.pet_id,))[0][0]}

        # 六、train 正向：坐上**真实的**列车段再拍一张
        # 做法：真的买票出发（tokyo_flight），然后从 `web_journey_legs` 里**查出** mode='train' 的那一段，
        # 把时钟推到那段的中点。**不照抄别人用例里的分钟数**（时刻表一改就失真），也**不改库把打车伪成坐火车**。
        t = owner_with_pet("q-c26-trainpos")
        web.economy.apply(t.pet_id, 4000, EconomyTransactionType.web_reward, f"q-c26-air:{t.pet_id}", reason="Q 合同机票", source="q.contract")
        flight_out = t.post(f"/journey/depart?pet_id={t.pet_id}", {"destination_key": "tokyo_flight"})
        legs = self._sql("SELECT sequence, mode, starts_at, ends_at FROM web_journey_legs WHERE journey_id = ? ORDER BY sequence",
                         (flight_out.json().get("journey_id"),)) if flight_out.status_code == 200 else []
        train_leg = next(((seq, mode, s, e) for seq, mode, s, e in legs if mode == "train"), None)
        ferry_leg = next(((seq, mode, s, e) for seq, mode, s, e in legs if mode in ("ferry", "flight")), None)
        train_pos: dict = {"depart_http": flight_out.status_code, "modes": sorted({row[1] for row in legs}),
                           "train_leg_found": train_leg is not None}
        if train_leg is not None:
            starts, ends = parse_dt(train_leg[2]), parse_dt(train_leg[3])
            clock.now = starts + (ends - starts) / 2  # 推到这一段的中点，取值来自库里这一段本身
            on_train = self._photo_request(t, t.pet_id, "train", key="q-c26-K6")
            body = on_train.json() if on_train.status_code == 200 else {}
            payload = self._sql("SELECT payload_json FROM web_tasks WHERE task_id = ?", (body.get("task_id") or "-",))
            facts = json.loads(payload[0][0]).get("scene_facts") if payload else None
            # 一条事实的结构是 {fact_id, token, pet_id, household_id, event_id, verified}，键名是 **token**
            train_pos.update({"leg": {"sequence": train_leg[0], "starts_at": train_leg[2], "ends_at": train_leg[3]},
                              "clock_at_request": clock.now.isoformat(), "http": on_train.status_code, "body": body,
                              "captured_at_is_now": bool(body.get("captured_at")) and parse_dt(body["captured_at"]) == clock.now,
                              "fact_tokens": sorted({(f.get("token") if isinstance(f, dict) else f) for f in (facts or [])}),
                              "facts_all_verified": all(f.get("verified") is True for f in (facts or [])) and bool(facts),
                              "registrations": len(self._registrations(t.pet_id))})
            # 同一段上要"家里那张"：必须被拒（对照，证明 train 通过不是因为一律放行）
            train_pos["home_while_on_train"] = self._photo_request(t, t.pet_id, "home", key="q-c26-K7").status_code
        if ferry_leg is not None:  # 在船/飞机那一段上要 train：也必须被拒
            starts, ends = parse_dt(ferry_leg[2]), parse_dt(ferry_leg[3])
            clock.now = starts + (ends - starts) / 2
            train_pos["ferry_leg_mode"] = ferry_leg[1]
            train_pos["train_while_on_ferry"] = self._photo_request(t, t.pet_id, "train", key="q-c26-K8").status_code

        # 七、同 key 跨宠：不能串到别人的登记
        d = owner_with_pet("q-c26-otherpet")
        cross = self._photo_request(d, d.pet_id, "home", key="q-c26-K1")  # 故意复用 A 用过的 key
        cross_pet = {"http": cross.status_code, "body": cross.json() if cross.status_code == 200 else None,
                     "registrations": len(self._registrations(d.pet_id))}

        ok_body, back = home_ok["body"] or {}, recovery["body"] or {}
        checks = {
            "在家时命令成立并留下一条登记": home_ok["http"] == 200 and home_ok["registrations"] == 1,
            "只丢回执后同 key 不报 409": recovery["http"] == 200,
            "只丢回执后取回的是**原来那个任务**": back.get("task_id") == ok_body.get("task_id"),
            "取回的拍摄时刻是**首次按下那一刻**": back.get("captured_at") == ok_body.get("captured_at"),
            "取回的地点与叙事都按首次写下的": (back.get("place"), back.get("narrative")) == (ok_body.get("place"), ok_body.get("narrative")),
            "接手不新增第二条登记": recovery["registrations"] == 1,
            "不在家却要 home：409 且连记录都不写": not_home["http"] == 409 and not_home["registrations_added"] == 0,
            "在家却要 train：409 且不留记录": not_train["http"] == 409 and not_train["registrations"] == 0,
            "flight 默认叙事被拒（必须显式选虚构）": flight["default_narrative_http"] == 422,
            "flight 明确虚构后成立并留可恢复登记": flight["http"] == 200 and flight["registrations"] == 1
                and bool((flight["body"] or {}).get("task_id")),
            "flight 不写世界事件、不建行程、不发勋章、不扣旅费": (flight["world_events_added"], flight["journeys"],
                                                              flight["badges"], flight["travel_fees"]) == (0, 0, 0, 0),
            "同 key 跨宠不串号": cross_pet["http"] == 200 and cross_pet["registrations"] == 1
                and (cross_pet["body"] or {}).get("task_id") != ok_body.get("task_id"),
            # train 正向：区间从库里查出来，不照抄魔数、不改库伪造
            "真的买票出发并落出一段 mode=train 的行程": train_pos["depart_http"] == 200 and train_pos["train_leg_found"],
            "坐在真实列车段上要 train：成立并留一条登记": train_pos.get("http") == 200 and train_pos.get("registrations") == 1,
            "登记里带着列车那几条已核验事实且都标为已核验": set(train_pos.get("fact_tokens") or []) >= {"on_train", "train_window", "train_seat"}
                and train_pos.get("facts_all_verified") is True,
            # 下发的是**按 TA 此刻所在城市换算**的本地时刻，所以比的是"同一瞬间"，不是字符串
            "拍摄时刻就是此刻（按当地时区下发）且带着地点": train_pos.get("captured_at_is_now") is True
                and bool((train_pos.get("body") or {}).get("place")),
            "同一段上要“家里那张”仍被拒（不是一律放行）": train_pos.get("home_while_on_train") == 409,
            "在飞行/轮渡段上要 train：被拒": train_pos.get("train_while_on_ferry") == 409,
        }
        return ContractResult(
            "Q-C26", "主动拍照命令：home／train 要真实状态，flight 明确虚构不碰真实旅行；同 key 跨分钟／丢回执／跨宠都不多登记",
            "COORD-Q-C26-C27、CR-Q5、A24", LEVEL_INTEGRATION, "I（photo-request 路由 ＋ photo_command）＋ A（登记链路）",
            PASS if all(checks.values()) else FAIL,
            "在家成立且一条登记；丢回执后同 key 取回原任务/原时刻/原地点/原叙事且不新增；不在家或非列车一律 409 不留记录；"
            "flight 需显式虚构、不碰真实旅行但留登记；同 key 跨宠不串号",
            {"checks": checks, "home_ok": home_ok, "recovery": recovery, "not_home": not_home, "not_train": not_train,
             "flight": flight, "cross_pet": cross_pet, "train_positive": train_pos},
            ["四位主人各带一只宠物，都开“生成照片”，生图供应商换成替身（不联网）",
             "在家用正式接口 POST /pets/{pet}/photo-request 拍一张（Idempotency-Key=K1），记下任务号/拍摄时刻/地点/叙事",
             "**只删掉 web_idempotency_keys 里那一行**（任务与插画记录都不动）→ 出门去 local:cafe → 时钟 +6 分钟 → 同 K1 再请求一次",
             "不在家却要 home、在家却要 train：各自应当 409 且一条登记都不写",
             "flight_adventure：默认叙事应 422；显式 fictional_adventure 后应成立，并核对世界事件/行程/勋章/旅费都没动",
             "拿另一只宠物复用 K1：不得串到前一只的登记",
             "train 正向：真的买票去 tokyo_flight，从 web_journey_legs **查出** mode=train 那一段，把时钟推到该段中点再请求",
             "对照：同一段上要 home 必须 409；在飞行/轮渡段上要 train 也必须 409（证明不是一律放行）",
             "**不照抄别人用例里的分钟数**（时刻表一改就失真），**也不改库把打车伪成坐火车**"],
            source_digests("app/routers/web/pets.py", "app/web_journey/photo_command.py", "app/schemas/web/pets.py",
                           "app/web_platform/idempotency.py", ILLUS_SRC), len(GUARD.attempts) - guard0)

    # ---- Q-C28：只读可见闭环与显式重画 ----
    def _requests_of(self, owner, pet_id: str | None = None):
        response = owner.get(f"/pets/{pet_id or owner.pet_id}/photo-requests")
        return response.status_code, (response.json() if response.status_code == 200 else None)

    def contract_c28_photo_requests_are_visible(self) -> ContractResult:
        """Q-C28：主人主动拍的那些照片，在只读列表里看得见、四态分得清；重画复用同一张票；别人的看不到。

        **参考照来源（CR-A15）由 I 在 `web_composition.py:401` 接好**：有照片＋我们自己画的基准照 → `original_companion`；
        有照片＋主人上传的原照（own_pet）→ `owner_original`；其余（没照片、领养预置素材）→ None → **hold**。
        「对不存在的 id 返回 None」**不能**用来判断接线有没有接上——接好的函数本来也该这样。
        本合同一律用**真实上传／真实基准照**，**不手补 `reference_origin_of`**。
        """
        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        from web_base import tiny_png

        def owner_with_pet(label: str, *, with_photo: bool = False):
            owner = self.user(label)
            owner.upload_pet("年糕", "cat", photo=tiny_png() if with_photo else None)
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            return owner

        def ask(owner, **kw):
            return self._photo_request(owner, owner.pet_id, "home", **kw)

        def reservations(task_id: str) -> list:
            return [dict(zip(("operation_id", "status", "outcome", "actual_units"), r)) for r in self._sql(
                "SELECT operation_id, status, outcome, actual_units FROM web_budget_reservations WHERE operation_id LIKE ? ORDER BY rowid",
                (f"illustration:{task_id}:%",))]

        # 一、排队中 → 画好了：列表里看得见，四态与 image_url 按 I 的口径
        art = self._use_illustrator(None, None)
        a = owner_with_pet("q-c28-ready", with_photo=True)  # 真实上传过照片：参考照来源明确，导演不会 hold
        created = ask(a, key="q-c28-K1").json()
        code, queued = self._requests_of(a)
        web.illustrations.run_pending()
        _, ready = self._requests_of(a)
        row_q = next((r for r in (queued or []) if r["request_id"] == created["request_id"]), None)
        row_r = next((r for r in (ready or []) if r["request_id"] == created["request_id"]), None)
        lifecycle = {"list_http": code, "is_bare_array": isinstance(queued, list),
                     "queued": row_q, "ready": row_r, "dispatched": art.dispatched,
                     "stable_id": created["request_id"] == (row_r or {}).get("request_id")}

        # 二、GET 是纯读：连读三次，替身调用次数、预占、任务状态都不许动
        before = (art.dispatched, len(reservations(created["task_id"])), self._rows_of(created["task_id"])["task"])
        for _ in range(3):
            self._requests_of(a)
        purity = {"before": before,
                  "after": (art.dispatched, len(reservations(created["task_id"])), self._rows_of(created["task_id"])["task"])}

        # 三、unknown 与 failed 要分得清（unknown 不是库里的状态，由 A 的 outcome_of 判）
        unknown_art = self._use_illustrator("timeout")  # 有参考照时一次请求只发一次调用
        b = owner_with_pet("q-c28-unknown", with_photo=True)
        b_created = ask(b, key="q-c28-K2").json()
        self._park_other_tasks(b_created["task_id"])
        web.illustrations.run_pending()
        _, b_list = self._requests_of(b)
        failed_art = self._use_illustrator("rejected", "rejected")
        c = owner_with_pet("q-c28-failed", with_photo=True)
        c_created = ask(c, key="q-c28-K3").json()
        self._park_other_tasks(c_created["task_id"])
        for _ in range(3):
            clock.advance(minutes=10)
            web.illustrations.run_pending()
        _, c_list = self._requests_of(c)
        four_states = {"unknown": next((r for r in (b_list or []) if r["request_id"] == b_created["request_id"]), None),
                       "failed": next((r for r in (c_list or []) if r["request_id"] == c_created["request_id"]), None),
                       "unknown_dispatched": unknown_art.dispatched, "failed_dispatched": failed_art.dispatched}

        # 四、显式重画：复用同一张票、已发出的成本不退；ready 的那条回 200 且不重排不再发
        redraw_art = self._use_illustrator(None)
        before_res = reservations(b_created["task_id"])
        retried = b.post(f"/pets/{b.pet_id}/photo-requests/{b_created['request_id']}/retry-image")
        after_click = self._rows_of(b_created["task_id"])
        web.illustrations.run_pending()
        _, after_list = self._requests_of(b)
        # 这一刻才开始数：上面那次 run_pending 是给 b 的重画跑的，别把它算到"已画好还再发"头上
        dispatched_before_ready_retry = redraw_art.dispatched
        ready_retry = a.post(f"/pets/{a.pet_id}/photo-requests/{created['request_id']}/retry-image")
        web.illustrations.run_pending()  # 真给它一轮机会：如果被错误地排回队，这一轮就会发出调用
        retry = {"http": retried.status_code, "returns_list": isinstance(retried.json() if retried.status_code == 200 else None, list),
                 "after_click_task": after_click["task"], "reservations_before": before_res,
                 "reservations_after": reservations(b_created["task_id"]),
                 "row_after": next((r for r in (after_list or []) if r["request_id"] == b_created["request_id"]), None),
                 "ready_retry_http": ready_retry.status_code,
                 "ready_task_after": self._rows_of(created["task_id"])["task"],
                 "dispatched_on_ready_retry": redraw_art.dispatched - dispatched_before_ready_retry}

        # 五、跨家庭一律 404（不泄露存在与否）
        stranger = owner_with_pet("q-c28-stranger")
        cross_list = stranger.get(f"/pets/{a.pet_id}/photo-requests")
        cross_retry = stranger.post(f"/pets/{stranger.pet_id}/photo-requests/{created['request_id']}/retry-image")
        permissions = {"list_http": cross_list.status_code, "retry_http": cross_retry.status_code}

        # 六、身份参考的来源标注：真实上传 → owner_original；说不清来源 → None → 挡下且一次调用都不发
        hold_art = self._use_illustrator(None, None)
        d = owner_with_pet("q-c28-noupload")  # 完全没有参考照：导演先挡下（B 已就次序问题提给 A）
        d_created = ask(d, key="q-c28-K4").json()
        self._park_other_tasks(d_created["task_id"])
        web.illustrations.run_pending()
        _, d_list = self._requests_of(d)
        origin_of = web.illustrations.reference_origin_of
        provenance = {"uploaded_pet_origin": origin_of(a.pet_id), "no_photo_pet_origin": origin_of(d.pet_id),
                      "absent_pet_origin": origin_of("PJ-DOES-NOT-EXIST"), "dispatched": hold_art.dispatched,
                      "row": next((r for r in (d_list or []) if r["request_id"] == d_created["request_id"]), None),
                      "note": "不存在的 id 返回 None 是正确的；它不能用来判断接线有没有接上",
                      "reservations": reservations(d_created["task_id"])}

        checks = {
            "列表是裸数组且新请求有稳定编号": lifecycle["is_bare_array"] and lifecycle["list_http"] == 200 and lifecycle["stable_id"],
            "排队中：processing、无图、不可重画": (row_q or {}).get("photo_status") == "processing"
                and (row_q or {}).get("image_url") is None and (row_q or {}).get("can_retry") is False,
            "画好了：ready、图址带前缀、不可重画": (row_r or {}).get("photo_status") == "ready"
                and (row_r or {}).get("image_url") == f"/api/v1/web/media/illustrations/{created['request_id']}"
                and (row_r or {}).get("can_retry") is False,
            "GET 是纯读（连读三次什么都不动）": purity["before"] == purity["after"],
            "结果未确认显示成 unknown 且可重画、无图": (four_states["unknown"] or {}).get("photo_status") == "unknown"
                and (four_states["unknown"] or {}).get("can_retry") is True
                and (four_states["unknown"] or {}).get("image_url") is None,
            "确认没画成显示成 failed 且可重画": (four_states["failed"] or {}).get("photo_status") == "failed"
                and (four_states["failed"] or {}).get("can_retry") is True,
            "unknown 与 failed 不是同一个取值": (four_states["unknown"] or {}).get("photo_status") != (four_states["failed"] or {}).get("photo_status"),
            "重画：200、返回整个列表、任务排回去": retry["http"] == 200 and retry["returns_list"] and retry["after_click_task"] == "queued",
            "重画：原先那笔已发出的成本没被退回": all(row["outcome"] != "not_sent" for row in retry["reservations_before"])
                and retry["reservations_before"] == retry["reservations_after"][:len(retry["reservations_before"])],
            "重画：另起一张票（票号带新的领取代数）": len(retry["reservations_after"]) > len(retry["reservations_before"]),
            "已经画好的那条重画：回 200 且不重排、不再发": retry["ready_retry_http"] == 200
                and retry["ready_task_after"] == "succeeded" and retry["dispatched_on_ready_retry"] == 0,
            "跨家庭看别人的列表：404": permissions["list_http"] == 404,
            "拿别人的编号重画：404": permissions["retry_http"] == 404,
            # 现状记录：这一条不是"应当如此"，是"现在如此"——参考照来源没接线时必须 hold 且不花钱
            # 现状记录（不是"应当如此"）：没上传过照片时参考照来源无从得知，导演挡下且一次调用都不发——不花钱，这一侧是安全的
            # 身份参考的来源标注：按真实事实断言，**不拿"对假 id 返回 None"当接线判据**
            "真实上传的原照标成 owner_original": provenance["uploaded_pet_origin"] == "owner_original",
            "说不清来源时返回 None（没照片、不存在的 id 都是）": provenance["no_photo_pet_origin"] is None
                and provenance["absent_pet_origin"] is None,
            # 这是**当前行为**：完全没有参考照时导演先挡下，所以不花钱。B 已就"次序"提给 A：
            # `_render` 里本有"先画一张基准照当参考"的退路，但 readiness 在它之前就挡了 → 没照片的伙伴永远拍不出。
            # 立不立合同另说，这里只钉住"挡下时不花钱"，不把它写成"应当永远如此"。
            "缺必需身份参考时挡下且 0 发送 0 预占": provenance["dispatched"] == 0
                and (provenance["row"] or {}).get("photo_status") in ("failed", "unknown")
                and provenance["reservations"] == [],
        }
        return ContractResult(
            "Q-C28", "主动拍照的只读可见闭环：四态分得清、GET 纯读、重画复用同一张票、别人的一律看不到",
            "COORD-Q-TRAIN-VISIBLE、CR-A3、CR-A15", LEVEL_INTEGRATION, "I（只读与重画入口）＋ A（结算与四态判据）",
            PASS if all(checks.values()) else FAIL,
            "列表裸数组、编号稳定；processing/ready/unknown/failed 四态与 image_url、can_retry 一致；连读三次什么都不动；"
            "重画排回队且不退已发出的成本；已 ready 的重画不重排不再发；跨家庭一律 404",
            {"checks": checks, "lifecycle": lifecycle, "purity": purity, "four_states": four_states,
             "retry": retry, "permissions": permissions, "reference_provenance": provenance},
            ["主人开“生成照片”，用正式接口 POST /pets/{pet}/photo-request 拍一张（home），再读 GET /pets/{pet}/photo-requests",
             "排队中与画好之后各读一次，核对 photo_status / image_url / can_retry 三项与编号稳定",
             "连读三次核对是纯读：替身调用次数、预占条数、任务状态都不变",
             "另两只宠物分别造出 unknown（超时）与 failed（当场被拒且次数用完），核对两者取值不同、都可重画、都无图",
             "对 unknown 那条走正式 POST .../retry-image：核对回 200 ＋ 整个列表、任务排回队、原先已发出的成本没被退回、另起一张票",
             "对已经 ready 的那条也点一次重画：应当回 200 ＋ 当前状态，且不重排、不再发",
             "另一个家庭的主人看别人的列表、拿别人的编号重画：都应当 404（不泄露存在与否）",
             "身份参考来源：用**真实上传**的宠物核对标成 `owner_original`；用**没有照片**的宠物与**不存在的 id** 核对都返回 None；"
             "缺必需身份参考时挡下且 0 发送 0 预占。**不手补该回调**，也**不拿“对假 id 返回 None”当接线判据**"],
            source_digests("app/routers/web/pets.py", "app/schemas/web/pets.py", ILLUS_SRC, "app/web_journey/photo_command.py",
                           "app/web_composition.py", "app/web_pets/service.py", "app/web_journey/photo_director_bridge.py",
                           "app/web_photo_director/compiler.py", "app/web_photo_director/readiness.py"),
            len(GUARD.attempts) - guard0)

CONTRACTS = ("c24_photo_is_atomic",
             "c26_photo_command_facts_and_idempotency",
             "c27_image_quota_two_layers", "c28_photo_requests_are_visible")
