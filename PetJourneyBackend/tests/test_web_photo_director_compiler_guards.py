"""`privacy.py` 两条真触发，`compiler.py` 四条**结构性不可达**的不变量。全程禁网。

分成两类写，因为它们证明的东西不一样：

* `PrivacyGuardTests` —— 真的走到那一行 `raise`，断言原因码。
* `CompilerUnreachableTests` —— `compiler.py` 那四条守卫在产品路径上**永远轮不到**，
  因为 `validate_context` 在每个入口都先跑过一遍，且两边的词表是同一个。
  这里钉的是**让它们不可达的那条不变量**：谁哪天把不变量改坏了，守卫就活了，
  这几条用例会当场失败并提示「请补真触发用例」。

**为什么不直接调 `compile_photo` 造一个触发**：那证明的是函数自己会拒，
不证明产品路径上会发生。把它写成"已覆盖"会让下一个人以为这条拒绝路径有证据，
而它其实一次都没在真实调用链上跑过。**宁可留成"已查明不可达＋不变量看着"，
也不要一条看起来绿、实际证明不了产品行为的用例。**

四条不可达的结构证明（读代码得出，不是"试了几种没触发"）：

1. `compiler.py:76` `capture_time_requires_timezone`
   —— `validation.py:89` 已拒 naive 时间，而 `director.direct`/`direct_with_rules`
      是唯二入口，两者都先调 `validate_context`。
2. `compiler.py:236` `reference_role_not_supported`
   —— `REFERENCE_ORDER` 与 `validate_references` 接受的三种 role **是同一个集合**。
3. `compiler.py:250` `identity_reference_must_be_first`
   —— `validation.py:146` 保证恰好一张 `pet_identity`，而 `REFERENCE_ORDER[0]`
      就是 `pet_identity`，排序后它必然排在第一个 slot。
4. `compiler.py:293` `directed_by_not_allowed`
   —— `compile_photo` 的全部调用点都在 `director.py`，三处传的都是**字面量**
      `"rule"` / `"model"`，没有任何变量路径。
"""
from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402

from harness import OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402
from app.web_photo_director.compiler import REFERENCE_ORDER  # noqa: E402

DIRECTOR_SOURCE = Path(__file__).resolve().parents[1] / "app" / "web_photo_director" / "director.py"


class PrivacyGuardTests(OfflineCase):
    def refuse(self, context, code: str) -> None:
        access = builders.build_access(context)
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, access)
        self.assertEqual(str(caught.exception), code)

    def test_dna_projected_for_another_purpose_is_refused(self):
        """按别的用途授权的 DNA 不能拿来画照片——授权是按用途给的，不是一次给全。"""
        context = builders.build_context("cafe")
        context = replace(context, dna=replace(context.dna, purpose="training_corpus"))
        self.refuse(context, "dna_purpose_or_version")

    def test_a_dna_value_that_is_not_a_list_of_strings_is_refused(self):
        """取值必须是字符串的列表。给一个裸字符串会被当成可迭代字符——

        那样 "calm" 会被拆成 c/a/l/m 四个"取值"，每个都不在词表里，
        报出来的却是词表错误，看不出真正的问题是类型给错了。
        """
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", dna_raw={"personality": "calm"})
        self.assertEqual(str(caught.exception), "dna_value_not_allowed")


class CompilerUnreachableTests(unittest.TestCase):
    """钉住让 `compiler.py` 四条守卫不可达的不变量。破坏其一，守卫即活。"""

    def test_naive_capture_time_is_already_refused_before_the_compiler(self):
        """不变量 1：场景校验先拒 naive 时间，编译器那层因此永远轮不到。"""
        scene = builders.build_scene(
            "cafe", "fx-pet-amber",
            captured_at=datetime(2026, 9, 23, 10, 0))  # 不带时区
        context = builders.build_context("cafe", scene=scene)
        with self.assertRaises(PhotoDirectorError) as caught:
            from app.web_photo_director.validation import validate_context
            validate_context(context, builders.build_access(context))
        self.assertEqual(
            str(caught.exception), "capture_time_requires_timezone",
            "若这里不再先拒 naive 时间，compiler.py:76 就变成可达，请补真触发用例")

    def test_the_compiler_knows_exactly_the_roles_validation_accepts(self):
        """不变量 2：两边是同一个 role 集合，所以编译器那条 role 守卫轮不到。"""
        accepted = {"pet_identity", "companion_identity", "place_environment"}
        self.assertEqual(
            set(REFERENCE_ORDER), accepted,
            "REFERENCE_ORDER 与 validate_references 接受的 role 不再一致，"
            "compiler.py:236 变成可达，请补真触发用例")

    def test_identity_sorts_first_by_construction(self):
        """不变量 3：身份图排第一是**排序**保证的，不是靠调用方摆对顺序。"""
        self.assertEqual(
            REFERENCE_ORDER[0], "pet_identity",
            "身份图不再排在 REFERENCE_ORDER 首位，compiler.py:250 变成可达，请补真触发用例")

    def test_every_compile_call_passes_a_literal_directed_by(self):
        """不变量 4：`directed_by` 的每个实参都是字面量，没有变量路径能带进别的值。"""
        tree = ast.parse(DIRECTOR_SOURCE.read_text(encoding="utf-8"))
        seen = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != "compile_photo":
                continue
            for kw in node.keywords:
                if kw.arg == "directed_by":
                    self.assertIsInstance(
                        kw.value, ast.Constant,
                        f"director.py:{node.lineno} 的 directed_by 不再是字面量，"
                        "compiler.py:293 变成可达，请补真触发用例")
                    seen.append(kw.value.value)
        self.assertTrue(seen, "没有找到任何 compile_photo 调用，这条不变量已失效")
        self.assertLessEqual(set(seen), {"rule", "model"}, f"出现了词表外的 directed_by：{seen}")


if __name__ == "__main__":
    unittest.main()
