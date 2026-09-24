"""旅行手账流水线（TRV-03；方案 §12；P 的 TRV-05 简报）。真实迁移建库、**真实插画服务**、**假**画师、0 次付费调用。

钉的是：一版计划发布 → 同一事务里一页手账、一个画图任务（T01 的手账一段）；画师收到的是 P 的简报——
不含站名与数字、竖幅 1024x1536、不请求 background、参考图就是编译时那张；准确站名在排版层（给页面排，不进图）；
同一画面版本的新一版计划**复用那张图**（改文字不重画）；
没有照片 → 无肖像版：不给参考、**不补画证件照**、预占 1 个单位；
照片在编译与画图之间换了 → 不发送；图 failed 与 unknown 分开、文字仍在、unknown 不自动重试、显式重画走四态凭据（T09）；
简报被拒 → 不登记画图，计划照常 ready。

**预占单位按分支记**（Q 的提醒）：插画链路「无参考照先画证件照」一次占 2 个单位；旅行手账（`travel_journal`）不补画证件照，
有照片、无肖像版都是 1 个。每条用例都写明自己走的是哪个分支，免得有人把 1 读成「少发了一次」。
"""

from __future__ import annotations

import json
import re
import unittest

from character_fakes import rgb_png
from travel_wish_fakes import TravelJournalTestBase

from app.web_photo_director import journal_brief
from app.web_providers import ImageUnavailable
from app.web_travel.model import READY

PAST = "2000-01-01T00:00:00+00:00"


class CountingIllustrations:
    """**不去重**、只数「登记新图」被叫了几次的插画桩（没有画师：简报按无参考图能力编译）。"""

    illustrator = None

    def __init__(self) -> None:
        self.requests: list[str] = []

    def request_image_in(self, conn, user_id, pet_id, source_key, *, style, **extras):
        self.requests.append(source_key)
        return f"wt-stub-{len(self.requests)}"


class TravelJournalDrawingTests(TravelJournalTestBase):
    def test_a_published_plan_gets_one_page_and_one_drawing_from_the_brief(self) -> None:
        """分支：travel_journal／有照片 → 预占 1 个单位。"""
        self.publish()
        (journal,) = self.journal_rows()
        plan = self.plans()[0]
        self.assertEqual((journal["plan_id"], journal["plan_revision"], journal["phase"], journal["identity_mode"]),
                         (plan["plan_id"], 1, "plan", "photo"), "手账指向当时那一版计划")
        self.assertEqual(len(self.drawings()), 1)

        self.ills.run_pending()
        (call,) = self.painter.calls
        self.assertEqual((call["size"], call["background"], call["reference"]), ("1024x1536", None, (self.photo, "image/png")))
        for name in ("浅水湾", "赤柱"):
            self.assertNotIn(name, call["prompt"], "站名不进图，由页面排版")
        self.assertIsNone(re.search(r"[0-9０-９]", call["prompt"]), "数字不进图")
        self.assertEqual([s["name"] for s in json.loads(journal["layout_json"])["stations"]], ["浅水湾", "赤柱"], "准确站名在排版层")
        image = self.image()
        self.assertEqual(image.status, "ready")
        self.assertTrue(image.url)
        self.assertEqual(self.image_units(), [1])

    def test_the_page_follows_the_trv07_t1_template_and_default_paper(self) -> None:
        """TRV-07（r7k）：基础版式 t1，首批默认 cream 米白旧纸＋watercolor 淡水彩；改之前先回 TRV-07。
        提示词里的纸笔描述直接取 P 词表里对应的那段文字，不在用例里抄中文。"""
        self.publish()
        (journal,) = self.journal_rows()
        self.assertEqual(journal["template_revision"], "t1")
        self.ills.run_pending()
        (call,) = self.painter.calls
        self.assertIn(journal_brief.PAPER["cream"], call["prompt"])
        self.assertIn(journal_brief.BRUSH["watercolor"], call["prompt"])

    def test_the_journal_itself_does_not_ask_again_for_the_same_picture(self) -> None:
        """手账这一层自己的复用（按 计划×画面摘要×模板 查已有的图）。真插画服务按 `illustration:<source_key>` 唯一去重，
        同一画面的 source_key 也相同——两层同时生效、互相遮挡，下一条用例分不出是哪层挡的。这里换成**不去重、只数次数**的桩单钉这一层。
        要删这层、改由队列去重兜底：先确认 source_key 仍与（计划、画面摘要、模板）一一对应，再删这条。"""
        stub = CountingIllustrations()
        self.journals.illustrations = stub
        self.journals.identity_of = lambda conn, pet_id: None
        self.publish()
        self.research.retry(self.wishes.read("pet-1").wish_id, self.wishes.read("pet-1").wish_revision)
        self.research.run_pending()

        first, second = self.journal_rows()
        self.assertEqual((first["plan_revision"], second["plan_revision"]), (1, 2))
        self.assertEqual(first["visual_digest"], second["visual_digest"], "前提：同一画面")
        self.assertEqual(len(stub.requests), 1, "同一画面：手账不再登记新图")
        self.assertEqual(second["image_task_id"], first["image_task_id"])

    def test_a_new_revision_with_the_same_picture_reuses_the_drawing(self) -> None:
        """方案 §12：信息修正先更新文字；与画面无关的变化不自动生成新背景。"""
        self.publish()
        self.ills.run_pending()
        self.research.retry(self.wishes.read("pet-1").wish_id, self.wishes.read("pet-1").wish_revision)
        self.research.run_pending()
        self.ills.run_pending()

        first, second = self.journal_rows()
        self.assertEqual((first["plan_revision"], second["plan_revision"]), (1, 2))
        self.assertEqual(first["visual_digest"], second["visual_digest"])
        self.assertEqual(second["image_task_id"], first["image_task_id"], "同一画面版本：复用那张图")
        self.assertEqual((len(self.drawings()), len(self.painter.calls)), (1, 1), "没有再付费画一次")

    def test_no_photo_gives_a_portrait_free_page_without_an_id_photo_call(self) -> None:
        """分支：travel_journal／无肖像 → 不补画证件照、预占 1 个单位（插画链路普通「无参考」分支是 2）。"""
        self.photo = None
        self.journals.identity_of = lambda conn, pet_id: None
        self.publish()
        (journal,) = self.journal_rows()
        self.assertEqual(journal["identity_mode"], "none")
        self.ills.run_pending()

        (call,) = self.painter.calls
        self.assertIsNone(call["reference"])
        self.assertEqual(self.portraits, [], "没有照片时不另画证件照来凑")
        self.assertEqual(self.image_units(), [1])

    def test_a_photo_changed_after_compiling_sends_nothing(self) -> None:
        self.publish()
        self.photo = rgb_png(64, 64, lambda x, y: (9, 9, 9))  # 编译之后主人换了照片
        self.ills.run_pending()
        self.assertEqual(self.painter.calls, [], "参考照不是编译时那张：不发")
        self.assertEqual(self.image().status, "failed")


class TravelJournalOutcomeTests(TravelJournalTestBase):
    def test_a_failed_drawing_keeps_the_text_and_an_explicit_redraw_retries_it(self) -> None:
        self.painter.raises = ImageUnavailable("rejected")
        self.publish()
        self.ills.run_pending()
        image = self.image()
        self.assertEqual(image.status, "failed")
        self.assertIsNotNone(image.ticket)
        self.assertEqual(json.loads(self.journal_rows()[0]["layout_json"])["title"], "去看海", "图没画成，文字照样在")
        self.assertEqual(self.wishes.read("pet-1").status, READY, "图片不能否决文字出游（合同第 9 节）")

        self.painter.raises = None
        self.assertEqual(self.journals.redraw(self.plans()[0]["plan_id"]), "requeued")
        self.ills.run_pending()
        self.assertEqual((self.image().status, len(self.painter.calls)), ("ready", 2))

    def test_an_unconfirmed_drawing_reads_unknown_and_is_not_retried_by_itself(self) -> None:
        self.painter.raises = ImageUnavailable("timeout")
        self.publish()
        self.ills.run_pending()
        self.assertEqual(self.image().status, "unknown", "可能已经花过钱：不折进 failed")
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET run_after = ? WHERE kind = 'illustration'", (PAST,))
        self.ills.run_pending()
        self.assertEqual(len(self.painter.calls), 1, "unknown 不自动重试")

    def test_a_refused_brief_draws_nothing_and_the_plan_still_stands(self) -> None:
        self.journals.mood_of = lambda pet_id: "angry"  # P 的编译器不认这个心情
        self.publish()
        (journal,) = self.journal_rows()
        self.assertIsNone(journal["image_task_id"])
        self.assertEqual(json.loads(journal["layout_json"])["image_refused"], "mood_unknown")
        self.assertEqual((self.drawings(), self.wishes.read("pet-1").status), ([], READY))


class TravelJournalMappingTests(unittest.TestCase):
    def test_every_fact_verdict_has_a_brief_mapping_and_nothing_extra(self) -> None:
        """合同 §19.2／§20.3：A 的事实结论取值 ↔ 交给 P 的映射，双向相等。新增第六种结论而没登记映射，这条当场红。"""
        from app.web_travel import facts, journal
        verdicts = {facts.VERIFIED, facts.UNVERIFIED, facts.STALE, facts.CONFLICT, facts.REJECTED}
        self.assertEqual(set(journal.VERIFICATION), verdicts)
        self.assertLessEqual(set(journal.VERIFICATION.values()), {"verified", "unverified", "stale", "conflicting"}, "P 只认这四个")


if __name__ == "__main__":
    unittest.main()
