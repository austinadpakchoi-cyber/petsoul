"""宠物自主世界（网页）：TA 此刻的状态、按状态决定何时回复、主动发来的消息、进程内世界定时器。

所有规则都由服务端裁定；模型只负责“用 TA 的口吻说话”，不决定时间、钱或行程。
"""

from .moment import MomentBuilder, PetMoment
from .reply_policy import ReplyPlan, is_distress, plan_reply

__all__ = ["MomentBuilder", "PetMoment", "ReplyPlan", "is_distress", "plan_reply"]
