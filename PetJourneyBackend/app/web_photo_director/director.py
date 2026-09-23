"""编排：校验 → 回忆已有结论 → （最多）一次模型 → 否则规则 → 编译。

这里有意**不做**的事：任何数据库写入、任何调度器、任何图片调用、任何生图重试。
导演只产出一条指令并交回去；任务、图片额度、未知结果规则与媒体都归 A。
同一个事件重复调用 `direct` 得到同一条指令，这正是它能被可重试的 worker 调用的前提。
"""
from __future__ import annotations

from .compiler import compile_photo
from .contracts import (
    DirectedPhoto,
    PhotoAccess,
    PhotoContext,
    PhotoDirectorError,
    TextCallRecord,
)
from .draft import validate_draft
from .memo import DirectorMemo, recall, remember, remember_attempt
from .port import DirectorBudget, DirectorChat, request_draft
from .rules import rule_draft
from .validation import model_operation_id, validate_context


class PhotoDirector:
    """只接注入的端口；构造一次反复用。

    `chat` / `budget` 留空是受支持的离线配置——此时走规则导演并如实标记，
    不会假装是模型写的。`memo` 留空时功能不变，但"重启不会重复调用"这条保证不成立，
    会被记成 `memo_absent`。
    """

    def __init__(
        self,
        *,
        chat: DirectorChat | None = None,
        budget: DirectorBudget | None = None,
        memo: DirectorMemo | None = None,
        abort_on: tuple = (),
        on_settlement_failure=None,
    ) -> None:
        self.chat = chat
        self.budget = budget
        self.memo = memo
        # 精确的"必须中止"异常类（例如 web_platform 的 LeaseLost）。
        # 不传也会按类名兜底，见 port.ABORT_EXCEPTION_NAMES。
        self.abort_on = abort_on
        # 账本写不进去时的对账通知（可选）。它失败也不会盖掉主信号。
        self.on_settlement_failure = on_settlement_failure

    def direct(self, context: PhotoContext, access: PhotoAccess) -> DirectedPhoto:
        # 先 fail closed：撤权的家庭、已被更正的事件，都不该走到模型、词表或编译器。
        validate_context(context, access)
        operation_id = model_operation_id(context)

        # 这个事件以前有没有结论？有就复用，一次都不再调用。
        draft, record = recall(self.memo, context, operation_id)
        if record is not None:
            return self._finish(context, draft, record, reused=True)

        draft, record = request_draft(
            context,
            chat=self.chat,
            budget=self.budget,
            operation_id=operation_id,
            text_director_allowed=access.text_director,
            abort_on=self.abort_on,
            on_attempt=lambda: remember_attempt(self.memo, operation_id),
            on_settlement_failure=self.on_settlement_failure,
        )
        remember(self.memo, operation_id, draft, record)
        return self._finish(context, draft, record, reused=False)

    def _finish(self, context, draft, record: TextCallRecord, *, reused: bool) -> DirectedPhoto:
        if draft is not None:
            # 解析时已经校验过；这里再验一次，让"直接喂 draft 进来"的调用方也绕不开围栏。
            validate_draft(draft, context)
            return compile_photo(
                context, draft, directed_by="model", fallback_reason=None, text_call=record
            )
        reason = record.reason or record.outcome
        if self.memo is None and record.outcome in {"sent_ok", "sent_unknown", "invalid_output"}:
            # 如实说明：没有备忘端口，就没有跨进程的"只调用一次"保证。
            reason = f"{reason};memo_absent"
        return compile_photo(
            context,
            rule_draft(context),
            directed_by="rule",
            fallback_reason=reason + (";reused" if reused else ""),
            text_call=record,
        )

    def direct_with_rules(self, context: PhotoContext, access: PhotoAccess) -> DirectedPhoto:
        """明确的离线路径：一次都不碰模型端口，也不读写备忘。"""
        validate_context(context, access)
        return compile_photo(
            context,
            rule_draft(context),
            directed_by="rule",
            fallback_reason="rule_only",
            text_call=TextCallRecord(
                outcome="rule_only",
                operation_id=model_operation_id(context),
                reserved=False,
                reason="rule_only",
            ),
        )


__all__ = ["PhotoDirector", "PhotoDirectorError"]
