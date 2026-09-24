"""出发闸要的那个谓词：此刻有没有**拦住出行**的有效承诺（TRV-02，合同 15 节）。

`journeys.active_commitment_in(conn, pet_id, now) -> str | None` 由装配接上；出发的写事务里调一次。

**为什么只认一个信号。** 决策上下文里的 `commitments` 是**给模型看的材料**，内容主要是
`f"有家人建议：{title}"`——那是"**建议去**"，不是"不许去"。拿它当出发闸在语义上是反的：
有人建议去，反而把出门拦住。所以这里**只认唯一一个禁止形态的信号**：主人在私聊里说过"今天待在家"。
别的（待回复、工钱、到家时间）都不是"不许出门"的意思，**不在这里拼**——真要加得先有产品裁定。

**为什么返回的是种类名而不是原话。** 数据源 `owner_asked_stay_home_in` 只回 `bool`、有意不转述主人的话
（合同 16）。这个返回值会进 `JourneyError` 的 details，**再往上就可能出现在接口与日志里**，
所以这里也只给一个稳定的种类名，不把私聊内容带出来。

**为什么用工厂而不是直接 import。** 决策包不 import 通讯器：把端口当参数传进来，方向上只有装配知道两边，
`decision/**` 保持可以被单独测试、也不制造新的包间依赖。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from .service_reader import STAY_HOME_HOURS

OWNER_ASKED_STAY_HOME = "owner_asked_stay_home"


def commitment_gate(communicator, *, hours: int = STAY_HOME_HOURS) -> Callable[..., str | None]:
    """造一个出发闸谓词。`communicator` 只需要有 `owner_asked_stay_home_in(conn, user_id, pet_id, since)`。

    `hours` 沿用 `service_reader` 里那一个常量——同一个判定不写两份数值（写两处就会漂，而且漂了不报错）。
    """

    def active_commitment_in(conn, pet_id: str, now: datetime) -> str | None:
        # 必须用调用方那个 conn：出发的写事务里另开连接读的是事务开始前的快照（CR-C1 那个坑，这是第四次同形）
        if communicator.owner_asked_stay_home_in(conn, "", pet_id, now - timedelta(hours=hours)):
            return OWNER_ASKED_STAY_HOME
        return None

    return active_commitment_in
