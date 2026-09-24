"""能力表与路由必须说同一件事（Q 独立验收；I 2026-09-24 批准新增）。

前端**按能力表决定显不显示**，所以两个方向都有产品后果：
  · 声明可用、路由却拒 → 用户看见一个点了就报错的功能；
  · 路由拒绝时引用的能力键不在表里 → 客户端**查不到这个键**，没法解释也没法降级。

**这份用例只读**：只读能力清单与路由的拒绝点，不改任何路由、不改任何能力声明。

先说清楚一件**不能**这样查的事（我第一版就错在这里）：
「某个能力声明 `available`，同时代码里存在引用它的拒绝点」**不等于**不一致——
`identity.password_registration` 的声明是 `available if settings.auth_secret else not_configured`，
而拒绝条件恰恰是 `if not settings.auth_secret`：**同一个开关**，声明为可用时那条路径根本进不去。
静态地比「声明」和「有没有拒绝点」必然误报。所以下面分两类：
  · 静态只查**键的存在性**（键必须可被客户端查到），这一类不依赖运行配置；
  · 配置联动的一致性用**单变量对照**验（同一件事只拨一个开关，看声明与行为是否一起翻面）。
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import unittest

from web_base import WebPlatformTestBase

from app.routers.web import WEB_ROUTER_MODULES, collect_capabilities
from app.schemas.web.common import WEB_API_PREFIX

# 从**被扫的那个包自己**取目录，不从本文件的 `__file__` 往上数：
# 后者把「这份用例放在哪里」变成了扫描范围的前提，文件一挪就静默扫空——
# 而扫空的结果是全绿。
ROUTERS_DIR = pathlib.Path(__import__("app.routers.web", fromlist=["__file__"]).__file__).parent

# 路由有**两种**拒绝形态，都要扫；只扫 `not_implemented(` 会漏掉四处，我第一版就漏了。
REFUSAL_PATTERNS = (
    re.compile(r"not_implemented\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"capability_unavailable\(\s*[\"']([^\"']+)[\"']"),
)


def refusal_keys() -> dict[str, set[str]]:
    """{能力键: {出现在哪些文件}}；`_shared.py` 是转发帮手本身，不算调用点。"""
    found: dict[str, set[str]] = {}
    for path in sorted(ROUTERS_DIR.rglob("*.py")):
        if path.name == "_shared.py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in REFUSAL_PATTERNS:
            for match in pattern.finditer(text):
                found.setdefault(match.group(1), set()).add(path.name)
    return found


class CapabilityRouteConsistency(WebPlatformTestBase):
    """能力表与路由的一致性。"""

    def test_every_capability_key_a_route_can_cite_is_in_the_list(self) -> None:
        """路由拒绝时引用的每个能力键，客户端都必须能在能力表里查到。

        查不到时前端只剩「调一次看看」这一条路：既不能提前隐藏入口，
        也没法把 `capability` 那个字段翻译成一句人话。
        """
        declared = {item.key for item in collect_capabilities(self.settings)}
        cited = refusal_keys()
        missing = {key: sorted(files) for key, files in cited.items() if key not in declared}
        self.assertEqual({}, missing,
                         "这些能力键路由会引用、能力表里却没有——客户端查不到它们：\n"
                         + "\n".join(f"  {k}（出现在 {', '.join(v)}）" for k, v in sorted(missing.items())))

    def test_every_mounted_web_router_module_is_in_the_collected_list(self) -> None:
        """挂上 app 的每个 web 路由模块，它的 `capabilities()` 都必须被收集到。

        这是上一格的**成因层**：`collect_capabilities` 只遍历 `WEB_ROUTER_MODULES`，
        而路由可以绕过那个元组、被别处 `include_router` 直接挂上去。
        绕过之后**路由活着、能力表里没有它**，而且两边都不会报错。
        """
        # 按**路径前缀**认「这是一条 web 路由」，不按模块名在不在 `app.routers.web.` 下。
        # 后者今天恰好覆盖全部 24 个模块，但那是**当下的事实、不是不变量**：
        # 哪天有人把 web 路由定义在别的包里，按模块名筛就会**静默漏掉**，而漏掉的结果是绿。
        registered = {module.__name__ for module in WEB_ROUTER_MODULES}
        mounted: dict[str, str] = {}
        for route in self.app.routes:
            path = getattr(route, "path", "")
            if not path.startswith(WEB_API_PREFIX):
                continue
            name = getattr(getattr(route, "endpoint", None), "__module__", "<取不到模块名>")
            if name not in registered:
                mounted.setdefault(name, path)
        self.assertEqual({}, mounted,
                         "这些 web 路由模块挂上了 app，却不在 WEB_ROUTER_MODULES 里，"
                         "于是它们声明的能力一条都不会进能力表：\n"
                         + "\n".join(f"  {m}（例如 {p}）" for m, p in sorted(mounted.items())))

    def test_no_capability_key_is_declared_twice(self) -> None:
        """同一个键只能由一个模块声明——两处声明时，排序一变前端读到的状态就换一个。"""
        seen: dict[str, list[str]] = {}
        for item in collect_capabilities(self.settings):
            seen.setdefault(item.key, []).append(item.module)
        duplicated = {key: mods for key, mods in seen.items() if len(mods) > 1}
        self.assertEqual({}, duplicated, f"能力键重复声明：{duplicated}")


class ConfigGatedCapabilityFlipsTogether(WebPlatformTestBase):
    """配置联动的那一类：**声明**和**闸**必须读同一个开关。

    用单变量对照来验——同一件事只拨 `auth_secret` 这一个开关，看两边是否一起翻面。
    这一格要防的是：有人改了闸的条件却没改声明（或反过来），
    于是能力表说「可以注册」而注册接口当场拒绝。**静态比对做不到这件事**（见文件开头）。
    """

    def test_password_registration_declaration_and_gate_read_the_same_switch(self) -> None:
        configured = dataclasses.replace(self.settings, auth_secret="q-consistency-probe")
        blank = dataclasses.replace(self.settings, auth_secret="")

        def status_of(settings) -> str:
            for item in collect_capabilities(settings):
                if item.key == "identity.password_registration":
                    return item.status.value
            self.fail("能力表里没有 identity.password_registration，这一格的前提就不成立")

        self.assertEqual("available", status_of(configured), "配了密钥就该声明可用")
        self.assertEqual("not_configured", status_of(blank), "没配密钥就该声明未配置")

        # 行为那一侧：同一个开关，注册接口必须跟着翻面。
        response = self.client.post("/api/v1/web/auth/register",
                                    json={"username": "q-cap-probe", "password": "QCapProbe-123456"})
        self.assertEqual(201, response.status_code, f"本轮配了密钥，注册必须走得通：{response.text}")

        self.settings.auth_secret = ""
        try:
            refused = self.client.post("/api/v1/web/auth/register",
                                       json={"username": "q-cap-probe-2", "password": "QCapProbe-123456"})
        finally:
            self.settings.auth_secret = configured.auth_secret
        # 状态码按状态分：`not_configured` → 503 NOT_CONFIGURED（配置问题，可能会好）；
        # `not_implemented` → 501 CAPABILITY_UNAVAILABLE（没做，等也没用）。前端靠这个分「再试」和「别试」。
        self.assertEqual(503, refused.status_code, f"密钥一撤，注册必须当场拒绝：{refused.text}")
        details = refused.json()["error"]["details"]
        self.assertEqual("identity.password_registration", details.get("capability"),
                         "拒绝时要指名**同一个**能力键，否则前端对不上号")
        # 真正的不变量在这一句：**拒绝时报的状态，必须等于同一份配置下能力表给的状态**。
        # 只断言「拒绝了」挡不住「表说未配置、拒绝时却报未实现」——那会让前端把「配一下就能用」显示成「这辈子别等了」。
        self.assertEqual(status_of(blank), details.get("status"),
                         "拒绝时报的状态和能力表给的状态必须是同一个")


if __name__ == "__main__":
    unittest.main()
