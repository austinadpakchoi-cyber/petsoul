"""宠物的有限自主决策（工作包 C）：DNA 与真实经历 → 授权上下文 → 模型在规则给出的可行行动里选择 → 带版本的提案。

共享数据类型来自 app.schemas.runtime_internal（runtime-internal 0.1.0）；本包只定义自己的端口、限额、调用记录与审计信息。
决策包只产出提案：不写库、不扣钱、不发消息。执行、结算、发布前的最终核对由集成窗口在同一个事务里完成；
模型不可用、预算不足或输出不合格时返回明确的 DecisionFailure，规则后备由集成窗口执行并标 rule_fallback。
"""

from .brain import Brain, decide
from .chat_adapter import ChatModelAdapter
from .commitments import OWNER_ASKED_STAY_HOME, commitment_gate
from .context import BuiltContext, build_context, can_continue
from .offers import action_kind_of, destination_key_of, offers_from_options
from .outcomes import CallRecord, DecisionAudit, DecisionResult, reason_of
from .ports import (CallLimits, ContextReader, DecisionRequest, DnaSnapshot, ModelAdapter, ModelCallError, ModelReply, PetBrief, Record, ToolPort,
                    ToolSpec)
from .projections import dna_snapshot
from .prompt import PROMPT_VERSION
from .service_reader import ServiceContextReader

__all__ = [
    "commitment_gate", "OWNER_ASKED_STAY_HOME",
    "PROMPT_VERSION", "Brain", "BuiltContext", "CallLimits", "CallRecord", "ChatModelAdapter", "ContextReader", "DecisionAudit", "DecisionRequest",
    "DecisionResult", "DnaSnapshot", "ModelAdapter", "ModelCallError", "ModelReply", "PetBrief", "Record", "ServiceContextReader", "ToolPort",
    "ToolSpec", "action_kind_of", "build_context", "can_continue", "decide", "destination_key_of", "dna_snapshot", "offers_from_options", "reason_of",
]
