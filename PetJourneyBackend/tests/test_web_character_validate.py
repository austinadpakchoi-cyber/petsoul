"""角色图校验与角色提示词的**纯单元**用例：不建应用、不开库、不联网、0 次付费调用。

从 `test_web_character_publish.py` 拆出来的，两个理由：

  - **职责不同**：那一套管"什么情况下不许发布"（要整机装配），这一套管"这张图本身合不合格"；
  - 那个文件当时 31 个 def/class，**超了 `arch_gate` 的 30 上限**，本来也得拆。

判据照 P（ada5）《世界角色导演模式》4.2，
`docs/coordination/WORLD-CHARACTER-DIRECTOR-SPEC-ada5.md`（277 行，① b3da9e30a4c0b4fa ② 909933bed703901c）。
"""

from __future__ import annotations

import logging
import unittest
from unittest import mock

from character_fakes import checker, opaque_png, rgb_png, rgba_png, transparent_png, two_subjects_png

from app.web_character import prompts, validate


class CharacterImageVerdictTests(unittest.TestCase):
    def test_a_well_formed_character_passes_with_measured_geometry(self) -> None:
        verdict = validate.inspect(transparent_png(), "image/png")

        self.assertTrue(verdict.ok, verdict.reason)
        self.assertEqual((verdict.width, verdict.height), (64, 96))
        self.assertEqual(verdict.content_box, (10, 10, 53, 85))
        self.assertEqual(verdict.anchor, (0.5, 86 / 96), "落地点＝外接框底边中点，归一化")
        self.assertAlmostEqual(verdict.opaque_ratio, 44 * 76 / (64 * 96), places=6)

    def test_each_rejection_reason_is_reachable(self) -> None:
        """每条原因码都能被真正触发——**不是**列一张永远走不到的枚举表。"""
        cases = [
            (validate.NO_ALPHA_CHANNEL, rgb_png(), "image/png"),
            (validate.OPAQUE, opaque_png(), "image/png"),
            (validate.MULTIPLE, two_subjects_png(), "image/png"),
            (validate.EMPTY, rgba_png(64, 96, lambda x, y: False), "image/png"),
            (validate.TOO_SMALL, rgba_png(64, 96, lambda x, y: 30 <= x < 34 and 40 <= y < 44), "image/png"),
            (validate.TOO_BIG, rgba_png(64, 96, lambda x, y: not (x < 2 and y < 2)), "image/png"),
            (validate.CUT_OFF, rgba_png(64, 96, lambda x, y: x < 40 and 10 <= y < 80), "image/png"),
            (validate.NOT_PNG, b"\xff\xd8\xffnot a png", "image/jpeg"),
            (validate.UNDECODABLE, b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png"),
        ]
        for reason, data, content_type in cases:
            with self.subTest(reason=reason):
                verdict = validate.inspect(data, content_type)
                self.assertFalse(verdict.ok)
                self.assertEqual(verdict.reason, reason)

    def test_a_png_with_alpha_is_not_automatically_transparent(self) -> None:
        """**这条是整道闸存在的理由**：一张 8 位 RGBA、alpha 全 255 的 PNG 是合法 PNG，
        却一个透明像素都没有。只检查"有没有 alpha 通道"会把它放过去。"""
        verdict = validate.inspect(opaque_png(), "image/png")

        self.assertEqual(verdict.reason, validate.OPAQUE)
        self.assertNotEqual(verdict.reason, validate.NO_ALPHA_CHANNEL, "它有通道，问题是通道没被用上")

    def test_a_checkerboard_drawn_into_the_pixels_is_named_as_such(self) -> None:
        """不透明、背景是灰白方格 ⇒ `checkerboard_drawn`，**与"纯不透明"分开记**。

        两者处置完全不同：棋盘格说明 alpha 在上游有过、被传输压平了（改响应格式／端点）；
        纯不透明说明参数被忽略（改参数或报能力缺失）。合并记会让人去改错地方。

        **错开半格那一例是判别器**：图案不从左上角那个像素对齐是真实情况。按网格分奇偶格的写法
        在错开半格时两组均值相等、一定漏判；平移比较法与相位无关，所以两例都要中。
        """
        cases = {
            "对齐": rgb_png(256, 256, checker(16)),
            "错开半格": rgb_png(256, 256, checker(16, 8, 8)),
            "大方格": rgb_png(256, 256, checker(32, 5, 11)),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                verdict = validate.inspect(data, "image/png")
                self.assertEqual(verdict.reason, validate.CHECKERBOARD)
                self.assertEqual((verdict.width, verdict.height), (256, 256), "宽高要带上，不是 0×0")

    def test_stripes_and_flat_colour_are_not_mistaken_for_a_checkerboard(self) -> None:
        """**宁可漏判不可误判**：误判会把"参数被忽略"说成"被传输压平"，让人去改错地方。

        竖条纹只在一个方向上交替，棋盘格要**横竖两个方向**都交替——这条钉的就是那个"两个方向"。
        """
        stripes = rgb_png(256, 256, lambda x, y: (255, 255, 255) if (x // 16) % 2 else (204, 204, 204))
        flat = rgb_png(256, 256, lambda x, y: (240, 240, 240))

        for name, data in (("竖条纹", stripes), ("纯色", flat)):
            with self.subTest(name=name):
                self.assertEqual(validate.inspect(data, "image/png").reason, validate.NO_ALPHA_CHANNEL)

    def test_the_verdict_is_the_same_whichever_row_filter_the_encoder_used(self) -> None:
        """行过滤器只是编码方式，不该改变判定——这条钉住"只还原 alpha 一条通道"那个取巧是对的。

        四种过滤器的预测值都只引用同一通道的邻居，所以 alpha 能脱离颜色通道单独还原；
        要是这个前提不成立，Up 过滤器那张就会算出另一个边界。
        """
        plain = validate.inspect(transparent_png(filter_type=0), "image/png")
        filtered = validate.inspect(transparent_png(filter_type=2), "image/png")

        self.assertTrue(plain.ok and filtered.ok, (plain.reason, filtered.reason))
        self.assertEqual((plain.content_box, plain.anchor), (filtered.content_box, filtered.anchor))


class CharacterReasonContractTests(unittest.TestCase):
    """契约里的 `CharacterReason` 码表与实现里的 `model.ALL_REASONS` **必须逐个对得上**。

    背景：前端要把这些码翻成人话，先前只能手抄一份，靠「加了新码记得说一声」维持同步——
    漏通知一次玩家就会看到 `budget_denied` 这种原始码。I 把它做成了契约枚举。

    **为什么用一条不变量而不是让实现 import 契约枚举**：
    契约是从实现**派生**出来的，反过来 import 会把依赖方向倒过来（领域层依赖对外 schema）。
    这条用例两个方向都查——实现多一个码、契约多一个码，都会红——
    既不倒依赖，又不靠"一次性核对过了"。

    **第一版这条用例自己有个盲点，已经修了**：它的实现侧是在用例里**手工列举常量**的，
    而 `already_queued` 当时是 `service.py` 里的一个硬编码字面量，列举时根本不会出现——
    **不变量挡得住"两份常量表不同步"，挡不住"有人直接写字面量"**（6c2b 在真实接口上撞到的）。
    修法两层：字面量提成 `model.ALREADY_QUEUED`；实现侧改读 `model.ALL_REASONS` 这**一个**常量，
    用例里不再有任何列举。再加一层运行期留痕，见 `test_an_off_table_reason_is_logged_on_its_way_out`。
    """

    def test_the_contract_lists_exactly_the_codes_the_implementation_can_emit(self) -> None:
        from app.schemas.web.character import CharacterReason
        from app.web_character.model import ALL_REASONS

        contract = {item.value for item in CharacterReason}

        self.assertEqual(ALL_REASONS - contract, set(), "实现会发出、契约没列：前端会看到没翻译的原始码")
        self.assertEqual(contract - ALL_REASONS, set(), "契约列了、实现发不出：前端会为一个到不了的分支写文案")

    def test_every_no_retry_reason_is_something_the_owner_can_be_told(self) -> None:
        """不重试的每一个原因都会被展示出去，所以它必须是词表的子集。

        反过来不成立：`already_queued` 是"这次不用再排了"，不是失败。
        两个集合**不定义成彼此**，只钉住这层包含关系——哪天出现一个可重试又要展示的原因，
        按重试集去推词表就会漏掉它。
        """
        from app.web_character.model import ALL_REASONS, NO_RETRY_REASONS

        self.assertEqual(NO_RETRY_REASONS - ALL_REASONS, set())
        self.assertIn("already_queued", ALL_REASONS - NO_RETRY_REASONS, "它不是失败，不该进重试策略集")

    def test_an_off_table_reason_is_logged_on_its_way_out(self) -> None:
        """**第二层**：常量表比不到的东西（有人直接写字面量），在送出去那一刻至少要留痕。

        不拦——拦了就是为一个文案问题让整个响应 500，玩家看到的更糟。
        """
        from app.routers.web.character import _reason

        with self.assertLogs("petsoul.web.character", level="WARNING") as captured:
            returned = _reason("某个没进码表的新码")

        self.assertEqual(returned, "某个没进码表的新码", "只留痕，不改值、不抛出")
        self.assertIn("not in the published table", "".join(captured.output))

    def test_a_listed_reason_passes_through_quietly(self) -> None:
        """对照：表里有的码不该刷日志，否则告警变噪音、真出问题时没人看。"""
        from app.routers.web.character import _reason
        from app.web_character.model import ALREADY_QUEUED

        logger = logging.getLogger("petsoul.web.character")
        with mock.patch.object(logger, "warning") as warned:
            self.assertEqual(_reason(ALREADY_QUEUED), ALREADY_QUEUED)
            self.assertIsNone(_reason(None))

        warned.assert_not_called()


class CharacterPromptTests(unittest.TestCase):
    def test_the_appearance_clause_matches_the_photo_directors(self) -> None:
        """**跨包不变量**（P 提的做法，我采纳）：角色链路拼「参考图里已确认的特征」那一句，
        必须与照片导演 `compiler._appearance_clause` **逐字相同**。

        为什么不是"把 P 的私有函数提成公开的就完了"：提成公开只防 P 改名，
        **不防两边措辞各自漂移**——而漂移谁也不报错，行为会静悄悄变成两套说法。
        这一条两样都防，且在**任何一边**改动时当场响。
        """
        from app.web_photo_director import compiler

        for tags in ((), ("silver_coat",), ("silver_coat", "tabby_markings", "white_chest"),
                     ("pink_nose", "upright_ears", "long_whiskers"), ("不在词表里的标签",)):
            with self.subTest(tags=tags):
                self.assertEqual(prompts._appearance_clause(tags), compiler._appearance_clause(tags))

    def test_every_supported_species_gets_its_own_neutral_pose(self) -> None:
        """猫狗兔鼠鸟不能硬套同一种骨架（方案第 32 行）。词表外（含 `other`）**不猜**，直接拒。"""
        for species in ("cat", "dog", "rabbit", "hamster", "bird", "parrot"):
            with self.subTest(species=species):
                self.assertTrue(prompts.supported(species))
                self.assertIn(prompts.POSES[species], prompts.build_character_prompt(species))
        self.assertNotEqual(prompts.POSES["cat"], prompts.POSES["bird"], "四足站立和双脚并立不是一回事")
        for species in ("other", "", "dragon"):
            with self.subTest(species=species):
                self.assertFalse(prompts.supported(species))
                with self.assertRaises(ValueError):
                    prompts.build_character_prompt(species)

    def test_the_prompt_keeps_the_identity_lock_right_after_the_subject(self) -> None:
        """身份锁**紧跟主体**：角色图没有场景段占位，身份排到后段脸型会漂移（P 规范 2.1 第 50 行的实测结论）。"""
        from app.web_photo_director.catalog import IDENTITY_RULE

        prompt = prompts.build_character_prompt("cat")
        lock = IDENTITY_RULE.format(animal="猫")

        self.assertIn(lock, prompt, "身份锁逐字复用 P 的常量，不另写一套")
        self.assertLess(prompt.index(lock) / len(prompt), 0.25, "身份锁要落在前四分之一")

    def test_a_bird_gets_no_perch(self) -> None:
        """栖木是物件，属于场景层。画进角色图，它会跟着这只鸟进到每一个场景里。"""
        prompt = prompts.build_character_prompt("bird")

        for word in ("栖木", "树枝", "站架"):
            self.assertNotIn(word, prompt)


if __name__ == "__main__":
    unittest.main()
