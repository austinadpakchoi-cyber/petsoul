"""1500：平台员工后台（身份、角色、会话、审计、账号处置、举报处理、受控开关）。

只新增 admin_* 表，**不改任何既有表**：玩家账号、宠物、家庭、钱包、任务、预算的真相仍然只有一份。
账号冻结记在 admin_account_flags，不动 users / web_accounts；举报处理记在 admin_report_actions，
不动 web_reports（举报事实本身要保留）。

admin_audit 是**仅追加**的：这里用触发器挡住 UPDATE / DELETE。如实说明——同一个 SQLite 文件里的
触发器不是防篡改证明（有文件写权限的人可以绕开），要真正不可抵赖需要独立留存/异地备份，见方案 §6。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    # ---- 员工身份 ----
    conn.execute(
        """
        CREATE TABLE admin_staff (
            staff_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            username_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
            mfa_secret TEXT,
            mfa_enabled INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            created_by TEXT,
            password_updated_at TEXT NOT NULL,
            disabled_at TEXT,
            disabled_by TEXT,
            last_login_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE admin_staff_roles (
            staff_id TEXT NOT NULL REFERENCES admin_staff(staff_id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granted_by TEXT,
            PRIMARY KEY (staff_id, role)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE admin_sessions (
            session_id TEXT PRIMARY KEY,
            staff_id TEXT NOT NULL REFERENCES admin_staff(staff_id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            revoked_reason TEXT,
            client_hint TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_sessions_staff ON admin_sessions (staff_id, revoked_at)")

    # ---- 审计（仅追加）----
    conn.execute(
        """
        CREATE TABLE admin_audit (
            audit_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            actor_staff_id TEXT,
            actor_username TEXT,
            action TEXT NOT NULL,
            permission TEXT,
            target_kind TEXT,
            target_id TEXT,
            reason TEXT,
            status TEXT NOT NULL CHECK (status IN ('allowed', 'denied', 'succeeded', 'failed', 'replayed')),
            outcome TEXT,
            operation_id TEXT,
            request_id TEXT,
            changes_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_audit_time ON admin_audit (occurred_at DESC)")
    conn.execute("CREATE INDEX idx_admin_audit_actor ON admin_audit (actor_staff_id, occurred_at DESC)")
    conn.execute("CREATE INDEX idx_admin_audit_target ON admin_audit (target_kind, target_id, occurred_at DESC)")
    conn.execute(
        "CREATE TRIGGER admin_audit_no_update BEFORE UPDATE ON admin_audit "
        "BEGIN SELECT RAISE(ABORT, 'admin_audit is append-only'); END"
    )
    conn.execute(
        "CREATE TRIGGER admin_audit_no_delete BEFORE DELETE ON admin_audit "
        "BEGIN SELECT RAISE(ABORT, 'admin_audit is append-only'); END"
    )

    # ---- 账号处置（平台侧状态，不改玩家账号表）----
    conn.execute(
        """
        CREATE TABLE admin_account_flags (
            user_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('active', 'frozen')),
            reason TEXT,
            changed_at TEXT NOT NULL,
            changed_by TEXT,
            version INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    # ---- 举报处理记录（web_reports 本身只读）----
    conn.execute(
        """
        CREATE TABLE admin_report_actions (
            action_id TEXT PRIMARY KEY,
            report_id TEXT,
            target_kind TEXT NOT NULL,
            target_id TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('takedown', 'restore', 'dismiss')),
            reason TEXT NOT NULL,
            staff_id TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_report_actions_target ON admin_report_actions (target_kind, target_id, created_at DESC)")

    # ---- 受控开关（例如：暂停新增 AI 调用）----
    conn.execute(
        """
        CREATE TABLE admin_switches (
            switch_key TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            reason TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            changed_at TEXT NOT NULL,
            changed_by TEXT
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1500_admin",
    module="web_admin",
    description="platform staff identity, roles, sessions, append-only audit, account flags, report actions, controlled switches",
    apply=_apply,
)
