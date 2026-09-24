"""证件照（CR-6C2B-IDPHOTO）的纯函数：提示词、校验、合成与裁切。纯单元：不联网、0 次付费调用、不依赖 Pillow。

提示词照 P《宠物证件照导演规范》§二 逐字编译。规范里能直接写成用例的不变量（§六）都钉在这里：
禁用字一个都不出现、没有宠物名字、推荐路线没有底色词；再拿 §七 的实测数（汉字数、身份锁位置）逐条对一遍——
那是 P 独立算的，**两边各算一遍、数对得上**。
校验照 §4.2 的 5 条（**不照搬角色那套**：证件照的胸口本来就该碰到底边）。

整链（上传即登记、泵领取、认领、重画、领养）在 `test_web_id_photo.py`。
"""

from __future__ import annotations

import re
import unittest

from character_fakes import rgba_png, rgb_png, transparent_png

from app.web_character import flatten, prompts, raster, validate
from app.web_character.id_photo import BACKDROP, IdPhotoService
from app.web_photo_director.catalog import APPEARANCE, IDENTITY_RULE, SPECIES, SPECIES_CN

SPEC_TAGS = ("silver_coat", "tabby_markings", "white_chest", "pink_nose", "upright_ears", "long_whiskers")


def head_and_shoulders(width: int = 96, height: int = 144, *, top: int = 10, left: int = 20, right: int = 76) -> bytes:
    """合格的透明证件照替身：头在上方、左右留空，胸口一直到底边。"""
    return rgba_png(width, height, lambda x, y: left <= x < right and y >= top)


class IdPhotoPromptTests(unittest.TestCase):
    def test_the_example_in_the_spec_is_reproduced(self) -> None:
        """P §七：猫、外貌词为空 277 个汉字、身份锁 19.5%；带测试宠物 6 个标签 313 字、17.1%。"""
        identity = IDENTITY_RULE.format(animal=SPECIES_CN["cat"])
        for tags, (characters, position) in (((), (277, 19.5)), (SPEC_TAGS, (313, 17.1))):
            text = prompts.build_id_photo_prompt("cat", tags)
            with self.subTest(tags=len(tags)):
                self.assertEqual(len(re.findall(r"[一-鿿]", text)), characters)
                self.assertEqual(round(100 * text.index(identity) / len(text), 1), position)

    def test_no_forbidden_word_ever_reaches_the_prompt(self) -> None:
        """写了「证件」「护照」「照片」，模型就会画出一张带边框、带字的证件卡（§一 第 2 条）。两条路线都查。"""
        for species in sorted(SPECIES):
            for tags in ((), SPEC_TAGS, tuple(sorted(APPEARANCE))):
                for opaque in (False, True):
                    text = prompts.build_id_photo_prompt(species, tags, opaque=opaque)
                    with self.subTest(species=species, tags=len(tags), opaque=opaque):
                        self.assertEqual([word for word in prompts.ID_PHOTO_FORBIDDEN if word in text], [])

    def test_the_recommended_route_has_no_colour_word_and_the_backup_has_exactly_one(self) -> None:
        """推荐路线请求透明底，底色在发布时合成——**提示词里一个颜色字都没有**；备选路线只换最后一句（§4.3）。"""
        transparent = prompts.build_id_photo_prompt("cat")
        opaque = prompts.build_id_photo_prompt("cat", opaque=True)
        self.assertNotIn("蓝", transparent)
        self.assertTrue(transparent.endswith("画面里只有这一只猫的头部和上半身，主体之外整片留空。"))
        self.assertTrue(opaque.endswith("画面里只有这一只猫的头部和上半身，身后是一整片均匀的浅灰蓝色，没有纹理、没有渐变。"))
        self.assertEqual(transparent.rsplit("。", 2)[0], opaque.rsplit("。", 2)[0], "除了最后一句，其余一字不变")

    def test_birds_are_shot_three_quarter_and_ears_follow_the_reference(self) -> None:
        """鸟的眼睛长在头两侧，正脸反而看不清；耳朵不写"竖起"，狗和兔子有垂耳的。"""
        self.assertIn("四分之三侧向镜头", prompts.build_id_photo_prompt("bird"))
        for species in ("cat", "dog", "rabbit"):
            self.assertIn("耳朵保持参考图里的样子", prompts.build_id_photo_prompt(species))
            self.assertNotIn("竖起", prompts.ID_PHOTO_FACE[species])


class IdPhotoCheckTests(unittest.TestCase):
    """P §4.2 的 5 条。门槛是按道理定的、未经真图验证——这里钉的是"每条都真的在判"，不是门槛本身对不对。"""

    def test_a_head_and_shoulders_cut_out_passes(self) -> None:
        self.assertTrue(validate.inspect_id_photo(head_and_shoulders(), "image/png").ok)

    def test_the_five_checks_each_refuse_their_own_case(self) -> None:
        cases = {
            validate.OPAQUE: rgba_png(96, 144, lambda x, y: True),  # ① 背景没抠掉
            validate.PHOTO_NOT_TO_BOTTOM: transparent_png(96, 144),  # ② 四边留空：拍成了全身
            validate.PHOTO_HEADROOM_OFF: head_and_shoulders(top=0),  # ③ 头顶顶到上边
            validate.PHOTO_HEAD_CUT_OFF: head_and_shoulders(left=0),  # ④ 上方正方形里贴到左边：头像会裁掉耳朵
            validate.MULTIPLE: rgba_png(96, 144, lambda x, y: (10 <= x < 40 or 56 <= x < 86) and y >= 10),  # ⑤ 两块
        }
        for reason, data in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(validate.inspect_id_photo(data, "image/png").reason, reason)

    def test_the_character_rule_would_have_refused_every_good_id_photo(self) -> None:
        """为什么不能照搬角色那套：合格的证件照胸口碰底边，角色校验一律判成被裁断。"""
        self.assertEqual(validate.inspect(head_and_shoulders(), "image/png").reason, validate.CUT_OFF)

    def test_the_opaque_route_refuses_small_square_and_blank_pictures(self) -> None:
        """不透明备选路线（§4.3）自己的三条：够大、是竖幅、不是整片单色。每条各有一张只违反它的图。"""
        subject = lambda x, y: (120, 90, 60) if 128 <= x < 384 and y >= 60 else (220, 232, 242)  # noqa: E731
        cases = {
            None: rgb_png(512, 768, subject),
            validate.PHOTO_TOO_SMALL: rgb_png(256, 384, subject),  # 竖幅、有主体，只是短边不到 512
            validate.PHOTO_WRONG_SHAPE: rgb_png(768, 768, subject),  # 够大、有主体，只是方的
            validate.PHOTO_BLANK: rgb_png(512, 768),  # 够大、竖幅，只是整片一个颜色
        }
        inspect = IdPhotoService(None)._inspect
        for reason, data in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(inspect(data, "image/png", False), reason)


class IdPhotoComposeTests(unittest.TestCase):
    def test_the_backdrop_is_exactly_the_ui_colour(self) -> None:
        """底色**分毫不差**是走透明路线的全部理由：透明处合成后正好是 #DCE8F2，主体原样。"""
        width, height, rgb = flatten.onto(head_and_shoulders(), BACKDROP)
        self.assertEqual((width, height), (96, 144))
        self.assertEqual(tuple(rgb[0:3]), BACKDROP, "左上角是背景")
        middle = (72 * width + 48) * 3
        self.assertEqual(tuple(rgb[middle:middle + 3]), (120, 90, 60), "主体原样")

    def test_the_card_crop_is_three_by_four_from_the_top(self) -> None:
        width, height, rgb = flatten.onto(head_and_shoulders(), BACKDROP)
        card = raster.top_portrait(width, height, rgb)
        self.assertEqual(validate._header(card)[:2], (96, 128), "1024 宽即 1024×1365；这里 96 宽即 96×128")
        self.assertEqual(validate._header(card)[3], 2, "8 位真彩，没有 alpha")

    def test_the_avatar_is_the_top_square_shrunk_to_256(self) -> None:
        width, height, rgb = flatten.onto(head_and_shoulders(), BACKDROP)
        avatar = raster.avatar_of(width, height, rgb)
        w, h, pixels = raster.decode(avatar)
        self.assertEqual((w, h), (256, 256))
        self.assertEqual(tuple(pixels[0:3]), BACKDROP)
        centre = (128 * 256 + 128) * 3
        self.assertEqual(tuple(pixels[centre:centre + 3]), (120, 90, 60), "头在上方正方形的中间")

    def test_decode_reads_opaque_truecolour_and_rejects_what_it_cannot(self) -> None:
        width, height, rgb = raster.decode(rgb_png(8, 12))
        self.assertEqual((width, height, tuple(rgb[0:3])), (8, 12, (200, 180, 160)))
        with self.assertRaises(ValueError):
            raster.decode(b"not a png at all")

    def test_blank_pictures_have_no_spread(self) -> None:
        width, height, rgb = raster.decode(rgb_png(16, 24))
        self.assertEqual(raster.luma_spread(width, height, rgb), 0)


if __name__ == "__main__":
    unittest.main()
