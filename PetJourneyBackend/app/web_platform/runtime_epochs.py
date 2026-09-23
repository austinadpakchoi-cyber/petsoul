"""每只宠物的语义版本代数：活动、用途授权、家庭成员、运行归属变了就 +1。

用法：在**改变这些事实的同一个业务事务里**调用 bump_in（或 bump_many_in），不要事后补。
思考、生图、排队回复这些需要时间的事，开始时记下代数，提交前再比一次——中途变了就不作数（见 Versions.stale_fields）。
代数只增不减，进程重启也不回退；表在迁移 0060 建立。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime

from ..utils import iso

EPOCHS = ("runtime_epoch", "activity_epoch", "privacy_epoch", "membership_epoch")


def bump_in(conn: sqlite3.Connection, pet_id: str, field: str, now: datetime) -> None:
    if field not in EPOCHS:
        raise ValueError(f"未知的版本字段：{field}")
    if not pet_id:
        return
    stamp = iso(now)
    conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, stamp))
    conn.execute(f"UPDATE web_entity_runtime SET {field} = {field} + 1, updated_at = ? WHERE pet_id = ?", (stamp, pet_id))


def bump_many_in(conn: sqlite3.Connection, pet_ids: Iterable[str], field: str, now: datetime) -> None:
    for pet_id in pet_ids:
        bump_in(conn, pet_id, field, now)


def versions_in(conn: sqlite3.Connection, pet_id: str) -> "Versions":
    """在**调用方的写事务里**读出这只宠物此刻的全部语义版本（用同一个连接，不另开）。

    为什么必须用同一个连接：在 BEGIN IMMEDIATE 之后调用另开连接的读取函数，读到的是事务开始前的另一份快照，
    而且会和自己的写事务争锁——那样的"复核"既不准也会卡住（验收 CR-C1）。
    """
    from ..schemas.runtime_internal import Versions

    row = conn.execute("SELECT runtime_epoch, activity_epoch, privacy_epoch, membership_epoch FROM web_entity_runtime WHERE pet_id = ?",
                       (pet_id,)).fetchone()
    dna = conn.execute("SELECT version FROM web_pet_dna WHERE pet_id = ?", (pet_id,)).fetchone()
    journey = conn.execute("SELECT itinerary_version FROM web_journeys WHERE pet_id = ? AND lifecycle = 'active'", (pet_id,)).fetchone()
    return Versions(runtime_epoch=int(row["runtime_epoch"]) if row else 0, activity_epoch=int(row["activity_epoch"]) if row else 0,
                    dna_version=int(dna["version"]) if dna else 0, privacy_epoch=int(row["privacy_epoch"]) if row else 0,
                    membership_epoch=int(row["membership_epoch"]) if row else 0,
                    itinerary_version=int(journey["itinerary_version"]) if journey else None)


def household_pets_in(conn: sqlite3.Connection, household_id: str) -> list[str]:
    """这个家里的宠物（成员变化要让全家的宠物都换代）。"""
    return [row["pet_id"] for row in conn.execute("SELECT pet_id FROM web_household_pets WHERE household_id = ?", (household_id,))]
