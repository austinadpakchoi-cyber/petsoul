"""生活时间线与打工记录（对齐说明 §4、§10）：只读汇总已经发生的记录，不另造事实。

时间线把旅行、打工工资、证件签发、护照纪念章、驾考、朋友、明信片与收藏串起来；
证件、明信片、账单与消息关联的是同一段经历（同一旅程 / 考试 / 签发记录）。
0.4.0：这些都属于宠物本身（全家看到同一份，领养前在星球上的公开经历也保留）；只有“一起听/看”的回忆只给陪着的那位家人。
"""

from __future__ import annotations

import json
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import parse_dt

CREDENTIAL_TITLE = {"identity_card": "拿到星球身份证", "bank_card": "开通星球银行卡", "care_profile": "建立照护档案", "passport": "领到护照", "driver_license": "拿到驾驶证"}
COLLECTION_TITLE = {"postcard": "寄回一张明信片", "badge": "获得一枚勋章", "seed": "带回稀有种子", "shared_memory": "和你一起听歌/看片的回忆",
                    "license_photo": "和你一起领了驾照", "car_voucher": "拿到驾校借车券"}
SUBJECT_NAMES = {"s1": "科目一", "s2": "科目二", "s3": "科目三", "s4": "科目四"}


def job_records(storage: JourneyStorage, user_id: str, pet_id: str, now: datetime, jobs: dict) -> list[dict]:
    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT j.journey_id, j.destination_key, j.title, j.departed_at, j.completes_at, v.place_json, v.starts_at, v.ends_at FROM web_journeys j "
            "LEFT JOIN web_visits v ON v.journey_id = j.journey_id WHERE j.pet_id = ? AND j.destination_key LIKE 'work:%' "
            "ORDER BY j.departed_at DESC LIMIT 50", (pet_id,)).fetchall()
    result = []
    for r in rows:
        job = jobs.get(r["destination_key"].split(":", 1)[1])
        starts, ends = parse_dt(r["starts_at"]), parse_dt(r["ends_at"])
        status = "going" if now < starts else ("working" if now < ends else "done")
        paid = storage.get_transaction_by_idempotency_key(f"web:job:{r['journey_id']}") is not None
        place = json.loads(r["place_json"]).get("name") if r["place_json"] else None
        result.append({"journey_id": r["journey_id"], "job_key": r["destination_key"].split(":", 1)[1], "title": r["title"], "place": place,
                       "starts_at": starts, "ends_at": ends, "status": status, "pay": job.pay if job else 0, "paid": paid})
    return result


def timeline(storage: JourneyStorage, user_id: str, pet_id: str, limit: int = 100) -> list[dict]:
    items: list[dict] = []
    with storage.connect() as conn:
        drives = 0
        for r in conn.execute("SELECT journey_id, destination_key, title, city, departed_at, completed_at FROM web_journeys WHERE pet_id = ? AND lifecycle != 'cancelled' "
                              "ORDER BY departed_at", (pet_id,)):
            if r["destination_key"] == "local:drive_trip":
                drives += 1
            kind = "first_drive" if r["destination_key"] == "local:drive_trip" and drives == 1 else ("work" if r["destination_key"].startswith("work:") else "trip")
            title = {"first_drive": f"第一次自己开车：{r['title']}", "work": f"去打工：{r['title']}"}.get(kind, f"出发：{r['title']}")
            items.append({"at": parse_dt(r["departed_at"]), "kind": kind, "title": title, "detail": r["city"], "ref_id": r["journey_id"]})
            if r["completed_at"]:
                back = "收工回到家" if kind == "work" else "回到家"
                items.append({"at": parse_dt(r["completed_at"]), "kind": "home", "title": f"{back}：{r['title']}", "detail": None, "ref_id": r["journey_id"]})
        for r in conn.execute("SELECT tx_id, reason, before_json, after_json, created_at FROM economy_transactions WHERE pet_id = ? AND type = 'web_job_income'", (pet_id,)):
            before, after = json.loads(r["before_json"] or "{}"), json.loads(r["after_json"] or "{}")
            items.append({"at": parse_dt(r["created_at"]), "kind": "salary", "title": f"领到工资 {after.get('travel_coin', 0) - before.get('travel_coin', 0)} 星币",
                          "detail": r["reason"], "ref_id": r["tx_id"]})
        for r in conn.execute("SELECT enrolled_at FROM web_driving WHERE pet_id = ? AND enrolled_at IS NOT NULL", (pet_id,)):
            items.append({"at": parse_dt(r["enrolled_at"]), "kind": "school", "title": "报名了爪爪驾校", "detail": "龟教练·慢慢", "ref_id": None})
        for r in conn.execute("SELECT attempt_id, part, passed, score, max_score, taken_at FROM web_exam_attempts WHERE pet_id = ? "
                              "ORDER BY taken_at, part = 'practical', attempt_no", (pet_id,)):  # 旧版驾考的记录
            part = "理论" if r["part"] == "theory" else "场景驾驶"
            items.append({"at": parse_dt(r["taken_at"]), "kind": "exam", "title": f"{part}考试{'通过' if r['passed'] else '没通过'}",
                          "detail": f"{r['score']}/{r['max_score']}", "ref_id": r["attempt_id"]})
        for r in conn.execute("SELECT session_id, subject, attempt_kind, passed, score, settled_at FROM web_school_sessions WHERE pet_id = ? "
                              "AND mode = 'formal' AND state = 'settled' ORDER BY settled_at", (pet_id,)):
            name = SUBJECT_NAMES.get(r["subject"], "驾考")
            kind = "补考" if r["attempt_kind"] == "retake" else "考试"
            items.append({"at": parse_dt(r["settled_at"]), "kind": "exam", "title": f"{name}{kind}{'通过' if r['passed'] else '没通过'}",
                          "detail": f"{r['score']} 分", "ref_id": r["session_id"]})
        for r in conn.execute("SELECT credential_id, kind, number, issued_at FROM web_credentials WHERE pet_id = ? ORDER BY issued_at, rowid",
                              (pet_id,)):
            if r["kind"] in CREDENTIAL_TITLE:
                items.append({"at": parse_dt(r["issued_at"]), "kind": "credential", "title": CREDENTIAL_TITLE[r["kind"]], "detail": r["number"], "ref_id": r["credential_id"]})
        for r in conn.execute("SELECT journey_id, city, stamped_at FROM web_passport_stamps WHERE pet_id = ?", (pet_id,)):
            items.append({"at": parse_dt(r["stamped_at"]), "kind": "stamp", "title": f"护照上盖了{r['city']}的纪念章", "detail": None, "ref_id": r["journey_id"]})
        for r in conn.execute("SELECT friend_id, friend_kind, friend_name, first_met_at, last_place FROM web_pet_friends WHERE pet_id = ?", (pet_id,)):
            who = "星球居民" if r["friend_kind"] == "resident" else "新朋友"
            items.append({"at": parse_dt(r["first_met_at"]), "kind": "friend", "title": f"认识了{who}{r['friend_name']}", "detail": r["last_place"], "ref_id": r["friend_id"]})
        for r in conn.execute("SELECT item_id, kind, title, obtained_at FROM web_collection_items WHERE pet_id = ? AND (kind != 'shared_memory' OR user_id = ?)",
                              (pet_id, user_id)):
            items.append({"at": parse_dt(r["obtained_at"]), "kind": r["kind"], "title": COLLECTION_TITLE.get(r["kind"], "得到一件纪念"), "detail": r["title"], "ref_id": r["item_id"]})
        for r in conn.execute("SELECT guide_id, title, created_at FROM web_travel_guides WHERE pet_id = ?", (pet_id,)):
            items.append({"at": parse_dt(r["created_at"]), "kind": "guide", "title": f"写了一份攻略：{r['title']}", "detail": None, "ref_id": r["guide_id"]})
    # 新的在前；同一时刻按发生的先后（考试 → 签发证件，出发 → 写攻略），后发生的排在前面
    order = {id(item): index for index, item in enumerate(items)}
    return sorted(items, key=lambda i: (i["at"], order[id(i)]), reverse=True)[:limit]
