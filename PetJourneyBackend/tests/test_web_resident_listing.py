"""撤下 / 放回待领养居民：玩家那一侧的整体用例（迁移 0260；方案第九批 adm1 与 I 对过，这是 I 补的两处加强）。

加强之二：撤下之后，**所有**对外列出待领养居民的地方与领养入口都拿不到 TA——领养卡（/adoption/candidates）、
访客页名单（/public/residents）、访客页单只（/public/pets/{id}）、居民对应的领养卡（candidate_for_pet，注册前选中伙伴的人靠它看还能不能领养）、
领养（/adoption/adopt → 找不到）；放回之后全都回来，领养照常成功。
加强之一：设置函数的结果分清「改了 / 本来就是这个状态 / 不符合条件 / 没有这位」。

写入口只有 `PetsService.set_listed_in`（运营后台在自己的事务里调它）；这里同样在一个事务里直接调，访客页缓存按后台的做法当场清掉。
用例文件由 adm1 新增（用户 2026-09-25 把撤下交给运营后台，I 确认可开工）。
"""

from __future__ import annotations

import unittest

from web_base import PREFIX, WebPlatformTestBase

from app.routers.web.public import invalidate as invalidate_public
from app.web_platform.uow import unit_of_work


class ResidentListingTests(WebPlatformTestBase):
    def available_resident(self) -> tuple[str, str]:
        with self.app.state.storage.connect() as conn:
            row = conn.execute(
                "SELECT r.pet_id, r.candidate_id FROM web_residents r JOIN web_adoption_candidates c ON c.candidate_id = r.candidate_id "
                "WHERE r.status = 'resident' AND r.kind = 'adoptable' AND c.availability = 'available' ORDER BY r.pet_id LIMIT 1").fetchone()
        self.assertIsNotNone(row, "前提：测试库里有还可以领养的驿站居民")
        return row["pet_id"], row["candidate_id"]

    def set_listed(self, candidate_id: str, listed: bool) -> str:
        with unit_of_work(self.app.state.storage) as conn:
            outcome = self.web.pets.set_listed_in(conn, candidate_id, listed)
        invalidate_public(self.app)  # 后台撤下 / 放回之后也是当场清访客页缓存
        return outcome

    def seen(self, viewer, pet_id: str, candidate_id: str) -> dict[str, bool]:
        return {
            "adoption_cards": candidate_id in {c["candidate_id"] for c in viewer.get("/adoption/candidates").json()},
            "visitor_list": pet_id in {r["pet_id"] for r in self.client.get(f"{PREFIX}/public/residents").json()},
            "visitor_page": self.client.get(f"{PREFIX}/public/pets/{pet_id}").status_code == 200,
            "pending_adoption": self.web.pets.candidate_for_pet(pet_id) == candidate_id,
        }

    def test_delisting_hides_the_resident_everywhere_and_relisting_brings_it_back(self):
        pet_id, candidate_id = self.available_resident()
        viewer = self.user("listing-viewer")
        everywhere = {"adoption_cards": True, "visitor_list": True, "visitor_page": True, "pending_adoption": True}
        self.assertEqual(self.seen(viewer, pet_id, candidate_id), everywhere, "对照：撤下之前每一处都看得到 TA")

        self.assertEqual(self.set_listed(candidate_id, False), "changed")
        self.assertEqual(self.seen(viewer, pet_id, candidate_id), {key: False for key in everywhere}, "撤下之后每一处都拿不到")
        refused = viewer.post("/adoption/adopt", {"candidate_id": candidate_id})
        self.assertEqual(refused.status_code, 404, refused.text)  # 按「找不到」处理，不加新错误码
        self.assertIn(pet_id, self.web.residents.living(), "撤下不是暂停：TA 照常在驿站生活")

        self.assertEqual(self.set_listed(candidate_id, True), "changed")
        self.assertEqual(self.seen(viewer, pet_id, candidate_id), everywhere, "放回之后每一处都回来")
        adopted = viewer.post("/adoption/adopt", {"candidate_id": candidate_id})
        self.assertEqual((adopted.status_code, adopted.json().get("pet_id")), (200, pet_id), "放回之后照常领养，身份不变")

    def test_the_setter_tells_changed_unchanged_ineligible_and_missing_apart(self):
        pet_id, candidate_id = self.available_resident()
        self.assertEqual(self.set_listed(candidate_id, True), "unchanged", "本来就在名单上")
        self.assertEqual(self.set_listed(candidate_id, False), "changed")
        self.assertEqual(self.set_listed(candidate_id, False), "unchanged", "本来就撤下了")
        self.assertEqual(self.set_listed("no-such-candidate", False), "missing")
        self.assertEqual(self.set_listed(candidate_id, True), "changed")
        self.user("listing-adopter").adopt_and_move_in(candidate_id)
        self.assertEqual(self.set_listed(candidate_id, False), "not_eligible", "已被领养：身份与经历必须连续，不能撤下")
        with self.app.state.storage.connect() as conn:
            listed = conn.execute("SELECT listed FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()["listed"]
        self.assertEqual(listed, 1, "不符合条件时一个字都不改")


if __name__ == "__main__":
    unittest.main()
