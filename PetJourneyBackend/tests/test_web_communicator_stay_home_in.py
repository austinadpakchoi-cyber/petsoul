"""`owner_asked_stay_home_in`（TRV-00 合同 15.4／16.4）：出发写事务里当闸用，读得到本事务内的变化。不联网、0 次付费调用。

构造照合同 16.4：**状态变化放在事务内**——先开写事务、插一条还没提交的主人消息，再判定。
在事务前就把消息写好，新旧两种实现都会绿、分不开；这里的对照正是要把它们分开：
同一个 `conn` 的 `_in` 读到 True，同一时刻另开连接的旧入口读到 False；提交后两者都 True。
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import timedelta
from pathlib import Path

from task_budget_helpers import open_storage

from app.utils import iso, utcnow
from app.web_communicator.service import WebCommunicatorService


class StayHomeInTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "stay.sqlite3"))
        self.communicator = WebCommunicatorService(self.storage)
        self.since = utcnow() - timedelta(hours=12)

    @staticmethod
    def insert(conn, text: str, *, sender: str = "owner", channel: str = "private", created_at=None) -> None:
        stamp = iso(created_at or utcnow())
        conn.execute("INSERT INTO web_messages (message_id, user_id, pet_id, sender, text, created_at, available_at, channel) "
                     "VALUES (?, 'user-1', 'pet-1', ?, ?, ?, ?, ?)", (f"msg-{uuid.uuid4().hex[:12]}", sender, text, stamp, stamp, channel))

    def asked(self, conn=None) -> bool:
        if conn is None:
            return self.communicator.owner_asked_stay_home("user-1", "pet-1", self.since)
        return self.communicator.owner_asked_stay_home_in(conn, "user-1", "pet-1", self.since)

    def test_the_same_transaction_sees_the_change_and_another_connection_does_not(self) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.insert(conn, "今天别出去了好不好")
            self.assertIs(self.asked(conn), True, "同一个写事务：看得见还没提交的这句")
            self.assertIs(self.asked(), False, "另开连接：读到事务开始前的快照——旧入口当闸会放行")
        self.assertIs(self.asked(), True, "提交后旧入口也看得见（两个入口是同一份判定）")

    def test_only_an_owner_private_message_inside_the_window_counts(self) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.insert(conn, "今天天气真好")
            # 这三句本身都命中词表：挡下它们的只能是发送者、频道、时间窗三道过滤
            self.insert(conn, "别出门", sender="pet")
            self.insert(conn, "别出门", channel="family")
            self.insert(conn, "别出门", created_at=self.since - timedelta(minutes=1))
            self.assertIs(self.asked(conn), False)
            self.insert(conn, "今天别出门了")
            self.assertIs(self.asked(conn), True, "对照：同一事务里补一句，立刻算数")

    def test_only_an_instruction_not_to_go_out_counts(self) -> None:
        """词表只认祈使式（I 2026-09-24 裁定）：命中＝12 小时硬禁足。「谁在家」「谁休息」不是禁止——
        问句、主人说自己、甚至「休息一下再出发」（意思是要出门）都曾被判成禁足。每句单独一只干净的库，先断言这句真的落了库。"""
        cases = {"今天别出门了，外面下雨": True, "不要出去乱跑哦": True, "外面在下雨，别乱跑": True,  # 正例对照：闸还在工作
                 "今天在家吗": False, "今天在家吗？我带了点心回来": False, "我今天休息，陪你玩": False,
                 "我们今天休息一下再出发": False, "今天在家做了蛋糕": False, "我待在家里想你": False, "宝贝呆在家等我哦": False}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.setUp()
                with self.storage.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    self.insert(conn, text)
                    self.assertEqual([r["text"] for r in conn.execute("SELECT text FROM web_messages")], [text], "前提：这句真的落了库")
                    self.assertIs(self.asked(conn), expected)


if __name__ == "__main__":
    unittest.main()
