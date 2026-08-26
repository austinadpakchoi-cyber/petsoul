#!/usr/bin/env python3
"""前后端 wire 契约比对门禁（审计 P1-1 的 CI 脚本方案）。

把后端 Pydantic 模型的序列化字段名（alias 优先）与 iOS Codable 结构的
CodingKeys 逐对比较：后端下发的字段在 iOS 缺失即视为契约漂移，直接红。
这是上一轮「已漂移才补 fixture」的防复发升级——下一次漂移在 push 时就被拦截，
而不是等用户看到坏数据。

用法：
    python scripts/contract_diff.py            # 门禁模式：漂移即 exit 1
    python scripts/contract_diff.py --report   # 打印全部配对表（含 iOS 多出的字段）

配对规则（同名结构体/类）：
- 后端 wire 名 = Field(alias) / serialization_alias，否则字段名（snake_case）
- iOS wire 名 = CodingKeys 里的字符串；没有 CodingKeys 的结构用 snake_case(属性名)
- 只报「后端有、iOS 没有」的缺失；iOS 多出的字段（计算属性、展示辅助）只提示不报错
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "PetJourneyBackend"
IOS_MODELS_DIR = REPO_ROOT / "PetJourneyIOS" / "PetJourneyIOS" / "Models"


def snake_case(name: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def collect_backend_models() -> dict[str, set[str]]:
    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)
    try:
        import app.schemas as package_schemas
        import app.communicator.schemas as communicator_schemas
    except Exception as exc:  # pragma: no cover - 环境问题
        print(f"契约门禁：无法导入后端模型（{exc}）")
        sys.exit(2)

    from pydantic import BaseModel

    models: dict[str, set[str]] = {}
    seen: set[int] = set()
    for module in (package_schemas, communicator_schemas):
        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type) or not issubclass(obj, BaseModel):
                continue
            if not obj.__module__.startswith("app"):
                continue
            if id(obj) in seen or name in models:
                continue
            seen.add(id(obj))
            wire_names: set[str] = set()
            for field_name, field_info in obj.model_fields.items():
                wire = field_info.serialization_alias or field_info.alias or field_name
                if isinstance(wire, str) and wire:
                    wire_names.add(wire)
            if wire_names:
                models[name] = wire_names
    return models


STRUCT_RE = re.compile(
    r"^[ \t]*(?:public\s+|internal\s+|private\s+|fileprivate\s+)?struct\s+(\w+)\s*:",
    re.MULTILINE,
)
CODABLE_RE = re.compile(r"\bCodable\b")
VAR_RE = re.compile(r"^\s*var\s+(\w+)\s*:")
CASE_RE = re.compile(r"^\s*case\s+(\w+)(?:\s*=\s*\"([^\"]+)\")?", re.MULTILINE)


def collect_ios_models() -> dict[str, tuple[set[str], bool]]:
    """返回 {结构名: (wire 名集合, 是否有 CodingKeys)}。"""
    models: dict[str, tuple[set[str], bool]] = {}
    for swift_file in sorted(IOS_MODELS_DIR.glob("*.swift")):
        text = swift_file.read_text(encoding="utf-8")
        for match in STRUCT_RE.finditer(text):
            struct_name = match.group(1)
            declaration = text[match.start(): text.find("\n", match.start())]
            if not CODABLE_RE.search(declaration):
                continue
            body = _struct_body(text, match.end())
            has_coding_keys, coding_wires = _coding_key_wires(body)
            if has_coding_keys:
                models[struct_name] = (coding_wires, True)
            else:
                props = {
                    snake_case(var_match.group(1))
                    for line in body.splitlines()
                    if "{" not in line
                    for var_match in [VAR_RE.match(line)]
                    if var_match
                }
                models[struct_name] = (props, False)
    return models


def _struct_body(text: str, start: int) -> str:
    """从 struct 声明之后截取花括号平衡的正文。"""
    depth = 0
    index = text.find("{", start)
    if index == -1:
        return ""
    body_start = index + 1
    for cursor in range(index, len(text)):
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return text[body_start:cursor]
    return text[body_start:]


def _coding_key_wires(body: str) -> tuple[bool, set[str]]:
    match = re.search(r"enum\s+CodingKeys\s*:\s*String\s*,\s*CodingKey\s*\{(.*?)\n\s*\}", body, re.S)
    if not match:
        return False, set()
    wires: set[str] = set()
    for case_match in CASE_RE.finditer(match.group(1)):
        wires.add(case_match.group(2) or case_match.group(1))
    return True, wires


def main() -> int:
    parser = argparse.ArgumentParser(description="前后端 wire 契约比对门禁")
    parser.add_argument("--report", action="store_true", help="打印完整配对表")
    args = parser.parse_args()

    backend = collect_backend_models()
    ios = collect_ios_models()

    missing: list[str] = []
    pairs = 0
    for name in sorted(backend):
        if name not in ios:
            continue
        pairs += 1
        backend_wires = backend[name]
        ios_wires, _ = ios[name]
        for wire in sorted(backend_wires):
            if wire not in ios_wires:
                missing.append(f"{name}.{wire}")

    if args.report:
        print(f"配对模型：{pairs}（后端 {len(backend)} × iOS {len(ios)}）\n")
        for name in sorted(set(backend) & set(ios)):
            backend_wires = backend[name]
            ios_wires, has_keys = ios[name]
            extra = sorted(ios_wires - backend_wires)
            suffix = f"   iOS 多出: {extra}" if extra else ""
            print(f"{name}: 后端 {len(backend_wires)} 字段 / iOS {len(ios_wires)} wire{('(无CodingKeys)' if not has_keys else '')}{suffix}")

    if missing:
        print(f"契约门禁失败：{len(missing)} 处后端字段在 iOS 未建模：")
        for item in missing:
            print(f"  - {item}")
        return 1

    print(f"契约门禁通过：{pairs} 个同名配对全部对齐（后端 {len(backend)} 模型 / iOS {len(ios)} 结构）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
