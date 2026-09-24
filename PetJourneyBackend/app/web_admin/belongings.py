"""宠物的东西与家里的东西（方案 §3「宠物与世界」「游戏经济：查星币流水、库存与发放记录」）。

**只读、只给状态、数量与时间，不给任何正文。** 下面这些字段一律不取（`tests/test_admin_belongings.py` 逐条断言它们不出现在响应里）：
- 消息正文、明信片与攻略上的文字、图片地址；共同回忆只给数量；
- 驾校的愿望原文、考试的答案与宠物说的话；
- 证件只给种类、名字与编号末 4 位，照护档案的内容不取；
- 驾校留言的原文、练习的答卷、课堂的进度明细不取；口味偏好、吃什么推荐、吃后反馈只给数量，不给内容。

家里的东西（仓库、菜地、偷菜记录）属于**这个家**（多宠家庭共用），不属于某一只宠物，所以单独一页、从用户页进入。
物品名按作物目录取（与集市同一个口径）；目录里没有的照原样显示物品键，不编名字。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt, utcnow
from .social import people

COLLECTION_LIMIT = 50
MOVES_LIMIT = 50
STEALS_LIMIT = 30


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


def _item_label(item_key: str) -> str | None:
    from ..web_farm.service import CROPS
    crop = CROPS.get(item_key)
    return crop.label if crop is not None else None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row] | None:
    """表还不在（这个库没迁移到那一步）就返回 None：查不了 ≠ 没有。"""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return None


class AdminBelongings:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    # ---- 宠物 ----
    def pet(self, pet_id: str, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or utcnow()
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM web_pet_profiles WHERE pet_id = ?", (pet_id,)).fetchone() is None:
                return None
            return {
                "pet_id": pet_id,
                "collection": self._collection(conn, pet_id),
                "credentials": self._credentials(conn, pet_id),
                "passport": self._passport(conn, pet_id),
                "driving": self._driving(conn, pet_id),
                "messages": self._messages(conn, pet_id, now),
                "character": self._character(conn, pet_id),
                "friends": self._friends(conn, pet_id),
                "school": self._school(conn, pet_id),
                "media": self._media(conn, pet_id),
                "food": self._food(conn, pet_id),
                "privacy_note": "这里只有状态、数量与时间：消息正文、明信片与攻略上的字、驾校的愿望原文与留言、考试答案、"
                                "照护档案、口味偏好的内容都不在后台显示。",
            }

    def _collection(self, conn, pet_id: str) -> dict[str, Any] | None:
        counts = _rows(conn, "SELECT kind, COUNT(*) AS n FROM web_collection_items WHERE pet_id = ? GROUP BY kind", (pet_id,))
        if counts is None:
            return None
        items = conn.execute(
            "SELECT item_id, kind, city, image_status, obtained_at, consumed_at, tradable FROM web_collection_items "
            "WHERE pet_id = ? AND kind != 'shared_memory' ORDER BY obtained_at DESC LIMIT ?", (pet_id, COLLECTION_LIMIT)).fetchall()
        return {"counts": {row["kind"]: int(row["n"]) for row in counts},
                "items": [{"item_id": r["item_id"], "kind": r["kind"], "city": r["city"], "image_status": r["image_status"],
                           "obtained_at": _dt(r["obtained_at"]), "consumed_at": _dt(r["consumed_at"]), "tradable": bool(r["tradable"])}
                          for r in items]}

    def _credentials(self, conn, pet_id: str) -> list[dict] | None:
        rows = _rows(conn, "SELECT kind, title, number, issued_at FROM web_credentials WHERE pet_id = ? ORDER BY issued_at", (pet_id,))
        if rows is None:
            return None
        return [{"kind": r["kind"], "title": r["title"], "number_tail": (r["number"] or "")[-4:] or None,
                 "issued_at": _dt(r["issued_at"])} for r in rows]

    def _passport(self, conn, pet_id: str) -> dict[str, Any] | None:
        rows = _rows(conn, "SELECT city, title, stamped_at FROM web_passport_stamps WHERE pet_id = ? ORDER BY stamped_at DESC", (pet_id,))
        if rows is None:
            return None
        return {"count": len(rows), "recent": [{"city": r["city"], "title": r["title"], "stamped_at": _dt(r["stamped_at"])}
                                               for r in rows[:10]]}

    def _driving(self, conn, pet_id: str) -> dict[str, Any] | None:
        rows = _rows(conn, "SELECT stage, enrolled_at, theory_passed_at, licensed_at, needs_practice, last_study_at "
                           "FROM web_driving WHERE pet_id = ?", (pet_id,))
        if rows is None:
            return None
        if not rows:
            return {"stage": None, "note": "没有学车记录。"}
        row = rows[0]
        stage = row["stage"]
        if stage == "licensed" and not _rows(conn, "SELECT 1 FROM web_credentials WHERE pet_id = ? AND kind = 'driver_license' LIMIT 1",
                                             (pet_id,)):
            stage = "license_pending"  # 记成考过了、却还没有驾驶证（旧版留下的）：与 web_driving/service.py 的 _stage_in 同一个判断
        exams = _rows(conn, "SELECT part, attempt_no, score, max_score, passed, taken_at FROM web_exam_attempts "
                            "WHERE pet_id = ? ORDER BY taken_at DESC LIMIT 10", (pet_id,)) or []
        return {"stage": stage, "enrolled_at": _dt(row["enrolled_at"]), "theory_passed_at": _dt(row["theory_passed_at"]),
                "licensed_at": _dt(row["licensed_at"]), "needs_practice": bool(row["needs_practice"]),
                "last_study_at": _dt(row["last_study_at"]),
                "exams": [{"part": e["part"], "attempt_no": e["attempt_no"], "score": e["score"], "max_score": e["max_score"],
                           "passed": bool(e["passed"]), "taken_at": _dt(e["taken_at"])} for e in exams]}

    def _messages(self, conn, pet_id: str, now: datetime) -> dict[str, Any] | None:
        by_sender = _rows(conn, "SELECT sender, COUNT(*) AS n, MAX(created_at) AS last_at FROM web_messages WHERE pet_id = ? GROUP BY sender",
                          (pet_id,))
        if by_sender is None:
            return None
        photos = conn.execute("SELECT photo_status, COUNT(*) AS n FROM web_messages WHERE pet_id = ? AND photo_status IS NOT NULL "
                              "GROUP BY photo_status", (pet_id,)).fetchall()
        pending = _rows(conn, "SELECT due_at, reason, outcome, created_at FROM web_pending_replies WHERE pet_id = ? "
                              "ORDER BY created_at DESC LIMIT 10", (pet_id,)) or []
        return {"by_sender": {r["sender"]: {"count": int(r["n"]), "last_at": _dt(r["last_at"])} for r in by_sender},
                "photos": {r["photo_status"]: int(r["n"]) for r in photos},
                # 主人发来消息后 TA 什么时候回：到期时间、为什么晚一点、结果（不含任何一方的正文）
                "replies": [{"due_at": _dt(r["due_at"]), "reason": r["reason"], "outcome": r["outcome"],
                             "overdue": r["outcome"] is None and bool(r["due_at"]) and parse_dt(r["due_at"]) < now,
                             "created_at": _dt(r["created_at"])} for r in pending]}

    def _character(self, conn, pet_id: str) -> dict[str, Any] | None:
        takes = _rows(conn, "SELECT pose, state, reason, task_id, revision, updated_at FROM web_pet_characters WHERE pet_id = ? "
                            "ORDER BY updated_at DESC LIMIT 20", (pet_id,))
        if takes is None:
            return None
        active = _rows(conn, "SELECT set_id, revision, published_at FROM web_pet_character_active WHERE pet_id = ?", (pet_id,)) or []
        return {"active": ({"set_id": active[0]["set_id"], "revision": active[0]["revision"], "published_at": _dt(active[0]["published_at"])}
                           if active else None),
                "takes": [{"pose": t["pose"], "state": t["state"], "reason": t["reason"], "task_id": t["task_id"],
                           "revision": t["revision"], "updated_at": _dt(t["updated_at"])} for t in takes],
                "id_photo": self._id_photo(conn, pet_id)}

    def _id_photo(self, conn, pet_id: str) -> dict[str, Any] | None:
        """证件照（web_character/id_photo.py）：每一版的状态与没做成的原因、现在生效的是哪一版。只给状态，不给任何文件路径与图片。"""
        takes = _rows(conn, "SELECT revision, state, reason, task_id, updated_at FROM web_pet_id_photos WHERE pet_id = ? "
                            "ORDER BY revision DESC LIMIT 10", (pet_id,))
        if takes is None:
            return None
        active = _rows(conn, "SELECT revision, published_at FROM web_pet_id_photo_active WHERE pet_id = ?", (pet_id,)) or []
        return {"active": {"revision": active[0]["revision"], "published_at": _dt(active[0]["published_at"])} if active else None,
                "takes": [{"revision": t["revision"], "state": t["state"], "reason": t["reason"], "task_id": t["task_id"],
                           "updated_at": _dt(t["updated_at"])} for t in takes]}

    # ---- 家 ----
    def homes_of_user(self, user_id: str) -> list[dict]:
        """这位用户所在家庭的家（用户页用来链到「家里的东西」）。按家庭成员算，不按 web_homes.user_id（那只是建家的人）。"""
        with self.storage.connect() as conn:
            rows = _rows(conn, "SELECT h.home_id, h.household_id, h.activated_at FROM web_homes h "
                               "JOIN web_household_members m ON m.household_id = h.household_id WHERE m.user_id = ? "
                               "ORDER BY h.created_at", (user_id,)) or []
        return [{"home_id": r["home_id"], "household_id": r["household_id"], "activated_at": _dt(r["activated_at"])} for r in rows]

    def home(self, home_id: str, *, pantry: bool, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or utcnow()
        with self.storage.connect() as conn:
            home = conn.execute("SELECT home_id, household_id, created_at, activated_at FROM web_homes WHERE home_id = ?",
                                (home_id,)).fetchone()
            if home is None:
                return None
            steals = self._steals(conn, home_id, home["household_id"])
            pantry_rows = self._pantry(conn, home_id) if pantry else None
            actors = [m["actor_user_id"] for m in pantry_rows["moves"]] if pantry_rows else []
            if steals:
                actors += [x["thief_user_id"] for x in steals["from_this_home"] + steals["by_this_household"]]
            # 名字在 pets 表（与 directory.py 同一个口径）
            pets = conn.execute("SELECT hp.pet_id, pt.name FROM web_household_pets hp JOIN pets pt ON pt.pet_id = hp.pet_id "
                                "WHERE hp.household_id = ? ORDER BY pt.name", (home["household_id"],)).fetchall()
            return {
                "home_id": home_id, "household_id": home["household_id"],
                "created_at": _dt(home["created_at"]), "activated_at": _dt(home["activated_at"]),
                "pets": [{"pet_id": p["pet_id"], "name": p["name"]} for p in pets],
                "pantry": pantry_rows,
                "orders": self._orders(conn, home_id) if pantry else None,
                "farm": self._farm(conn, home_id, now),
                "steals": steals,
                "people": people(conn, actors),
                "note": "仓库属于这个家（家里的宠物共用）。星币不在这里，在每只宠物自己的游戏账本里。",
            }

    def _pantry(self, conn, home_id: str) -> dict[str, Any] | None:
        stock = _rows(conn, "SELECT item_key, qty, updated_at FROM web_home_inventory WHERE home_id = ? AND qty > 0 ORDER BY item_key",
                      (home_id,))
        if stock is None:
            return None
        moves = conn.execute("SELECT item_key, delta, reason, actor_user_id, pet_id, created_at FROM web_home_inventory_moves "
                             "WHERE home_id = ? ORDER BY created_at DESC LIMIT ?", (home_id, MOVES_LIMIT)).fetchall()
        return {"stock": [{"item_key": r["item_key"], "item_label": _item_label(r["item_key"]), "qty": int(r["qty"]),
                           "updated_at": _dt(r["updated_at"])} for r in stock],
                # 变动原因是系统写的说明（「收获豌豆」「卖给杂货铺」），不是玩家写的字
                "moves": [{"item_key": m["item_key"], "item_label": _item_label(m["item_key"]), "delta": int(m["delta"]),
                           "reason": m["reason"], "actor_user_id": m["actor_user_id"], "pet_id": m["pet_id"],
                           "created_at": _dt(m["created_at"])} for m in moves]}

    def _farm(self, conn, home_id: str, now: datetime) -> dict[str, Any] | None:
        plots = _rows(conn, "SELECT slot, crop_key, planted_at, ripe_at, stolen_units, harvested_at FROM web_farm_plots "
                            "WHERE home_id = ? ORDER BY slot", (home_id,))
        if plots is None:
            return None
        patrol = _rows(conn, "SELECT started_at, until FROM web_farm_patrols WHERE home_id = ?", (home_id,)) or []

        def state(row) -> str:
            if not row["crop_key"]:
                return "empty"
            if row["harvested_at"]:
                return "harvested"
            ripe = _dt(row["ripe_at"])
            return "ripe" if ripe is not None and ripe <= now else "growing"

        return {"plots": [{"slot": p["slot"], "crop_key": p["crop_key"], "crop_label": _item_label(p["crop_key"]) if p["crop_key"] else None,
                           "state": state(p), "planted_at": _dt(p["planted_at"]), "ripe_at": _dt(p["ripe_at"]),
                           "stolen_units": int(p["stolen_units"] or 0), "harvested_at": _dt(p["harvested_at"])} for p in plots],
                "patrol": ({"started_at": _dt(patrol[0]["started_at"]), "until": _dt(patrol[0]["until"]),
                            "active": bool(patrol[0]["until"]) and parse_dt(patrol[0]["until"]) > now} if patrol else None)}

    def _steals(self, conn, home_id: str, household_id: str | None) -> dict[str, Any] | None:
        stolen = _rows(conn, "SELECT thief_user_id, thief_household_id, units, created_at FROM web_farm_steals "
                             "WHERE victim_home_id = ? ORDER BY created_at DESC LIMIT ?", (home_id, STEALS_LIMIT))
        if stolen is None:
            return None
        took = conn.execute("SELECT victim_home_id, thief_user_id, units, created_at FROM web_farm_steals WHERE thief_household_id = ? "
                            "ORDER BY created_at DESC LIMIT ?", (household_id, STEALS_LIMIT)).fetchall() if household_id else []
        return {"from_this_home": [{"thief_user_id": r["thief_user_id"], "thief_household_id": r["thief_household_id"],
                                    "units": int(r["units"]), "created_at": _dt(r["created_at"])} for r in stolen],
                "by_this_household": [{"victim_home_id": r["victim_home_id"], "thief_user_id": r["thief_user_id"],
                                       "units": int(r["units"]), "created_at": _dt(r["created_at"])} for r in took]}

    # ---- 第八批：宠物的朋友、驾校课堂、同行影音、口味 ----
    def _friends(self, conn, pet_id: str) -> list[dict] | None:
        rows = _rows(conn, "SELECT friend_id, friend_kind, friend_name, meet_count, first_met_at, last_met_at, last_place FROM web_pet_friends "
                           "WHERE pet_id = ? ORDER BY last_met_at DESC LIMIT 30", (pet_id,))
        if rows is None:
            return None
        return [{"friend_id": r["friend_id"], "friend_kind": r["friend_kind"], "friend_name": r["friend_name"], "meet_count": int(r["meet_count"] or 0),
                 "first_met_at": _dt(r["first_met_at"]), "last_met_at": _dt(r["last_met_at"]), "last_place": r["last_place"]} for r in rows]

    def _school(self, conn, pet_id: str) -> dict[str, Any] | None:
        subjects = _rows(conn, "SELECT subject, round_no, fails_in_round, cooldown_until, passed_at, passed_score, practice_count "
                               "FROM web_school_subjects WHERE pet_id = ? ORDER BY subject", (pet_id,))
        if subjects is None:
            return None
        sessions = _rows(conn, "SELECT subject, mode, state, passed, score, created_at, settled_at FROM web_school_sessions WHERE pet_id = ? "
                               "ORDER BY created_at DESC LIMIT 10", (pet_id,)) or []
        notes = _rows(conn, "SELECT COUNT(*) AS n, SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered "
                            "FROM web_driving_notes WHERE pet_id = ?", (pet_id,))
        practice = _rows(conn, "SELECT COUNT(*) AS n FROM web_driving_practice WHERE pet_id = ?", (pet_id,))
        from ..web_driving.curriculum import META

        def title(code: str) -> str | None:
            return (META.get(code) or {}).get("title")

        return {
            "subjects": [{"subject": r["subject"], "title": title(r["subject"]), "round_no": r["round_no"], "fails_in_round": r["fails_in_round"],
                          "cooldown_until": _dt(r["cooldown_until"]), "passed_at": _dt(r["passed_at"]), "passed_score": r["passed_score"],
                          "practice_count": int(r["practice_count"] or 0)} for r in subjects],
            "sessions": [{"subject": r["subject"], "title": title(r["subject"]), "mode": r["mode"], "state": r["state"],
                          "passed": None if r["passed"] is None else bool(r["passed"]), "score": r["score"],
                          "created_at": _dt(r["created_at"]), "settled_at": _dt(r["settled_at"])} for r in sessions],
            # 主人给驾校留的话：只给条数与送到没有，不给原文
            "notes": ({"count": int(notes[0]["n"] or 0), "delivered": int(notes[0]["delivered"] or 0)} if notes else None),
            "practice_rounds": int(practice[0]["n"]) if practice else None,
        }

    def _media(self, conn, pet_id: str) -> dict[str, Any] | None:
        sessions = _rows(conn, "SELECT session_id, state, updated_at FROM web_media_sessions WHERE pet_id = ? ORDER BY updated_at DESC", (pet_id,))
        if sessions is None:
            return None
        ids = [r["session_id"] for r in sessions[:10]]
        joined = (conn.execute("SELECT session_id, mode, counted_ms FROM web_media_participation WHERE session_id IN ("
                               + ",".join("?" for _ in ids) + ")", ids).fetchall() if ids else [])
        by_session: dict[str, list] = {}
        for row in joined:
            by_session.setdefault(row["session_id"], []).append(row)
        return {"count": len(sessions),
                "recent": [{"session_id": r["session_id"], "state": r["state"], "updated_at": _dt(r["updated_at"]),
                            "devices": len(by_session.get(r["session_id"], [])),
                            "modes": sorted({x["mode"] for x in by_session.get(r["session_id"], [])}),
                            "minutes": round(sum(int(x["counted_ms"] or 0) for x in by_session.get(r["session_id"], [])) / 60000, 1)}
                           for r in sessions[:10]]}

    def _food(self, conn, pet_id: str) -> dict[str, Any] | None:
        """口味偏好、推荐与反馈：只给数量（按主体与方式分），不给任何一条的内容。"""
        prefs = _rows(conn, "SELECT subject, COUNT(*) AS n FROM web_food_preferences WHERE pet_id = ? GROUP BY subject", (pet_id,))
        if prefs is None:
            return None
        recs = _rows(conn, "SELECT mode, COUNT(*) AS n FROM web_food_recommendations WHERE pet_id = ? GROUP BY mode", (pet_id,)) or []
        feedback = _rows(conn, "SELECT COUNT(*) AS n FROM web_food_feedback f JOIN web_food_recommendations r "
                               "ON r.recommendation_id = f.recommendation_id WHERE r.pet_id = ?", (pet_id,))
        return {"preferences": {r["subject"]: int(r["n"]) for r in prefs}, "recommendations": {r["mode"]: int(r["n"]) for r in recs},
                "feedback": int(feedback[0]["n"]) if feedback else None}

    # ---- 第八批：家里的居民订单（游戏资产，与仓库同一条权限）----
    def _orders(self, conn, home_id: str) -> list[dict] | None:
        rows = _rows(conn, "SELECT order_id, day, slot, resident, item_key, qty, reward, fulfilled_at FROM web_resident_orders WHERE home_id = ? "
                           "ORDER BY day DESC, slot LIMIT 30", (home_id,))
        if rows is None:
            return None
        return [{"order_id": r["order_id"], "day": r["day"], "slot": r["slot"], "resident": r["resident"], "item_key": r["item_key"],
                 "item_label": _item_label(r["item_key"]), "qty": int(r["qty"]), "reward": int(r["reward"]),
                 "fulfilled_at": _dt(r["fulfilled_at"])} for r in rows]
