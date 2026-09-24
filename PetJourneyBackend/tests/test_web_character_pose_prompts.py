"""批次二五个姿态的**提示词**（P《世界角色导演模式》§6-5）。纯单元：不联网、0 次付费调用。

规范里有两条可以直接写成用例的东西，这里都钉上：

  1. **状态名和道具名都不进提示词**：晒太阳不写阳光，吃东西不写碗，回应抚摸不写手——写了模型就会画进精灵；
  2. **P 离线编译的实测表**：用规格文件里的 6 个外貌标签编译猫的五个姿态，「汉字数」与「身份锁位置」逐条复现。
     这张表是 P 那边独立算出来的，**两边各算一遍、数对得上**，比拿自己的输出当期望值更有说服力。
     口径（2026-09-24 在批次一上先复现出 P 的 348 字、17.3% 才定下来）：
     汉字数＝CJK 表意字个数；身份锁位置＝身份锁句起点 ÷ 全文字符数。

表格单元与规范逐字节相同这件事，是一次性对照（本窗口日志记了结果），**不在这里读规范文件**——
规范在 `docs/` 下，测试不该依赖协作文档的路径与排版。
"""

from __future__ import annotations

import re
import unittest
from types import SimpleNamespace

from app.schemas.web.character import CharacterPose
from app.web_character import prompts
from app.web_photo_director.catalog import ANATOMY_RULE, APPEARANCE, IDENTITY_RULE, SPECIES, SPECIES_CN
from app.web_providers.gpt_images import TRANSPARENT, GPTIllustrator

# 规格文件 `test-pet-spec.json` 里测试宠物（银灰虎斑猫）的 6 个外貌标签，**顺序也照抄**——顺序会改变外貌句
SPEC_TAGS = ("silver_coat", "tabby_markings", "white_chest", "pink_nose", "upright_ears", "long_whiskers")
# P §6-5「实测」表：(汉字数, 身份锁位置 %)
P_MEASURED = {"sleeping": (325, 18.6), "sunbathing": (334, 21.2), "eating": (327, 20.6), "walking": (326, 19.6),
              "petted": (326, 19.9)}


def _all_prompts(tags=()):
    return {(species, pose): prompts.build_pose_prompt(species, pose, tags)
            for species in sorted(SPECIES) for pose in prompts.EXTRA_POSES}


class PosePromptTests(unittest.TestCase):
    def test_every_pose_compiles_for_every_species(self) -> None:
        compiled = _all_prompts()

        self.assertEqual(len(compiled), 30, "5 个姿态 × 6 个物种")
        for (species, pose), text in compiled.items():
            self.assertTrue(text.startswith(f"写实摄影级的角色立绘：一只真实的{SPECIES_CN[species]}，"), (species, pose))
            self.assertIn(prompts.POSE_TEXT[species][pose], text)
            self.assertIn(prompts.POSE_FRAMING[pose], text)

    def test_no_state_or_prop_word_ever_reaches_the_prompt(self) -> None:
        """规范 §6-5 的可执行不变量。三种外貌标签组合都查：空的（真实链路现状）、规格文件那 6 个、词表里全部。"""
        for tags in ((), SPEC_TAGS, tuple(sorted(APPEARANCE))):
            for key, text in _all_prompts(tags).items():
                with self.subTest(key=key, tags=len(tags)):
                    self.assertEqual([word for word in prompts.POSE_FORBIDDEN if word in text], [])

    def test_pose_and_framing_never_mention_the_ground(self) -> None:
        """P 提的可选用例：模板结尾已经写了「脚下不画地面」，姿态句与取景句再提「地面」就可能把地面引出来。
        **只查这两类参数，不查整条**——整条里本来就有「脚下不画地面」。晒太阳那次就是靠避开这个词才没画出地面（n=1）。"""
        for species, table in prompts.POSE_TEXT.items():
            for pose, text in table.items():
                self.assertNotIn("地面", text, (species, pose))
        for pose, text in prompts.POSE_FRAMING.items():
            self.assertNotIn("地面", text, pose)

    def test_the_three_fixed_differences_from_the_neutral_template(self) -> None:
        """与中性姿态模板有意不同的三处（规范 §6-5）：不要求"头耳四肢尾巴都在画面内"、解剖句只留结构半句、留空句不提托盘。"""
        for key, text in _all_prompts(SPEC_TAGS).items():
            with self.subTest(key=key):
                self.assertNotIn("头、耳、四肢与尾巴都在画面内", text, "蜷睡时四肢收在身下，这句会和姿态打架")
                self.assertNotIn(ANATOMY_RULE, text, "「拿东西用爪子和嘴」「人手」在吃东西、回应抚摸里会被连到别处")
                self.assertNotIn("托盘", text, "「托盘」在吃东西时同样暗示器皿")
                self.assertIn(prompts.POSE_ANATOMY, text)

    def test_the_paw_sentence_sits_right_after_the_pose(self) -> None:
        """「挪到动作句旁」是 P 按四对真图复核意见补的——两半都要：写具体，**也要挪**。"""
        for (species, pose), text in _all_prompts().items():
            with self.subTest(species=species, pose=pose):
                self.assertIn(f"{prompts.POSE_TEXT[species][pose]}，{prompts.PAW[species]}，全身完整入画。", text)

    def test_the_identity_lock_follows_the_subject_sentence(self) -> None:
        """身份锁紧跟主体句（规范 2.1）：角色图没有场景段占位，身份排到后段脸型会漂移。"""
        for (species, pose), text in _all_prompts().items():
            first_sentence_end = text.index("全身完整入画。") + len("全身完整入画。")
            self.assertTrue(text[first_sentence_end:].startswith(IDENTITY_RULE.format(animal=SPECIES_CN[species])),
                            (species, pose))

    def test_p_measured_table_is_reproduced(self) -> None:
        """P 独立离线编译的实测表（猫 ＋ 规格文件 6 个标签），逐条复现。"""
        identity = IDENTITY_RULE.format(animal=SPECIES_CN["cat"])
        for pose, (characters, position) in P_MEASURED.items():
            text = prompts.build_pose_prompt("cat", pose, SPEC_TAGS)
            with self.subTest(pose=pose):
                self.assertEqual(len(re.findall(r"[一-鿿]", text)), characters)
                self.assertEqual(round(100 * text.index(identity) / len(text), 1), position)

    def test_the_neutral_prompt_still_measures_what_p_measured(self) -> None:
        """批次一**本批不改**（改了就是改正式中性姿态的产出）。P 表里批次一的基准：348 字、身份锁 17.3%。"""
        text = prompts.build_character_prompt("cat", SPEC_TAGS)

        self.assertEqual(len(re.findall(r"[一-鿿]", text)), 348)
        self.assertEqual(round(100 * text.index(IDENTITY_RULE.format(animal="猫")) / len(text), 1), 17.3)

    def test_unknown_pose_or_species_is_refused_not_guessed(self) -> None:
        with self.assertRaises(ValueError):
            prompts.build_pose_prompt("other", "sleeping")
        with self.assertRaises(ValueError):
            prompts.build_pose_prompt("cat", "neutral_full")  # 中性姿态走批次一那一套，不从这里编
        with self.assertRaises(ValueError):
            prompts.build_pose_prompt("cat", "resting")  # 早先的占位键，2026-09-24 已从契约删除


class PoseKeysAndCanvasTests(unittest.TestCase):
    def test_pose_keys_match_the_contract_in_both_directions(self) -> None:
        """实现的姿态键与对外契约 `CharacterPose` 是**同一个词**，两个方向都查，**没有例外**。

        早先的占位 `resting`（从不产出）2026-09-24 已删：前端屋内先改用 `sleeping` 并登记，
        后台词表那一条由 adm1 精确释放、同一次改动删掉——那边对词表与枚举也是双向相等检查，分两次删必有一段红。
        """
        contract = {pose.value for pose in CharacterPose}

        self.assertEqual(contract, {"neutral_full", *prompts.EXTRA_POSES})

    def test_every_canvas_passes_through_the_gpt_adapter_unchanged(self) -> None:
        """三种画幅都在 `GPTIllustrator.render` 接受的集合里，而且**原样透传**——被映射成别的画幅，
        舒展躺平的猫就会被塞进方形里，模型只能把它缩小或裁掉。"""
        recorder = SimpleNamespace(calls=[])
        recorder.generate_image_with_references = lambda prompt, *, references, size: recorder.calls.append(size) or "ok"
        meter = SimpleNamespace(allow=lambda kind: True, record=lambda *args, **kwargs: None)
        illustrator = GPTIllustrator(SimpleNamespace(image_model="gpt-test", image_api_key="k", image_base_url="http://unused"), meter)
        illustrator._transparent = recorder

        for pose, canvas in prompts.POSE_CANVAS.items():
            illustrator.render("姿态", (b"ref", "image/png"), size=canvas, background=TRANSPARENT)

        self.assertEqual(recorder.calls, list(prompts.POSE_CANVAS.values()))


if __name__ == "__main__":
    unittest.main()
