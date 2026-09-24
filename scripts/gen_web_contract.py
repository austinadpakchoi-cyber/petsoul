#!/usr/bin/env python3
"""网页契约生成与漂移门禁（WEB-CONTRACT v0.1）。

唯一来源是后端 ``PetJourneyBackend/app/schemas/web``（Pydantic）与 ``/api/v1/web`` 路由表。
生成物：
- ``PetJourneyWeb/src/shared/contracts/generated.ts``：前端 DTO / 枚举 / 端点表
- ``docs/contracts/generated/web-contract.schema.json``：JSON Schema
- ``docs/contracts/generated/WEB-ROUTES.md``：路由、权限、CSRF、幂等一览

用法（仓库根目录）：
    python scripts/gen_web_contract.py            # 重新生成
    python scripts/gen_web_contract.py --check    # 门禁：生成物与代码不一致即 exit 1；
                                                  # 若存在 PetJourneyWeb/.runtime/contract-examples/*.json，
                                                  # 同时用 Pydantic 校验前端 fixture 导出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import types
import typing
from datetime import date, datetime
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "PetJourneyBackend"
TS_OUT = REPO_ROOT / "PetJourneyWeb" / "src" / "shared" / "contracts" / "generated.ts"
SCHEMA_OUT = REPO_ROOT / "docs" / "contracts" / "generated" / "web-contract.schema.json"
ROUTES_OUT = REPO_ROOT / "docs" / "contracts" / "generated" / "WEB-ROUTES.md"
EXAMPLES_DIRS = (
    REPO_ROOT / "PetJourneyWeb" / ".runtime" / "contract-examples",  # npm test 导出的最新 fixture
    REPO_ROOT / "docs" / "contracts" / "examples",  # 已发布的契约样例
)


def load_backend():
    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)
    from pydantic import BaseModel

    import app.schemas.web as web_schemas

    return web_schemas, BaseModel


def collect(web_schemas, base_model):
    enums: list[type[Enum]] = []
    models: list[type] = []
    for module in web_schemas.CONTRACT_MODULES:
        for name in module.__all__:
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Enum):
                enums.append(obj)
            elif isinstance(obj, type) and issubclass(obj, base_model) and obj.__name__ != "WebModel":
                models.append(obj)
    # 生成的 TypeScript 里枚举与模型共用一个命名空间：重名会让前端类型互相覆盖，直接拒绝生成。
    owners: dict[str, str] = {}
    for obj in [*enums, *models]:
        where = f"{obj.__module__}.{obj.__qualname__}"
        if owners.setdefault(obj.__name__, where) != where:
            raise SystemExit(f"契约类型重名：{obj.__name__}（{owners[obj.__name__]} 与 {where}），请改名")
    return enums, models


def ts_type(annotation, base_model) -> str:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        parts = [ts_type(arg, base_model) for arg in args if arg is not type(None)]
        if type(None) in args:
            parts.append("null")
        return " | ".join(parts)
    if origin in (list, tuple, set, frozenset):
        inner = ts_type(args[0], base_model)
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    if origin is dict:
        return f"Record<string, {ts_type(args[1], base_model)}>"
    if annotation is typing.Any:
        return "unknown"
    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return annotation.__name__
        if issubclass(annotation, base_model):
            return annotation.__name__
        if annotation is bool:
            return "boolean"
        if annotation in (int, float):
            return "number"
        if annotation is str:
            return "string"
        if annotation in (datetime,):
            return "IsoDateTime"
        if annotation in (date,):
            return "IsoDate"
    raise TypeError(f"无法映射类型 {annotation!r}")


def dependency_calls(dependant) -> set[str]:
    names: set[str] = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", ""))
        names |= dependency_calls(dep)
    return names


def collect_routes():
    from app.config import Settings
    from app.main import create_app
    from app.schemas.web.common import WEB_API_PREFIX

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            database_path=Path(tmp) / "contract.sqlite3",
            upload_dir=Path(tmp) / "uploads",
            scheduler_enabled=False,
        )
        app = create_app(settings)
    routes = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(WEB_API_PREFIX):
            continue
        deps = dependency_calls(route.dependant)
        body = route.body_field.type_.__name__ if getattr(route, "body_field", None) is not None else None
        response = route.response_model
        response_name = None
        if response is not None:
            response_name = ts_type(response, __import__("pydantic").BaseModel)
        for method in sorted(route.methods):
            routes.append(
                {
                    "method": method,
                    "path": path[len(WEB_API_PREFIX):] or "/",
                    "name": route.name,
                    "request": body,
                    "response": response_name,
                    "status": route.status_code or 200,
                    "auth": "required" if "require_principal" in deps else ("optional" if "optional_principal" in deps else "public"),
                    "csrf": "require_csrf" in deps,
                    "idempotency": "require_idempotency_key" in deps,
                }
            )
    routes.sort(key=lambda item: (item["path"], item["method"]))
    return routes


def render_ts(enums, models, routes, base_model) -> str:
    from app.schemas.web.common import WEB_API_PREFIX, WEB_CONTRACT_VERSION

    lines = [
        "/* eslint-disable */",
        "// 由 scripts/gen_web_contract.py 从 PetJourneyBackend/app/schemas/web 生成，请勿手改。",
        "// 修改契约：改 Python DTO → 运行 `npm run contract:gen` → 更新 WEB-CONTRACT 文档。",
        "",
        f'export const WEB_CONTRACT_VERSION = "{WEB_CONTRACT_VERSION}";',
        f'export const WEB_API_PREFIX = "{WEB_API_PREFIX}";',
        "",
        "/** UTC ISO 8601，例如 2026-09-22T07:35:00Z */",
        "export type IsoDateTime = string;",
        "/** YYYY-MM-DD */",
        "export type IsoDate = string;",
        "/** 把有服务端默认值的字段变为可选：用于请求体。 */",
        "export type WithOptional<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;",
        "",
    ]
    for enum in enums:
        values = [member.value for member in enum]
        lines.append(f"export type {enum.__name__} = {' | '.join(json.dumps(v, ensure_ascii=False) for v in values)};")
        lines.append(
            f"export const {enum.__name__}Values = [{', '.join(json.dumps(v, ensure_ascii=False) for v in values)}] as const;"
        )
        lines.append("")
    for model in models:
        doc = (model.__doc__ or "").strip().splitlines()
        if doc and doc[0]:
            lines.append(f"/** {doc[0]} */")
        lines.append(f"export interface {model.__name__} {{")
        defaulted = []
        for field_name, field in model.model_fields.items():
            ts = ts_type(field.annotation, base_model)
            if field.description:
                lines.append(f"  /** {field.description} */")
            # 追加字段（json_schema_extra={"x-additive": True}）在前端类型里是可选属性：旧客户端/fixture 字面量不因新增字段而编译失败
            extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
            optional_mark = "?" if extra.get("x-additive") else ""
            lines.append(f"  {field_name}{optional_mark}: {ts};")
            if not field.is_required():
                defaulted.append(field_name)
        lines.append("}")
        if defaulted:
            keys = " | ".join(json.dumps(name) for name in defaulted)
            lines.append(f"export type {model.__name__}Input = WithOptional<{model.__name__}, {keys}>;")
        else:
            lines.append(f"export type {model.__name__}Input = {model.__name__};")
        lines.append("")
    lines.append("export interface WebEndpoint {")
    lines.append("  method: \"GET\" | \"POST\" | \"PUT\" | \"PATCH\" | \"DELETE\";")
    lines.append("  path: string;")
    lines.append("  auth: \"public\" | \"optional\" | \"required\";")
    lines.append("  csrf: boolean;")
    lines.append("  idempotency: boolean;")
    lines.append("}")
    lines.append("")
    lines.append("export const WEB_ENDPOINTS = {")
    for route in routes:
        lines.append(
            f"  {json.dumps(route['name'])}: {{ method: {json.dumps(route['method'])}, path: {json.dumps(route['path'])}, "
            f"auth: {json.dumps(route['auth'])}, csrf: {str(route['csrf']).lower()}, idempotency: {str(route['idempotency']).lower()} }},"
        )
    lines.append("} as const satisfies Record<string, WebEndpoint>;")
    lines.append("export type WebEndpointName = keyof typeof WEB_ENDPOINTS;")
    lines.append("")
    return "\n".join(lines)


def render_schema(models) -> str:
    from pydantic.json_schema import models_json_schema

    _, schema = models_json_schema([(model, "serialization") for model in models], title="PetSoul Web Contract v0.1")
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_routes_md(routes) -> str:
    lines = [
        "# /api/v1/web 路由表（生成物）",
        "",
        "由 `scripts/gen_web_contract.py` 从 FastAPI 实际注册的路由生成，请勿手改。语义说明见 `../WEB-CONTRACT-v0.1.md`。",
        "",
        "| 方法 | 路径（前缀 /api/v1/web） | 请求体 | 响应 | 成功状态 | 登录 | CSRF | 幂等键 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in routes:
        lines.append(
            f"| {r['method']} | `{r['path']}` | {r['request'] or '—'} | {r['response'] or '—'} | {r['status']} | "
            f"{r['auth']} | {'是' if r['csrf'] else '—'} | {'必填' if r['idempotency'] else '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def validate_examples(models) -> list[str]:
    problems: list[str] = []
    by_name = {model.__name__: model for model in models}
    paths = [path for folder in EXAMPLES_DIRS if folder.exists() for path in sorted(folder.glob("*.json"))]
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload:
            model = by_name.get(entry["type"])
            if model is None:
                problems.append(f"{path.name}: 未知类型 {entry['type']}")
                continue
            try:
                model.model_validate(entry["value"])
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{path.name}:{entry.get('name')} → {entry['type']} 校验失败：{exc}")
    return problems


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    web_schemas, base_model = load_backend()
    enums, models = collect(web_schemas, base_model)
    routes = collect_routes()
    outputs = {
        TS_OUT: render_ts(enums, models, routes, base_model),
        SCHEMA_OUT: render_schema(models),
        ROUTES_OUT: render_routes_md(routes),
    }
    if args.check:
        stale = [str(path.relative_to(REPO_ROOT)) for path, text in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
        problems = validate_examples(models)
        for item in stale:
            print(f"契约生成物已过期：{item}（运行 python scripts/gen_web_contract.py）")
        for item in problems:
            print(f"fixture 导出不符合契约：{item}")
        example_count = sum(len(list(folder.glob("*.json"))) for folder in EXAMPLES_DIRS if folder.exists())
        print(
            f"web contract: {len(enums)} enums, {len(models)} models, {len(routes)} routes; "
            f"fixture export files checked: {example_count}"
        )
        return 1 if stale or problems else 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"generated {len(enums)} enums, {len(models)} models, {len(routes)} routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
