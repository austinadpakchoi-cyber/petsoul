"""主人有没有说过「今天别出门」一类的话（TRV-00 合同 15.4、16）。

从 `service.py` 拆出：那个文件到了 arch_gate 每文件 30 个定义的上限，这块判定是独立的一件事（读主人私聊里的一种意思）。

一份判定、两个入口：
  - `owner_asked_stay_home_in(conn, …)`：只用调用方的连接（不开连接、不 BEGIN、不提交）——出发写事务里当闸用，读得到本事务内的变化；
  - `owner_asked_stay_home(…)`：开短连接后调它（旧调用方不用改）。
只回 bool，**不转述原话**。`user_id` 与旧入口同形保留：判定按宠物看全家，任何一位家人说过都算。
"""

from __future__ import annotations

import re
from datetime import datetime

from ..utils import iso

# 只认**禁止 TA 出门**的祈使式（I 2026-09-24 裁定）。它是硬闸的判据：命中＝12 小时内一切自主出门被拒。
# 去掉的「今天在家／今天休息／待在家／呆在家」说的是**谁在家**，不是禁止——一半以上的误命中是主人在说自己
# （「我今天休息，陪你玩」「今天在家做了蛋糕」），「我们今天休息一下再出发」更是要出门。第一人称靠词表分不出来，不再加规则去猜。
# 漏判（「你今天在家好好休息」）是有意接受的：误判＝半天不能动、撞「宠物自主、主人只建议」；漏判＝主人再说一句「别出门」就行。
STAY_HOME = re.compile(r"(别出门|不要出门|别出去|不要出去|别乱跑)")


class StayHomeReader:
    """混入 `WebCommunicatorService`：只用到 `self.storage`。"""

    def owner_asked_stay_home(self, user_id: str, pet_id: str, since: datetime) -> bool:
        """最近有没有哪位家人说过“今天别出门”一类的话（只影响 TA 出不出门的倾向，不执行任何操作；不转述原话）。"""
        with self.storage.connect() as conn:
            return self.owner_asked_stay_home_in(conn, user_id, pet_id, since)

    def owner_asked_stay_home_in(self, conn, user_id: str, pet_id: str, since: datetime) -> bool:
        """同一份判定的同事务入口（TRV-00 合同 15.4）：**只用调用方的 `conn`**，不开连接、不 BEGIN、不提交。

        出发的写事务里当闸用：在 `BEGIN IMMEDIATE` 之后另开连接读，会读到事务开始前的快照、还和自己的写事务争锁
        （CR-C1 那个坑）；用同一个 `conn` 才读得到本事务里刚发生的变化。只回 bool，**不转述原话**（合同 16）。
        `user_id` 与旧入口同形保留；判定按宠物看全家——任何一位家人说过都算。
        """
        rows = conn.execute("SELECT text FROM web_messages WHERE pet_id = ? AND sender = 'owner' AND channel = 'private' AND created_at >= ?",
                            (pet_id, iso(since))).fetchall()
        return any(STAY_HOME.search(r["text"]) for r in rows)
