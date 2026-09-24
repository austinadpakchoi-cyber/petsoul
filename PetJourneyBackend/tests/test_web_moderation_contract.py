"""契约枚举与实现取值的**双向**不变量（公告级别、举报结局）。

**为什么要双向**：这两份清单必须一致，而「一致」这件事**没有任何东西会主动提醒**——
实现里加一个新的公告级别，契约不会自己长出来；契约里删一个码，实现也不会报错。
一次性核对只在核对那一刻为真。

**两个方向都查**：实现多一个 → 红；契约多一个 → 也红。
所以无论从哪边动手，都会在这里当场停下，而不是等前端拿到一个它不认识的字符串才发现。

**为什么不让实现 import 契约来消除重复**：那会让领域层（`web_admin`）依赖对外 schema，
依赖方向倒过来，撞 `dependency_gate`。契约是从实现派生的，不能反着依赖——
所以用一条用例锁住，而不是用一个 import。
"""

from __future__ import annotations

import unittest

from app.schemas.web.moderation import AnnouncementSeverity, ReportOutcome
from app.web_admin.content_types import ANNOUNCEMENT_SEVERITIES
from app.web_admin.moderation import OUTCOMES


class ModerationContractTests(unittest.TestCase):
    def test_announcement_severities_match_both_ways(self) -> None:
        contract = {member.value for member in AnnouncementSeverity}
        implementation = set(ANNOUNCEMENT_SEVERITIES)
        self.assertEqual(contract, implementation,
                         "公告级别两边对不上：实现在 web_admin/content_types.py 的 ANNOUNCEMENT_SEVERITIES，"
                         "契约在 schemas/web/moderation.py 的 AnnouncementSeverity。**两边都要改。**")

    def test_report_outcomes_match_both_ways(self) -> None:
        contract = {member.value for member in ReportOutcome}
        implementation = {code for code, _message in OUTCOMES.values()}
        self.assertEqual(contract, implementation,
                         "举报结局两边对不上：实现在 web_admin/moderation.py 的 OUTCOMES（取每项的第一个元素），"
                         "契约在 schemas/web/moderation.py 的 ReportOutcome。**两边都要改。**")

    def test_every_outcome_has_a_fixed_message(self) -> None:
        """每个结局都必须有固定措辞：前端**不该**按 outcome 自己拼文案。

        这条在这里，是因为一旦有人加了新结局却忘了写 message，
        前端会拿到空字符串，而它没有任何依据去补——措辞属于产品口径，不属于前端。
        """
        for code, message in OUTCOMES.values():
            with self.subTest(outcome=code):
                self.assertTrue(message and message.strip(), f"{code} 没有固定措辞")


if __name__ == "__main__":
    unittest.main()
