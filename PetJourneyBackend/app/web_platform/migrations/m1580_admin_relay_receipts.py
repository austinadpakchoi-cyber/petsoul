"""1580：经自建中转站的逐次调用回执（c84a 审查 ADM-COST-01，`docs/coordination/CR-ADMIN-RELAY-COST-2026-09-24.md`）。

- **一次发送一条**：`(relay_instance, relay_event_id)` 唯一。一项业务可能发两次，两条回执都留；重复导入同一条不会记两次。
- 同号但内容不同：**不覆盖**，写进 `admin_relay_import_issues` 留错；被拒的（不在白名单里的客户端、字段不合规）也留在那里。
- 金额分三种证据各放各的列：中转实测用量（token / 图片数）、按有来源价格估算（`estimated_amount` ＋ `price_version`）、
  供应商账单确认（`billed_amount` ＋ `bill_reference`）。缺的就是 NULL，不补 0；币种分开，和游戏星币没有任何关系。
- 这张表只追加：导入从不改已有的行。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_relay_receipts (
            relay_instance TEXT NOT NULL,
            relay_event_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            project_id TEXT,
            environment TEXT,
            operation_id TEXT,
            dispatch_attempt_id TEXT,
            purpose TEXT,
            provider TEXT,
            endpoint TEXT,
            requested_model TEXT,
            reported_model TEXT,
            provider_request_id TEXT,
            started_at_utc TEXT NOT NULL,
            completed_at_utc TEXT,
            http_status INTEGER,
            dispatch_outcome TEXT NOT NULL,
            input_text_tokens INTEGER,
            input_image_tokens INTEGER,
            cached_tokens INTEGER,
            output_tokens INTEGER,
            images_returned INTEGER,
            usage_present INTEGER NOT NULL,
            usage_source TEXT,
            estimated_amount TEXT,
            currency TEXT,
            price_version TEXT,
            cost_state TEXT NOT NULL,
            billed_amount TEXT,
            bill_reference TEXT,
            reconciled_at TEXT,
            content_sha256 TEXT NOT NULL,
            import_batch_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (relay_instance, relay_event_id)
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_relay_receipts_day ON admin_relay_receipts (started_at_utc)")
    conn.execute("CREATE INDEX idx_admin_relay_receipts_operation ON admin_relay_receipts (operation_id)")
    conn.execute(
        """
        CREATE TABLE admin_relay_import_batches (
            batch_id TEXT PRIMARY KEY,
            staff_id TEXT NOT NULL,
            source_note TEXT NOT NULL,
            file_name TEXT,
            received INTEGER NOT NULL,
            inserted INTEGER NOT NULL,
            duplicates INTEGER NOT NULL,
            conflicts INTEGER NOT NULL,
            rejected INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE admin_relay_import_issues (
            issue_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            relay_instance TEXT,
            relay_event_id TEXT,
            kind TEXT NOT NULL CHECK (kind IN ('conflict', 'rejected')),
            reason TEXT NOT NULL,
            existing_sha256 TEXT,
            incoming_sha256 TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1580_admin_relay_receipts",
    module="web_admin",
    description="relay per-dispatch receipts (unique per relay event), import batches and import issues (conflicts / rejections kept)",
    apply=_apply,
)
