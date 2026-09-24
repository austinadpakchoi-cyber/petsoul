"""1700：旅行心愿 → 联网攻略 → 自动手账的持久层（TRV-03；号由 I 在 TRV-00 合同第 1 节分配，1700–1799 段，A 唯一作者）。

表名与键照 `docs/coordination/travel-wish/TRV-00-contract-v1.md` 11.1／11.6，Q 按表查痕迹（改名先回报 I）。
这是冻结的快照：DDL 写死在这里，不从领域模块导入——以后改仓储代码不会让已经跑过的迁移悄悄变样。

  - `web_travel_wishes`：一个心愿一行；`wish_id` 连续身份、`wish_revision` 单调递增。
    `(pet_id, trigger_event_id)` 唯一＝同一有效事件重复投递不新增心愿（T02）；
    **每只宠物同时只有一个进行中的心愿**：active／ready 上的部分唯一索引，并发也只进得去一个。
    等待原因按写入方分两列：`life_waiting_json`（B：钱、承诺、维护态）与 `research_waiting_json`（A：研究与资料），互不覆盖。
    复查时刻叫 `reconsider_after`，不叫 `next_review_at`（合同 5.4：那是心跳的列，语义不同）；它只是给页面看的缓存值。
  - `web_travel_considerations`：**按宠物**记「上次真正问过大脑是什么时候」（只在 ask_brain 那一轮写，不是每一轮 tick）。
    冷却闸读它＋策略自己的间隔（合同 17.1）。**不挂在心愿行上**：DS 可以决定留在家里、根本不形成心愿，
    那时没有心愿行可挂，冷却却照样要挡（B 核出）。只往后走：迟到的旧时刻不把它拨回去。
  - `web_travel_research_receipts`：研究回执，**一次发送尝试一行**，`operation_id` 与额度预占同号且唯一。
    先落 `intent` 再发送，响应先落 `answered` 再发布（方案 §11.2）；`plan_id`／`plan_revision` 指向它产出的那一版计划。
    `tool_executions`／`tool_execution_ids_json` 是「检索真的执行过」的唯一依据（合同 11.3）。
  - `web_travel_facts`：逐条事实，带来源、抓取／观测／适用时间与核验结论；时间没有就是空，不伪造（合同 11.4）。
    结论用 P 编译器那套形容词：verified／unverified／stale／conflicting；另有 rejected（引用了不存在的 source_id）。
  - `web_travel_plans`：计划修订（`plan_id` 稳定、`plan_revision` 每次研究结果落地 +1）；旅程不存在时 `journey_id` 为空，不预建假旅程。
  - `web_travel_journals`：手账修订（`journal_id` 稳定、`journal_revision` 递增），绑定计划的那一版；排版数据与图片分开存。
    画面版本用 P 编译器给的 `visual_digest`（只含画面输入：改站名、时间、提醒不变，回忆阶段与计划阶段相同），连同 `template_revision`、`reference_revision`、`identity_mode` 一起存（TRV-05 第 3 点）。计划表不另算一个画面摘要，免得两套口径。
    **手账图的状态不另存**：以插画记录为准（按 `image_task_id` 关联 `web_illustrations`，`unknown` 用插画服务的 `outcome_of`），一份口径。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_travel_wishes (
            wish_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            household_id TEXT,
            wish_revision INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'ready', 'linked', 'completed', 'cancelled')),
            trigger_event_id TEXT NOT NULL,
            interest_tags_json TEXT NOT NULL,
            candidates_json TEXT NOT NULL,
            selected_index INTEGER NOT NULL,
            destination_key TEXT NOT NULL,
            destination_name TEXT NOT NULL,
            city TEXT NOT NULL,
            owner_reason TEXT NOT NULL,
            funds_goal INTEGER,
            window_start TEXT,
            window_end TEXT,
            life_waiting_json TEXT NOT NULL DEFAULT '[]',
            life_detail_json TEXT NOT NULL DEFAULT '{}',
            research_waiting_json TEXT NOT NULL DEFAULT '[]',
            reconsider_after TEXT,
            research_round INTEGER NOT NULL DEFAULT 1,
            plan_id TEXT NOT NULL,
            plan_revision INTEGER,
            journey_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX ux_travel_wish_trigger ON web_travel_wishes (pet_id, trigger_event_id)")
    conn.execute("CREATE UNIQUE INDEX ux_travel_wish_open ON web_travel_wishes (pet_id) WHERE status IN ('active', 'ready')")
    conn.execute("CREATE INDEX ix_travel_wish_journey ON web_travel_wishes (journey_id)")
    conn.execute(
        """
        CREATE TABLE web_travel_considerations (
            pet_id TEXT PRIMARY KEY,
            last_considered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_travel_research_receipts (
            receipt_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL UNIQUE,
            wish_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            plan_revision INTEGER,
            round INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('intent', 'answered', 'published', 'not_sent', 'unknown', 'failed', 'discarded')),
            query_json TEXT NOT NULL,
            requested_model TEXT,
            effective_model TEXT,
            provider_request_id TEXT,
            usage_json TEXT,
            search_uses INTEGER,
            tool_executions INTEGER,
            tool_execution_ids_json TEXT,
            cost_amount REAL,
            cost_currency TEXT,
            result_json TEXT,
            settle_state TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX ix_travel_receipts_round ON web_travel_research_receipts (wish_id, round)")
    conn.execute(
        """
        CREATE TABLE web_travel_facts (
            fact_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            wish_id TEXT NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            value_json TEXT NOT NULL,
            source_ids_json TEXT NOT NULL,
            retrieved_at TEXT,
            published_at TEXT,
            observed_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
            verification TEXT NOT NULL,
            conclusion TEXT,
            verdict TEXT NOT NULL CHECK (verdict IN ('verified', 'unverified', 'stale', 'conflicting', 'rejected')),
            blocks_departure INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX ix_travel_facts_operation ON web_travel_facts (operation_id)")
    conn.execute(
        """
        CREATE TABLE web_travel_plans (
            plan_id TEXT NOT NULL,
            plan_revision INTEGER NOT NULL,
            wish_id TEXT NOT NULL,
            wish_revision_at_build INTEGER NOT NULL,
            pet_id TEXT NOT NULL,
            destination_key TEXT NOT NULL,
            operation_id TEXT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            stops_json TEXT NOT NULL,
            owner_tips_json TEXT NOT NULL,
            rain_alternative TEXT,
            preconditions_json TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            valid_from TEXT,
            valid_until TEXT,
            journey_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (plan_id, plan_revision)
        )
        """
    )
    conn.execute("CREATE INDEX ix_travel_plans_journey ON web_travel_plans (journey_id)")
    conn.execute(
        """
        CREATE TABLE web_travel_journals (
            journal_id TEXT NOT NULL,
            journal_revision INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            plan_revision INTEGER NOT NULL,
            visual_digest TEXT NOT NULL,
            phase TEXT NOT NULL CHECK (phase IN ('plan', 'memory')),
            event_ids_json TEXT NOT NULL,
            template_revision TEXT NOT NULL,
            brief_version TEXT NOT NULL,
            identity_mode TEXT NOT NULL CHECK (identity_mode IN ('photo', 'none')),
            identity_note TEXT,
            reference_revision INTEGER,
            image_task_id TEXT,
            layout_json TEXT NOT NULL,
            digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (journal_id, journal_revision)
        )
        """
    )
    conn.execute("CREATE INDEX ix_travel_journal_plan ON web_travel_journals (plan_id, phase)")
    conn.execute("CREATE INDEX ix_travel_journal_task ON web_travel_journals (image_task_id)")


MIGRATION = WebMigration(
    migration_id="1700_travel_wish",
    module="travel",
    description="travel wishes, research receipts, verified facts, plan revisions and journal revisions (TRV-03)",
    apply=_apply,
)
