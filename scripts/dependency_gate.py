#!/usr/bin/env python3
"""后端依赖方向门禁（架构审计 P0-2 / P1-3）。

把 AGENTS.md「架构分层」变成机器检查：
- routers → engines → repositories → storage/infra；
- schemas / utils / config 是公共底层，不得反向 import 上层；
- 组合根（main.py / dependencies.py）可以 import 一切。

规则（按源模块分层）：
1. app.schemas.*           只允许 import app.schemas.*（+标准库/第三方）
2. app.repositories.* 与 app.storage   只允许 import app.schemas / app.repositories /
   app.utils / app.config
3. 底层工具（app.http_utils / app.config / app.utils / app.seeding /
   app.city_timezones）    只允许 import 底层工具集合与 app.schemas
4. 其余模块（引擎/根模块） 不得 import app.routers.*（引擎不依赖路由层）

退出码：0 通过；1 存在违规；2 无法解析。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = REPO_ROOT / "PetJourneyBackend" / "app"

ROUTER_PREFIX = "app.routers"
COMPOSITION_ROOTS = {"app.main", "app.dependencies"}

BOTTOM_ALLOWED = {
    "app.schemas",
    "app.config",
    "app.utils",
    "app.http_utils",
    "app.seeding",
    "app.city_timezones",
}

REPO_ALLOWED = {
    "app.schemas",
    "app.repositories",
    "app.utils",
    "app.config",
}


def module_name(path: Path) -> str:
    relative = path.relative_to(APP_ROOT)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return "app." + ".".join(parts) if parts else "app"


def imported_app_modules(path: Path) -> list[str]:
    """返回该文件 import 的全部 app.* 模块名（import 的完整模块路径）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                results.append(node.module)
    return [name for name in results if name == "app" or name.startswith("app.")]


def allowed(target: str, prefixes: set[str]) -> bool:
    return any(target == prefix or target.startswith(prefix + ".") for prefix in prefixes)


def main() -> int:
    if not APP_ROOT.is_dir():
        print(f"依赖方向门禁：找不到 {APP_ROOT}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        source = module_name(path)
        if source in COMPOSITION_ROOTS:
            continue
        for target in imported_app_modules(path):
            problem = None
            if source.startswith("app.schemas."):
                if not allowed(target, {"app.schemas"}):
                    problem = "schemas 只能 import schemas 内部"
            elif source.startswith("app.repositories.") or source == "app.storage":
                if not allowed(target, REPO_ALLOWED):
                    problem = "repositories/storage 只能 import schemas/repositories/utils/config"
            elif source in BOTTOM_ALLOWED:
                if not allowed(target, BOTTOM_ALLOWED):
                    problem = "底层工具不得 import 引擎/路由/仓储层"
            elif source.startswith(ROUTER_PREFIX):
                continue  # 路由层是顶层，可以 import 一切
            else:
                if target.startswith(ROUTER_PREFIX) or target == "app.main":
                    problem = "引擎/根模块不得反向 import 路由层"

            if problem:
                violations.append(f"{source} → {target}：{problem}")

    if violations:
        print(f"依赖方向门禁失败：{len(violations)} 处层次违规：")
        for item in violations:
            print(f"  - {item}")
        return 1

    print("依赖方向门禁通过：后端模块依赖方向符合 AGENTS.md 架构分层。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
