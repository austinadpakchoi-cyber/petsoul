"""W1 统一世界状态：**一家养两只**时的可见范围（从 `test_web_world_state.py` 拆出）。

2026-09-24 拆分原因：那个文件加上这一组之后 31 个定义、越过 `arch_gate` 的 30 上限。
**按职责拆**——那边是「一只宠物的四种事实、phase、pose、纯读」，这边是「家里有几只、谁能看见」。

（拆之前它红了一次门禁，是我自己加用例顶破的。记在这里是因为 B 今天说过：
这类红「位置在用例、成因在别处」，很容易被下一个跑门禁的人误判成自己弄的。）
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class MultiPetScopeTests(WebPlatformTestBase):
    """一家养两只时，**不指明 pet_id 也要能读**——W1 给的是「这个家」，不是「某一只」。

    2026-09-24 P0（6c2b 报）：第二只入住后 /map 整页 409 pet_required，玩家登录后被困在报错页。
    根因是 W1 照搬了 `require_pet` 的消歧规则，而**它根本没有歧义要消**：
    两只属于同一个家，返回的本来就是两只。

    **这不违背 `test_web_households.py` 那条「没有全局当前宠物」的既有意图**——
    那条针对的是**按宠物**的接口（`/home?pet_id=`），一只一份数据，不指明确实不知道要哪份。
    W1 是**按家**的：只需要知道是哪个家，而一家两只时家是唯一的。
    **跨多个家时仍然 409**，那才是真的有歧义。
    """

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("w1-two-pets")
        self.first = self.owner.upload_pet("年糕", "cat").json()["pet_id"]
        self.owner.move_in()
        household_id = self.owner.get("/households").json()[0]["household_id"]
        adopted = self.owner.post("/adoption/adopt", {"candidate_id": "adopt-lan", "household_id": household_id})
        self.assertEqual(adopted.status_code, 200, adopted.text)
        self.second = adopted.json()["pet_id"]
        moved = self.owner.post("/onboarding/move-in", {"pet_id": self.second})
        self.assertEqual(moved.status_code, 200, moved.text)

    def test_two_pets_in_one_home_do_not_need_pet_id(self) -> None:
        """**这条专门用来区分两种实现**：照搬 require_pet 的消歧规则会在这里 409。"""
        response = self.owner.get("/world/state")
        self.assertEqual(response.status_code, 200, f"一家两只不该要求指明是哪一只：{response.text}")
        self.assertEqual({p["pet_id"] for p in response.json()["pets"]}, {self.first, self.second},
                         "W1 给的是这个家的全部宠物，两只都要在")

    def test_an_explicit_pet_id_still_works_and_gives_the_whole_home(self) -> None:
        """显式指明仍然可用，且给的仍是全家——**指明的是「哪个家」，不是「只要这一只」**。"""
        for label, pet_id in (("第一只", self.first), ("第二只", self.second)):
            with self.subTest(pet=label):
                body = self.owner.get(f"/world/state?pet_id={pet_id}").json()
                self.assertEqual({p["pet_id"] for p in body["pets"]}, {self.first, self.second})


if __name__ == "__main__":
    unittest.main()
