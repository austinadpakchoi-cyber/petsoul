"""服务端下发给玩家的用词（6c2b 2026-09-24 统一：货币只叫「星币」，「旅费」只当用途讲；叮嘱不叫「便笺」；不向玩家露技术词）。

前端的防回退测试扫不到服务端字符串，所以这里守：

  · 静态：用语法树只看这些模块里**会下发的字符串**（字符串常量与 f-string 的文字部分），跳过注释和文档字符串——
    开发者说明里写「旅费」「地图服务」不算违规，玩家看到的才算；
  · 行为：走真实接口，确认集市、出发报错、入住欢迎的账单事由确实是新说法。

「旅费」讲用途的说法（「「某地」的旅费」「攒一点旅费」「星币只用于 TA 在星球上的旅费」）是合规的，不拦。

**它能做与不能做的**（C 2026-09-24 提醒）：它验的是「这几种旧说法没有回来」，验不了「现在这几句说得对」——文字好不好仍要人判断。
只换给玩家看的话、不换原因码（例如 `LocalUnavailable("map_unavailable", …)` 的码一个字没动）：码给日志和排查，话给主人。
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from app.reception.guided import FOLLOW_UPS, HOST_DISCLOSURE, MODEL_DISCLOSURE
from web_base import WebPlatformTestBase

APP = Path(__file__).resolve().parent.parent / "app"
CURRENCY_AS_UNIT = re.compile(r"[+＋]\s*(\{\})?\s*旅费|付了\s*(\{\})?\s*旅费|旅费还不够|入住欢迎旅费")
TECH_MAP = re.compile(r"地图服务")
NOTE_OLD = re.compile(r"便笺")


def shipped_strings(path: Path) -> list[str]:
    """模块里会被执行到的字符串：常量与 f-string（占位写成 {}），不含模块／类／函数的文档字符串。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    found, inside_fstring = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                inside_fstring.add(id(value))
                parts.append(value.value if isinstance(value, ast.Constant) else "{}")
            found.append("".join(parts))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and id(node) not in inside_fstring:
            found.append(node.value)
    return found


class ShippedWordingTests(unittest.TestCase):
    def assert_clean(self, files: list[str], pattern: re.Pattern, why: str) -> None:
        for name in files:
            for text in shipped_strings(APP / name):
                with self.subTest(file=name, text=text[:40]):
                    self.assertIsNone(pattern.search(text), why)

    def test_money_is_called_star_coins_not_travel_fee(self) -> None:
        self.assert_clean(["web_market/service.py", "web_journey/service.py", "web_home/service.py"], CURRENCY_AS_UNIT,
                          "余额和数目的单位叫「星币」；「旅费」只当用途讲")

    def test_player_errors_do_not_mention_the_map_service(self) -> None:
        self.assert_clean(["web_journey/planning.py", "web_journey/local.py", "web_transport/daytrip.py"], TECH_MAP,
                          "玩家看到的是「找不到路线」，不是哪个服务坏了")

    def test_reception_says_care_notes_not_memo_slips(self) -> None:
        self.assert_clean(["reception/guided.py", "reception/store.py", "routers/web/reception.py"], NOTE_OLD, "叮嘱不叫「便笺」")

    def test_the_frontend_still_recognises_the_guided_disclosure(self) -> None:
        """前端 `ReceptionPage.tsx` 用 `/引导(?:便笺|叮嘱|记录)模式/` 认这句；改名不能让它失效。"""
        self.assertRegex(HOST_DISCLOSURE, r"引导(?:便笺|叮嘱|记录)模式")
        for text in (HOST_DISCLOSURE, MODEL_DISCLOSURE, *FOLLOW_UPS):
            self.assertNotIn("便笺", text)

    def test_the_scanner_itself_catches_the_old_wording(self) -> None:
        """对照：扫描器真能认出旧说法（否则上面几条会一直绿却什么都没守）。"""
        self.assertIsNotNone(CURRENCY_AS_UNIT.search("杂货铺收下了 {} 个{}，+{} 旅费。"))
        self.assertIsNotNone(CURRENCY_AS_UNIT.search("付了 {} 旅费。"))
        self.assertIsNone(CURRENCY_AS_UNIT.search("「{}」的旅费"), "讲用途的说法合规")
        tree_texts = shipped_strings(Path(__file__))
        self.assertIn("杂货铺收下了 {} 个{}，+{} 旅费。", tree_texts, "f-string 以外的常量也收进来了")


class LiveWordingTests(WebPlatformTestBase):
    def test_the_welcome_gift_is_star_coins_in_the_ledger(self) -> None:
        owner = self.user("wording-welcome")
        owner.adopt_and_move_in("adopt-lan")
        with self.app.state.storage.connect() as conn:
            reasons = [r["reason"] for r in conn.execute("SELECT reason FROM economy_transactions WHERE pet_id = ?", (owner.pet_id,))]
        self.assertIn("入住欢迎星币（每个家一次，不可交易）", reasons)

    def test_not_enough_money_to_depart_says_star_coins(self) -> None:
        owner = self.user("wording-broke")
        owner.adopt_and_move_in("adopt-lan")
        balance = self.web.economy.wallet(owner.pet_id).balance
        from app.schemas import EconomyTransactionType
        self.web.economy.apply(owner.pet_id, -balance, EconomyTransactionType.web_reward, "test:empty-wallet", reason="测试清空", source="test")
        refused = owner.post("/journey/depart", {"destination_key": "macau_ferry"})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("星币还不够", refused.json()["error"]["message"])

    def test_a_resident_on_the_way_to_a_job_titled_with_zai_reads_naturally(self) -> None:
        """行程标题常带方位词（「在花店帮忙」「去附近喝一杯」）：访客页不能拼出「在去在…」「在去去…」（6c2b 实测、C 补出后一半）。"""
        from types import SimpleNamespace
        from app.routers.web.public import _resident
        from app.schemas.web.pets import PetPresence
        from web_base import PREFIX
        row = next(r for r in self.web.residents.public_list())
        self.web.journeys.peek = lambda pet_id: (PetPresence.in_transit, SimpleNamespace(title="在花店帮忙"), None)
        request = SimpleNamespace(app=self.app)
        self.assertEqual(_resident(request, row).doing, "在去花店帮忙的路上")
        self.web.journeys.peek = lambda pet_id: (PetPresence.in_transit, SimpleNamespace(title="去附近喝一杯"), None)
        self.assertEqual(_resident(request, row).doing, "在去附近喝一杯的路上", "以「去」开头的也不能拼成「在去去」（C 补出）")
        self.web.journeys.peek = lambda pet_id: (PetPresence.in_transit, SimpleNamespace(title="港岛咖啡馆"), None)
        self.assertEqual(_resident(request, row).doing, "在去港岛咖啡馆的路上", "不以「在」开头的照旧")
        self.assertTrue(self.client.get(f"{PREFIX}/public/residents").status_code == 200)


if __name__ == "__main__":
    unittest.main()
