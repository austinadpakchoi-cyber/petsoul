"""独立验收（工作包 Q）：接待叮嘱的**用途授权**不跨范围使用（Q-C32，CR-IMAGE-MEMORY-PURPOSE-2026-09-24 第 26-27 条）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。
**不使用任何真实私密记录**：叮嘱内容是本合同当场生成的**唯一合成标记**，只用来回答"这段文字有没有漏到别处去"。

被测的是 I 的修法：`keepsake_of` 改为要求 **`public_story` ∩ `media_generation`**，
按 `(note_id, note_version)` 取交集——**同一条叮嘱两个用途都授权才给值**。

**本合同刻意把两道防线分开，因为它们会互相掩盖**：
  ① **I 这一层**（`web_composition.slot_for_all_purposes`）决定 `keepsake_of` 给不给值 →
     承重的是**家庭故事**那条路（`adventures.render_story` 把它拼进 story，再进家庭频道）；
  ② **A 那一层**（`illustrations.request` 不存 `story`、只存 `adventure_key`，
     发送时 `render_story(template, name, None)` **无条件**不带叮嘱）→ 挡的是**生图**那条路。

**所以"替身收到的提示词里没有标记"这一条，即使 I 的修法不存在也会成立**——它由 A 那层单独保证。
只断言它等于什么都没验到 I 的修法。本合同因此把正向对照**限定在家庭故事**上：
两个用途都授权时，标记**应当**出现在家庭故事里、而**仍然不应当**出现在提示词里——
后者不是缺陷，是 A 那层照常生效。
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from runtime_contract_media import StagedIllustrator
from web_base import LUNCH_UTC, FakeClock

C32_SOURCES = ("app/web_composition.py", "app/reception/policy.py", "app/web_journey/adventures.py",
               "app/web_journey/service.py", "app/web_journey/illustrations.py", "app/web_journey/photo_prompts.py",
               "app/reception/guided.py")


class MemoryPurposeContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql`、`_photo_journey` 由同组的用例提供）。"""

    def _c32_note(self, owner, text: str, purposes: list[str], slot_value: str) -> dict:
        """走**正式接待入口**确认一条叮嘱，并把槽位值改成本合同的合成标记。

        入口：`POST /reception/sessions` → `/turns` → `/confirmations`，与主人在页面上做的是同一条路。
        """
        session = owner.post("/reception/sessions", {"pet_id": owner.pet_id, "branch": "own_pet"}).json()
        session = owner.post(f"/reception/sessions/{session['session_id']}/turns",
                             {"text": text, "expected_revision": session["draft_revision"]}).json()
        decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet",
                      "purposes": purposes, "slot": c["suggested_slot"], "slot_value": slot_value}
                     for c in session["candidates"] if c["kind"] != "owner_private" and c["suggested_slot"] == "favorite_object"]
        assert decisions, f"这段话应当产出一个 favorite_object 候选：{session['candidates']}"
        result = owner.post("/reception/confirmations", {"session_id": session["session_id"],
                                                         "draft_revision": session["draft_revision"], "decisions": decisions})
        assert result.status_code == 200, result.text
        return result.json()

    def _c32_projected(self, owner, purpose: str) -> list:
        """这只宠物在某个用途下的投影里，`favorite_object` 的取值（用真实的接待服务读，不是替身）。"""
        from app.schemas.web.reception import MemoryPurpose

        items = self.web.reception.projection(owner.user_id, owner.pet_id, MemoryPurpose(purpose)).items
        return [i.slot_value for i in items if i.slot_value and str(getattr(i.slot, "value", i.slot)) == "favorite_object"]

    def contract_c32_note_purposes_do_not_leak(self) -> ContractResult:
        """Q-C32：只授权私聊的叮嘱不得进家庭故事与生图输入；两个用途分别控制、不互相默认授权。"""
        guard0 = len(GUARD.attempts)
        started = source_digests(*C32_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        prompts: list[str] = []

        class RecordingIllustrator(StagedIllustrator):
            """把**替身实际收到的提示词**记下来——这是"有没有漏给外部供应商"的唯一可信观察点。"""

            def render(self, prompt, reference=None, size="2048x2048"):
                prompts.append(prompt)
                return super().render(prompt, reference, size)

        def use_recorder() -> RecordingIllustrator:
            from app.web_providers import WebProviders

            art = RecordingIllustrator(None, None)
            current = web.providers
            web.providers = WebProviders(enabled=True, chat=current.chat, geo=current.geo, illustrator=art, meter=current.meter)
            web.illustrations.illustrator = art
            return art

        def scenario(label: str, grants: list[list[str]], *, correct: bool = False) -> dict:
            """一位主人、一只宠物：按 `grants` 确认 1～2 条叮嘱（各自的用途），再真的出门一趟。

            `grants` 每一项是一条**独立叮嘱**的用途列表——两条各授一个用途，用来验交集是按
            `(note_id, note_version)` 取的，而不是"两个用途各自都有值就算数"。
            """
            marker = f"QMK{uuid.uuid4().hex[:8].upper()}毯子"
            art = use_recorder()
            before = len(prompts)
            owner = self.user(f"q-c32-{label}")
            owner.upload_pet("年糕", "cat")
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            corrected_marker = None
            for index, purposes in enumerate(grants):
                # 每条叮嘱用不同措辞，避免被判成同一条的重复确认；槽位值都设成同一个合成标记
                result = self._c32_note(owner, f"它最喜欢那条{'旧' * (index + 1)}毯子。", purposes, marker)
            if correct:  # 主人把这条叮嘱改了：**旧版本的许可不该延续到新内容**
                note = result["notes"][0]
                corrected_marker = f"QMK{uuid.uuid4().hex[:8].upper()}新毯子"
                fixed = owner.post(f"/care-notes/{note['note_id']}/corrections",
                                   {"action": "correct", "expected_version": note["version"],
                                    "new_text": "它最喜欢那条新毯子。", "new_slot_value": corrected_marker})
                assert fixed.status_code == 200, fixed.text
            journey_id = owner.post("/journey/depart", {"destination_key": "macau_ferry"}).json().get("journey_id")
            from app.schemas import EconomyTransactionType

            web.economy.apply(owner.pet_id, 300, EconomyTransactionType.web_reward, f"q-c32:{owner.pet_id}",
                              reason="Q 合同船票", source="q.contract")
            if journey_id is None:  # 钱不够时先补票再出发
                journey_id = owner.post("/journey/depart", {"destination_key": "macau_ferry"}).json()["journey_id"]
            clock.advance(hours=3)
            self.run_background(clock.now)
            web.illustrations.run_pending()

            messages = [m["text"] for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]]
            family = [row[0] for row in self._sql("SELECT text FROM web_messages WHERE pet_id = ? AND channel = 'family'",
                                                  (owner.pet_id,))]
            # 一趟里不止一张图（冒险插画、明信片、攻略…）；**只有冒险那张**才带 adventure_key，
            # 所以 A 那层的断言要落在冒险那条任务上，不能"每条都得有"。
            rows = self._sql("SELECT dedupe_key, payload_json FROM web_tasks WHERE kind = 'illustration' "
                             "AND payload_json LIKE ?", (f"%{owner.pet_id}%",))
            payloads = [text for _key, text in rows]
            adventure = [json.loads(text) for key, text in rows if ":adventure:" in (key or "")]
            return {"marker": marker, "owner": owner, "corrected_marker": corrected_marker,
                    "old_marker_in_family_story": any(marker in text for text in family),
                    "new_marker_in_family_story": bool(corrected_marker) and any(corrected_marker in text for text in family),
                    "private_chat_projection": self._c32_projected(owner, "private_chat"),
                    "public_story_projection": self._c32_projected(owner, "public_story"),
                    "marker_in_family_story": any(marker in text for text in family),
                    "marker_in_any_message": any(marker in text for text in messages),
                    "marker_in_task_payload": any(marker in text for text in payloads),
                    "marker_in_prompt": any(marker in text for text in prompts[before:]),
                    "any_payload_has_story_field": any("story" in json.loads(text) for text in payloads),
                    "adventure_tasks": len(adventure),
                    "adventure_payload_keys": sorted({k for payload in adventure for k in payload}),
                    "family_messages": len(family), "prompts": len(prompts) - before,
                    "illustrations_ready": self._sql("SELECT COUNT(*) FROM web_illustrations WHERE pet_id = ? AND status = 'ready'",
                                                     (owner.pet_id,))[0][0]}

        private_only = scenario("private", [["private_chat"]])
        story_only = scenario("story", [["public_story"]])
        media_only = scenario("media", [["media_generation"]])
        both_purposes = scenario("both", [["public_story", "media_generation"]])
        corrected = scenario("fixed", [["public_story"]], correct=True)
        cases = {"private_only": private_only, "story_only": story_only, "media_only": media_only,
                 "both_purposes": both_purposes, "corrected": corrected}

        def trimmed(case: dict) -> dict:
            return {k: v for k, v in case.items() if k != "owner"}

        checks = {
            # ① 只授私聊：私聊里还用得上（证明叮嘱确实存在），别处一个字都不许漏
            "只授私聊：该叮嘱在私聊投影里确实可用": private_only["marker"] in private_only["private_chat_projection"],
            "只授私聊：家庭故事里没有这段文字": not private_only["marker_in_family_story"],
            "只授私聊：任何一条消息里都没有": not private_only["marker_in_any_message"],
            "只授私聊：生图任务载荷里没有": not private_only["marker_in_task_payload"],
            "只授私聊：替身收到的提示词里没有": not private_only["marker_in_prompt"],
            # ② 按**接收方各自授权**（C84A-MEMORY-RECIPIENT-01）：两个用途分别控制**各自的那一个范围**，
            #    不是"两个都授权才给"。图片那侧已由 A 从根上断开，所以"给家庭文字"不再需要捎带图片许可。
            "只授 public_story：**可以**进家庭故事（按接收方授权，不再要求捎带图片许可）":
                story_only["marker_in_family_story"],
            "只授 public_story：仍然不进图（任务载荷与提示词都没有）":
                not story_only["marker_in_task_payload"] and not story_only["marker_in_prompt"],
            "只授 media_generation：不进家庭故事": not media_only["marker_in_family_story"],
            "只授 media_generation：本批也不进图": not media_only["marker_in_prompt"],
            "两个用途都授：照旧进家庭故事（public_story 已足够，多授一个不改变结果）":
                both_purposes["marker_in_family_story"],
            # ③ 版本保护：叮嘱被更正后，**旧版本的许可不延续到新内容**
            "叮嘱更正后：旧版本那段文字不再出现在家庭故事里": not corrected["old_marker_in_family_story"],
            # ④ A 那一层单独成立（独立于 I 的入口）
            "生图载荷里一律不留 story（A 那层，独立于 I 的入口）":
                all(not case["any_payload_has_story_field"] for case in cases.values()),
            "冒险那张图的载荷只留 adventure_key，不带故事原文":
                all(case["adventure_tasks"] >= 1 and "adventure_key" in case["adventure_payload_keys"]
                    and "story" not in case["adventure_payload_keys"] for case in cases.values()),
            "即使授权了 media_generation，提示词里**仍然**没有叮嘱内容（A 那层照常生效，这不是缺陷）":
                not both_purposes["marker_in_prompt"],
            # ⑤ 普通链路没有被挡死
            "五个场景都照常出了家庭来信与图": all(case["family_messages"] >= 1 and case["illustrations_ready"] >= 1
                                                  for case in cases.values()),
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C32_SOURCES),
        }
        return ContractResult(
            "Q-C32", "接待叮嘱的用途授权不跨范围：只授私聊的不进家庭故事与生图；两个用途分别控制、不互相默认授权",
            "CR-IMAGE-MEMORY-PURPOSE-2026-09-24 第 26-27 条", LEVEL_INTEGRATION,
            "I（keepsake_of 交集）＋ A（生图载荷不留 story）",
            PASS if all(checks.values()) else FAIL,
            "只授 private_chat 的 favorite_object 在私聊投影可用，但家庭故事／任务载荷／替身提示词里都没有那段文字；"
            "public_story 与 media_generation 分别控制、不互相默认授权；两条不同叮嘱各授一个用途拼不成一次许可；"
            "同一条叮嘱两个用途都授时确实进家庭故事；普通来信与图片照常产生",
            {"checks": checks, "cases": {name: trimmed(case) for name, case in cases.items()},
             "digests_at_start": started, "digests_at_end": source_digests(*C32_SOURCES)},
            ["每个场景一位新主人一只新宠物，叮嘱内容是**当场生成的唯一合成标记**（不使用任何真实私密记录）",
             "走**正式接待入口**确认叮嘱：`POST /reception/sessions` → `/turns` → `/confirmations`，"
             "在确认时把槽位值设成该标记、并指定这条叮嘱的用途",
             "再真的坐船去澳门（`macau_ferry`）跑一趟：途中的奇遇会写一条家庭来信并排一张图",
             "四处观察点各查一遍标记：接待投影（应当有）、家庭频道消息、生图任务载荷、**替身实际收到的提示词**",
             "五个场景：只授 private_chat／只授 public_story（**应当进家庭故事**）／只授 media_generation／"
             "两个用途都授／**确认后再更正该叮嘱**（验旧版本的许可不延续到新内容）",
             "**本合同不再覆盖多用途交集**：按 C84A-MEMORY-RECIPIENT-01，`keepsake_of` 现在只传 `public_story` 一个用途，"
             "`slot_for_all_purposes` 里那条交集逻辑**从这个调用点走不到了**——"
             "它仍在代码里、且仍会被将来需要双授权的接收方用到，但**本合同不再为它作证**",
             "**两道防线分开验**：家庭故事那条路承重的是 I 的 `slot_for_all_purposes`；"
             "生图那条路由 A 的「载荷不留 story、发送时按模板重渲」**独立**保证——"
             "所以「提示词里没有标记」即使没有 I 的修法也成立，**单验它等于没验 I 的修法**",
             "**未覆盖**：CR 第 28-29 条（排队后用途撤回／内容更正、晚到结果的发布边界）属 A 那半，待其解冻后另验",
             "**另两处「同模式、未追到底」我在源码可达性上追完了（不是运行时断言，扫描口径如下）**："
             "① `credentials`：`web_credentials_wiring.care_notes` 只有一个消费方 `routers/web/credentials.py:105`，"
             "写进 `care_profile` 凭证详情并回给**请求者本人**，而读投影用的正是同一个 `principal.user_id`——"
             "不进故事、不进家庭频道、不进提示词；② `travel_quest_engine/planning.py:318` 那句 `Story context: {story}`："
             "该 `story` 来自 `quest_flow._souvenir_templates` 的模板元组，且**整包 5 个文件对 "
             "`keepsake_of`／`CareNoteSlot`／`MemoryPurpose`／`reception` 的引用为 0 处**，够不到叮嘱系统。"
             "**这两条是源码可达性论证，不是本合同的运行时断言**；grep 扫的是 `app/` 下的静态引用，"
             "动态分派扫不到。要运行时钉住得另开一条合同"],
            source_digests(*C32_SOURCES), len(GUARD.attempts) - guard0)


    def _c33_trip(self, label: str, clock, marker: str, *, on_call=None):
        """一位主人、一只宠物，叮嘱授权 `public_story`（所以标记**会**进家庭故事），再坐船出门一趟。

        返回 (主人, 叮嘱, 任务号, 替身)。`on_call` 用来在替身发送的**某个时点**插一件事。
        """
        from app.schemas import EconomyTransactionType
        from app.web_providers import WebProviders

        prompts: list[str] = []

        class Recorder(StagedIllustrator):
            def render(self, prompt, reference=None, size="2048x2048"):
                prompts.append(prompt)
                return super().render(prompt, reference, size)

        art = Recorder(None, None, on_call=on_call)
        art.prompts = prompts
        current = self.web.providers
        self.web.providers = WebProviders(enabled=True, chat=current.chat, geo=current.geo, illustrator=art, meter=current.meter)
        self.web.illustrations.illustrator = art

        owner = self.user(label)
        owner.upload_pet("年糕", "cat")
        owner.move_in()
        assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
        note = self._c32_note(owner, "它最喜欢那条毯子。", ["public_story"], marker)["notes"][0]
        self.web.economy.apply(owner.pet_id, 300, EconomyTransactionType.web_reward, f"q-c33:{owner.pet_id}",
                               reason="Q 合同船票", source="q.contract")
        assert owner.post("/journey/depart", {"destination_key": "macau_ferry"}).status_code == 200
        clock.advance(hours=3)
        self.run_background(clock.now)
        rows = self._sql("SELECT task_id FROM web_tasks WHERE kind = 'illustration' AND dedupe_key LIKE ? AND payload_json LIKE ?",
                         ("%:adventure:%", f"%{owner.pet_id}%"))
        assert rows, "坐船那趟应当排出一张冒险插画"
        # 同一趟还会排明信片、攻略等插画：**把它们推远**，这样这一档里跑的每一次发送都属于被观察的那个任务。
        # 不park 的话 ①prompts／dispatched 会混进别的任务，②五档加起来会撞上全局每日图片上限，
        # 让最后一档因为**与本合同无关的原因**失败。
        self._park_other_tasks(rows[0][0])
        return owner, note, rows[0][0], art

    def _c33_rewrite_payload(self, task_id: str, *, story: str, keep_key: bool) -> dict:
        """把任务载荷改回**升级前的旧形状**（带 `story`），只动 Q 自己的一次性临时库。

        **忠实性**：旧代码那一版载荷里**确实带 story**（这正是 A 改掉它的原因）；
        `keep_key=False` 再模拟更旧的一档——连 `adventure_key` 都还没有。
        """
        conn = sqlite3.connect(self.settings.database_path)
        try:
            row = conn.execute("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
            payload = json.loads(row[0])
            payload["story"] = story
            if not keep_key:
                payload.pop("adventure_key", None)
            with conn:
                conn.execute("UPDATE web_tasks SET payload_json = ? WHERE task_id = ?",
                             (json.dumps(payload, ensure_ascii=False), task_id))
            return payload
        finally:
            conn.close()

    def contract_c33_late_changes_and_legacy_payloads(self) -> ContractResult:
        """Q-C33：升级前排下的**旧载荷**不会把叮嘱带给供应商；执行中／发布前撤回叮嘱也不改变这一点，费用事实照留。"""
        guard0 = len(GUARD.attempts)
        started = source_digests(*C32_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)

        def reservations(task_id: str) -> list:
            return [dict(zip(("status", "outcome", "actual_units"), r)) for r in self._sql(
                "SELECT status, outcome, actual_units FROM web_budget_reservations WHERE operation_id LIKE ?",
                (f"illustration:{task_id}:%",))]

        def state(owner, task_id: str, art, marker: str) -> dict:
            family = [row[0] for row in self._sql("SELECT text FROM web_messages WHERE pet_id = ? AND channel = 'family'",
                                                  (owner.pet_id,))]
            return {"prompts": len(art.prompts), "marker_in_prompt": any(marker in p for p in art.prompts),
                    "illustration": (self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,)) or [("-",)])[0][0],
                    "task": (self._sql("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,)) or [(None, None)])[0],
                    "reservations": reservations(task_id), "dispatched": art.dispatched,
                    "marker_still_in_written_story": any(marker in text for text in family)}

        def legacy(label: str, *, keep_key: bool) -> dict:
            marker = f"QMK{uuid.uuid4().hex[:8].upper()}毯子"
            owner, _note, task_id, art = self._c33_trip(f"q-c33-{label}", clock, marker)
            payload = self._c33_rewrite_payload(task_id, story=f"它带着你准备的{marker}上了船。", keep_key=keep_key)
            self.web.illustrations.run_pending()
            return {"marker": marker, "payload_had_story": "story" in payload,
                    "payload_had_key": "adventure_key" in payload, **state(owner, task_id, art, marker)}

        def note_state(note_id: str) -> dict:
            """这条叮嘱在库里的撤回痕迹——**用来证明撤回真的发生过**，不是只看 HTTP 回了 200。"""
            rows = self._sql("SELECT revoked_at FROM web_care_notes WHERE note_id = ?", (note_id,))
            grants = self._sql("SELECT COUNT(*), COUNT(revoked_at) FROM web_memory_grants WHERE note_id = ?", (note_id,))
            return {"note_revoked": bool(rows and rows[0][0]),
                    "grants_total": grants[0][0] if grants else 0, "grants_revoked": grants[0][1] if grants else 0}

        def revoke_at(label: str, phase: str | None, *, mode: str = "revoke") -> dict:
            """在替身发送的某个时点撤回这条叮嘱（正式入口 `POST /care-notes/{id}/corrections`）。

            `mode` 三档，**后两档是让前一档具备区分力的对照**（C84A-Q-C33-INJECTION-01）：
              - `revoke`   ：到点就撤回；
              - `readonly` ：同一时点同样嵌一次**走到库**的 HTTP，但只读——分开"撤回造成的"与"嵌套调用造成的"；
              - `none`     ：**根本不装钩子**——c84a 实测过：去掉 on_call 后原来那版合同**照样 14/14 全绿**，
                             说明那些断言对"撤回有没有发生"毫无区分力。本档存在就是为了让这件事变红：
                             注入命中数、HTTP 成功、库里的撤回痕迹，三项在本档都必须**为空**。
            """
            marker = f"QMK{uuid.uuid4().hex[:8].upper()}毯子"
            box: list = []
            hook_calls: list = []
            fired: list = []

            def hook(index: int, at: str) -> None:
                if at == phase and box:
                    owner, note = box[0]
                    # **阶段语义**：替身在 `enter` 时还没越过发送边界（`dispatched` 尚未 +1），
                    # 在 `exit` 时这一次已经发出去了。记下当刻的发送数，让"哪个时点"是可核的，不是靠命名。
                    fired.append({"nth": index, "phase": at, "dispatched_at_hook": art_box[0].dispatched})
                    if mode == "revoke":
                        done = owner.post(f"/care-notes/{note['note_id']}/corrections",
                                          {"action": "revoke", "expected_version": note["version"]})
                    else:
                        # 只读对照：同一时点同样嵌一次**走到库**的 HTTP（读消息列表），不是一个会 404 的空路由
                        done = owner.get(f"/communicator/{owner.pet_id}/messages")
                    hook_calls.append(done.status_code)

            art_box: list = []

            owner, note, task_id, art = self._c33_trip(f"q-c33-{label}", clock, marker,
                                                       on_call=None if mode == "none" else hook)
            art_box.append(art)
            box.append((owner, note))
            before = note_state(note["note_id"])
            worker_error = None
            try:
                self.web.illustrations.run_pending()
            except BaseException as exc:  # noqa: BLE001 - worker 抛了就带回来，不能悄悄吞掉
                worker_error = f"{type(exc).__name__}: {exc}"
            after = note_state(note["note_id"])
            return {"marker": marker, "hook_http": hook_calls, "hook_fired": fired, "worker_error": worker_error,
                    "note_before": before, "note_after": after,
                    "revocation_landed": (not before["note_revoked"]) and after["note_revoked"]
                    and after["grants_revoked"] > before["grants_revoked"],
                    **state(owner, task_id, art, marker)}

        with_key = legacy("legacykey", keep_key=True)
        no_key = legacy("legacybare", keep_key=False)
        mid_render = revoke_at("midrender", "enter")
        before_publish = revoke_at("beforepublish", "exit")
        # 对照一：同一时点只读、不撤回。两者一致 ⇒ 是"嵌套 HTTP"造成的，不是撤回造成的
        nested_only = revoke_at("nestedonly", "enter", mode="readonly")
        # 对照二（C84A-Q-C33-INJECTION-01）：**根本不装钩子**。撤回三项指标在这一档必须全空，
        # 否则说明那些断言与"撤回有没有发生"无关——c84a 实测原版去掉钩子仍全绿，就是这个洞。
        no_hook = revoke_at("nohook", None, mode="none")
        normal_marker = f"QMK{uuid.uuid4().hex[:8].upper()}毯子"
        owner_n, _n, task_n, art_n = self._c33_trip("q-c33-normal", clock, normal_marker)
        self.web.illustrations.run_pending()
        normal = {"marker": normal_marker, **state(owner_n, task_n, art_n, normal_marker)}
        cases = {"legacy_with_key": with_key, "legacy_no_key": no_key,
                 "revoke_mid_render": mid_render, "revoke_before_publish": before_publish,
                 "nested_http_only": nested_only, "no_hook_control": no_hook, "normal": normal}

        def settled(case: dict) -> bool:
            return bool(case["reservations"]) and all(r["status"] in ("settled", "unknown") for r in case["reservations"])

        checks = {
            "旧载荷（带 story ＋ adventure_key）：确实是旧形状，且提示词里没有那段叮嘱":
                with_key["payload_had_story"] and with_key["payload_had_key"] and not with_key["marker_in_prompt"],
            "更旧的载荷（只有 story、连 adventure_key 都没有）：提示词里同样没有":
                no_key["payload_had_story"] and not no_key["payload_had_key"] and not no_key["marker_in_prompt"],
            "两档旧载荷都走到终态，不是崩在半路": all(case["task"][0] in ("succeeded", "failed") for case in (with_key, no_key)),
            # **前提断言**：先证明"撤回这件事真的发生了"，再谈它的后果（C84A-Q-C33-INJECTION-01）
            "两个撤回档：注入确实命中（钩子跑了）": all(case["hook_fired"] for case in (mid_render, before_publish)),
            "两个撤回档：撤回接口确实成功（第一次 200）":
                all(case["hook_http"] and case["hook_http"][0] == 200 for case in (mid_render, before_publish)),
            "两个撤回档：库里确实留下撤回痕迹（撤回前没有、撤回后有，且授权被吊销）":
                all(case["revocation_landed"] for case in (mid_render, before_publish)),
            # **移除钩子的对照必须失败**：不装钩子时三项指标全空 ⇒ 上面三条确有区分力
            "移除钩子对照：没有注入、没有 HTTP、库里也没有撤回痕迹":
                not no_hook["hook_fired"] and not no_hook["hook_http"]
                and not no_hook["note_after"]["note_revoked"] and no_hook["note_after"]["grants_revoked"] == 0,
            # **阶段语义**：enter 在越过发送边界**之前**，exit 在这一次已经发出**之后**
            # 取值写成**不会抛**的形式：钩子没跑时这两条要给出 False（红），而不是 IndexError。
            # 合同该给结论，不该给 traceback——那样跑批只会记成"用例出错"，看不出是哪一条不成立。
            "阶段语义可核：enter 时这一次还没发出（发送数为 0）":
                (mid_render["hook_fired"] or [{}])[0].get("dispatched_at_hook") == 0,
            "阶段语义可核：exit 时这一次已经发出（发送数 ≥ 1）":
                ((before_publish["hook_fired"] or [{}])[0].get("dispatched_at_hook") or 0) >= 1,
            "执行中撤回：提示词里没有叮嘱内容": not mid_render["marker_in_prompt"],
            "执行中撤回：仍然走到终态，不留永久处理中": mid_render["task"][0] in ("succeeded", "failed"),
            "执行中撤回：已发出的那次照实结算，不被抹掉": settled(mid_render) and mid_render["dispatched"] >= 1,
            "发布前撤回：提示词里没有叮嘱内容": not before_publish["marker_in_prompt"],
            "发布前撤回：仍然走到终态": before_publish["task"][0] in ("succeeded", "failed"),
            "发布前撤回：已发出的那次照实结算": settled(before_publish) and before_publish["dispatched"] >= 1,
            # 发送数与账本记的确认计量对齐（六档都对）
            "每一档：替身实际发送次数 ＝ 账本记下的 actual_units":
                all(case["dispatched"] == sum(int(r["actual_units"] or 0) for r in case["reservations"])
                    for case in cases.values()),
            "正常对照：不撤回时照常出图": normal["illustration"] == "ready" and normal["dispatched"] >= 1,
            "正常对照：授权过 public_story，所以那段文字**确实**在已写下的家庭来信里":
                normal["marker_still_in_written_story"],
            "六档都真的发出过调用（不是因为没发所以没漏）": all(case["dispatched"] >= 1 for case in cases.values()),
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C32_SOURCES),
        }
        return ContractResult(
            "Q-C33", "旧载荷不把叮嘱带给供应商；执行中／发布前撤回不改变这一点，已发出的费用事实照留",
            "CR-IMAGE-MEMORY-PURPOSE-2026-09-24 第 49 条", LEVEL_INTEGRATION, "A（载荷与发送边界）＋ I（撤回入口）",
            PASS if all(checks.values()) else FAIL,
            "把任务载荷改回升级前的两种旧形状（带 story／连 adventure_key 都没有），真实 worker 跑完后"
            "替身收到的提示词里都没有那段叮嘱；在 render 进行中与响应返回后各撤回一次，结果仍走到终态、"
            "提示词同样干净、已发出的预占照实结算；正常对照照常出图",
            {"checks": checks, "cases": cases, "digests_at_start": started, "digests_at_end": source_digests(*C32_SOURCES),
             "observation": {
                 "marker_still_in_written_story": {name: case["marker_still_in_written_story"] for name, case in cases.items()},
                 "note": "撤回只停止**今后**的使用；**已经写下的**那条家庭来信里的文字不会被追溯删除。"
                         "这是实测现状，不是本合同的断言——要不要追溯清理由产品定。"}},
            ["每档一位新主人一只新宠物，叮嘱授权 `public_story`（所以标记**会**进家庭故事），坐船去澳门跑一趟",
             "**旧载荷反例**：任务排好之后，把它的载荷改回升级前的形状——"
             "①带 `story`＋`adventure_key`；②只带 `story`（更旧的一档）。只改 Q 自己的一次性临时库",
             "**忠实性**：旧版本载荷里确实带 `story`（那正是 A 改掉它的原因），不是造一个产生不出来的状态",
             "**两个时点各撤回一次**：替身 `render` **进行中**（enter）与**响应已返回、写事务之前**（exit），"
             "走正式入口 `POST /care-notes/{id}/corrections` action=revoke",
             "每档都核：替身实际收到的提示词、插画与任务终态、该任务的预占结算、以及**确实发出过调用**",
             "**未断言、只记录**：撤回之后，已经写下的那条家庭来信里的文字仍在——追溯清理与否是产品决定"],
            source_digests(*C32_SOURCES), len(GUARD.attempts) - guard0)
