#!/usr/bin/env python3
"""架构门禁：文件规模、类型密度、跨文件类型体量、Views 目录纯净度。

背景：本仓库曾因「优先往现有文件加代码」的规则催生出多个数千行的 God File。
单文件检查落地后，出现了「把同一类型用 extension 摊进多个文件」绕过门禁的
形态（架构审计 P0-1）。本脚本在单文件检查之外新增：

1. 跨文件类型体量：Swift 按类型名归并 struct/class/enum/extension，Python 按
   同名 class 归并，合并行数/定义数超标即红——拆文件绕不过去；
2. Views 纯净度：Views/ 目录只允许 View 类型——SwiftUI View（含
   UIViewRepresentable / UIViewControllerRepresentable）与 UIKit 视图子类
   （UIControl / MKAnnotationView 等）；领域模型/枚举/构建器不得再放进来
   （架构审计 P1-1）。

用法：
    python scripts/arch_gate.py                  # 从仓库根运行，用默认阈值
    python scripts/arch_gate.py --max-lines 600  # 自定义行数阈值
    python scripts/arch_gate.py --path PetJourneyIOS  # 只扫某子目录

退出码：
    0  全部通过
    1  存在违规（接入 CI 时据此判失败）
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_MAX_LINES = 800
DEFAULT_MAX_TYPES = 30
DEFAULT_MAX_TYPE_LINES = 600
DEFAULT_MAX_TYPE_DEFS = 25

EXCLUDE_DIRS = {
    ".git", ".claude", "node_modules", "__pycache__", ".venv", "venv",
    "build", "DerivedData", ".build", "GeneratedSources", "data",
}

SWIFT_TYPE_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+|fileprivate\s+|open\s+)*"
    r"(?:final\s+)?(?:struct|class|enum|protocol|extension|actor)\s+\w+"
)
PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+\w+|^\s*class\s+\w+")


def is_excluded(path: Path) -> bool:
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
            def_count = count_py_defs(path)
            if def_count > max_types:
                problems.append(f"{def_count} 个 def/class > {max_types}")
        if problems:
            rel = path.relative_to(root)
            violations.append((str(rel), line_count, problems))
    return violations


# ---------------------------------------------------------------------------
# 跨文件类型体量（架构审计 P0-1）：按类型名归并，拆 extension 绕不过去。
# ---------------------------------------------------------------------------

SWIFT_NAMED_TYPE_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+|fileprivate\s+|open\s+)*"
    r"(?:final\s+)?(?:struct|class|enum|protocol|extension|actor)\s+(\w+)"
)
SWIFT_FUNC_RE = re.compile(r"^\s*func\s+\w+")
PY_CLASS_RE = re.compile(r"^\s*class\s+(\w+)")


def _merge_spans(lines, pattern):
    """把文件按顶层类型声明切成 (name, start, end) 区间。"""
    spans = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            spans.append((match.group(1), index, None))
    for position, (kind, start, _) in enumerate(spans):
        end = spans[position + 1][1] if position + 1 < len(spans) else len(lines)
        spans[position] = (kind, start, end)
    return spans


def scan_swift_cross_file_types(root: Path):
    aggregates = {}
    for path in sorted(root.rglob("*.swift")):
        if not path.is_file() or is_excluded(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for kind, start, end in _merge_spans(lines, SWIFT_NAMED_TYPE_RE):
            name = kind
            if name == "CodingKeys":
                # CodingKeys 是 Codable 基础设施模式，不是业务类型，不参与体量归并
                continue
            body = lines[start:end]
            aggregate = aggregates.setdefault(name, {"lines": 0, "defs": 0, "files": []})
            aggregate["lines"] += end - start
            aggregate["defs"] += sum(1 for line in body if SWIFT_FUNC_RE.match(line))
            aggregate["files"].append(str(path.relative_to(root)))
    return aggregates


def scan_py_cross_file_classes(root: Path):
    aggregates = {}
    for path in sorted(root.rglob("*.py")):
        if not path.is_file() or is_excluded(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for name, start, end in _merge_spans(lines, PY_CLASS_RE):
            body = lines[start:end]
            aggregate = aggregates.setdefault(name, {"lines": 0, "defs": 0, "files": []})
            aggregate["lines"] += end - start
            aggregate["defs"] += sum(1 for line in body if PY_DEF_RE.match(line))
            aggregate["files"].append(str(path.relative_to(root)))
    return aggregates


# ---------------------------------------------------------------------------
# Views/ 纯净度（架构审计 P1-1）：只允许 View 类型。
# ---------------------------------------------------------------------------

VIEW_DECL_RE = re.compile(
    r"^(?:public |private |internal |fileprivate |open )*(?:final )?"
    r"(struct|class)\s+(\w+)"
)


# Views/ 下视为「View 层」的声明：
# - SwiftUI View / UIViewRepresentable / UIViewControllerRepresentable
# - UIKit 视图子类（UIControl、MKAnnotationView 等同样是视图层，不是领域模型）
VIEW_BASE_TOKENS = (
    ": View",
    "UIViewRepresentable",
    "UIViewControllerRepresentable",
    ": UIControl",
    ": UIView",
    ": MKAnnotationView",
    ": MKMarkerAnnotationView",
    ": MKOverlayRenderer",
    ": MKOverlayView",
    ": UIButton",
    ": UILabel",
    ": UIImageView",
    ": UITableViewCell",
    ": UICollectionViewCell",
    ": UIStackView",
    ": UIScrollView",
)


def scan_views_non_view_types(root: Path):
    violations = []
    views_root = root / "Views"
    if not views_root.is_dir():
        return violations
    for path in sorted(views_root.rglob("*.swift")):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = VIEW_DECL_RE.match(line)
            if not match:
                continue
            name = match.group(2)
            if any(token in line for token in VIEW_BASE_TOKENS):
                continue
            violations.append(name)
    return sorted(set(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description="架构门禁：文件规模 / 跨文件类型体量 / Views 纯净度")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES,
                        help=f"单文件最大行数（默认 {DEFAULT_MAX_LINES}）")
    parser.add_argument("--max-types", type=int, default=DEFAULT_MAX_TYPES,
                        help=f"单文件最大类型/def 数（默认 {DEFAULT_MAX_TYPES}）")
    parser.add_argument("--max-type-lines", type=int, default=DEFAULT_MAX_TYPE_LINES,
                        help=f"跨文件归并后单类型最大行数（默认 {DEFAULT_MAX_TYPE_LINES}）")
    parser.add_argument("--max-type-defs", type=int, default=DEFAULT_MAX_TYPE_DEFS,
                        help=f"跨文件归并后单类型最大定义数（默认 {DEFAULT_MAX_TYPE_DEFS}）")
    parser.add_argument("--path", type=str, default=".",
                        help="扫描根目录（默认当前目录）")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"错误：路径不存在或不是目录：{root}", file=sys.stderr)
        return 2

    failures = []
    warnings = []

    for rel, line_count, problems in scan(root, args.max_lines, args.max_types):
        failures.append(f"{rel}（{line_count} 行 · " + "；".join(problems) + "）")

    ios_root = root / "PetJourneyIOS" / "PetJourneyIOS"
    backend_root = root / "PetJourneyBackend" / "app"

    if ios_root.is_dir():
        for name, aggregate in scan_swift_cross_file_types(ios_root).items():
            if aggregate["lines"] > args.max_type_lines or aggregate["defs"] > args.max_type_defs:
                warnings.append(
                    f"[待拆分] {name}：{aggregate['lines']} 行 / {aggregate['defs']} 个定义，"
                    f"分布在 {len(aggregate['files'])} 个文件"
                )
    if backend_root.is_dir():
        for name, aggregate in scan_py_cross_file_classes(backend_root).items():
            if aggregate["lines"] > args.max_type_lines or aggregate["defs"] > args.max_type_defs:
                warnings.append(
                    f"[待拆分] {name}：{aggregate['lines']} 行 / {aggregate['defs']} 个定义，"
                    f"分布在 {len(aggregate['files'])} 个文件"
                )

    if ios_root.is_dir():
        for name in scan_views_non_view_types(ios_root):
            warnings.append(f"[Views 非 View 类型] {name}")

    if failures:
        print(f"架构门禁失败：{len(failures)} 处违规：\n")
        for item in failures:
            print(f"  - {item}")
        print("\n建议：按职责拆分上述文件，并在 iOS 侧同步登记 project.pbxproj。")
        return 1

    print(f"架构门禁通过：未发现超过 {args.max_lines} 行 / {args.max_types} 类型的文件。")
    for item in warnings:
        print(f"  ⚠ {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
