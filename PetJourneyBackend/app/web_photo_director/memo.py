"""一次事件的导演决定要能被记住，否则"稳定编号"挡不住重复付费。

`model_operation_id` 对同一个事件是稳定的，但那只是一个**名字**：
进程崩在发出之后、任务被接管重跑、worker 重启——每一次都会拿着同一个编号
再调一次文本模型。真正挡住重复调用的是"这个编号已经有结论了"这条记录。

所以这里定义一个可注入的备忘端口。**它不是本包实现的存储**：
持久化归 A（任务/额度那一侧），本包只定义读写形状和复用规则。
没有注入备忘时，导演仍然可用，但"重启不会重复调用"这条保证不成立——
`DirectorMemo` 缺席会被如实记成 `memo_absent`，不会假装已经防住。

复用规则有意保守：
  - 记到 `sent_ok` 且拍法仍然合法 → 直接复用，**一次都不再调用**；
  - 记到 `sent_unknown` / `invalid_output` / `refused` → 那次已经可能计费或已被拒，
    **不再调用**，直接走规则导演；
  - 记下来的拍法在当前上下文里已经不合法（事实变了、撤权了）→ 也不再调用，走规则。
"""
from __future__ import annotations

from typing import Protocol

from .contracts import PhotoDirectorError, SceneDraft, TextCallRecord
from .draft import normalise_draft

# 这些结论一旦记下，就不再发第二次文本请求。
TERMINAL_OUTCOMES = frozenset({"sent_ok", "sent_unknown", "invalid_output", "refused"})
# 先写后发留下的标记：请求已经要发出了，但还没写回结果。
# 读到它就当"可能已经发出、可能已经计费"，同样不再调用。
IN_FLIGHT = "in_flight"
NO_RETRY_OUTCOMES = TERMINAL_OUTCOMES | {IN_FLIGHT}


class DirectorMemo(Protocol):
    """同一个事件的导演结论。实现方负责持久化与并发安全。"""

    def get(self, operation_id: str) -> dict | None: ...

    def put(self, operation_id: str, record: dict) -> None: ...


def recall(memo: DirectorMemo | None, context, operation_id: str):
    """看这个事件是不是已经有结论了。

    返回 (draft 或 None, TextCallRecord 或 None)。
    第二项不是 None 就表示**不要再调用模型**，按它记录的结论走。
    """
    if memo is None:
        return None, None
    stored = memo.get(operation_id)
    if not isinstance(stored, dict):
        return None, None
    outcome = stored.get("outcome")
    if outcome not in NO_RETRY_OUTCOMES:
        return None, None
    if outcome == IN_FLIGHT:
        # 上一轮发出去了却没写回结果（崩在中间）。当作结果不明：不再发，走规则。
        return None, TextCallRecord(
            outcome="sent_unknown", operation_id=operation_id, reserved=True,
            reason="previous_attempt_in_flight",
        )

    record = TextCallRecord(
        outcome=outcome,
        operation_id=operation_id,
        reserved=bool(stored.get("reserved")),
        provider_label=stored.get("provider_label"),
        requested_model=stored.get("requested_model"),
        effective_model=stored.get("effective_model"),
        reason=stored.get("reason") or "reused_recorded_decision",
    )
    recipe = stored.get("recipe")
    if outcome != "sent_ok" or not recipe:
        # 上一次没拿到可用的拍法（超时、被拒、输出无效）。不再试一次，交给规则导演。
        return None, record
    try:
        draft = normalise_draft(
            recipe=recipe,
            expression=stored.get("expression", ""),
            visible_facts=tuple(stored.get("visible_facts", ())),
            context=context,
        )
    except PhotoDirectorError as exc:
        # 事实变了或撤权了，旧拍法已经不合法。也**不**重新调用，直接走规则。
        return None, TextCallRecord(
            outcome=outcome, operation_id=operation_id,
            reserved=bool(stored.get("reserved")),
            reason=f"recorded_decision_stale:{exc}",
        )
    return draft, record


def remember_attempt(memo: DirectorMemo | None, operation_id: str) -> None:
    """先写后发：请求离开进程之前先记一笔"在途"。

    这是堵住"已经发出、还没写回结果就崩"这个窗口的唯一办法。
    没有它的话，恢复的进程会拿着同一个稳定编号再发一次。
    """
    if memo is not None:
        memo.put(operation_id, {"outcome": IN_FLIGHT, "reserved": True})


def remember(memo: DirectorMemo | None, operation_id: str,
             draft: SceneDraft | None, record: TextCallRecord) -> None:
    """把这次的结论写下来，让重试和重启读得到。"""
    if memo is None or record.outcome not in TERMINAL_OUTCOMES:
        return
    payload: dict = {
        "outcome": record.outcome,
        "reserved": record.reserved,
        "provider_label": record.provider_label,
        "requested_model": record.requested_model,
        "effective_model": record.effective_model,
        "reason": record.reason,
    }
    if draft is not None:
        payload.update(
            recipe=draft.recipe,
            expression=draft.expression,
            visible_facts=list(draft.visible_facts),
        )
    memo.put(operation_id, payload)
