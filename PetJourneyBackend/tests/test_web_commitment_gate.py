"""出发闸那个谓词本身：`decision.commitment_gate`（TRV-02，合同 15 节）。

用**真实通讯器**与真实私聊消息，不打替身；出发那一侧的用例在 `test_web_wish_commit.py`。
不联网、不调用供应商、不新增付费。
"""

from __future__ import annotations

import unittest

from app.web_agent.decision import OWNER_ASKED_STAY_HOME, commitment_gate
from test_web_wish_commit import WishCommitBase


class CommitmentPredicateTests(WishCommitBase):
    """谓词本身（`decision.commitment_gate`）：用**真实通讯器**与真实私聊消息，不打替身。

    这是出发闸唯一认的那个信号。别的（家人建议去某处、待回复、工钱）**不在这里拼**——
    "建议去"不是"不许去"，拿它当闸语义是反的。
    """

    def say(self, text: str) -> None:
        """主人在私聊里说一句。**先断言这句话真的写进去了**——前提不成立的话，下面"没有拦住的承诺"只是空转。"""
        sent = self.owner.post(f"/communicator/{self.owner.pet_id}/messages",
                               {"text": text, "client_message_id": f"cm-{abs(hash(text)) % 10**8}"})
        self.assertEqual(sent.status_code, 200, sent.text)
        rows = self.rows("SELECT sender, channel FROM web_messages WHERE pet_id = ? AND sender = 'owner'", self.owner.pet_id)
        self.assertTrue(rows, "主人这句话没落库，后面的断言都不作数")
        self.assertEqual(rows[-1], ("owner", "private"), "闸只看私聊里主人说的话")

    def gate(self):
        return commitment_gate(self.web.communicator)

    def ask(self) -> str | None:
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")  # 闸是在写事务里问的，这里照同一个形态问
            return self.gate()(conn, self.owner.pet_id, self.clock.now)

    def test_the_owner_asking_to_stay_home_is_a_blocking_commitment(self) -> None:
        self.say("今天在家陪我吧，别出门啦")

        self.assertEqual(self.ask(), OWNER_ASKED_STAY_HOME)

    def test_nothing_said_means_no_blocking_commitment(self) -> None:
        self.assertIsNone(self.ask(), "没说过就不该拦")

    def test_a_family_suggestion_to_go_somewhere_is_not_a_blocker(self) -> None:
        """"有家人建议去 X" 是建议去，**不是**不许去——它绝不能变成出发闸。"""
        self.say("要不要去海边咖啡馆坐坐？")

        self.assertIsNone(self.ask(), "建议去某处不能被当成拦住出行的承诺")

    def test_saying_who_is_home_is_not_a_prohibition(self) -> None:
        """「今天在家」说的是**谁在家**，不是不许出门（I 2026-09-24 裁定，词表收紧到祈使式）。

        钉的是**不误判**：这句里主人在说**自己**，第一人称靠词表分不出来，
        而命中＝12 小时内一切自主出门被拒——半天不能动，撞「宠物自主、主人只建议」。

        **不是**在钉那条有意接受的**漏判**（「你今天在家好好休息」这种真叮嘱会被漏掉）。
        那一条 A 只写进 `stay_home.py` 的注释、**特意没有钉成用例**，理由是对的：
        将来换成显式按钮时，一条把漏判写成规格的用例会**挡住**改进——
        那就成了「反向的保护」。两条性质不同，别混：这里是误判，那里是漏判。
        """
        self.say("我今天休息，在家做了蛋糕")

        self.assertIsNone(self.ask(), "主人在说自己今天在家，不是禁止 TA 出门")

    def test_it_returns_a_kind_not_the_owners_words(self) -> None:
        """返回值会进 JourneyError 的 details，再往上可能出现在接口与日志里：**不能带出私聊原话**。"""
        secret = "今天别出门，我还没跟别人说过这件事"
        self.say(secret)

        self.assertEqual(self.ask(), OWNER_ASKED_STAY_HOME)
        self.assertNotIn(secret[:8], str(self.ask()), "只给种类名，不转述主人的话")

    def test_it_reads_inside_the_callers_transaction(self) -> None:
        """同一个写事务里刚写下的那句话，闸必须读得到——另开连接读的是事务开始前的快照（CR-C1）。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO web_messages (message_id, user_id, pet_id, sender, source_event_id, text, created_at, available_at, channel) "
                         "VALUES ('msg-inflight', ?, ?, 'owner', 'test:inflight', '今天别出门了吧', ?, ?, 'private')",
                         (self.owner.user_id, self.owner.pet_id, self.clock.now.isoformat(), self.clock.now.isoformat()))
            inside = self.gate()(conn, self.owner.pet_id, self.clock.now)      # 同一个 conn
            with self.app.state.storage.connect() as other:
                outside = self.gate()(other, self.owner.pet_id, self.clock.now)  # 另开连接
            conn.execute("ROLLBACK")

        self.assertEqual(inside, OWNER_ASKED_STAY_HOME, "同事务里刚说的话，闸要读得到")
        self.assertIsNone(outside, "另开连接读不到——这正是必须用调用方 conn 的原因")


if __name__ == "__main__":
    unittest.main()
