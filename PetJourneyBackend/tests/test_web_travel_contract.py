"""旅行心愿这一批**跨方清单**的双向不变量：合同 TRV-00 ↔ 各实现。

**本文件 2026-09-24 由 `test_web_waiting_reason_contract.py` 改名而来**：它现在锁四份清单，
原名只说得出其中一份。**名字比内容窄，下一个人就会以为另外三份没人管**——今天已经在
`compile_art_brief`（只存在于合同里的名字）和 `note_considered_in`（合同发明的端口名）上栽过两次。

锁住的四组：

    §5.2 waiting_reasons    合同 ↔ B WaitingReason ↔ A ALL_REASONS ↔ P VERIFICATION_REASON
    §5.1 心愿主状态          合同 ↔ B WishStatus ↔ A WISH_STATES
    §5.1 研究任务状态        合同 ↔ B ResearchStatus ↔ A R_*     ※ 不是集合相等，见下
    §5.1 手账图四态          合同 ↔ PhotoStatus ↔ A IMAGE_STATES
    §23  DTO 四组            合同 ↔ 对外 schemas/web/travel.py（含 P 的 IDENTITY_MODES）

**为什么需要**：同一份清单写在多处，而「一致」这件事**没有任何东西会主动提醒**。今天实测漂过三次：
`fact_conflict`→`fact_conflicting` 的重命名（A 未跟上）、新增的 `plan_stale`（A 未接住，
**Q 和 B 都没报出来，是这条用例第一次跑显出来的**）、以及 `IMAGE_STATES` 那行靠注释声称的相等关系。

**两个方向都查**：实现多一个码红、合同多一个码也红。无论从哪边动手都在这里当场停下，
而不是等 UI 拿到一个它不认识的字符串才发现——那时各方都会觉得「我这边是对的」。

**权威清单为什么手抄在下面、不解析合同 md**：解析会把成败绑在排版上，而且解析出来的清单
和实现来自同一次「我以为合同是这么写的」。手抄意味着改合同时必须同时改这里。

**为什么不让各方 import 同一份常量**：A、B、P 分属三个不相邻的包，互相 import 会把决策层
和图片层拴在一起，撞 `dependency_gate`。所以锁住，而不是合并——与
`test_web_moderation_contract.py` 同一手法。

**这份不是唯一的检查**：Q 另持一份按合同文本独立取码的，两份互不复用。
**可靠性来自「两份」而不是「有一条用例」**——只剩一份就回到了单点。
"""

from __future__ import annotations

import unittest

from app.schemas.web.social import PhotoStatus
from app.web_agent.wish_policy import LIFE_SIDE, WaitingReason, WishStatus
from app.web_photo_director.journal_brief import IDENTITY_MODES, VERIFICATION_REASON
from app.schemas.web.travel import (
    TravelFactVerdict, TravelIdentityMode, TravelJournalPhase, TravelResearchStatus,
    TravelStopRole, TravelWaitingReason, TravelWishStatus)
from app.web_travel.facts import CONFLICT, REJECTED, STALE, UNVERIFIED, VERIFIED
from app.web_travel.model import (
    ALL_REASONS, IMAGE_STATES, LIFE_REASONS, PHASE_MEMORY, PHASE_PLAN, R_FAILED, R_QUEUED, R_READY,
    RESEARCH_REASONS,
    R_RUNNING, R_UNKNOWN, ROLE_PRIMARY, ROLE_SUGGESTION, WISH_STATES)

# 合同 TRV-00 §5.2 的 `waiting_reasons` 全集。**改合同时连这里一起改。**
CONTRACT_WAITING_REASONS = frozenset({
    "missing_funds",        # 钱不够（宠物自己的星币）
    "quota_denied",         # 平台调用额度不够（不是宠物的钱）
    "research_pending",     # 研究还没做完
    "research_unknown",     # 可能已发出、结果没确认：不自动重发
    "research_failed",      # 确定没拿到结果
    "fact_stale",           # 关键事实过期或不覆盖出行时间
    "plan_stale",           # 计划版本已过期。**本批无生产者**（§20.1）：写入方是 A，恒为 False
    "fact_unverified",      # 关键事实没有可用来源（假来源／只有模型自述／没查到）
    "fact_conflicting",     # 关键事实互相矛盾（得有人判哪条对）
    "weather_unsuitable",   # 已核实的天气不适合按计划出门
    "commitment_active",    # 答应过的事还没兑现
    "maintenance",          # 运营暂停
})

# 这三个形容词式的名字是一组（§5.2、§18.2 裁定）：**必须同时存在、同时改名**。
# 单独盯 `fact_conflicting` 会漏掉 `fact_unverified`——B 就是去读了合同原文才发现第二处的。
FACT_REASONS = frozenset({"fact_unverified", "fact_conflicting", "fact_stale"})

# 合同 §5.1 的三个**独立**状态字段（页面分别显示，不合并）。
CONTRACT_WISH_STATES = frozenset({"active", "ready", "linked", "completed", "cancelled"})
CONTRACT_RESEARCH_STATES = frozenset({"queued", "running", "ready", "failed", "unknown"})
CONTRACT_IMAGE_STATES = frozenset({"processing", "ready", "failed", "unknown"})

# 2026-09-24：**`ResearchStatus` 连同 `none` 哨兵已被 B 删掉**（等待原因按写入方分两列之后，
# 策略侧不再持有研究状态）。所以研究状态现在是**三方**：合同 ↔ A 的 R_* ↔ DTO。
# **策略侧不再有它，不是缺陷，是合法的范围收窄。**
#
# 但那个哨兵留下一条**仍然要守的不变量**：`none` 曾经存在过，
# **它若再出现在任何一侧，就是有人把「还没登记」当成了一个真状态** —— 见
# `test_the_vanished_sentinel_stays_vanished`。**哨兵消失了，对它的断言不能跟着消失**，
# 否则等于悄悄减掉一条检查（今天反复说的减号陷阱）。
VANISHED_SENTINEL = "none"

# B 的 `LIFE_SIDE`（三条）是**生活侧**的写入边界：`update_waiting_in` 里
# `if not reasons <= LIFE_REASONS: raise WishRejected`——B 写研究侧的码会被当场拒收。
# 这是 B↔A 新建立的一致面，实测逐字相同。


class WaitingReasonContractTests(unittest.TestCase):
    """三个实现各自的角色不同：B 与 A 持**全集**，P 只持 fact_* 那一组的**子集**。"""

    def test_decision_side_matches_the_contract_both_ways(self) -> None:
        implementation = {member.value for member in WaitingReason}
        self.assertEqual(CONTRACT_WAITING_REASONS, implementation,
                         "决策侧与合同对不上：实现在 app/web_agent/wish_policy.py 的 WaitingReason，"
                         "合同在 TRV-00 §5.2（本文件顶上抄了一份）。**两边都要改。**")

    def test_storage_side_matches_the_contract_both_ways(self) -> None:
        implementation = set(ALL_REASONS)
        self.assertEqual(CONTRACT_WAITING_REASONS, implementation,
                         "研究与存储侧与合同对不上：实现在 app/web_travel/model.py 的 ALL_REASONS"
                         "（= LIFE_REASONS | RESEARCH_REASONS），合同在 TRV-00 §5.2。**两边都要改。**")

    def test_the_two_full_sets_agree_with_each_other(self) -> None:
        """B 与 A 直接对照：即使两边同时漏改，上面两条也会红；这一条让**差在哪**一眼看见。"""
        decision = {member.value for member in WaitingReason}
        storage = set(ALL_REASONS)
        self.assertEqual(decision, storage,
                         f"决策侧多出 {sorted(decision - storage)}；存储侧多出 {sorted(storage - decision)}")

    def test_photo_brief_reasons_are_a_subset_not_a_fourth_dialect(self) -> None:
        """P 只发 fact_* 那三个，但**必须是全集里的那三个**——它是子集，不是另一套方言。"""
        emitted = set(VERIFICATION_REASON.values())
        self.assertTrue(emitted <= CONTRACT_WAITING_REASONS,
                        f"图片简报发出了合同里没有的码：{sorted(emitted - CONTRACT_WAITING_REASONS)}"
                        "（实现在 app/web_photo_director/journal_brief.py 的 VERIFICATION_REASON）")
        self.assertEqual(emitted, FACT_REASONS, "图片简报的三个核验原因应当正好是 fact_* 那一组")

    def test_the_three_fact_reasons_exist_everywhere(self) -> None:
        """三个形容词式名字是一组，**分开改就会漏**。逐个断言，好让红的那条直接说出是哪一个。"""
        decision = {member.value for member in WaitingReason}
        storage = set(ALL_REASONS)
        for reason in sorted(FACT_REASONS):
            with self.subTest(reason=reason):
                self.assertIn(reason, CONTRACT_WAITING_REASONS, "合同里没有这个码")
                self.assertIn(reason, decision, "app/web_agent/wish_policy.py 的 WaitingReason 里没有")
                self.assertIn(reason, storage, "app/web_travel/model.py 的 ALL_REASONS 里没有")


class StateEnumContractTests(unittest.TestCase):
    """§5.1 的三个独立状态字段。**研究状态那组不是集合相等**——见本类最后两条。"""

    def test_wish_states_match_both_ways(self) -> None:
        for label, actual in (("决策侧 WishStatus", {m.value for m in WishStatus}),
                              ("存储侧 WISH_STATES", set(WISH_STATES))):
            with self.subTest(side=label):
                self.assertEqual(CONTRACT_WISH_STATES, actual, f"{label} 与合同 §5.1 对不上")

    def test_image_states_match_both_ways(self) -> None:
        """A 的 `IMAGE_STATES` 上写着「与 schemas.web.social.PhotoStatus 同口径」——
        **那句注释断言了一个相等关系，而注释不是不变量**（Q 核出）。这条把它变成不变量。
        """
        for label, actual in (("PhotoStatus", {m.value for m in PhotoStatus}),
                              ("A 的 IMAGE_STATES", set(IMAGE_STATES))):
            with self.subTest(side=label):
                self.assertEqual(CONTRACT_IMAGE_STATES, actual, f"{label} 与合同 §5.1 的手账图四态对不上")

    def test_stored_research_states_match_the_contract_both_ways(self) -> None:
        self.assertEqual(CONTRACT_RESEARCH_STATES, {R_QUEUED, R_RUNNING, R_READY, R_FAILED, R_UNKNOWN},
                         "A 的 R_* 与合同 §5.1 的研究任务状态对不上")

    def test_life_side_write_boundary_matches_both_ways(self) -> None:
        """B 的 `LIFE_SIDE` ↔ A 的 `LIFE_REASONS`：**生活侧的写入边界**。

        `update_waiting_in` 里 `if not reasons <= LIFE_REASONS: raise WishRejected`——
        两边对不上时，B 写进去的原因会被**当场拒收**。这一面是 2026-09-24 才建立的
        （等待原因按写入方分两列），**在那之前不存在，所以此前没有任何用例看着它**。
        """
        self.assertEqual(set(LIFE_SIDE), set(LIFE_REASONS),
                         "B 的 LIFE_SIDE 与 A 的 LIFE_REASONS 对不上：B 写进去的原因会被 WishRejected 拒收")
        self.assertTrue(set(LIFE_SIDE) <= CONTRACT_WAITING_REASONS,
                        "生活侧的码必须都在 §5.2 全集里")

    def test_the_two_writers_partition_the_whole_set(self) -> None:
        """两个写入方**恰好划分**全集：不重叠、不遗漏。（Q 的那份也钉了这三件事，各自手抄、互不 import。）

        **两条各自会红在不同的缺陷上**：
        · **重叠** → 两边都能写同一个码，后写的把先写的冲掉，而`update_waiting_in` 不会拒绝它——
          B 今天踩的正是这一族（它把研究侧的码也算了一遍）；
        · **遗漏** → 某个码**没有任何人负责写**，页面上永远不会出现，而全集里有它、看起来一切正常。
        """
        life, research = set(LIFE_REASONS), set(RESEARCH_REASONS)
        self.assertEqual(life & research, set(),
                         f"两个写入方的码重叠了：{sorted(life & research)}——会互相冲掉且不报错")
        self.assertEqual(life | research, CONTRACT_WAITING_REASONS,
                         f"并集与合同 §5.2 不符；无人负责写的码：{sorted(CONTRACT_WAITING_REASONS - life - research)}")

    def test_the_vanished_sentinel_stays_vanished(self) -> None:
        """**哨兵消失了，对它的断言不能跟着消失。**

        `ResearchStatus.NONE`（「还没登记」）随 `ResearchStatus` 一起被删掉了。
        删掉是对的，但**如果连这条断言也一并删掉，就等于悄悄减掉一条检查**——
        下一个人重新引入 `none` 时不会有任何东西红。

        它若再出现在任何一侧，说明有人**把「还没登记」当成了一个真状态**，
        而那正是当初要用哨兵避开、后来索性删掉的东西。
        """
        storage = {R_QUEUED, R_RUNNING, R_READY, R_FAILED, R_UNKNOWN}
        for side, values in (("合同 §5.1", CONTRACT_RESEARCH_STATES), ("A 的 R_*", storage),
                             ("DTO", {m.value for m in TravelResearchStatus})):
            with self.subTest(side=side):
                self.assertNotIn(VANISHED_SENTINEL, values,
                                 f"{side} 不该出现 `{VANISHED_SENTINEL}`：它是已被删除的「还没登记」哨兵")


class DtoContractTests(unittest.TestCase):
    """对外 DTO（`schemas/web/travel.py`）是这些清单的**又一份**，一并锁住。

    DTO 层是第四方：合同文本、B 的策略枚举、A 的存储常量之外，前端拿到的是这一份。
    **它漂了不会有任何后端用例红**——前端会拿到一个它不认识的字符串，而那时三方都觉得自己是对的。
    """

    def test_dto_waiting_reasons_match_the_contract_both_ways(self) -> None:
        self.assertEqual(CONTRACT_WAITING_REASONS, {m.value for m in TravelWaitingReason},
                         "DTO 的 TravelWaitingReason 与合同 §5.2 对不上")

    def test_dto_wish_and_research_states_match(self) -> None:
        self.assertEqual(CONTRACT_WISH_STATES, {m.value for m in TravelWishStatus})
        self.assertEqual(CONTRACT_RESEARCH_STATES, {m.value for m in TravelResearchStatus},
                         "DTO 不该带策略侧哨兵 none——它不会被存下来，也不该出现在对外契约里")

    def test_dto_sentinel_never_reaches_the_contract(self) -> None:
        """**允许的差异要正向断言**（§24.3）。哨兵已被删除，这条改由
        `StateEnumContractTests.test_the_vanished_sentinel_stays_vanished` 三侧一起钉。"""
        self.assertNotIn(VANISHED_SENTINEL, {m.value for m in TravelResearchStatus})

    def test_stop_role_matches_the_storage_side(self) -> None:
        self.assertEqual({m.value for m in TravelStopRole}, {ROLE_PRIMARY, ROLE_SUGGESTION},
                         "DTO 的 TravelStopRole 与 A 的 ROLE_PRIMARY／ROLE_SUGGESTION 对不上")

    def test_fact_verdict_matches_the_storage_side(self) -> None:
        """注意 A 那边**常量名是 `CONFLICT`、值是 `"conflicting"`**——名字是旧的、值是对的。

        所以这一条比的是**值**不是名字；靠名字去对会以为两边不一致。
        """
        self.assertEqual({m.value for m in TravelFactVerdict},
                         {VERIFIED, UNVERIFIED, STALE, CONFLICT, REJECTED},
                         "DTO 的 TravelFactVerdict 与 A 的 facts.py 五个结论对不上")

    def test_journal_phase_matches_the_storage_side(self) -> None:
        self.assertEqual({m.value for m in TravelJournalPhase}, {PHASE_PLAN, PHASE_MEMORY})

    def test_identity_mode_matches_the_photo_director_both_ways(self) -> None:
        """2026-09-24：**这一组从「锁不住」变成锁住了**，用例名也跟着改。

        原先 P 那边 `identity_mode` 只有一句注释和散落的 `mode == "photo"` 比较，
        **没有常量清单**——没有第二份就没有「双向」可言，所以当时只断言了 DTO 自己的取值，
        并如实记成具名缺口，**没有造一条看起来在检查的假用例**。
        应我的请求 P 提了常量（`journal_brief.py:52-53` 的 `IDENTITY_MODES`），现在能真查了。
        """
        self.assertEqual({m.value for m in TravelIdentityMode}, set(IDENTITY_MODES),
                         "DTO 的 TravelIdentityMode 与 P 的 IDENTITY_MODES 对不上")


if __name__ == "__main__":
    unittest.main()
