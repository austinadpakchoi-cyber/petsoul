"""1540：平台调用的价格表（只追加）。

方案 §3「平台 API 成本：分别显示估算费用、账单确认费用与未确认费用；人民币/美元与星币完全分账；
无价格时费用未知」。估算需要单价，单价只能由员工带着**来源**与**生效时间**录入——代码不带任何默认价格。

价格历史就是算账的依据，所以这张表**只追加**：
- 改价＝录一条生效时间更晚的新价；
- 录错了＝把那条标成作废（留作废人、时间与原因），行本身不删；
- 数据库触发器守着：除「有效 → 作废」这一种更新（且只能写作废三列）以外，任何 UPDATE 与 DELETE 都会失败。
  同一个 SQLite 文件里的触发器不是防篡改证明（有文件写权限的人可以绕开），它防的是代码里的误写。

单价以「百万分之一货币单位」存整数，不用浮点。计量单位只有 `call_unit`（额度账按调用次数计，没有 token 数）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration

_IMMUTABLE = ("price_id", "provider", "purpose", "currency", "unit_price_micros", "unit", "effective_from",
              "source_note", "created_by", "created_at", "operation_id")


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_provider_prices (
            price_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            purpose TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency IN ('CNY', 'USD')),
            unit_price_micros INTEGER NOT NULL CHECK (unit_price_micros >= 0),
            unit TEXT NOT NULL CHECK (unit = 'call_unit'),
            effective_from TEXT NOT NULL,
            source_note TEXT NOT NULL,
            model_note TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            retired_by TEXT,
            retired_at TEXT,
            retired_reason TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_provider_prices_lookup ON admin_provider_prices (provider, purpose, effective_from)")
    unchanged = " AND ".join(f"NEW.{column} = OLD.{column}" for column in _IMMUTABLE)
    conn.execute(
        "CREATE TRIGGER admin_provider_prices_only_retire BEFORE UPDATE ON admin_provider_prices "
        f"WHEN NOT (OLD.status = 'active' AND NEW.status = 'retired' AND {unchanged} "
        "AND NEW.model_note IS OLD.model_note "
        "AND NEW.retired_by IS NOT NULL AND NEW.retired_at IS NOT NULL AND NEW.retired_reason IS NOT NULL) "
        "BEGIN SELECT RAISE(ABORT, 'admin_provider_prices: rows are append-only; only active -> retired is allowed'); END"
    )
    conn.execute(
        "CREATE TRIGGER admin_provider_prices_no_delete BEFORE DELETE ON admin_provider_prices "
        "BEGIN SELECT RAISE(ABORT, 'admin_provider_prices: rows are append-only'); END"
    )


MIGRATION = WebMigration(
    migration_id="1540_admin_pricing",
    module="web_admin",
    description="append-only provider price table for estimated platform call costs (CNY/USD, per call unit)",
    apply=_apply,
)
