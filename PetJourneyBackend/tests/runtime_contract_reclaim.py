"""独立验收（工作包 Q）：**角色链路**上"已付费结果的认领"的几个边界（Q-C37）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。

插画那半在 Q-C35／Q-C36；角色这半单独成文，**不是为了对称好看，是因为两条链路的形状本来就不同**（A 指出的）：
  - 角色**没有「重画」**——「调整形象」是新建任务、新 revision，本来就没有上一次可问。
    所以插画的"第三次认领"与"无可认领时重画照旧付费"在角色这边**不存在**，不是缺口；
  - 第二次认领后发布**又**失败 → `attempts_exhausted`、**不重付**、那张图留在磁盘上
    （**"不重复付费"做到了、"不浪费已付费的结果"没做到**——这是被记录的取舍，不是缺陷）。

另：本模块新起一个文件，是因为 `runtime_contract_metering.py` 已经顶在 `arch_gate` 的 30 个定义上限。
"""

from __future__ import annotations

from pathlib import Path

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from web_base import LUNCH_UTC, FakeClock

C38_SOURCES = ("app/web_character/id_photo.py", "app/web_character/service.py",
               "app/web_platform/paid_result.py", "app/web_character/validate.py",
               "app/web_character/raster.py", "app/web_platform/budget.py")
C37_SOURCES = ("app/web_platform/paid_result.py", "app/web_character/service.py", "app/web_character/poses.py",
               "app/web_platform/budget.py", "app/web_platform/tasks.py")


class ReclaimContractCases:
    """与 web_base.WebPlatformTestBase 组合使用；沿用 MeteringContractCases 的注入与预占读取助手。"""

    def _c37_setup(self, label: str, *, fail_reason: str | None = None):
        """一位主人、一只**带原照**的猫：上传即排一张中性站姿。返回 (主人, asset_id, task_id, 替身)。"""
        from character_fakes import FakeCharacterIllustrator
        from web_base import tiny_png

        art = FakeCharacterIllustrator(fail_reason=fail_reason)
        art.available = True
        self.web.character.illustrator = art  # 先读后写由 `_c36_inject` 保证；这里是整体替换供应商
        owner = self.user(f"q-c37-{label}")
        assert owner.upload_pet("先建家", "cat", photo=None).status_code == 201  # 不带照片的不排队
        household_id = self.web.households.memberships(owner.user_id)[0].household_id
        created = owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=household_id)
        assert created.status_code == 201, created.text
        rows = self._sql("SELECT asset_id, task_id FROM web_pet_characters WHERE pet_id = ? ORDER BY rowid",
                         (created.json()["pet_id"],))
        assert rows, "带原照的宠物上传之后应当排一张中性站姿"
        return owner, rows[0][0], rows[0][1], art

    def _c37_state(self, asset_id: str, task_id: str, art) -> dict:
        row = self._sql("SELECT state, reason, rel_path FROM web_pet_characters WHERE asset_id = ?", (asset_id,))
        return {"calls": art.calls, "reservations": self._c35_reservations(f"character:{task_id}:"),
                "state": row[0][0] if row else None, "reason": row[0][1] if row else None,
                "rel_path": row[0][2] if row else None,
                "task": (self._sql("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,))
                         or [(None, None)])[0]}

    def _c37_paths(self, asset_id: str, attempt: int) -> tuple:
        """那一次尝试的图与小票：`characters/<user>/<asset>-<attempt>.png` ＋ 同 stem 的小票。"""
        row = self._sql("SELECT user_id FROM web_pet_characters WHERE asset_id = ?", (asset_id,))
        stem = Path(self.settings.web_private_media_dir) / "characters" / row[0][0] / f"{asset_id}-{attempt}"
        return stem.with_suffix(".png"), Path(f"{stem}.receipt.json")

    def contract_c37_character_reclaim_edges(self) -> ContractResult:
        """Q-C37：角色链路上，付费成功但没写进去之后的几个边界——再失败不重付、小票/图不对不认领、丢租约也认领。"""
        guard0 = len(GUARD.attempts)
        started = source_digests(*C37_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web

        def rounds(n: int = 3) -> None:
            for _ in range(n):
                clock.advance(minutes=10)
                web.character.run_pending(limit=1)  # **每轮只跑 1 个**：默认一轮多个会把中间状态抹掉

        # ① 第二次认领之后发布**又**失败 → 终态、不重付、图仍在磁盘
        owner, asset1, task1, art1 = self._c37_setup("twice")
        hook = self._c36_inject(web.character, "_publish_in", times=2)
        try:
            web.character.run_pending(limit=1)
            rounds()
        finally:
            hook["restore"]()
        image1, receipt1 = self._c37_paths(asset1, 1)
        twice_failed = {"injections": hook["fired"], "after": self._c37_state(asset1, task1, art1),
                        "image_on_disk": image1.is_file(), "receipt_on_disk": receipt1.is_file()}

        # ②③ 小票没了 / 图被改：都不认领、**也不重付**
        def broken(label: str, *, drop_receipt: bool) -> dict:
            owner_b, asset, task, art = self._c37_setup(label)
            hook_b = self._c36_inject(web.character, "_publish_in", times=1)
            try:
                web.character.run_pending(limit=1)
            finally:
                hook_b["restore"]()
            image, receipt = self._c37_paths(asset, 1)
            existed = {"image": image.is_file(), "receipt": receipt.is_file()}
            if drop_receipt:
                receipt.unlink()
            else:
                image.write_bytes(image.read_bytes() + b"Q-C37-tampered")  # 只改字节：sha256 对不上
            rounds()
            return {"existed_before": existed, "image_still_on_disk": image.is_file(),
                    "after": self._c37_state(asset, task, art)}

        no_receipt = broken("noreceipt", drop_receipt=True)
        tampered = broken("tampered", drop_receipt=False)

        # ④ 丢租约：画完把时钟推过租期，围栏拒绝这一次提交；下一轮应当**认领**而不是重画
        owner_l, asset_l, task_l, art_l = self._c37_setup("lease")
        jumped = {"done": False}

        def jump(*_args, **_kwargs):
            if not jumped["done"]:
                jumped["done"] = True
                clock.advance(minutes=5)  # 远超 120 秒租期

        real_render = art_l.render

        def render_then_jump(*args, **kwargs):
            image = real_render(*args, **kwargs)
            jump()
            return image

        art_l.render = render_then_jump
        web.character.run_pending(limit=1)
        lease_first = self._c37_state(asset_l, task_l, art_l)
        rounds()
        lease = {"clock_jumped": jumped["done"], "first": lease_first,
                 "after": self._c37_state(asset_l, task_l, art_l)}

        def paid_once(case: dict) -> bool:
            rows = case["after"]["reservations"]
            return case["after"]["calls"] == 1 and len(rows) == 1 and rows[0]["outcome"] == "succeeded"

        checks = {
            # ① 再失败也不重付
            "①前提：注入确实连抛两次，且第一次确实付费成功": twice_failed["injections"] == 2
                and bool(twice_failed["after"]["reservations"])
                and twice_failed["after"]["reservations"][0]["outcome"] == "succeeded",
            "①第二次认领后又失败：**没有再付一次**": paid_once(twice_failed),
            "①任务进终态，不留永久在跑": twice_failed["after"]["task"][0] in ("failed", "succeeded"),
            "①那张已经付过钱的图**仍然留在磁盘上**（不重复付费做到了、不浪费没做到——记录不是要求）":
                twice_failed["image_on_disk"] and twice_failed["receipt_on_disk"],
            # ②③ 小票没了 / 图被改
            "②③前提：破坏之前图与小票都确实存在":
                all(case["existed_before"] == {"image": True, "receipt": True} for case in (no_receipt, tampered)),
            "②小票没了：不认领、**不重付**": paid_once(no_receipt),
            "③图被改（sha256 对不上）：不认领、**不重付**": paid_once(tampered),
            "②③两档都没有把没认领成的结果当成功发布":
                no_receipt["after"]["state"] != "ready" and tampered["after"]["state"] != "ready",
            "②③图都仍在磁盘上": no_receipt["image_still_on_disk"] and tampered["image_still_on_disk"],
            # ④ 丢租约
            "④前提：确实在画完之后推过了租期": lease["clock_jumped"],
            "④丢租约之后**认领**上一次那张：没有再付一次": paid_once(lease),
            "④最终发布的是第一次那张（相对路径带 -1）":
                (lease["after"]["rel_path"] or "").endswith("-1.png") and lease["after"]["state"] == "ready",
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C37_SOURCES),
        }
        return ContractResult(
            "Q-C37", "角色链路的认领边界：第二次失败也不重付、小票/图不对时不认领不重付、丢租约也认领",
            "用户直派（A 修恢复、Q 禁网故障注入复验）", LEVEL_INTEGRATION, "A（已付费结果的认领 · 角色链路）",
            PASS if all(checks.values()) else FAIL,
            "注入发布失败后：第二次认领再失败也不再付费、任务进终态、图留在磁盘；小票被删或图被改时不认领也不重付；"
            "丢租约之后认领第一次那张并发布 -1",
            {"checks": checks, "second_failure": twice_failed, "receipt_missing": no_receipt,
             "image_tampered": tampered, "lease_lost": lease, "digests_at_start": started},
            ["每档一位新主人：先建一只**不带照片**的（不排队），再上传一只**带原照**的——后者会排一张中性站姿",
             "**故障注入在发布那一步**（`web_character._publish_in`，在 `queue.fenced(claim)` 事务体内）："
             "此刻付费调用**已经成功返回并结算过**，抛出去让写入整批回滚",
             "①连抛两次 → 第二次认领后又失败 → 核对不再付费、任务进终态、图与小票**都还在磁盘上**",
             "②③注入一次之后分别**删掉小票**与**改掉图的字节**（sha256 对不上），再跑重试",
             "④在替身画完**之后**把时钟推 5 分钟（远超 120 秒租期）让围栏拒绝；**每轮只跑 1 个任务**，"
             "默认一轮跑多个会在同一轮里把它回收掉、中间状态留不下来",
             "**角色没有「重画」**：「调整形象」是新建任务、新 revision，插画那两条（第三次认领、"
             "无可认领时重画照旧付费）在这里**不存在**，不是缺口",
             "**未覆盖**：姿态（批次二）那一套走同一条 `_resume`，但开关默认关，要单独打开才验得到——本合同没做"],
            source_digests(*C37_SOURCES), len(GUARD.attempts) - guard0)


    # ---- Q-C38：证件照链路（CR-6C2B-IDPHOTO） ----
    def _c38_setup(self, label: str, *, id_fail: str | None = None):
        """真实装配 ＋ 假供应商：上传一只带原照的猫，会同时排角色与**证件照**两个任务。

        证件照替身沿用 A 的 `IdPhotoIllustrator`（它按提示词分流，证件照那一路给合格的头肩像）；
        `id_fail` 让**证件照那一路**抛错——父类的 `fail_reason` 只作用在角色那一路，这里要单独来。
        """
        from character_fakes import FakeCharacterIllustrator  # noqa: F401  （保持与 A 的替身同源）
        from id_photo_chain_base import IdPhotoIllustrator
        from web_base import tiny_png

        from app.web_providers import ImageUnavailable

        class Art(IdPhotoIllustrator):
            def render(self, prompt, reference=None, size="2048x2048", background=None):
                if id_fail and "头部和上半身" in prompt:
                    self.id_calls.append({"prompt": prompt, "failed": id_fail})
                    raise ImageUnavailable(id_fail)
                return super().render(prompt, reference, size=size, background=background)

        art = Art()
        art.available = True
        web = self.web
        web.character.illustrator = art
        web.character.transparency_requested = True  # 与生产一致：请求透明底
        owner = self.user(f"q-c38-{label}")
        assert owner.upload_pet("先建家", "cat", photo=None).status_code == 201  # 不带照片的不排任何生图
        household_id = web.households.memberships(owner.user_id)[0].household_id
        created = owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=household_id)
        assert created.status_code == 201, created.text
        pet_id = created.json()["pet_id"]
        rows = self._sql("SELECT asset_id, task_id FROM web_pet_id_photos WHERE pet_id = ? ORDER BY rowid", (pet_id,))
        assert rows, "带原照的宠物上传之后应当排一张证件照"
        return owner, pet_id, rows[0][0], rows[0][1], art

    def _c38_state(self, owner, pet_id: str, asset_id: str, task_id: str, art) -> dict:
        row = self._sql("SELECT state, reason, rel_path, source_rel_path FROM web_pet_id_photos WHERE asset_id = ?",
                        (asset_id,))
        view = owner.get(f"/pets/{pet_id}/character")
        body = view.json() if view.status_code == 200 else {}
        return {"id_calls": len(art.id_calls), "reservations": self._c35_reservations(f"id_photo:{task_id}:"),
                "state": row[0][0] if row else None, "reason": row[0][1] if row else None,
                # **发布出来的是重新合成、重新裁切的那几份**；认领回来的原图记在 source_rel_path 上，
                # 所以"发布的是第一次那张"要看 source，不是 rel_path——照抄角色那半会看错列。
                "rel_path": row[0][2] if row else None, "source_rel_path": row[0][3] if row else None,
                "api_status": ((body.get("id_photo") or {}).get("status") if body else None),
                "task": (self._sql("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,))
                         or [(None, None)])[0]}

    def contract_c38_id_photo_reclaim_and_unknown(self) -> ContractResult:
        """Q-C38：证件照链路——付费成功没写进去时认领原图；结果不明时不重发且读接口显示 unknown。"""
        from pathlib import Path as _Path

        guard0 = len(GUARD.attempts)
        started = source_digests(*C38_SOURCES)
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web

        def rounds(n: int = 3) -> None:
            for _ in range(n):
                clock.advance(minutes=10)
                web.character.id_photo.run_pending(limit=1)  # 每轮只跑 1 个，中间状态才留得住

        def stem_of(asset_id: str, user_id: str, attempt: int) -> "_Path":
            return _Path(self.settings.web_private_media_dir) / "id-photos" / user_id / f"{asset_id}-{attempt}"

        # ① 付费成功、写入失败 → 自动重试**认领**原图（不再付一次）
        owner, pet, asset, task, art = self._c38_setup("claim")
        hook = self._c36_inject(web.character.id_photo, "_publish_in", times=1)
        try:
            web.character.id_photo.run_pending(limit=1)
        finally:
            hook["restore"]()
        first = self._c38_state(owner, pet, asset, task, art)
        receipt = _Path(f"{stem_of(asset, owner.user_id, 1)}.receipt.json")
        rounds()
        claim = {"injections": hook["fired"], "first": first, "receipt_written": receipt.is_file(),
                 "after": self._c38_state(owner, pet, asset, task, art)}

        # ② 结果不明（超时）：不重发，读接口显示 unknown——**不得折进 failed／absent**
        owner2, pet2, asset2, task2, art2 = self._c38_setup("unknown", id_fail="timeout")
        web.character.id_photo.run_pending(limit=1)
        unknown_first = self._c38_state(owner2, pet2, asset2, task2, art2)
        rounds()
        unknown = {"first": unknown_first, "after": self._c38_state(owner2, pet2, asset2, task2, art2)}

        # ③ 小票没了：不认领、**也不重付**
        owner3, pet3, asset3, task3, art3 = self._c38_setup("noreceipt")
        hook3 = self._c36_inject(web.character.id_photo, "_publish_in", times=1)
        try:
            web.character.id_photo.run_pending(limit=1)
        finally:
            hook3["restore"]()
        receipt3 = _Path(f"{stem_of(asset3, owner3.user_id, 1)}.receipt.json")
        existed3 = receipt3.is_file()
        if existed3:
            receipt3.unlink()
        rounds()
        no_receipt = {"receipt_existed": existed3, "after": self._c38_state(owner3, pet3, asset3, task3, art3)}

        def paid_once(case: dict) -> bool:
            rows = case["after"]["reservations"]
            return case["after"]["id_calls"] == 1 and len(rows) == 1

        checks = {
            # ① 认领
            "①前提：注入确实命中，且第一次确实付费成功、写了小票":
                claim["injections"] == 1 and claim["receipt_written"]
                and bool(claim["first"]["reservations"])
                and claim["first"]["reservations"][0]["outcome"] == "succeeded",
            "①前提：第一次的结果确实没写进去": claim["first"]["state"] != "ready",
            "①自动重试**认领**：证件照供应商只被调过一次": paid_once(claim),
            "①认领回来的是**第一次那张原图**（source 带 -1）":
                (claim["after"]["source_rel_path"] or "").endswith("-1.png"),
            "①最终发布出来（重新合成、重新裁切）": claim["after"]["state"] == "ready"
                and bool(claim["after"]["rel_path"]),
            # ② 结果不明不重发，读接口显示 unknown
            "②前提：第一次确实发出过且结果不明（预占停在 unknown）":
                unknown["first"]["id_calls"] == 1
                and any(r["status"] == "unknown" for r in unknown["first"]["reservations"]),
            "②自动重试**不重发**（证件照供应商仍只被调过一次）":
                unknown["after"]["id_calls"] == 1 and len(unknown["after"]["reservations"]) == 1,
            "②读接口显示 **unknown**，没有折进 failed／absent":
                unknown["after"]["api_status"] == "unknown",
            # ③ 小票没了
            "③前提：破坏之前小票确实存在": no_receipt["receipt_existed"],
            "③小票没了：不认领、**也不重付**": paid_once(no_receipt),
            "③没认领成时不当成功发布": no_receipt["after"]["state"] != "ready",
            "全程没有一次出网": len(GUARD.attempts) - guard0 == 0,
            "跑完这一轮期间实现没有被改动": started == source_digests(*C38_SOURCES),
        }
        return ContractResult(
            "Q-C38", "证件照链路：付费成功没写进去时认领原图；结果不明时不重发且读接口显示 unknown",
            "CR-6C2B-IDPHOTO（A 实现、Q 禁网故障注入复验）", LEVEL_INTEGRATION, "A（证件照链路）",
            PASS if all(checks.values()) else FAIL,
            "注入发布失败后：只调过一次供应商、认领第一次那张原图（source 带 -1）、重新合成后发布；"
            "结果不明时不重发且读接口显示 unknown；小票被删时不认领也不重付",
            {"checks": checks, "reclaim": claim, "unknown_not_resent": unknown, "receipt_missing": no_receipt,
             "digests_at_start": started},
            ["真实装配 ＋ A 的证件照替身（按提示词分流，证件照那一路给合格头肩像）；上传一只带原照的猫会同时排角色与证件照两个任务",
             "**只驱动 `id_photo.run_pending(limit=1)`**：证件照是独立种类（`pet_id_photo`），"
             "`character.run_pending` 不领它——这一点我核过它的 handlers 表，不是采信自述",
             "①在 `id_photo._publish_in`（围栏事务体内）抛一次：付费已成功并结算过，写入整批回滚",
             "②让**证件照那一路**超时——父类的 `fail_reason` 只作用在角色那一路，要单独抛",
             "③注入一次之后删掉小票，再跑重试",
             "**认领回来的原图记在 `source_rel_path`**，`rel_path` 是重新合成、重新裁切的产物——"
             "照抄角色那半会看错列，「发布的是第一次那张」必须看 source",
             "**未覆盖**：P §4.2 的五条门槛与不透明路线的三条门槛（A 自述未用真图验证过）；"
             "姿态开关打开之后的那一套"],
            source_digests(*C38_SOURCES), len(GUARD.attempts) - guard0)
