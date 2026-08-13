#!/usr/bin/env python3
"""架构门禁：检查文件规模与类型密度，防止 God File / God Object 复发。

背景：本仓库曾因「优先往现有文件加代码」的规则催生出多个数千行的 God File
（Swift 侧三大 View 4000+ 行、PetModels 211 类型；Python 侧 storage/agent_engine
1500+ 行）。本脚本作为本地 + CI 通用护栏，对超标的单文件发出告警。

用法：
    python scripts/arch_gate.py                  # 从仓库根运行，用默认阈值
    python scripts/arch_gate.py --max-lines 600  # 自定义行数阈值
    python scripts/arch_gate.py --max-types 20   # 自定义单文件类型数阈值（仅 Swift）
    python scripts/arch_gate.py --path PetJourneyIOS  # 只扫某子目录

退出码：
    0  全部通过
    1  存在违规文件（接入 CI 时据此判失败）
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_MAX_LINES = 800
DEFAULT_MAX_TYPES = 30

# 不参与扫描的目录（生成物 / 依赖 / 版本控制）
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "build",
    "DerivedData",
    ".build",
    "GeneratedSources",
    "data",
}

# Swift 类型声明：覆盖 struct / class / final class / enum / protocol / extension / actor，
# 以及 public/private/internal/fileprivate/open 等访问修饰符前缀。
SWIFT_TYPE_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+|fileprivate\s+|open\s+)*"
    r"(?:final\s+)?(?:struct|class|enum|protocol|extension|actor)\s+\w+"
)

# Python 定义：顶层 def / class / async def（按缩进对齐到列首判断，避免误算方法内嵌套）。
PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+\w+|^\s*class\s+\w+")


def is_excluded(path: Path) -> bool:
    """任一祖先目录命中排除名单即跳过。"""
    return any(part in EXCLUDE_DIRS for part in path.parts)


def count_swift_types(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    return sum(1 for line in lines if SWIFT_TYPE_RE.match(line))


def count_py_defs(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    return sum(1 for line in lines if PY_DEF_RE.match(line))


def scan(root: Path, max_lines: int, max_types: int):
    violations = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or is_excluded(path):
            continue
        suffix = path.suffix.lower()
        if suffix not in (".swift", ".py"):
            continue

        try:
            line_count = sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
        except OSError:
            continue

        problems = []
        if line_count > max_lines:
            problems.append(f"{line_count} 行 > {max_lines}")

        if suffix == ".swift":
            type_count = count_swift_types(path)
            if type_count > max_types:
                problems.append(f"{type_count} 个类型 > {max_types}")
        elif suffix == ".py":
            # Python 侧按行数为主，另报单文件 def/class 密度供参考（阈值 = max_types）。
            def_count = count_py_defs(path)
            if def_count > max_types:
                problems.append(f"{def_count} 个 def/class > {max_types}")

        if problems:
            rel = path.relative_to(root)
            violations.append((str(rel), line_count, problems))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="架构门禁：文件规模与类型密度检查")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES,
                        help=f"单文件最大行数（默认 {DEFAULT_MAX_LINES}）")
    parser.add_argument("--max-types", type=int, default=DEFAULT_MAX_TYPES,
                        help=f"单文件最大类型/def 数（默认 {DEFAULT_MAX_TYPES}）")
    parser.add_argument("--path", type=str, default=".",
                        help="扫描根目录（默认当前目录）")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"错误：路径不存在或不是目录：{root}", file=sys.stderr)
        return 2

    violations = scan(root, args.max_lines, args.max_types)

    if not violations:
        print(f"架构门禁通过：未发现超过 {args.max_lines} 行 / {args.max_types} 类型的文件。")
        return 0

    print(f"架构门禁失败：发现 {len(violations)} 个违规文件（阈值 {args.max_lines} 行 / {args.max_types} 类型）：\n")
    for rel, line_count, problems in violations:
        print(f"  {rel}")
        print(f"      {line_count} 行 · " + "；".join(problems))
    print(f"\n建议：按职责拆分上述文件，并在 iOS 侧同步登记 project.pbxproj。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
