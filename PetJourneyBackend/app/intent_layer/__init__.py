"""可替换的意图判断层（默认关闭）。Jev / 已配置主模型为候选实现，R0 未接通、未评测。"""

from .judge import RULE_VERSION, JudgeUnavailable, RuleIntentJudge, UnconnectedJudge
from .layer import IntentLayer, build_judge

__all__ = ["RULE_VERSION", "IntentLayer", "JudgeUnavailable", "RuleIntentJudge", "UnconnectedJudge", "build_judge"]
