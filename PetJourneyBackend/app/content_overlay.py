"""运营发布版本对游戏内置目录的覆盖层（底层工具，只依赖标准库）。

为什么存在：冒险模板、作物、打工岗位这些目录原本是 Python 常量。运营要能发布新版本，
又必须保证"已经发生过的事实不被静默改写"。折中办法是：**目录在被取用的那一刻**问一次
已发布版本，取不到就用内置值。至于会不会改写既有事实，由各目录**可发布哪些字段**来保证
（见 `app/web_admin/content.py` 的字段白名单），不是靠这里。

用法（各领域自己声明合并规则，本模块不认识任何领域类型）：

    CROPS = OverlayCatalog("crop", merge_crop, {...})   # CROPS[key] / .get / .values 都带覆盖

没有注册解析器时（独立任务进程、旧测试）行为与过去**完全一致**：一次查询都不发生。
解析器抛异常时回落到内置值——后台读不出来不能让世界推进失败。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterator

logger = logging.getLogger("petsoul.content_overlay")

# (content_type, slug) -> 已发布正文 dict，或 None。由组合根注册（app/web_admin 提供实现）。
Resolver = Callable[[str, str], "dict[str, Any] | None"]
_resolver: Resolver | None = None


def set_resolver(resolver: Resolver | None) -> None:
    global _resolver
    _resolver = resolver


def published(content_type: str, slug: str) -> dict[str, Any] | None:
    if _resolver is None:
        return None
    try:
        return _resolver(content_type, slug)
    except Exception:  # noqa: BLE001 - 发布表读不到：用内置值，不影响世界
        logger.warning("content overlay lookup failed type=%s slug=%s", content_type, slug)
        return None


class OverlayCatalog(dict):
    """内置目录 + 运营发布覆盖层。

    `merge(base, body)` 由各领域给出：它只读 body 里**该领域允许发布的字段**，其余一律用 base。
    读接口（`[]` / `get` / `values` / `items`）全部带覆盖；`base_of` 明确取内置值（不覆盖）。
    键集合永远是内置的那一份——运营不能凭空造出新条目，只能给已有条目发新版本。
    """

    __slots__ = ("_content_type", "_merge")

    def __init__(self, content_type: str, merge: Callable[[Any, dict[str, Any]], Any], items: dict[str, Any]) -> None:
        super().__init__(items)
        self._content_type = content_type
        self._merge = merge

    @property
    def content_type(self) -> str:
        return self._content_type

    def base_of(self, key: str) -> Any:
        """内置值，不带覆盖。给"和已发布版本比差异"用。"""
        return dict.__getitem__(self, key)

    def __getitem__(self, key: str) -> Any:
        base = dict.__getitem__(self, key)
        body = published(self._content_type, key)
        if not body:
            return base
        try:
            return self._merge(base, body)
        except Exception:  # noqa: BLE001 - 合并不成立（字段类型不对等）：用内置值，别让世界崩在目录上
            logger.warning("content overlay merge failed type=%s slug=%s", self._content_type, key)
            return base

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        if not dict.__contains__(self, key):
            return default
        return self[key]

    def values(self) -> list[Any]:  # type: ignore[override]
        return [self[key] for key in dict.keys(self)]

    def items(self) -> list[tuple[str, Any]]:  # type: ignore[override]
        return [(key, self[key]) for key in dict.keys(self)]

    def __iter__(self) -> Iterator[str]:
        return dict.__iter__(self)
