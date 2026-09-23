"""独立验收（工作包 Q）：正式 worker 发给图像适配器的东西，确由照片导演的编译结果决定（Q-C25）。

非测试模块（不以 test 开头），discover 不收集。一次性临时库、正式装配、替身生图供应商，不联网、不产生付费调用。

**四个目标场景各自走到真实 worker**（COORD-Q-C25-SCENE-COVERAGE）：
  home / train / flight_adventure 走主人主动拍照命令（I 的 `POST /pets/{pet}/photo-request`），
  cafe 走宠物**自己**在真实到访里按下的 `take_photo`（B 的世界事件链路）。
场景准入（能不能提这个要求）由 Q-C26 证明；这里证明的是**发出去的那一次调用**长什么样。

**不手装任何回调**：`reference_origin_of`、`event_revision_of`、`consent_in` 等一律用正式装配里的那一份；
缺了就如实失败，Q 不替装配方补。观察点只在测试进程内包一层**记录**，不改行为、不改共享业务源码。
"""

from __future__ import annotations

import hashlib
import json

from runtime_contract_harness import FAIL, GUARD, LEVEL_INTEGRATION, PASS, ContractResult, source_digests
from runtime_contract_media import StagedIllustrator
from web_base import LUNCH_UTC, FakeClock

from app.utils import parse_dt

# 这条合同要比对的实现面：**开跑前**取一次、收尾再取一次，两次不同说明跑的过程中被改了（不作为稳定验收）。
# 进程真正加载的那一版由 `verify_runtime_evidence.run_contracts` 在导入 app 之前另记一份。
C25_SOURCES = ("app/web_journey/illustrations.py", "app/web_journey/photo_director_bridge.py",
               "app/web_journey/photo_prompts.py", "app/web_journey/photo_command.py", "app/web_composition.py",
               "app/web_agent_wiring.py", "app/web_agent/photo_wiring.py", "app/web_agent/photo_scene.py",
               "app/web_photo_director/compiler.py", "app/web_photo_director/readiness.py",
               "app/web_photo_director/validation.py", "app/web_photo_director/contracts.py",
               "app/web_photo_director/delivery.py", "app/web_photo_director/recipes.py",
               "app/web_photo_director/port.py", "app/web_photo_director/catalog.py",
               "app/web_photo_director/rules.py", "app/routers/web/pets.py")

SCENES = ("home", "train", "flight_adventure", "cafe")


def pet_png(red: int) -> bytes:
    """一张 1x1 的 PNG，像素颜色按 `red` 变。

    每只宠物上传**互不相同**的一张：这样"参考图就是**这只**宠物那张"才是可证的——
    四只都用同一份字节的话，串到别人的参考图也照样对得上，那条断言就是空的。
    """
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    body = (chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes([0, red, 32, 64]))) + chunk(b"IEND", b""))
    return bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + body


class DirectorContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql`、`_photo_request`、`_park_other_tasks` 由同组的用例提供）。"""

    def contract_c25_worker_uses_director_output(self) -> ContractResult:
        """Q-C25：四个目标场景各自走到真实 worker，传给图像适配器的 prompt／尺寸／参考图逐项等于**同一次**导演编译的结果。

        比对方式：把 `_director_inputs`／`_director_ready` 各包一层**只记录**的壳（不改行为），
        拿到这一次真实的导演输入，再用**真实的** `photo_director_bridge.compile_call` 自己编一遍，
        与适配器**实际收到**的逐项比。参考图按 **bytes 的 SHA-256** 比（导演包只带摘要，从不持有字节），
        并且要等于这只宠物**真实上传**的那张。缺必需身份参考时必须在**预占之前**挡下：0 预占、0 发送，且不回落旧模板。
        """
        guard0 = len(GUARD.attempts)
        started = source_digests(*C25_SOURCES)  # 开跑这一刻的实现指纹
        clock = FakeClock(LUNCH_UTC).install(self)
        web = self.web
        tints = {"home": 10, "train": 70, "flight": 130, "cafe": 190}

        seen: dict[str, list] = {"calls": [], "inputs": [], "ready": []}
        real_inputs, real_ready = web.illustrations._director_inputs, web.illustrations._director_ready

        def recording_inputs(*args, **kwargs):  # 只记录，不改行为
            value = real_inputs(*args, **kwargs)
            seen["inputs"].append(value)
            return value

        def recording_ready(*args, **kwargs):  # 只记录，不改行为：闸门到底判成什么
            value = real_ready(*args, **kwargs)
            seen["ready"].append(value if isinstance(value, str) else None if value is None else
                                 {"ready": getattr(value, "ready", None), "reason": getattr(value, "reason", None),
                                  "missing_required": list(getattr(value, "missing_required", ()) or ())})
            return value

        class RecordingIllustrator(StagedIllustrator):
            """在替身生图里把**适配器实际收到的**提示词、尺寸、参考图字节记下来（参考图只记摘要）。"""

            def render(self, prompt, reference=None, size="2048x2048"):
                seen["calls"].append({"prompt": prompt, "size": size,
                                      "reference_sha256": hashlib.sha256(reference[0]).hexdigest() if reference else None})
                return super().render(prompt, reference, size)

        def install() -> RecordingIllustrator:
            from app.web_providers import WebProviders

            art = RecordingIllustrator(None, None)
            current = web.providers
            web.providers = WebProviders(enabled=True, chat=current.chat, geo=current.geo, illustrator=art, meter=current.meter)
            web.illustrations.illustrator = art
            web.illustrations._director_inputs = recording_inputs
            web.illustrations._director_ready = recording_ready
            return art

        def owner_with(label: str, *, photo: bool = True):
            owner = self.user(label)
            # 每只宠物上传**不一样**的一张：串了别人的参考图这里就对不上
            owner.upload_pet("年糕", "cat", photo=pet_png(tints[label.rsplit("-", 1)[-1]]) if photo else None)
            owner.move_in()
            assert owner.patch("/settings", {"generated_photos": True}).status_code == 200
            return owner

        def observe(art, owner, task_id: str | None, http: int, marks: tuple[int, int, int]) -> dict:
            """跑完这一条任务之后，把这一次**实际发生**的事取下来。"""
            if task_id:
                self._park_other_tasks(task_id)
            web.illustrations.run_pending()
            row = self._sql("SELECT payload_json, status, last_error FROM web_tasks WHERE task_id = ?", (task_id or "-",))
            payload = json.loads(row[0][0]) if row else {}
            reservations = self._sql("SELECT operation_id, status FROM web_budget_reservations WHERE operation_id LIKE ?",
                                     (f"illustration:{task_id}:%",)) if task_id else []
            uploaded = web.pets.photo_path(owner.pet_id)
            return {"http": http, "task_id": task_id, "dispatched": art.dispatched,
                    "calls": seen["calls"][marks[0]:], "inputs": seen["inputs"][marks[1]:], "readiness": seen["ready"][marks[2]:],
                    # 闸门只在"有场景编号且 style=selfie"时才走导演：这两项落在正式入口写下的 payload 里
                    "gate": {"scene_key": payload.get("scene_key"), "style": payload.get("style"),
                             "event_origin": payload.get("event_origin")},
                    "task": {"status": row[0][1] if row else None, "last_error": row[0][2] if row else None},
                    "reservations": [dict(zip(("operation_id", "status"), r)) for r in reservations],
                    "uploaded_sha256": hashlib.sha256(uploaded[0].read_bytes()).hexdigest() if uploaded else None,
                    "illustration": (self._sql("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id or "-",))
                                     or [("-",)])[0][0],
                    "place": payload.get("place"), "city": payload.get("city"), "scene": payload.get("scene")}

        def marks() -> tuple[int, int, int]:
            return len(seen["calls"]), len(seen["inputs"]), len(seen["ready"])

        def commanded(label: str, scene: str, *, photo: bool = True, narrative: str = "daily_life", arrange=None) -> dict:
            """主人主动按下那一次拍照命令（I 的正式入口）。`arrange` 把宠物先安置到这个场景成立的真实状态。"""
            art = install()
            owner = owner_with(f"q-c25-{label}", photo=photo)
            extra = arrange(owner) if arrange is not None else {}
            at = marks()
            created = self._photo_request(owner, owner.pet_id, scene, narrative=narrative, key=f"q-c25-{label}")
            body = created.json() if created.status_code == 200 else {}
            return {**observe(art, owner, body.get("task_id"), created.status_code, at), "arranged": extra}

        def board_train(owner) -> dict:
            """真的买票出发，再从**已落库的行程段**里查出 mode='train' 那一段，把时钟推到该段中点。

            不照抄别人用例里的分钟数（时刻表一改就失真），也不改库把打车伪成坐火车。
            """
            from app.schemas import EconomyTransactionType

            web.economy.apply(owner.pet_id, 4000, EconomyTransactionType.web_reward, f"q-c25-air:{owner.pet_id}",
                              reason="Q 合同机票", source="q.contract")
            out = owner.post(f"/journey/depart?pet_id={owner.pet_id}", {"destination_key": "tokyo_flight"})
            legs = self._sql("SELECT sequence, mode, starts_at, ends_at FROM web_journey_legs WHERE journey_id = ? ORDER BY sequence",
                             (out.json().get("journey_id"),)) if out.status_code == 200 else []
            leg = next(((seq, mode, s, e) for seq, mode, s, e in legs if mode == "train"), None)
            if leg is not None:
                starts, ends = parse_dt(leg[2]), parse_dt(leg[3])
                clock.now = starts + (ends - starts) / 2
            return {"depart_http": out.status_code, "modes": sorted({row[1] for row in legs}),
                    "train_leg": {"sequence": leg[0], "starts_at": leg[2], "ends_at": leg[3]} if leg else None,
                    "clock_at_request": clock.now.isoformat()}

        def at_cafe(label: str) -> dict:
            """宠物**自己**在一次真实到访里按下 take_photo（B 的世界事件链路），不是主人下的命令。"""
            art = install()
            owner = owner_with(f"q-c25-{label}", photo=True)
            journey_id = owner.post("/journey/depart", {"destination_key": "local:cafe"}).json()["journey_id"]
            clock.advance(minutes=20)
            self.run_background(clock.now)
            visit_id = owner.get("/journey/map").json()["current_visit_id"]
            assert visit_id, "到店之后应当有一次到访"
            activities = owner.get(f"/visits/{visit_id}").json()["activities"]
            taking = next(a for a in activities if a["kind"] == "take_photo")
            at = marks()
            acted = owner.post(f"/visits/{visit_id}/actions", {"activity_id": taking["activity_id"]})
            rows = self._sql("SELECT task_id FROM web_tasks WHERE kind = 'illustration' AND dedupe_key = ?",
                             (f"illustration:photo:{visit_id}",))
            category = self._sql("SELECT place_json FROM web_visits WHERE visit_id = ?", (visit_id,))
            return {**observe(art, owner, rows[0][0] if rows else None, acted.status_code, at),
                    "arranged": {"journey_id": journey_id, "visit_id": visit_id,
                                 "place_category": json.loads(category[0][0]).get("category") if category else None}}

        try:
            scenes = {"home": commanded("home", "home"),
                      "train": commanded("train", "train", arrange=board_train),
                      "flight_adventure": commanded("flight", "flight_adventure", narrative="fictional_adventure"),
                      "cafe": at_cafe("cafe")}
            missing = commanded("missing", "home", photo=False)  # 缺必需身份参考 → 预占前挡下
        finally:
            web.illustrations._director_inputs = real_inputs
            web.illustrations._director_ready = real_ready

        from app.web_journey import photo_director_bridge as bridge
        from app.web_journey.photo_prompts import build_selfie_prompt  # 旧模板：**必须写全路径**（build_prompt 同名多处）

        def compare(scene: dict) -> dict:
            """用**真实的** bridge 把这一次的导演输入自己编一遍，与适配器实际收到的逐项比。"""
            inputs = next((value for value in scene["inputs"] if isinstance(value, tuple)), None)
            actual = scene["calls"][-1] if scene["calls"] else {}
            if inputs is None:
                return {"compiled": None, "actual": actual, "same_prompt": False, "same_size": False, "reference_matches": False,
                        "dropped": None, "not_old_template": False}
            prompt, size, dropped = bridge.compile_call(*inputs)
            old = build_selfie_prompt(species="cat", name="年糕", place=scene.get("place") or "", city=scene.get("city") or "",
                                      scene=scene.get("scene") or "", with_reference=True)
            return {"compiled": {"prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16], "size": size,
                                 "dropped": list(dropped), "prompt_chars": len(prompt)},
                    "actual": {"size": actual.get("size"), "reference_sha256": actual.get("reference_sha256"),
                               "prompt_sha256": hashlib.sha256(actual["prompt"].encode("utf-8")).hexdigest()[:16]
                               if actual.get("prompt") else None},
                    "same_prompt": actual.get("prompt") == prompt, "same_size": actual.get("size") == size == "2048x2048",
                    "reference_matches": actual.get("reference_sha256") is not None
                    and actual["reference_sha256"] == scene["uploaded_sha256"],
                    "dropped": list(dropped), "not_old_template": bool(actual.get("prompt")) and actual["prompt"] != old}

        compared = {name: compare(scene) for name, scene in scenes.items()}
        checks = {
            "四个目标场景都真的发出了调用并出图": all(scenes[name]["dispatched"] >= 1 and scenes[name]["illustration"] == "ready"
                                                  for name in SCENES),
            "四个场景的闸门都判成 ready（没有一个是回落旧路径蒙混过去的）":
                all(scenes[name]["readiness"] and scenes[name]["readiness"][-1] == {"ready": True, "reason": None, "missing_required": []}
                    for name in SCENES),
            "每个场景收到的提示词＝**同一次**导演编译的那一份": all(compared[name]["same_prompt"] for name in SCENES),
            "每个场景收到的尺寸都是导演给的 2048": all(compared[name]["same_size"] for name in SCENES),
            "每个场景的参考图按 bytes 的 SHA-256 对得上，且就是这只宠物真实上传的那张":
                all(compared[name]["reference_matches"] for name in SCENES),
            "四只宠物的参考图互不相同：对得上的是**这只**的那张，不是同一份假图":
                len({compared[name]["actual"]["reference_sha256"] for name in SCENES}) == len(SCENES),
            "四个场景都不回落旧自拍模板（逐字不同）": all(compared[name]["not_old_template"] for name in SCENES),
            "只丢负面词，没有静默丢别的": all(compared[name]["dropped"] in ([], ["negative_prompt"]) for name in SCENES),
            "train 那张是在**库里查出来的**真实列车段上拍的": scenes["train"]["arranged"]["depart_http"] == 200
                and scenes["train"]["arranged"]["train_leg"] is not None,
            "cafe 那张来自真实到访里宠物自己按下的 take_photo，且地点类目认得出":
                scenes["cafe"]["http"] == 200 and scenes["cafe"]["gate"]["scene_key"] == "cafe"
                and scenes["cafe"]["arranged"]["place_category"] is not None,
            "虚构那张明确标成 owner_directed，且 home/train 也各自带着来源":
                scenes["flight_adventure"]["gate"]["event_origin"] == "owner_directed"
                and scenes["home"]["gate"]["event_origin"] == "owner_directed"
                and scenes["train"]["gate"]["event_origin"] == "owner_directed",
            "缺必需身份参考：一次都不发": missing["dispatched"] == 0 and missing["calls"] == [],
            "缺必需身份参考：一笔预占都没有": missing["reservations"] == [],
            "缺必需身份参考：如实落没画成，不回落旧模板": missing["illustration"] == "failed"
                and (missing["task"]["last_error"] or "").startswith("image director_hold:"),
            # 起止指纹一致才算数：跑的过程中实现被改了，这一轮的结论不绑任何版本
            "跑完这一轮期间实现没有被改动": started == source_digests(*C25_SOURCES),
        }

        def trim(scene: dict) -> dict:
            return {k: v for k, v in scene.items() if k not in ("inputs", "calls")}

        return ContractResult(
            "Q-C25", "四个目标场景走到真实 worker：发给图像适配器的提示词／尺寸／参考图，逐项等于同一次导演编译的结果",
            "COORD-Q-C25-SCENE-COVERAGE、COORD-Q-PHOTO-NEXT、P3", LEVEL_INTEGRATION,
            "P（导演编译）＋ A（worker 与桥接）＋ B（场景事实与装配）＋ I（拍照命令与参考来源）",
            PASS if all(checks.values()) else FAIL,
            "home／train／flight_adventure／cafe 四个场景各自发出调用并出图；每一次适配器实收的 prompt／size 与**同次** "
            "bridge.compile_call 的输出逐项相同；参考图 SHA-256 等于该宠物真实上传那张；只丢 negative_prompt；"
            "缺必需身份参考时 0 预占 0 发送、如实落 failed 且不回落旧模板",
            {"checks": checks, "compared": compared, "scenes": {name: trim(scene) for name, scene in scenes.items()},
             "missing": trim(missing), "digests_at_start": started, "digests_at_end": source_digests(*C25_SOURCES)},
            ["五只宠物各自真实上传一张**互不相同**的照片（缺参考那只不传），主人都开“生成照片”；生图供应商换成替身，全程禁网",
             "home：直接用正式接口 POST /pets/{pet}/photo-request 拍一张",
             "train：真的买票去 tokyo_flight，从 web_journey_legs **查出** mode='train' 那一段，把时钟推到该段中点再请求",
             "flight_adventure：显式选 fictional_adventure 叙事再请求",
             "cafe：去 local:cafe 真实到访，由宠物自己按下 take_photo（B 的世界事件链路，不是主人下的命令）",
             "替身生图里把**适配器实际收到的** prompt／size／参考图字节记下来（参考图按 SHA-256 记，不存字节）",
             "把 `_director_inputs`／`_director_ready` 各包一层**只观察**的壳，取到这一次真实的导演输入与闸门判定",
             "对每个场景各自用**真实的** `photo_director_bridge.compile_call` 编一遍，逐项比 prompt／size／参考图 SHA-256",
             "与旧自拍模板（**全路径** `app.web_journey.photo_prompts.build_selfie_prompt`）比，必须逐字不同",
             "缺必需身份参考那只：核对 0 发送、0 预占、如实落 failed，且失败原因是导演的 hold",
             "**不手装任何回调**——`reference_origin_of`、`event_revision_of` 等一律用正式装配里的那一份",
             "开跑前与收尾各取一次实现指纹；进程真正加载的那一版由跑批脚本在导入 app 之前另记一份"],
            source_digests(*C25_SOURCES), len(GUARD.attempts) - guard0)


CONTRACTS = ("c25_worker_uses_director_output",)
