"""证件照整链两组用例共用的装置与替身。非测试模块。

**真实装配 ＋ 假供应商**（见 `character_fakes` 抬头），不联网、**0 次付费调用**。
拆成两个文件只是为了守 `arch_gate` 的每文件 30 个 def/class 上限（与 `pose_chain_base.py` 同一做法）：
`test_web_id_photo.py` 管链路本身，`test_web_id_photo_gates.py` 管各道门。
"""

from __future__ import annotations

import uuid

from character_fakes import FakeCharacterIllustrator, rgb_png, rgba_png
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase, tiny_png

from app.image_provider.models import GeneratedImage
from app.schemas.web.pets import PetOrigin, PetSpecies
from app.utils import utcnow
from app.web_character.id_photo import KIND
from app.web_pets.media import sanitize_image, store_private

HEAD = rgba_png(96, 144, lambda x, y: 20 <= x < 76 and y >= 10)  # 合格的透明头肩像
FLAT = rgb_png(512, 768, lambda x, y: (120, 90, 60) if 128 <= x < 384 and y >= 60 else (220, 232, 242))  # 合格的不透明直出


class IdPhotoIllustrator(FakeCharacterIllustrator):
    """**假的**供应商：证件照的请求（提示词里有「头部和上半身」）给证件照替身图，其余照角色替身图给。"""

    def __init__(self, photo: bytes = HEAD, **kwargs) -> None:
        super().__init__(**kwargs)
        self.photo = photo
        self.id_calls: list[dict] = []

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        if "头部和上半身" not in prompt:
            return super().render(prompt, reference, size=size, background=background)
        self.id_calls.append({"prompt": prompt, "size": size, "background": background, "reference": reference})
        return GeneratedImage(image_bytes=self.photo, mime_type="image/png", model="fake-id", provider="fake", source="b64")


class IdPhotoChainBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("id-owner")
        self.illustrator = IdPhotoIllustrator()
        self.web.character.illustrator = self.illustrator
        self.web.character.transparency_requested = True  # 与生产的 GPT 一致：请求透明底
        first = self.owner.upload_pet("先建家", "cat", photo=None)  # 先建家那只不带照片：不排任何生图
        self.household_id = self.web.households.memberships(self.owner.user_id)[0].household_id
        created = self.owner.upload_pet("小银", "cat", photo=tiny_png(), household_id=self.household_id)
        self.assertEqual((first.status_code, created.status_code), (201, 201), created.text)
        self.pet_id = created.json()["pet_id"]

    # ---- 辅助 ----
    @property
    def id_photo(self):
        return self.web.character.id_photo

    def query(self, sql: str, params: tuple = ()):
        with self.app.state.storage.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def rows(self, pet_id: str | None = None):
        return self.query("SELECT * FROM web_pet_id_photos WHERE pet_id = ? ORDER BY revision", (pet_id or self.pet_id,))

    def tasks(self):
        return self.query("SELECT * FROM web_tasks WHERE kind = ?", (KIND,))

    def state(self, pet_id: str | None = None) -> dict:
        response = self.owner.get(f"/pets/{pet_id or self.pet_id}/character")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id_photo"]

    def draw(self) -> None:
        self.id_photo.run_pending()

    def resident_with_archive_photo(self) -> str:
        """一只还在驿站、带真实档案照、没有家的居民（`adopted_real_archive`），外加指向它的领养名单。"""
        pet_id = f"PJ-{uuid.uuid4().hex[:8].upper()}"
        keeper = self.user("resident-keeper").user_id  # 宠物表对主人有外键：驿站那边要是个真账号
        clean, content_type = sanitize_image(tiny_png())
        photo_ref = store_private(self.web.pets.media_root, keeper, clean, content_type)
        with self.app.state.storage.connect() as conn:
            self.web.pets._insert_pet(conn, pet_id, keeper, "阿档", PetSpecies.cat, PetOrigin.adopted_real_archive,
                                      f"cand-{pet_id}", photo_ref, content_type, utcnow())
            conn.execute("INSERT INTO web_adoption_candidates (candidate_id, name, species, personality, dream, origin, source_note, "
                         "background_available, availability, adopted_pet_id, created_at) "
                         "VALUES (?, '阿档', 'cat', '安静', '晒太阳', 'adopted_real_archive', '公益档案', 1, 'available', ?, ?)",
                         (f"cand-{pet_id}", pet_id, utcnow().isoformat()))
        return pet_id
