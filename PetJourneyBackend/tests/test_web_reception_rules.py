"""引导便笺规则：原话按句拆分（不改写）、不同话题分开、私密片段单列、称呼/物件建议不误判。"""

from __future__ import annotations

import unittest

from app.reception.guided import rederive_slot_value, suggestions_for
from app.schemas.web.reception import CandidateKind, CareNoteSlot, ReceptionBranch


def run(text: str):
    return [(seg, kind, slot, value) for seg, kind, _subject, slot, value in suggestions_for(text, ReceptionBranch.own_pet)]


class GuidedNotesRules(unittest.TestCase):
    def test_distinct_topics_become_separate_verbatim_candidates(self) -> None:
        text = "叫我姐姐就好。它最喜欢那条蓝色的毯子。它不喜欢被抱。"
        result = run(text)
        self.assertEqual([r[2] for r in result], [CareNoteSlot.owner_title, CareNoteSlot.favorite_object, CareNoteSlot.interaction_boundary])
        self.assertEqual("".join(r[0] for r in result), text, "只在句子边界拆，拼回去就是原话")
        self.assertEqual(result[0][3], "姐姐")
        self.assertEqual(result[1][3], "蓝色的毯子")

    def test_same_topic_sentences_keep_context(self) -> None:
        result = run("它早上会叫我起床。它吃饭很慢。")
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0][2], "“会叫我起床”不是主人希望的称呼")

    def test_private_part_is_its_own_candidate(self) -> None:
        result = run("它最爱小球。它小时候走丢过一次，别告诉它。")
        self.assertEqual(result[-1][1], CandidateKind.owner_private)
        self.assertNotIn("走丢", result[0][0])

    def test_wish_is_not_history(self) -> None:
        (seg, kind, slot, value), = run("以后想带它去看海。")
        self.assertEqual((kind, slot, value), (CandidateKind.wish, CareNoteSlot.wish_place, "海"))

    def test_correction_rederives_or_clears_slot_value(self) -> None:
        self.assertEqual(rederive_slot_value(CareNoteSlot.owner_title, "叫我姐姐就好。"), "姐姐")
        self.assertIsNone(rederive_slot_value(CareNoteSlot.owner_title, "它喜欢晒太阳。"))


if __name__ == "__main__":
    unittest.main()
