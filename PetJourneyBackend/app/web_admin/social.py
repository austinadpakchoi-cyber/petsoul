"""社交与举报关联（方案 §3「社区审核与客服」：处理举报时要看得到前因后果）。只读。

**给什么、不给什么**：
- 动态与评论是玩家自己发到公开范围的内容：公开的、以及被下架的（下架前是公开的，审核要看），只给**前 40 个字**做摘要；
  **仅关注者可见的动态不给正文**，只给时间与状态。私聊不在这里（它不是社交内容，也不在任何默认角色的权限里）。
- 拉黑、关注、点赞是关系事实，不含正文；处理骚扰类举报要用（「举报人是不是早就把对方拉黑了」）。
- 举报队列的「关系上下文」只给计数与是否拉黑，不给任何一方的正文。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt

EXCERPT = 40
RECENT = 20


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


def _excerpt(text: str | None, visibility: str | None) -> str | None:
    """只给公开范围里的内容做摘要；仅关注者可见的一律不给。"""
    if not text or visibility not in ("public", "removed"):
        return None
    clean = " ".join(text.split())
    return clean if len(clean) <= EXCERPT else clean[:EXCERPT] + "…"


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row] | None:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return None  # 表还不在：查不了 ≠ 没有


def people(conn: sqlite3.Connection, user_ids) -> dict[str, dict[str, Any]]:
    """玩家编号 → 用户名与显示名（页面上显示名字，不只给编号）。查不到的不在结果里。"""
    ids = sorted({uid for uid in user_ids if uid})
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT u.user_id, u.display_name, a.username FROM users u LEFT JOIN web_accounts a ON a.user_id = u.user_id "
        f"WHERE u.user_id IN ({','.join('?' for _ in ids)})", ids).fetchall()
    return {r["user_id"]: {"username": r["username"], "display_name": r["display_name"]} for r in rows}


class AdminSocial:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def user(self, user_id: str) -> dict[str, Any]:
        with self.storage.connect() as conn:
            posts = _rows(conn, "SELECT post_id, author_pet_id, text, visibility, created_at, removed_at FROM web_posts WHERE user_id = ? "
                                "ORDER BY created_at DESC", (user_id,))
            comments = _rows(conn, "SELECT comment_id, post_id, actor_kind, text, created_at, removed_at FROM web_comments "
                                   "WHERE user_id = ? AND actor_kind != 'npc' ORDER BY created_at DESC", (user_id,))
            blocked = _rows(conn, "SELECT blocked_user_id AS other, created_at FROM web_blocks WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            blocked_by = _rows(conn, "SELECT user_id AS other, created_at FROM web_blocks WHERE blocked_user_id = ? ORDER BY created_at DESC", (user_id,))
            pets = [r["pet_id"] for r in conn.execute("SELECT hp.pet_id FROM web_household_pets hp JOIN web_household_members m "
                                                       "ON m.household_id = hp.household_id WHERE m.user_id = ? AND m.status = 'active'",
                                                       (user_id,))]
            marks = ",".join("?" for _ in pets)
            following = (_rows(conn, f"SELECT follower_pet_id, followee_pet_id, created_at FROM web_follows WHERE follower_pet_id IN ({marks})", tuple(pets))
                         if pets else [])
            followers = (_rows(conn, f"SELECT follower_pet_id, followee_pet_id, created_at FROM web_follows WHERE followee_pet_id IN ({marks})", tuple(pets))
                         if pets else [])
            reactions_given = _rows(conn, "SELECT COUNT(*) AS n FROM web_reactions WHERE user_id = ?", (user_id,))
            reactions_received = _rows(conn, "SELECT COUNT(*) AS n FROM web_reactions r JOIN web_posts p ON p.post_id = r.post_id WHERE p.user_id = ?",
                                       (user_id,))
            filed = _rows(conn, "SELECT COUNT(*) AS n FROM web_reports WHERE reporter_user_id = ?", (user_id,))
            against = _rows(conn, "SELECT COUNT(*) AS n FROM web_reports r WHERE "
                                  "(r.target_kind = 'post' AND r.target_id IN (SELECT post_id FROM web_posts WHERE user_id = ?)) OR "
                                  "(r.target_kind = 'comment' AND r.target_id IN (SELECT comment_id FROM web_comments WHERE user_id = ?))",
                            (user_id, user_id))
            reported_targets = {(r["target_kind"], r["target_id"]) for r in conn.execute("SELECT target_kind, target_id FROM web_reports")}
            names = people(conn, [r["other"] for r in (blocked or [])] + [r["other"] for r in (blocked_by or [])])
            pet_names = {r["pet_id"]: r["name"] for r in conn.execute("SELECT pet_id, name FROM pets")} if (following or followers) else {}

        def count(rows) -> int | None:
            return None if rows is None else int(rows[0]["n"])

        return {
            "user_id": user_id,
            "posts": None if posts is None else {
                "by_visibility": _tally(posts, "visibility"),
                "recent": [{"post_id": r["post_id"], "author_pet_id": r["author_pet_id"], "visibility": r["visibility"],
                            "excerpt": _excerpt(r["text"], r["visibility"]), "created_at": _dt(r["created_at"]),
                            "removed_at": _dt(r["removed_at"]), "reported": ("post", r["post_id"]) in reported_targets} for r in posts[:RECENT]]},
            "comments": None if comments is None else {
                "total": len(comments), "removed": sum(1 for r in comments if r["removed_at"]),
                "recent": [{"comment_id": r["comment_id"], "post_id": r["post_id"], "actor_kind": r["actor_kind"],
                            "excerpt": _excerpt(r["text"], "removed" if r["removed_at"] else "public"), "created_at": _dt(r["created_at"]),
                            "removed_at": _dt(r["removed_at"]), "reported": ("comment", r["comment_id"]) in reported_targets}
                           for r in comments[:RECENT]]},
            "blocks": None if blocked is None else {
                "blocked": [{"user_id": r["other"], "name": names.get(r["other"]), "created_at": _dt(r["created_at"])} for r in blocked],
                "blocked_by": [{"user_id": r["other"], "name": names.get(r["other"]), "created_at": _dt(r["created_at"])} for r in (blocked_by or [])]},
            "follows": None if following is None else {
                "following": [{"pet_id": r["followee_pet_id"], "pet_name": pet_names.get(r["followee_pet_id"]), "created_at": _dt(r["created_at"])}
                              for r in following],
                "followers": [{"pet_id": r["follower_pet_id"], "pet_name": pet_names.get(r["follower_pet_id"]), "created_at": _dt(r["created_at"])}
                              for r in (followers or [])]},
            "reactions": {"given": count(reactions_given), "received": count(reactions_received)},
            "reports": {"filed": count(filed), "against": count(against)},
            "privacy_note": "动态与评论只给公开范围里的前 40 个字；仅关注者可见的动态不给内容。私聊不在这里。",
        }

    def report_context(self, conn: sqlite3.Connection, reporter_user_id: str, target_kind: str, target_id: str) -> dict[str, Any] | None:
        """举报队列里的一条：被举报的是谁、两人之间有没有拉黑、这个人被举报过几次、被下架过几次、举报人一共举报过几次。只给计数。"""
        table, key = ("web_posts", "post_id") if target_kind == "post" else ("web_comments", "comment_id")
        try:
            author = conn.execute(f"SELECT user_id FROM {table} WHERE {key} = ?", (target_id,)).fetchone()
            if author is None or not author["user_id"]:
                return None
            author_id = author["user_id"]
            blocked = lambda a, b: conn.execute("SELECT 1 FROM web_blocks WHERE user_id = ? AND blocked_user_id = ?", (a, b)).fetchone() is not None
            against = conn.execute(
                "SELECT COUNT(DISTINCT r.report_id) FROM web_reports r WHERE "
                "(r.target_kind = 'post' AND r.target_id IN (SELECT post_id FROM web_posts WHERE user_id = ?)) OR "
                "(r.target_kind = 'comment' AND r.target_id IN (SELECT comment_id FROM web_comments WHERE user_id = ?))",
                (author_id, author_id)).fetchone()[0]
            removed = (conn.execute("SELECT COUNT(*) FROM web_posts WHERE user_id = ? AND visibility = 'removed'", (author_id,)).fetchone()[0]
                       + conn.execute("SELECT COUNT(*) FROM web_comments WHERE user_id = ? AND removed_at IS NOT NULL", (author_id,)).fetchone()[0])
            filed = conn.execute("SELECT COUNT(*) FROM web_reports WHERE reporter_user_id = ?", (reporter_user_id,)).fetchone()[0]
        except sqlite3.OperationalError:
            return None
        return {"author_user_id": author_id, "author_name": people(conn, [author_id]).get(author_id),
                "reporter_blocked_author": blocked(reporter_user_id, author_id), "author_blocked_reporter": blocked(author_id, reporter_user_id),
                "reports_against_author": int(against), "author_removed": int(removed), "reporter_filed": int(filed),
                "same_person": author_id == reporter_user_id}


def _tally(rows, column: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row[column]] = out.get(row[column], 0) + 1
    return out
