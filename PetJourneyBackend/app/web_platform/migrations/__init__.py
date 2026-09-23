"""网页新表的显式版本迁移（自动发现，模块作者不改本文件）。

约定：
- 每个迁移一个文件 ``m<NNNN>_<slug>.py``，导出 ``MIGRATION = WebMigration(...)``；
- 编号区间按模块预留（见 docs/contracts/MODULE-MAP.md），避免并行窗口撞号；
- ``apply(conn)`` 只用 ``conn.execute`` 逐条执行（不要 executescript，它会隐式提交，
  破坏“迁移 + 登记”同一事务）；只新增表/列/索引，不改写旧 iOS 表语义；
- 已发布的迁移不可修改，只能追加新编号。
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3
from dataclasses import dataclass
from typing import Callable

from ...storage import JourneyStorage
from ...utils import iso, utcnow

MIGRATION_ID_RE = re.compile(r"^\d{4}_[a-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class WebMigration:
    migration_id: str
    module: str
    description: str
    apply: Callable[[sqlite3.Connection], None]


def discover_migrations() -> list[WebMigration]:
    found: dict[str, WebMigration] = {}
    for info in pkgutil.iter_modules(__path__):
        if not info.name.startswith("m"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        migration = getattr(module, "MIGRATION", None)
        if not isinstance(migration, WebMigration):
            raise RuntimeError(f"{info.name} 没有导出 MIGRATION")
        if not MIGRATION_ID_RE.match(migration.migration_id):
            raise RuntimeError(f"迁移编号格式错误：{migration.migration_id}")
        if info.name != f"m{migration.migration_id}":
            raise RuntimeError(f"文件名 {info.name} 与迁移编号 {migration.migration_id} 不一致")
        prefix = migration.migration_id[:4]
        clash = [m for m in found.values() if m.migration_id[:4] == prefix]
        if clash:
            raise RuntimeError(f"迁移编号重复：{migration.migration_id} / {clash[0].migration_id}")
        found[migration.migration_id] = migration
    return [found[key] for key in sorted(found)]


def apply_web_migrations(storage: JourneyStorage) -> list[str]:
    """按编号顺序执行未登记的迁移；每个迁移与登记在同一事务。返回全部已应用编号。"""
    with storage.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS web_schema_migrations ("
            "migration_id TEXT PRIMARY KEY, module TEXT NOT NULL, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
    for migration in discover_migrations():
        with storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute(
                "SELECT 1 FROM web_schema_migrations WHERE migration_id = ?", (migration.migration_id,)
            ).fetchone()
            if exists:
                continue
            migration.apply(conn)
            conn.execute(
                "INSERT INTO web_schema_migrations (migration_id, module, description, applied_at) VALUES (?, ?, ?, ?)",
                (migration.migration_id, migration.module, migration.description, iso(utcnow())),
            )
    with storage.connect() as conn:
        rows = conn.execute("SELECT migration_id FROM web_schema_migrations ORDER BY migration_id").fetchall()
    return [row["migration_id"] for row in rows]
