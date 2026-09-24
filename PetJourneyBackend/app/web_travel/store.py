"""旅行心愿的持久层（TRV-03，A 是唯一写实现者）。写函数都在**调用方的写事务里**执行（`*_in(conn, …)`，合同 0.1）。

表名与键照 TRV-00 合同 11.1／11.6（Q 按表查痕迹，改名先回报 I）：
  - `web_travel_wishes`：一个心愿一行，`wish_id` 连续身份、`wish_revision` 单调递增。`(pet_id, trigger_event_id)` 唯一＝
    同一有效事件重复投递不新增心愿（T02）；**每只宠物同时只有一个进行中的心愿**（active／ready 上的部分唯一索引）。
  - `web_travel_research_receipts`：研究回执，**一次发送尝试一行**，`operation_id` 与额度预占同号。
    先落 `intent` 再发送，响应先落 `answered` 再发布——进程在任何一步被杀，恢复时都读得到已经发生了什么（方案 §11.2）。
    `plan_id`／`plan_revision` 指向它产出的**那一版**计划（发布前 plan_revision 为空）。
  - `web_travel_facts`：逐条事实，带来源、抓取／观测／适用时间与核验结论；时间没有就是空，不伪造。
  - `web_travel_plans`：计划修订（`plan_id` 稳定、`plan_revision` 每次研究结果落地 +1）；旅程不存在时 `journey_id` 为空。
  - `web_travel_journals`：手账修订（`journal_id` 稳定、`journal_revision` 递增），绑定计划的那一版；排版数据与图片分开存。

表结构只在 `app/web_platform/migrations/m1700_travel_wish.py` 一处（冻结快照，号由 I 分配：1700–1799 段）。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .model import OPEN_STATES, VersionConflict


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    return default if text is None else json.loads(text)


def _insert(conn: sqlite3.Connection, table: str, row: dict[str, Any], *, ignore: bool = False) -> bool:
    """`ignore=True` 只跳过**重复**（主键、唯一、部分唯一索引），不跳过 CHECK／NOT NULL 违例——那些照常报错。
    不用 `INSERT OR IGNORE`：它连 CHECK 违例一起吞，词表一漂移数据就无声丢失（m1702 那次在旧库上实测：冲突事实被悄悄丢掉）。"""
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    skip = " ON CONFLICT DO NOTHING" if ignore else ""
    return conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks}){skip}", tuple(row.values())).rowcount == 1


# ---- 心愿 ----
def insert_wish_in(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    """插入一条心愿。触发事件重复或该宠物已有进行中的心愿时不插（返回 False），由调用方读回已有那条。"""
    return _insert(conn, "web_travel_wishes", row, ignore=True)


def wish_in(conn: sqlite3.Connection, wish_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_wishes WHERE wish_id = ?", (wish_id,)).fetchone()


def wish_by_trigger_in(conn: sqlite3.Connection, pet_id: str, trigger_event_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_wishes WHERE pet_id = ? AND trigger_event_id = ?", (pet_id, trigger_event_id)).fetchone()


def open_wish_in(conn: sqlite3.Connection, pet_id: str) -> sqlite3.Row | None:
    marks = ", ".join("?" for _ in OPEN_STATES)
    return conn.execute(f"SELECT * FROM web_travel_wishes WHERE pet_id = ? AND status IN ({marks})", (pet_id, *OPEN_STATES)).fetchone()


def latest_wish_in(conn: sqlite3.Connection, pet_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_wishes WHERE pet_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (pet_id,)).fetchone()


def update_wish_in(conn: sqlite3.Connection, wish_id: str, expected_revision: int, now: str, **fields: Any) -> int:
    """带版本条件更新，成功则 `wish_revision` +1 并返回新值；没命中抛 VersionConflict（调用方整体回滚）。"""
    assignments = "".join(f"{name} = ?, " for name in fields)
    updated = conn.execute(
        f"UPDATE web_travel_wishes SET {assignments}wish_revision = wish_revision + 1, updated_at = ? WHERE wish_id = ? AND wish_revision = ?",
        (*fields.values(), now, wish_id, int(expected_revision))).rowcount
    if updated != 1:
        raise VersionConflict(f"wish {wish_id} is not at revision {expected_revision}")
    return int(expected_revision) + 1


# ---- 按宠物的「上次考虑」（没有心愿时也要有：合同 17.1、B 核出）----
def note_considered_in(conn: sqlite3.Connection, pet_id: str, considered_at: str, now: str) -> None:
    """只往后走：迟到的旧时刻不把它拨回去（MAX）。"""
    conn.execute("INSERT INTO web_travel_considerations (pet_id, last_considered_at, updated_at) VALUES (?, ?, ?) "
                 "ON CONFLICT(pet_id) DO UPDATE SET last_considered_at = MAX(last_considered_at, excluded.last_considered_at), "
                 "updated_at = excluded.updated_at", (pet_id, considered_at, now))


def last_considered_in(conn: sqlite3.Connection, pet_id: str) -> str | None:
    row = conn.execute("SELECT last_considered_at FROM web_travel_considerations WHERE pet_id = ?", (pet_id,)).fetchone()
    return None if row is None else row["last_considered_at"]


# ---- 研究回执 ----
def insert_receipt_in(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    _insert(conn, "web_travel_research_receipts", row)


def update_receipt_in(conn: sqlite3.Connection, operation_id: str, now: str, *, only_from: tuple[str, ...] = (), **fields: Any) -> bool:
    """更新一条回执；`only_from` 限定只从这些状态改（例如只把 intent 改成 answered），迟到的写不会覆盖更靠后的状态。"""
    assignments = "".join(f"{name} = ?, " for name in fields)
    guard, extra = ("", ()) if not only_from else (f" AND status IN ({', '.join('?' for _ in only_from)})", only_from)
    return conn.execute(f"UPDATE web_travel_research_receipts SET {assignments}updated_at = ? WHERE operation_id = ?{guard}",
                        (*fields.values(), now, operation_id, *extra)).rowcount == 1


def receipt_in(conn: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_research_receipts WHERE operation_id = ?", (operation_id,)).fetchone()


def receipts_for_round_in(conn: sqlite3.Connection, wish_id: str, round_: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM web_travel_research_receipts WHERE wish_id = ? AND round = ? ORDER BY attempt_no, rowid",
                        (wish_id, int(round_))).fetchall()


# ---- 事实与计划 ----
def insert_facts_in(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        _insert(conn, "web_travel_facts", row, ignore=True)


def facts_for_operation_in(conn: sqlite3.Connection, operation_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM web_travel_facts WHERE operation_id = ? ORDER BY fact_id", (operation_id,)).fetchall()


def insert_plan_in(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    _insert(conn, "web_travel_plans", row)


def plan_in(conn: sqlite3.Connection, plan_id: str, plan_revision: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_plans WHERE plan_id = ? AND plan_revision = ?", (plan_id, int(plan_revision))).fetchone()


def next_plan_revision_in(conn: sqlite3.Connection, plan_id: str) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(plan_revision), 0) + 1 FROM web_travel_plans WHERE plan_id = ?", (plan_id,)).fetchone()[0])


def link_plan_in(conn: sqlite3.Connection, plan_id: str, plan_revision: int, journey_id: str) -> bool:
    """计划的那一版记下真旅程；已经记着同一个旅程时幂等，记着别的旅程则不改（返回 False）。"""
    return conn.execute("UPDATE web_travel_plans SET journey_id = ? WHERE plan_id = ? AND plan_revision = ? "
                        "AND (journey_id IS NULL OR journey_id = ?)", (journey_id, plan_id, int(plan_revision), journey_id)).rowcount == 1


def journal_for_plan_in(conn: sqlite3.Connection, plan_id: str, plan_revision: int) -> sqlite3.Row | None:
    """计划那一版的计划阶段手账（最新一次修订）。"""
    return conn.execute("SELECT * FROM web_travel_journals WHERE plan_id = ? AND plan_revision = ? AND phase = 'plan' "
                        "ORDER BY journal_revision DESC LIMIT 1", (plan_id, int(plan_revision))).fetchone()


def plan_for_journey_in(conn: sqlite3.Connection, journey_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM web_travel_plans WHERE journey_id = ? ORDER BY plan_revision DESC LIMIT 1", (journey_id,)).fetchone()
