"""每宠运行记录（web_entity_runtime）的读写。从 runtime_view.py 拆出来，原导入路径继续可用。

所有写方法都走 C 的 `unit_of_work`：后台线装了进程租约围栏时，**拿到写锁之后、写运行记录之前**再查一次租约，
失效就抛 LeaseLost 整体回滚。运行记录也是世界的一部分，被接管的旧进程不能继续往里写（验收 CR-A4）。

`updated_at` 一律 `max(updated_at, 本次时刻)`：它是"这一行被动过"的唤醒标记（`due_pets` 的 `changed` 靠它），
慢一轮的写入把它改小就会把别人刚写下的变化抹掉。时间戳都是同格式的 UTC ISO，按字符串比就是按时间比。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from collections.abc import Iterable
from typing import Callable

from ..utils import iso, parse_dt
from ..web_platform.runtime_epochs import bump_in, versions_in
from ..web_platform.uow import unit_of_work
from ..web_runtime.reasons import silence_of

logger = logging.getLogger("petsoul.web.runtime")


class RuntimeStore:
    def __init__(self, storage) -> None:
        self.storage = storage

    def row(self, pet_id: str) -> dict:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()
        return dict(row) if row else {}

    def bump_in(self, conn, pet_id: str, field: str, now: datetime) -> None:
        """在调用者的业务事务里把某个语义版本 +1（活动变化、撤权、成员变化、运行归属切换）。"""
        bump_in(conn, pet_id, field, now)

    def record_evaluation(self, pet_id: str, decision, now: datetime, *, expected=None) -> list[str]:
        """写下这次心跳的结论：下次检查时刻与安静原因（运维据此区分“正常安静”和“系统丢了后续任务”）。

        **旧评估不能确认它没读到的新版本**：给了 `expected` 就在同一个事务里再比一次语义版本，
        变了就**整个不写**，返回变了的字段名（空列表＝已经写下）。

        为什么必须挡：这次的结论是用旧事实算出来的。交错是这样发生的——
        评估读到旧状态 → 别的命令把 `privacy_epoch` 递增（`updated_at` 变成较新的时刻）→ 旧评估才写回来。
        写回去会把 `last_evaluated_at` 推到旧的那个时刻、并把 `updated_at` 覆盖成更早的值，
        于是 `due_pets` 的 `changed` 从成立变成不成立，那条新变化的唤醒信号就被抹掉了，
        下一次检查要等到六小时后的看门狗。这不是“安全地多唤醒一次”，是**漏唤醒**。
        """
        silence = decision.silence_reason or silence_of(decision)
        silence = getattr(silence, "value", silence)
        with unit_of_work(self.storage) as conn:
            if expected is not None:
                stale = expected.stale_fields(versions_in(conn, pet_id))
                if stale:
                    return list(stale)
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            conn.execute("UPDATE web_entity_runtime SET next_check_at = ?, silence_reason = ?, last_evaluated_at = ?, "
                         "updated_at = max(updated_at, ?) WHERE pet_id = ?",
                         (iso(decision.next_check_at) if decision.next_check_at else None, silence or None, iso(now), iso(now), pet_id))
        return []

    def record_decision(self, pet_id: str, now: datetime, *, by: str, next_review_at: datetime | None) -> None:
        with unit_of_work(self.storage) as conn:
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            conn.execute("UPDATE web_entity_runtime SET last_decision_at = ?, last_decision_by = ?, next_review_at = ?, "
                         "updated_at = max(updated_at, ?) WHERE pet_id = ?",
                         (iso(now), by, iso(next_review_at) if next_review_at else None, iso(now), pet_id))

    def record_decision_checked(self, pet_id: str, now: datetime, *, by: str, next_review_at: datetime | None, expected) -> list[str]:
        """"留在家里"也是一次真的决定：写之前在**同一个事务、同一个连接**里再核一遍语义版本。

        返回变了的字段名列表；空列表表示核对通过并且已经写下。撤权、改 DNA、活动变化都在这里被挡住（验收 CR-C1）。
        """
        with unit_of_work(self.storage) as conn:  # 先过租约围栏，再在同一事务里比版本
            if expected is not None:
                stale = expected.stale_fields(versions_in(conn, pet_id))
                if stale:
                    return list(stale)
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            conn.execute("UPDATE web_entity_runtime SET last_decision_at = ?, last_decision_by = ?, next_review_at = ?, "
                         "updated_at = max(updated_at, ?) WHERE pet_id = ?",
                         (iso(now), by, iso(next_review_at) if next_review_at else None, iso(now), pet_id))
        return []

    def record_attempt(self, pet_id: str, now: datetime, *, review_at: datetime | None, reason: str) -> None:
        """只记"这一轮想过了、下次什么时候再看"，**不写 last_decision_at / last_decision_by**。

        shadow 模式与被挡下的提案都走这里：世界并没有按这个结论走，不能冒充成一次生活决定（包 B 的 BLOCK-1）。
        """
        with unit_of_work(self.storage) as conn:
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            conn.execute("UPDATE web_entity_runtime SET next_review_at = ?, silence_reason = ?, updated_at = max(updated_at, ?) WHERE pet_id = ?",
                         (iso(review_at) if review_at else None, reason, iso(now), pet_id))

    def record_backoff(self, pet_id: str, now: datetime, *, review_at: datetime, reason: str) -> None:
        """这次没想成（模型失败、额度不足、复核没通过）：记下什么时候再看，别下一轮又来一次。

        只动 next_review_at 与安静原因，**不碰 last_decision_at / last_decision_by**——没做成决定就不能说谁决定了。
        """
        with unit_of_work(self.storage) as conn:
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            conn.execute("UPDATE web_entity_runtime SET next_review_at = ?, silence_reason = ?, updated_at = max(updated_at, ?) WHERE pet_id = ?",
                         (iso(review_at), reason, iso(now), pet_id))

    def open_decision(self, pet_id: str, now: datetime, *, new_id: Callable[[], str], stale_after: timedelta | None = None) -> str:
        """拿到"这一轮决策"的逻辑编号：库里还存着就复用它，没有才开一个新的并存下来。

        复用是关键：同一轮里崩溃后重试、换进程重启、跨过整分钟再回来，都必须是同一个编号——
        否则每次重试都会再预占一次额度，包 A 的重放保护也永远触发不了（验收 CR-A2）。

        `stale_after=None`（生活决策用的就是这个）：**只要还存着编号就一直沿用，不按时间轮换**。
        编号是在这次操作**有了明确结局**时才被清掉的（见 `BrainLife._close`），不能靠"过了多久"来换：
        预占到期只说明过了保留时限没人来结清，**不说明那次请求没发出去**（Q-C13 / Q-C19 2026-09-23 06:20 口径）。
        传了 `stale_after` 才按时长把没结束的当作废弃——只给那些"没发出去就是没发出去"的用途。
        """
        with unit_of_work(self.storage) as conn:
            conn.execute("INSERT OR IGNORE INTO web_entity_runtime (pet_id, updated_at) VALUES (?, ?)", (pet_id, iso(now)))
            row = conn.execute("SELECT decision_operation_id, decision_started_at FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()
            open_id, started = (row["decision_operation_id"], row["decision_started_at"]) if row else (None, None)
            if open_id and (stale_after is None or (started and now - parse_dt(started) <= stale_after)):
                return open_id
            operation_id = new_id()
            conn.execute("UPDATE web_entity_runtime SET decision_operation_id = ?, decision_started_at = ?, updated_at = max(updated_at, ?) "
                         "WHERE pet_id = ?", (operation_id, iso(now), iso(now), pet_id))
            return operation_id

    def close_decision(self, pet_id: str, now: datetime, *, operation_id: str | None = None) -> None:
        """这一轮有了明确结果（出发、留在家里、被复核挡下、失败）：清掉编号，下一轮才是新的一次决策。

        给了 operation_id 就**只清这一个**：对不上说明库里存的已经是别的轮次开的，不能替它做主（CR-Q14）。
        """
        where, params = ("", ()) if operation_id is None else (" AND decision_operation_id = ?", (operation_id,))
        with unit_of_work(self.storage) as conn:
            conn.execute("UPDATE web_entity_runtime SET decision_operation_id = NULL, decision_started_at = NULL, "
                         f"updated_at = max(updated_at, ?) WHERE pet_id = ?{where}", (iso(now), pet_id, *params))

    def due_pets(self, now: datetime, *, watchdog: timedelta, roster: Iterable[str] | None = None,
                 after: str = "", limit: int = 200) -> list[tuple[str, str]]:
        """现在该看哪些宠物：返回 [(pet_id, 为什么该看)]，按该看的先后排。用于把 30 秒全量扫描换成按到期取（CR-B6）。

        **五个唤醒来源，任缺一个都会漏调度**，所以宁可多叫醒、不可漏：
          1. `due`        —— 到了上一次心跳自己排的 `next_check_at`。可预测的边界（活动结束、承诺到期、
                             额度重置、看门狗上限）心跳算 next_check_at 时已经算进去了，这一条就把它们全兜住；
          2. `never`      —— 还没评估过（新宠物、迁移后的旧数据）；
          3. `changed`    —— 运行记录这一行在上次评估之后被动过（撤权、改 DNA、换成员、活动变化、退避、决定）。
                             按 `updated_at > last_evaluated_at` 判：会**多叫醒**（写退避也算一次），这是安全的一侧；
          4. `reply`      —— 有到点还没兑现的回复承诺（新消息进来时心跳还没排到）；
          5. `suggestion` —— 上次评估之后家人提了新建议。
        另加**看门狗兜底**：超过 watchdog 没被评估过的一律叫醒，事件来源万一漏了也不会有宠物被饿死。

        `roster`：调用方知道的全部宠物。运行记录是**第一次写才建行**的，新来的宠物在这张表里根本没有行，
        光查这张表会把它们整个看不见、永远排不上。给了 roster 就把"还没有行"的一并算成 `never`。

        `after` / `limit`：一轮最多看几只，以及从谁之后接着排。**新来的和已有的共用同一个上限、同一条轮转**——
        新宠物不能绕过上限（那会让一轮的工作量不受控），单纯按名字截断又会让排在后面的永远轮不到。
        所以按 pet_id 排好之后从 `after` 之后取、到尾部再绕回开头，和认知线的轮转是同一个办法（Q-C16）。
        调用方把返回的最后一个 pet_id 记下来当作下一轮的 `after`。

        候选查询本身不设上限：一只候选只取两列，比原来"每 30 秒每只做 8～10 次查询"便宜得多；
        `limit` 限的是**这一轮评估几只**。`next_check_at` 上有索引（m0060）。
        """
        at, stale = iso(now), iso(now - watchdog)
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT pet_id, why FROM (
                  SELECT r.pet_id AS pet_id,
                         CASE
                           WHEN r.last_evaluated_at IS NULL THEN 'never'
                           WHEN r.last_evaluated_at <= ? THEN 'watchdog'
                           WHEN r.next_check_at IS NULL OR r.next_check_at <= ? THEN 'due'
                           WHEN r.updated_at > r.last_evaluated_at THEN 'changed'
                           WHEN EXISTS (SELECT 1 FROM web_pending_replies p WHERE p.pet_id = r.pet_id AND p.due_at <= ?
                                        AND (p.delivered_message_id IS NULL
                                             OR (p.delivered_message_id LIKE 'claim-%'
                                                 AND (p.claimed_until IS NULL OR p.claimed_until <= ?)))) THEN 'reply'
                           WHEN EXISTS (SELECT 1 FROM web_owner_suggestions s WHERE s.pet_id = r.pet_id
                                        AND s.status = 'pending' AND s.created_at > r.last_evaluated_at) THEN 'suggestion'
                           ELSE NULL
                         END AS why
                    FROM web_entity_runtime r
                   WHERE r.maintenance = 0
                ) WHERE why IS NOT NULL
                ORDER BY pet_id
                """,
                (stale, at, at, at),
            ).fetchall()
            candidates = [(row["pet_id"], row["why"]) for row in rows]
            if roster is not None:
                known = {row["pet_id"] for row in conn.execute("SELECT pet_id FROM web_entity_runtime").fetchall()}
                candidates += [(pet_id, "never") for pet_id in set(roster) - known]  # 还没有运行记录的新宠物
        candidates.sort()
        start = next((i for i, (pet_id, _why) in enumerate(candidates) if pet_id > after), 0)
        rotated = candidates[start:] + candidates[:start]
        return rotated[:max(1, int(limit))]

    def decided_within(self, pet_id: str, now: datetime, window: timedelta) -> bool:
        """这只宠物刚刚做过生活决定吗（不论是模型还是规则决定的）。两条线共用这一个判断，避免同一时段各决定一次。"""
        last = self.row(pet_id).get("last_decision_at")
        return bool(last) and now - parse_dt(last) < window
