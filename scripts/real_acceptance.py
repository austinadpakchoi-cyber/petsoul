#!/usr/bin/env python3
"""真实服务验收（对着 scripts/real_integration.py 启动的 real-local 环境跑；不使用任何预置演示账号）。

    python scripts/real_acceptance.py run          # 新账号从零走完整条链路（A、B、C、D、E、家庭/访客），并启动 F 的自然时间打工
    python scripts/real_acceptance.py job-status   # F：查看自然时间打工的进度（可在中途重启 API / 任务进程后再看）
    python scripts/real_acceptance.py verify-job   # F：按工作实例核对工资、家庭消息、结束事件、回家各恰好一次；没到点保持 PENDING
    python scripts/real_acceptance.py judge        # 全部逐项判定（只读，不调用接口、不花钱），写 evidence/20-verdicts.json
    python scripts/real_acceptance.py export       # 只导出去敏关联表 evidence/15-linkage.json（给独立验收用）

判定与退出码见 scripts/real_acceptance_judge.py：0 全部 PASS；2 仍有 PENDING；1 有 FAIL 或 UNPROVEN（缺证据不算通过）。

- 账号口令随机生成，只写进数据目录里的 accounts.json（git 忽略），从不打印；
- 证据写进数据目录 evidence/*.json：只记接口返回里的业务字段（不记 cookie、CSRF、口令、邀请令牌、供应商密钥）；
- 会产生真实的地图与模型调用（都在既有的每日上限内）；不会触发生图（验收账号不开“生成照片”）。
"""

from __future__ import annotations

import argparse
import json
import secrets
import struct
import sys
import threading
import time
import uuid
import zlib
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import error, request

import real_acceptance_judge

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "PetJourneyBackend" / "data" / "web-real-acceptance"
EVIDENCE = DATA / "evidence"
ACCOUNTS = DATA / "accounts.json"
BASE = "http://127.0.0.1:18763/api/v1/web"
SECRET_FIELDS = {"token", "password", "csrf", "cookie", "join_path"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scrub(value):
    if isinstance(value, dict):
        return {k: ("[不记录]" if k in SECRET_FIELDS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class Client:
    """一个浏览器会话（独立 cookie）。写操作自动带 CSRF 与幂等键。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.jar = CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.jar))
        self.user_id: str | None = None

    def csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "petsoul_csrf"), "")

    def call(self, method: str, path: str, body=None, *, key: str | None = None, headers: dict | None = None, raw: bytes | None = None,
             content_type: str = "application/json") -> tuple[int, object]:
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        req = request.Request(BASE + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", content_type)
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            req.add_header("X-CSRF-Token", self.csrf())
            req.add_header("Idempotency-Key", key or f"acc-{uuid.uuid4().hex[:20]}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with self.opener.open(req, timeout=60) as response:
                text = response.read().decode("utf-8")
                return response.status, (json.loads(text) if text else None)
        except error.HTTPError as exc:
            text = exc.read().decode("utf-8")
            return exc.code, (json.loads(text) if text.startswith("{") else text)

    def get(self, path: str):
        return self.call("GET", path)

    def ok(self, method: str, path: str, body=None, **kw):
        status, payload = self.call(method, path, body, **kw)
        if status >= 300:
            raise SystemExit(f"[{self.label}] {method} {path} → {status} {json.dumps(scrub(payload), ensure_ascii=False)[:600]}")
        return payload


def png(width: int = 48, height: int = 48, rgb=(168, 170, 176)) -> bytes:
    """一张纯色测试照片（明确是验收用的测试图，不是任何真实宠物照片）。"""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + bytes(rgb) * width
    body = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + body


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = f"----acc{uuid.uuid4().hex}"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    for name, (filename, content, ctype) in files.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode("utf-8")
                     + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def save(name: str, payload) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{name}.json").write_text(json.dumps(scrub(payload), ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def accounts() -> dict:
    return json.loads(ACCOUNTS.read_text(encoding="utf-8")) if ACCOUNTS.exists() else {}


def new_account(label: str, entry: dict | None = None) -> Client:
    stamp = datetime.now().strftime("%m%d%H%M%S")
    username, password = f"acc{label}{stamp}", secrets.token_urlsafe(18)
    client = Client(label)
    body = {"username": username, "password": password, "display_name": f"验收{label}"}
    if entry:
        body["entry"] = entry
    status, payload = client.call("POST", "/auth/register", body)
    if status != 201:
        raise SystemExit(f"注册失败 {status} {payload}")
    client.user_id = payload["user"]["user_id"]
    stored = accounts()
    stored[label] = {"username": username, "password": password, "user_id": client.user_id}
    ACCOUNTS.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")
    return client


def login(label: str) -> Client:
    info = accounts()[label]
    client = Client(label)
    client.ok("POST", "/auth/login", {"username": info["username"], "password": info["password"]})
    client.user_id = info["user_id"]
    return client


def upload(client: Client, name: str, species: str, household_id: str | None = None) -> dict:
    fields = {"name": name, "species": species}
    if household_id:
        fields["household_id"] = household_id
    raw, ctype = multipart(fields, {"photo": ("pet.png", png(), "image/png")})
    return client.ok("POST", "/pets", raw=raw, content_type=ctype)


def reception(client: Client, pet_id: str, text: str, branch: str = "own_pet") -> dict:
    session = client.ok("POST", "/reception/sessions", {"pet_id": pet_id, "branch": branch})
    session = client.ok("POST", f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]})
    decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet",
                  "purposes": ["private_chat", "home_interaction", "travel_preference"], "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]}
                 for c in session["candidates"]]
    result = client.ok("POST", "/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"],
                                                            "decisions": decisions})
    return {"candidates": session["candidates"], "notes": result.get("notes"), "grants": result.get("grants")}


def farm_until(client: Client, home_id: str, pet_id: str, target: int, log: list) -> int:
    """真实种菜卖菜攒旅费：三块地种太阳豌豆（3 分钟成熟），收了卖给杂货铺，钱进 pet_id 的星球账户。"""
    while True:
        home = client.ok("GET", f"/home?pet_id={pet_id}")
        balance = home["wallet"]["balance"]
        if balance >= target:
            return balance
        for plot in home["plots"]:
            if plot["stage"] in ("ripe", "harvested"):
                if plot["stage"] == "ripe":
                    client.ok("POST", "/farm/actions", {"home_id": home_id, "plot_id": plot["plot_id"], "action": "harvest"})
                client.ok("POST", "/farm/actions", {"home_id": home_id, "plot_id": plot["plot_id"], "action": "plant", "crop_key": "sun_pea"})
            elif plot["stage"] == "empty":
                client.ok("POST", "/farm/actions", {"home_id": home_id, "plot_id": plot["plot_id"], "action": "plant", "crop_key": "sun_pea"})
        pantry = {i["item_key"]: i["qty"] for i in client.ok("GET", f"/market?pet_id={pet_id}")["pantry"]}
        if pantry.get("sun_pea"):
            sold = client.ok("POST", f"/market/sell?pet_id={pet_id}", {"item_key": "sun_pea", "qty": pantry["sun_pea"]})
            log.append({"at": now_iso(), "sold": pantry["sun_pea"], "gained": sold["gained_coins"], "balance": sold["wallet"]["balance"]})
            continue
        time.sleep(40)


def run() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    report: dict = {"started_at": now_iso(), "base": BASE}

    # ---- 访客：不登录先逛逛 ----
    visitor = Client("visitor")
    world = visitor.ok("GET", "/public/world")
    report["visitor"] = {"entries": [e["route"] for e in world["entries"]], "living_residents": world["living_residents"],
                         "residents": [{k: r[k] for k in ("pet_id", "name", "residence", "presence", "doing")} for r in world["residents"]]}
    save("01-visitor-world", world)
    chosen = world["residents"][0]

    # ---- A：新用户从零开始（接自己的宠物），入口带着访客页选中的伙伴 ----
    a = new_account("A", {"kind": "adopt", "pet_id": chosen["pet_id"]})
    onboarding = a.ok("GET", "/onboarding")
    report["A_register"] = {"step": onboarding["step"], "households": onboarding["households"], "entry": onboarding["entry"]}
    pet1 = upload(a, "年糕", "cat")
    recep = reception(a, pet1["pet_id"], "它叫我姐姐。最喜欢在阳台晒太阳，听到打雷会躲到床底下。它不爱熬夜，晚上十一点就睡。口头禅是咕噜咕噜。以后想带它去海边看船。")
    report["A_reception"] = {"candidates": [{k: c[k] for k in ("kind", "text", "suggested_slot")} for c in recep["candidates"]]}
    moved = a.ok("POST", "/onboarding/move-in", {"pet_id": pet1["pet_id"], "habitat": "seaside", "public_posts": True})
    household_id = moved["households"][0]["household_id"]
    home = a.ok("GET", f"/home?pet_id={pet1['pet_id']}")
    place = a.ok("GET", f"/home/place?pet_id={pet1['pet_id']}")
    cards = a.ok("GET", f"/credentials?pet_id={pet1['pet_id']}")
    report["A_home"] = {"step": moved["step"], "home_id": home["home_id"], "place": place["place"], "wallet": home["wallet"],
                        "cards": [{k: c.get(k) for k in ("kind", "status", "number", "issued_at")} for c in cards if c.get("credential_id")],
                        "entry_still_pending": moved["entry"] is not None}
    save("02-A-home", {"onboarding": moved, "home": home, "place": place, "cards": cards})

    # ---- 同一个家：再领养访客页选中的居民、再接一只自己的宠物（多宠共用一个家） ----
    adopted = a.ok("POST", "/adoption/adopt", {"candidate_id": chosen["candidate_id"], "household_id": household_id})
    status, moved2 = a.call("POST", "/onboarding/move-in", {"pet_id": adopted["pet_id"]})
    waited = 0
    while status == 409 and isinstance(moved2, dict) and moved2["error"]["details"].get("reason") == "pet_away" and waited < 3600:
        time.sleep(60)  # 领养时 TA 正在外面：等 TA 回到驿站（不瞬移）
        waited += 60
        status, moved2 = a.call("POST", "/onboarding/move-in", {"pet_id": adopted["pet_id"]})
    pet3 = upload(a, "小海", "dog", household_id)
    a.ok("POST", "/onboarding/move-in", {"pet_id": pet3["pet_id"]})
    pets = a.ok("GET", f"/home?pet_id={pet1['pet_id']}")["pets"]
    report["A_household"] = {"household_id": household_id, "adopted_resident_keeps_pet_id": adopted["pet_id"] == chosen["pet_id"],
                             "waited_for_resident_seconds": waited, "pets": [{k: p[k] for k in ("pet_id", "name", "origin", "join_step", "presence")} for p in pets],
                             "wallets": {p["pet_id"]: a.ok("GET", f"/home?pet_id={p['pet_id']}")["wallet"]["balance"] for p in pets},
                             "no_pet_id_without_choice": a.call("GET", "/home")[0]}
    save("03-A-household", report["A_household"])

    # ---- F：自然时间的短时打工（领养来的伙伴去花店帮忙 2 小时），期间可重启进程 ----
    job = a.ok("POST", f"/journey/depart?pet_id={adopted['pet_id']}", {"destination_key": "work:florist"})
    job_visit = a.ok("GET", f"/visits/{job['planned_visit_id']}")
    report["F_job_started"] = {"pet_id": adopted["pet_id"], "journey_id": job["journey_id"], "legs": [
        {k: l.get(k) for k in ("mode", "time_basis", "time_source")} | {"source": (l.get("reference") or {}).get("source_label")} for l in job["legs"]],
        "workplace": {k: job_visit["place"].get(k) for k in ("provider", "place_id", "name", "address", "attribution", "source_updated_at")},
        "work_from": job_visit["planned_arrival_utc"], "work_until": job_visit["leaving_at"], "home_at": job["legs"][-1]["times"]["planned_arrival_utc"]}
    save("04-F-job-start", {"snapshot": job, "visit": job_visit})

    # ---- 攒旅费：真实种菜卖菜（三块地，太阳豌豆 3 分钟成熟） ----
    farm_log: list = []
    farm_until(a, home["home_id"], pet3["pet_id"], 48, farm_log)
    report["farm"] = farm_log

    # ---- D + H：真实地点、路线与时间（家附近的真实咖啡店，高德步行估时）；同一个幂等键重复出发只成立一次、只扣一次钱 ----
    before_cafe = a.ok("GET", f"/home?pet_id={pet1['pet_id']}")["wallet"]["balance"]
    dup_key = f"acc-dup-{uuid.uuid4().hex[:12]}"
    cafe = a.ok("POST", f"/journey/depart?pet_id={pet1['pet_id']}", {"destination_key": "local:cafe"}, key=dup_key)
    cafe_again = a.ok("POST", f"/journey/depart?pet_id={pet1['pet_id']}", {"destination_key": "local:cafe"}, key=dup_key)
    cafe_visit = a.ok("GET", f"/visits/{cafe['planned_visit_id']}")
    report["D_cafe"] = {"legs": [{k: l.get(k) for k in ("mode", "time_basis", "time_source")} | {
        "source": (l.get("reference") or {}).get("source_label"), "verified_at": (l.get("reference") or {}).get("verified_at")} for l in cafe["legs"]],
        "place": {k: cafe_visit["place"].get(k) for k in ("provider", "place_id", "name", "address", "category", "attribution", "source_updated_at")},
        "planned_arrival_utc": cafe_visit["planned_arrival_utc"]}
    report["H_duplicate"] = {"same_journey": cafe["journey_id"] == cafe_again["journey_id"],
                             "charged": before_cafe - a.ok("GET", f"/home?pet_id={pet1['pet_id']}")["wallet"]["balance"]}
    save("05-D-cafe", {"snapshot": cafe, "visit": cafe_visit})

    # ---- E：有来源的远行计划（港澳一日行）：先预览，再出发 ----
    preview = a.ok("GET", f"/journey/plan?destination_key=macau_ferry&pet_id={pet3['pet_id']}")
    save("06-E-plan-preview", preview)
    trip = a.ok("POST", f"/journey/depart?pet_id={pet3['pet_id']}", {"destination_key": "macau_ferry"})
    ferry = [l for l in trip["legs"] if l["mode"] == "ferry" and l["kind"] == "main"]
    report["E_trip"] = {"leave_home_at": preview["leave_home_at"], "returns_home_at": preview["returns_home_at"], "venue": preview["venue"],
                        "ferry": [{"reference_id": l["reference"]["reference_id"], "world_service": l["world_service"]["service_code"],
                                   "carrier": l["world_service"]["carrier_name"], "world_reference": l["world_service"]["reference_id"],
                                   "planned_departure_utc": l["times"]["planned_departure_utc"]} for l in ferry],
                        "fares": [l.get("reference_fare") for l in preview["legs"] if l.get("reference_fare")],
                        "wallet_after": a.ok("GET", f"/home?pet_id={pet3['pet_id']}")["wallet"]["balance"]}
    save("07-E-trip", trip)

    # ---- 一只宠物同一时刻只有一个安排：在外面的宠物不能再出发 ----
    busy_status, busy = a.call("POST", f"/journey/depart?pet_id={pet1['pet_id']}", {"destination_key": "local:stroll"})
    report["H_one_place"] = {"status": busy_status, "reason": busy["error"]["details"]["reason"] if busy_status != 200 else None}

    # ---- C：真实模型调用，按 DNA 说话 ----
    a.ok("PATCH", "/settings", {"model_replies": True})
    dna = a.ok("PUT", f"/pets/{pet1['pet_id']}/dna", {"owner_title": "姐姐", "personality": "慢热但很黏人", "catchphrase": "咕噜咕噜",
                                                     "favorite_places": ["阳台"], "hobbies": ["晒太阳"], "fears": ["打雷"], "habits": ["不爱熬夜，晚上十一点就睡"]})
    sent = a.ok("POST", f"/communicator/{pet1['pet_id']}/messages", {"client_message_id": f"acc-{uuid.uuid4().hex[:16]}", "text": "今天下雨了，你在外面冷不冷？"})
    reply = None
    for _ in range(40):
        thread = a.ok("GET", f"/communicator/{pet1['pet_id']}/messages")
        # 收到的第一条回信不论来源都记下来；是不是真实模型由判定器按 composed_by=model 判（模板不算通过）
        reply = next((m for m in thread["items"] if m["sender"] == "pet" and m["created_at"] >= sent["created_at"] and m.get("channel") == "private"), None)
        if reply:
            break
        time.sleep(30)
    report["C_model"] = {"dna_version": dna.get("version"), "behavior_summary": (dna.get("behavior") or {}).get("summary"),
                         "reply": reply and {k: reply[k] for k in ("text", "composed_by", "created_at")}, "sent_note": sent.get("status_note")}
    save("08-C-model", {"dna": dna, "sent": sent, "reply": reply})

    # ---- 家庭：邀请一位家人（共同照顾者），私聊各自的、家庭频道共享；移除后立即失去访问 ----
    invite = a.ok("POST", f"/households/{household_id}/invites", {"role": "caregiver", "relation_hint": "妈妈", "ttl_hours": 24})
    c = new_account("C", {"kind": "invite", "invite_token": invite["token"]})
    pending = c.ok("GET", "/onboarding")["entry"]
    joined = c.ok("POST", "/invites/accept", {"token": invite["token"]})
    c.ok("POST", f"/communicator/{pet1['pet_id']}/messages", {"client_message_id": f"acc-{uuid.uuid4().hex[:16]}", "text": "我是妈妈，悄悄跟你说句话"})
    a_thread = a.ok("GET", f"/communicator/{pet1['pet_id']}/messages")["items"]
    c_thread = c.ok("GET", f"/communicator/{pet1['pet_id']}/messages")["items"]
    fam_a = [m["message_id"] for m in a_thread if m.get("channel") == "family"]
    fam_c = [m["message_id"] for m in c_thread if m.get("channel") == "family"]
    caregiver_settings = c.call("PATCH", f"/households/{household_id}/settings", {"public_posts": False})[0]
    a.ok("DELETE", f"/households/{household_id}/members/{c.user_id}")
    after = c.call("GET", f"/home?pet_id={pet1['pet_id']}")[0]
    report["family"] = {"invite_preview_pets": pending["pending_invite"]["pet_names"] if pending and pending.get("pending_invite") else None,
                        "joined_role": next(m["role"] for m in joined["members"] if m["user_id"] == c.user_id),
                        "private_message_hidden_from_A": not any("悄悄" in m["text"] for m in a_thread),
                        "family_channel_same_for_both": fam_a == fam_c and bool(fam_a), "family_ids_A": fam_a, "family_ids_C": fam_c,
                        "caregiver_changes_settings": caregiver_settings,
                        "after_removal_status": after}
    save("09-family", report["family"])

    # ---- B：两个新账号互相隔离；同时领养同一位居民只有一个成功 ----
    b1, b2 = new_account("B1"), new_account("B2")
    target = next(r for r in a.ok("GET", "/adoption/candidates") if r["availability"] == "available" and r.get("pet_id"))
    results: dict = {}

    def race(client: Client) -> None:
        results[client.label] = client.call("POST", "/adoption/adopt", {"candidate_id": target["candidate_id"]})[0]

    threads = [threading.Thread(target=race, args=(x,)) for x in (b1, b2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winner = b1 if results["B1"] == 200 else b2
    loser = b2 if winner is b1 else b1
    moved_b = winner.call("POST", "/onboarding/move-in", {"habitat": "city"})
    # H：钱不够时远行不成立，也不扣钱、不生成行程（领养来的居民账户里还没有旅费）
    broke_before = winner.ok("GET", f"/home?pet_id={target['pet_id']}")["wallet"]["balance"] if moved_b[0] == 200 else None
    broke_status, broke = winner.call("POST", f"/journey/depart?pet_id={target['pet_id']}", {"destination_key": "macau_ferry"})
    report["H_insufficient"] = {"move_in": moved_b[0], "balance_before": broke_before, "status": broke_status,
                                "reason": broke["error"]["details"].get("reason") if isinstance(broke, dict) and "error" in broke else None,
                                "code": broke["error"]["code"] if isinstance(broke, dict) and "error" in broke else None,
                                "balance_after": winner.ok("GET", f"/home?pet_id={target['pet_id']}")["wallet"]["balance"] if moved_b[0] == 200 else None,
                                "map_status": winner.call("GET", f"/journey/map?pet_id={target['pet_id']}")[0]}
    report["B"] = {"statuses": results, "one_winner": sorted(results.values()) == [200, 409],
                   "loser_cannot_see_winner_pet": loser.call("GET", f"/home?pet_id={target['pet_id']}")[0],
                   "loser_cannot_read_messages": loser.call("GET", f"/communicator/{target['pet_id']}/messages")[0],
                   "A_cannot_see_B_pet": a.call("GET", f"/home?pet_id={target['pet_id']}")[0]}
    save("10-B-isolation", report["B"])

    # ---- A：退出再登录，一切一致 ----
    before = {p["pet_id"]: a.ok("GET", f"/home?pet_id={p['pet_id']}")["wallet"]["balance"] for p in pets}
    a.ok("POST", "/auth/logout")
    logged_out = a.call("GET", "/home")[0]
    a2 = login("A")
    after_login = {p: a2.ok("GET", f"/home?pet_id={p}")["wallet"]["balance"] for p in before}
    report["A_relogin"] = {"logged_out_status": logged_out, "wallets_before": before, "wallets_after": after_login,
                           "pets_after": len(a2.ok("GET", f"/home?pet_id={pet1['pet_id']}")["pets"])}

    # ---- 供应商与任务进程状态 ----
    status = Client("ops").ok("GET", "/ops/status")
    report["ops"] = {"environment": status["environment"], "providers": [{k: p[k] for k in ("provider", "state", "calls_today", "last_success_at")} for p in status["providers"]],
                     "world": status["world"]}
    report["finished_at"] = now_iso()
    report["pets"] = {"pet1": pet1["pet_id"], "adopted": adopted["pet_id"], "pet3": pet3["pet_id"]}
    save("00-report", report)
    print(json.dumps(scrub(report), ensure_ascii=False, indent=1, default=str)[:6000])
    return real_acceptance_judge.judge("all")


def recheck_d() -> None:
    """D 复跑：全新账号，家在香港中环，去附近真实咖啡店（高德地点 + 步行估时）。"""
    d = new_account("D")
    pet = upload(d, "阿福", "dog")
    d.ok("POST", "/reception/sessions/" + d.ok("POST", "/reception/sessions", {"pet_id": pet["pet_id"], "branch": "own_pet"})["session_id"] + "/skip")
    d.ok("POST", "/onboarding/move-in", {"pet_id": pet["pet_id"], "habitat": "city"})
    place = d.ok("GET", f"/home/place?pet_id={pet['pet_id']}")["place"]
    options = {o["destination_key"]: o for o in d.ok("GET", f"/journey/destinations?pet_id={pet['pet_id']}")}
    cafe = d.ok("POST", f"/journey/depart?pet_id={pet['pet_id']}", {"destination_key": "local:cafe"})
    visit = d.ok("GET", f"/visits/{cafe['planned_visit_id']}")
    result = {"home": place, "option": options.get("local:cafe"), "place": visit["place"], "planned_arrival_utc": visit["planned_arrival_utc"],
              "legs": [{k: l.get(k) for k in ("mode", "time_basis", "time_source")} | {"from": l["times"]["planned_departure_utc"], "to": l["times"]["planned_arrival_utc"],
                        "source": (l.get("reference") or {}).get("source_label")} for l in cafe["legs"]], "checked_at": now_iso()}
    save("12-D-recheck", result)
    print(json.dumps(scrub(result), ensure_ascii=False, indent=1, default=str))


def chain() -> None:
    """同一件事在地图、家庭频道、公开动态、时间线、银行卡流水里是否指向同一趟行程（用 A 的账号读，和家人看到的一样）。"""
    report = json.loads((EVIDENCE / "00-report.json").read_text(encoding="utf-8"))
    a = login("A")
    pet = report["pets"]["pet1"]
    journey = a.ok("GET", f"/journey/map?pet_id={pet}")
    jid = journey["journey_id"]
    family = [m for m in a.ok("GET", f"/communicator/{pet}/messages")["items"] if m.get("channel") == "family"]
    feed = [p for p in a.ok("GET", "/circle/feed")["items"] if p["author"]["actor_id"] == pet]
    timeline = [i for i in a.ok("GET", f"/timeline?pet_id={pet}") if i.get("ref_id") == jid]
    cards = a.ok("GET", f"/credentials?pet_id={pet}")
    bank = next(c for c in cards if c["kind"] == "bank_card" and c.get("credential_id"))
    ledger = [e for e in a.ok("GET", f"/credentials/{bank['credential_id']}").get("ledger") or [] if e["type"] == "web_travel_fee"]
    visitor = Client("visitor")
    public_posts = [p["post_id"] for p in visitor.ok("GET", f"/public/pets/{pet}/posts")["items"]] if visitor.call("GET", f"/public/pets/{pet}/posts")[0] == 200 else []
    result = {"journey_id": jid, "lifecycle": journey["lifecycle"], "catching_up": journey.get("catching_up"),
              # 0.4.1：接口自己就带关联字段（source_event_id / reply_to / ref_kind / ref_id），不必再靠库级导出
              "family_messages": [{k: m.get(k) for k in ("message_id", "source_event_id", "reply_to", "channel", "composed_by", "created_at", "text")} for m in family],
              "posts": [{"post_id": p["post_id"], "source_event_id": p["source_event_id"], "visit_id": p["visit_id"], "text": p["text"]} for p in feed],
              "timeline": timeline, "fee_ledger": [{k: e.get(k) for k in ("tx_id", "type", "delta", "ref_kind", "ref_id", "created_at")} for e in ledger],
              "visitor_sees_posts": public_posts, "checked_at": now_iso()}
    save("13-chain", result)
    print(json.dumps(scrub(result), ensure_ascii=False, indent=1, default=str))


def job_status() -> None:
    report = json.loads((EVIDENCE / "00-report.json").read_text(encoding="utf-8"))
    a = login("A")
    pet = report["pets"]["adopted"]
    home = a.ok("GET", f"/home?pet_id={pet}")
    jobs = a.ok("GET", f"/jobs?pet_id={pet}")
    print(json.dumps({"presence": home["presence"], "wallet": home["wallet"]["balance"], "jobs": jobs}, ensure_ascii=False, indent=1, default=str))


def verify_job() -> int:
    """F：家人看到的接口视图 + 验收库只读关联（工资按幂等键、来信按 source_event_id），写 11 与 14 号证据，再逐项判定（21 号）。"""
    report = json.loads((EVIDENCE / "00-report.json").read_text(encoding="utf-8"))
    a = login("A")
    pet, journey_id = report["pets"]["adopted"], report["F_job_started"]["journey_id"]
    jobs = a.ok("GET", f"/jobs?pet_id={pet}")
    timeline = a.ok("GET", f"/timeline?pet_id={pet}")
    thread = a.ok("GET", f"/communicator/{pet}/messages")["items"]
    link = real_acceptance_judge.export_linkage()
    entry = (link.get("journeys") or {}).get("F") or {}
    result = {"checked_at": now_iso(), "journey_id": journey_id,
              "jobs": [{k: j.get(k) for k in ("journey_id", "status", "pay", "paid")} for j in jobs],
              # 这只宠物的全部打工收入（不只这份工作）：带幂等键，按 web:job:<journey> 关联到这份工作，其他键的条目也看得见
              "salary_entries": [{**t, "journey_id": journey_id if t["idempotency_key"] == f"web:job:{journey_id}" else None} for t in link.get("job_income") or []],
              "done_messages": [m for m in entry.get("messages") or [] if m["source_event_id"] == f"{journey_id}:work_done"],
              "family_messages_seen_by_A": [{k: m.get(k) for k in ("message_id", "channel", "composed_by", "created_at")} for m in thread if m.get("channel") == "family"],
              "salary_in_timeline": [{k: i.get(k) for k in ("kind", "ref_id", "at", "title")} for i in timeline if i["kind"] == "salary"],
              "basis": "jobs / family_messages_seen_by_A / salary_in_timeline 来自接口；salary_entries 与 done_messages 来自验收库只读关联（15-linkage.json）"}
    save("11-F-job-verify", result)
    save("14-F-restart", real_acceptance_judge.restart_evidence(report, link))
    return real_acceptance_judge.judge("F")


def _dig_reason(body) -> str | None:
    return ((body or {}).get("error") or {}).get("details", {}).get("reason")


def smoke() -> int:
    """0.4.1 冒烟（新账号、真实供应商）：命令 → 任务进程结算 → outbox → 家庭来信，全部按编号核对。

    读接口是纯读的，所以这里只发命令、然后等任务进程把世界推到位；等待期间不靠读接口推进。
    """
    user = new_account("S041")
    pet = upload(user, "小粥", "cat")
    session = user.ok("POST", "/reception/sessions", {"pet_id": pet["pet_id"], "branch": "own_pet"})
    user.ok("POST", f"/reception/sessions/{session['session_id']}/skip")
    user.ok("POST", "/onboarding/move-in", {"pet_id": pet["pet_id"], "habitat": "city"})
    before = user.ok("GET", f"/home?pet_id={pet['pet_id']}")
    place = user.ok("GET", f"/home/place?pet_id={pet['pet_id']}")["place"]
    status, body = user.call("POST", f"/journey/depart?pet_id={pet['pet_id']}", {"destination_key": "local:cafe"})
    asleep = status == 409 and isinstance(body, dict) and _dig_reason(body) == "pet_asleep"
    suggested = user.call("POST", f"/journey/suggest?pet_id={pet['pet_id']}", {"destination_key": "local:cafe"})[0] if asleep else None
    jid = body["journey_id"] if status == 200 else None
    departed, catching = None, None
    for _ in range(12 if jid else 0):  # 最多等两轮世界线（每轮 30 秒）
        home = user.ok("GET", f"/home?pet_id={pet['pet_id']}")
        catching = home["catching_up"] if catching is None else catching
        items = user.ok("GET", f"/communicator/{pet['pet_id']}/messages")["items"]
        departed = next((m for m in items if m.get("source_event_id") == f"{jid}:departed"), None)
        if departed:
            break
        time.sleep(10)
    cards = user.ok("GET", f"/credentials?pet_id={pet['pet_id']}")
    bank = next(c for c in cards if c["kind"] == "bank_card" and c.get("credential_id"))
    home_after = user.ok("GET", f"/home?pet_id={pet['pet_id']}")
    ledger = [e for e in user.ok("GET", f"/credentials/{bank['credential_id']}").get("ledger") or [] if e["type"] == "web_travel_fee"]
    ops = Client("ops").ok("GET", "/ops/status")
    result = {"checked_at": now_iso(), "contract_version": user.ok("GET", "/meta")["contract_version"], "journey_id": jid,
              "home_place": {k: place.get(k) for k in ("habitat", "city", "area_label", "timezone", "chosen")},
              "cards": sorted(c["kind"] for c in cards if c.get("credential_id")),
              "asleep_rule": {"status": status, "reason": _dig_reason(body) if isinstance(body, dict) else None, "suggest_status": suggested},
              "departed_message": {k: departed.get(k) for k in ("message_id", "source_event_id", "channel", "composed_by", "created_at")} if departed else None,
              "catching_up_seen": catching, "fee_ledger": [{k: e.get(k) for k in ("tx_id", "delta", "ref_kind", "ref_id")} for e in ledger],
              "wallet_before": before["wallet"]["balance"], "wallet_after": home_after["wallet"]["balance"], "catching_up_after": home_after["catching_up"],
              "world": {k: ops["world"][k] for k in ("lease_alive", "lease_pid", "ticks")},
              "cognition": {k: ops["cognition"][k] for k in ("lease_alive", "lease_pid", "ticks")},
              "outbox": ops["outbox"], "tasks": ops["tasks"]}
    save("16-smoke-041", result)
    print(json.dumps(scrub(result), ensure_ascii=False, indent=1, default=str))
    # 深夜（TA 按作息在睡觉）时出发本来就不成立：这时冒烟的结论是“新用户链路 + 作息规则”，不强求有行程
    if asleep:
        ok = suggested == 200 and len(result["cards"]) == 3 and result["home_place"]["chosen"] and not home_after["catching_up"]
    else:
        ok = bool(departed) and departed["channel"] == "family" and len(ledger) == 1 and ledger[0]["ref_id"] == jid
    print("冒烟结论：", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # 控制台编码不支持的字符用替代符，不因打印中断判定
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("run", "recheck-d", "chain", "job-status", "verify-job", "judge", "export", "smoke"))
    args = parser.parse_args()
    actions = {"run": run, "recheck-d": recheck_d, "chain": chain, "job-status": job_status, "verify-job": verify_job,
               "judge": lambda: real_acceptance_judge.judge("all"), "export": lambda: bool(real_acceptance_judge.export_linkage()) and 0, "smoke": smoke}
    return actions[args.action]() or 0


if __name__ == "__main__":
    sys.exit(main())
