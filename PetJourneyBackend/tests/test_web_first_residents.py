"""首批 6 位原创居民（迁移 1800，用户 2026-09-24 下令上传）。

钉的是这批「住进星球」到底意味着什么，而不是「迁移跑过了」：

  · **身份**：领养卡、公开页都看得到；来源是原创星球居民；同一个候选编号永远同一只。
  · **大脑档案**：每只一份 DNA，**经正式读取路径能解析**（`PetDNA` 是 extra="forbid"，多一个键就整份读不出）；
    而且**真的在驱动行为**——行为画像从 DNA 读出，外向好奇的和慢热恋家的被读成不同的样子。
  · **心跳**：生活引擎为它们跑日子；从 0 块钱起步，**先挣后花**，不会先花一笔付不起的钱。
  · **形象**：打包在仓里的原创形象从公开路由出来，字节不变；**标成生成的原创形象、不是真实照片**。
  · **不做的事**：初始无流水、无行程；运营备注不进任何玩家可见字段；老的 8 位不被波及。
"""

from __future__ import annotations

import unittest

from app.web_pets.service import PLATFORM_PHOTO_DIR, PLATFORM_PHOTO_PREFIX, _platform_photo
from app.web_platform.migrations.m1800_first_residents import FIRST_RESIDENTS
from web_base import LUNCH_UTC, PREFIX, FakeClock, WebPlatformTestBase, settle_world

NEW = {r["candidate_id"]: r for r in FIRST_RESIDENTS}
OLD = ("adopt-lan", "adopt-lizi", "adopt-arong", "adopt-doudou", "adopt-qiuqiu", "adopt-mochi", "adopt-pudding", "adopt-yunduo")


class FirstResidentsBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()  # `self.web` 由基类的只读属性提供（= app.state.web）
        self.rows = {r["candidate_id"]: r for r in self.client.get(f"{PREFIX}/public/residents").json()}

    def pet(self, candidate_id: str) -> str:
        return self.rows[candidate_id]["pet_id"]


class IdentityTests(FirstResidentsBase):
    def test_all_six_live_on_the_planet_as_original_residents(self) -> None:
        self.assertEqual(set(NEW) - set(self.rows), set(), "有的居民没出现在公开居民名单里")
        for cid, data in NEW.items():
            with self.subTest(resident=data["name"]):
                row = self.rows[cid]
                self.assertEqual((row["name"], row["species"]), (data["name"], data["species"]))
                self.assertEqual(row["origin"], "adopted_original")
                self.assertEqual(row["source_note"], "原创星球居民", "玩家可见来源说明要写明是原创")

    def test_the_old_eight_are_untouched(self) -> None:
        """老居民一个不少，也**没有被顺手写上 DNA**——这批只动这 6 只。"""
        self.assertTrue(set(OLD) <= set(self.rows))
        for cid in OLD:
            with self.subTest(resident=cid):
                self.assertIsNone(self.web.dna.saved(self.pet(cid)), "老居民不该被这次迁移写上 DNA")

    def test_the_seaside_dreamer_lives_by_the_sea(self) -> None:
        """住处沿用 0240 的规则、从现有驿站里选，不虚构驿站：想看灯塔的小满住西贡海边，其余住中环。"""
        for cid in NEW:
            with self.subTest(resident=NEW[cid]["name"]):
                expected = "西贡海边" if cid == "adopt-xiaoman" else "中环"
                self.assertIn(expected, self.rows[cid]["residence"])


class BrainTests(FirstResidentsBase):
    def test_each_has_its_own_dna_readable_through_the_real_path(self) -> None:
        seen = set()
        for cid, data in NEW.items():
            with self.subTest(resident=data["name"]):
                record = self.web.dna.saved(self.pet(cid))  # 走 PetDNA.model_validate：多一个键这里就炸
                self.assertIsNotNone(record, "没有 DNA")
                self.assertEqual(record.dna.personality, data["dna"]["personality"])
                self.assertEqual(record.dna.habits, data["dna"]["habits"])
                self.assertEqual(record.dna.favorite_foods, [], "资料里没写爱吃什么——留空，不编")
                seen.add(record.dna.personality)
        self.assertEqual(len(seen), 6, "六只的性格不能是同一份复制")

    def test_personality_actually_shapes_behaviour(self) -> None:
        """**行为画像是从 DNA 读出来的**：外向好奇的花卷和慢热恋家的麦穗必须被读成不同的样子。

        只断言「有 DNA」的话，DNA 写进去却没人读也照样绿——这一条钉的是「读了、而且读出了差别」。
        """
        huajuan = self.web.profile_of(self.pet("adopt-huajuan"))
        maisui = self.web.profile_of(self.pet("adopt-maisui"))
        self.assertTrue(huajuan.curious, "花卷写着「外向、好奇」")
        self.assertEqual(huajuan.sociability, "social")
        self.assertFalse(maisui.curious)
        self.assertEqual(maisui.sociability, "homebody", "麦穗写着「认真、慢热、耐心」")
        self.assertGreater(huajuan.outings_per_day, maisui.outings_per_day)

    def test_ops_only_notes_never_reach_the_player(self) -> None:
        """资料里「备注（仅运营可见）」只留在迁移注释里：公开简介、卡片、DNA 里都不能出现。"""
        leaks = ("仅运营可见", "不表示已分配", "不预发", "不代表已经具有", "不推断疾病", "未绑定具体城市")
        for cid in NEW:
            profile = self.web.pets.profile(self.pet(cid))
            dna = self.web.dna.saved(self.pet(cid)).dna
            visible = " ".join([profile.bio or "", self.rows[cid]["personality"], self.rows[cid]["dream"],
                                dna.catchphrase or "", dna.voice_style or ""])
            for word in leaks:
                with self.subTest(resident=NEW[cid]["name"], word=word):
                    self.assertNotIn(word, visible)


class HeartbeatTests(FirstResidentsBase):
    def test_they_start_with_nothing_but_themselves(self) -> None:
        """钱包 0、没有行程、没有流水：背景是原创设定，不转成到访、工资或回忆。"""
        with self.app.state.storage.connect() as conn:
            for cid in NEW:
                pet_id = self.pet(cid)
                with self.subTest(resident=NEW[cid]["name"]):
                    for table in ("web_journeys", "economy_transactions", "web_pet_friends", "web_collection_items"):
                        count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE pet_id = ?", (pet_id,)).fetchone()[0]
                        self.assertEqual(count, 0, f"{table} 一开始就该是空的")

    def test_the_heartbeat_gives_them_a_life_and_they_earn_before_they_spend(self) -> None:
        """跑 3 天心跳（生活引擎 ＋ 结算）：每只都自己出过门；**第一笔流水只能是收入**——从 0 起步，付不起的钱不会先花。

        注意是 `life.run` ＋ `settle_world` 一起跑：`settle_world` 只结算旅程与消息、**不跑生活引擎**，
        单用它会得到「一趟都没出」的假象（写这条用例时真踩过）。
        """
        clock = FakeClock(LUNCH_UTC).install(self)
        for _ in range(3 * 48):
            self.web.life.run(clock.now)
            settle_world(self.app)
            clock.advance(minutes=30)
        with self.app.state.storage.connect() as conn:
            for cid in NEW:
                pet_id = self.pet(cid)
                with self.subTest(resident=NEW[cid]["name"]):
                    trips = conn.execute("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?", (pet_id,)).fetchone()[0]
                    self.assertGreater(trips, 0, "三天里一次都没出门，心跳没在为它过日子")
                    first = conn.execute("SELECT type FROM economy_transactions WHERE pet_id = ? ORDER BY created_at, rowid LIMIT 1",
                                         (pet_id,)).fetchone()
                    if first is not None:
                        self.assertEqual(first["type"], "web_job_income", "从 0 块钱开始，第一笔只能是挣来的")


class PhotoTests(FirstResidentsBase):
    def test_the_bundled_photo_is_served_publicly_byte_for_byte(self) -> None:
        for cid in NEW:
            with self.subTest(resident=NEW[cid]["name"]):
                response = self.client.get(f"{PREFIX}/public/media/pets/{self.pet(cid)}/photo")  # 未登录访客
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "image/png")
                self.assertEqual(response.content, (PLATFORM_PHOTO_DIR / f"{cid}.png").read_bytes())

    def test_it_is_marked_as_a_generated_design_not_a_real_photo(self) -> None:
        """`photo_generated = 1`：形象链把它当不了「主人上传的真实照片」，那道保护照旧生效。"""
        with self.app.state.storage.connect() as conn:
            for cid in NEW:
                row = conn.execute("SELECT photo_ref, photo_generated FROM web_pet_profiles WHERE pet_id = ?", (self.pet(cid),)).fetchone()
                with self.subTest(resident=NEW[cid]["name"]):
                    self.assertEqual(row["photo_generated"], 1)
                    self.assertTrue(row["photo_ref"].startswith(PLATFORM_PHOTO_PREFIX))

    def test_the_adoption_card_carries_the_photo_only_while_adoptable(self) -> None:
        """领养卡带公开照片地址；没照片的老居民为 null；**领养之后不再从领养卡给出**（与 pet_id 同一条规则）。"""
        viewer = self.user("card-viewer")
        cards = {c["candidate_id"]: c for c in viewer.get("/adoption/candidates").json()}
        for cid in NEW:
            with self.subTest(resident=NEW[cid]["name"]):
                self.assertEqual(cards[cid]["photo_url"], f"/api/v1/web/public/media/pets/{self.pet(cid)}/photo")
        self.assertIsNone(cards["adopt-lan"]["photo_url"], "没有照片的居民不能给一个打不开的地址")
        adopter = self.user("maisui-family")
        adopter.adopt_and_move_in("adopt-maisui")
        after = {c["candidate_id"]: c for c in viewer.get("/adoption/candidates").json()}
        self.assertIsNone(after["adopt-maisui"]["photo_url"], "领养后不再从领养卡暴露")

    def test_the_public_resident_list_shows_the_photo_to_visitors(self) -> None:
        """访客「先去星球上逛逛」看到的居民列表也带形象照；地址打得开、字节就是打包的那张；没照片的老居民为 null。"""
        for cid in NEW:
            with self.subTest(resident=NEW[cid]["name"]):
                url = self.rows[cid]["avatar_url"]
                self.assertEqual(url, f"/api/v1/web/public/media/pets/{self.pet(cid)}/photo")
                self.assertEqual(self.client.get(url).content, (PLATFORM_PHOTO_DIR / f"{cid}.png").read_bytes())
        self.assertIsNone(self.rows["adopt-lan"]["avatar_url"], "没有照片的居民不能给一个打不开的地址")

    def test_platform_refs_only_resolve_inside_the_bundled_folder(self) -> None:
        """前缀后面带路径、点点、隐藏文件、别的后缀的，一律当不存在——不做目录穿越。"""
        self.assertIsNotNone(_platform_photo(f"{PLATFORM_PHOTO_PREFIX}adopt-maisui.png"))
        for bad in ("../web_pets/service.py", "..\\service.py", "sub/adopt-maisui.png", ".hidden.png",
                    "adopt-maisui.png.exe", "", "nope.png", "C:/Windows/win.ini"):
            with self.subTest(ref=bad):
                self.assertIsNone(_platform_photo(f"{PLATFORM_PHOTO_PREFIX}{bad}"))


class AdoptionTests(FirstResidentsBase):
    def test_adoption_keeps_the_same_pet_and_its_brain(self) -> None:
        """领养只改变归属：pet_id 不变、DNA 不变；同一只只进一个家庭。"""
        before_pet, before_dna = self.pet("adopt-huajuan"), self.web.dna.saved(self.pet("adopt-huajuan")).dna
        first = self.user("huajuan-family")
        first.adopt_and_move_in("adopt-huajuan")
        self.assertEqual(first.pet_id, before_pet, "领养后还是同一只")
        self.assertEqual(self.web.dna.saved(before_pet).dna, before_dna, "领养不重置性格")
        second = self.user("too-late")
        refused = second.post("/adoption/adopt", {"candidate_id": "adopt-huajuan"})
        self.assertEqual(refused.status_code, 409, "同一只不能进两个家庭")


if __name__ == "__main__":
    unittest.main()
