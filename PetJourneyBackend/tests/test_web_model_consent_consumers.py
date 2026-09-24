"""「模型回信」授权的消费点清单——一条**绊线**，不是正确性证明（C 2026-09-24 提议，I 持有）。

给主人看的那句话在 `app/schemas/web/identity.py` 的 `model_replies` 描述里，它要说清这个开关管哪些事
（私信回复与主动来信、明信片上的话、攻略措辞；第一位管理员的选择还管家庭频道措辞、到站明信片、TA 的思考用不用模型；
自主决策开着时叮嘱按用途进模型）。当天就发生过一次：清单漏了经 `family_model_enabled` 间接传下去的一处，
照漏项写出的描述给主人看时就少了一件事——**新增一处消费点，描述会静默变得不全，没有任何东西会响。**

这条做的事：按文件统计三种形状的出现次数（语法树里的真实使用，不数注释、不数夹着这个词的长字符串，不钉行号）——
  ① 值恰好是 `"model_replies"` 的字符串常量（下标、`.get(...)`、先提成常量、字典键都算）；
  ② 经 `family_model_enabled` 传下去；③ 经 `model_replies_of` 传下去。
次数一变就红。**红了该做的事**：去核那句描述还全不全，改好之后再更新下面的 EXPECTED。

**它不能做的事**：验不了那句话写得对不对——文字对不对仍要人判断。绿只说明「消费点没变」，不说明「描述是全的」。
扫不到的形状：把这个布尔值先存进别的对象、换个名字再传的（例如存进某个 dataclass 字段），这条看不见。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
INDIRECT = ("family_model_enabled", "model_replies_of")

EXPECTED = {
    "routers/web/identity.py": 1,               # 设置页展示
    "web_admin/diagnosis.py": 1,                # 运营诊断展示
    "web_admin/directory.py": 2,                # 运营用户详情展示（读＋字典键）
    "web_agent/decision/service_reader.py": 1,  # 叮嘱进自主决策上下文（按成员各自）
    "web_agent/proactive.py": 2,                # 家庭频道措辞（family_model_enabled）
    "web_agent_wiring.py": 7,                   # 攻略、明信片、主动来信、家庭频道、认知线（projector.model_enabled）
    "web_communicator/service.py": 2,           # 私信回复（model_replies_of）
    "web_composition.py": 3,                    # 私信回复接线、到站明信片写话（family_model_enabled）
    "web_identity/service.py": 6,               # 开关本身：用途授权元组、读、合并、写
}


def is_consumer(node: ast.AST) -> bool:
    """数「值恰好是 "model_replies" 的字符串常量」而不是只数下标：`prefs.get("model_replies")`、先提成常量再下标、
    字典键，都会被数进来（C 实测：只认下标时前两种会漏，而它们是随手就会写出的惯用法）。宁可多认——
    多认的代价是有人来看一眼，漏认的代价是描述静默变旧。SQL、文档字符串里夹着这个词的长字符串不算。"""
    if isinstance(node, ast.Constant):
        return node.value == "model_replies"
    if isinstance(node, ast.Attribute):
        return node.attr in INDIRECT
    return isinstance(node, ast.Name) and node.id == "family_model_enabled"


def consumers() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith(("schemas/", "web_platform/migrations/")):
            continue
        n = sum(1 for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if is_consumer(node))
        if n:
            counts[rel] = n
    return counts


class ModelConsentConsumerTripwire(unittest.TestCase):
    def test_every_model_consent_consumer_is_accounted_for(self) -> None:
        self.assertEqual(consumers(), EXPECTED,
                         "「模型回信」的消费点变了：先去核 app/schemas/web/identity.py 里 model_replies 的描述还全不全，"
                         "改好描述再更新本文件的 EXPECTED（绿只说明消费点没变，不说明描述是全的）")

    def test_the_counter_sees_all_three_shapes(self) -> None:
        """对照：三种形状各自真能被数到（否则上面那条可能一直绿却什么都没守）。"""
        lines = ['prefs(u)["model_replies"]', 'prefs(u).get("model_replies", False)', 'KEY = "model_replies"',
                 "proactive.family_model_enabled = f", "x = family_model_enabled", "c.model_replies_of(u)",
                 '"model_replies 夹在长字符串里"', "# family_model_enabled 只出现在注释里"]
        found = sum(1 for node in ast.walk(ast.parse("\n".join(lines))) if is_consumer(node))
        self.assertEqual(found, 6, "六种真实使用各数一次（含 .get 与提成常量）；夹在长字符串里、写在注释里的不算")


if __name__ == "__main__":
    unittest.main()
