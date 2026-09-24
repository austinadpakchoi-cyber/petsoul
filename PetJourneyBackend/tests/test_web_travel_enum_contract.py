"""旅行心愿的三份状态清单：合同 ↔ 决策侧(B) ↔ 存储侧(A) 双向一致（TRV-08 / Q）。

**为什么要有这条**：同一份清单抄在多处时，谁漏抄一个码都不会报错——
`plan_stale` 缺在存储侧那次，就是双向用例第一次跑才显出来的，不是任何人记住的。
搜词只能发现「多出来的」，发现不了「少掉的」；**只有把两边取成集合做对称差才两个方向都查得到**。

**权威清单手抄在下面，不解析合同 md**：解析会把成败绑在排版上，
而且解析出来的清单和实现来自同一次「我以为合同是这么写的」。
清单出处：TRV-00 §5.1（业务主状态／研究任务／手账图三个**独立**字段，页面分别显示、不合并）。

**这一份是第二道检查，不是唯一一道。** I 在 `test_web_travel_contract.py` 里另有一份
（它原名 `test_web_waiting_reason_contract.py`，2026-09-24 改名——**原名只说得出四组清单里的一份，
名字比内容窄**）。两份**互不 import、各自手抄**：可靠性来自两条互不复用的检查，
不是一条更用力的；**两份都可能抄错，但抄错同一处的概率低得多**。
"""
from __future__ import annotations

import unittest

from app.schemas.web.social import PhotoStatus
from app.schemas.web.travel import TravelResearchStatus, TravelWaitingReason, TravelWishStatus
from app.web_agent.wish_policy import LIFE_SIDE, WaitingReason, WishStatus
from app.web_travel import model as storage

# ---- 手抄自 TRV-00 §5.1／§5.2（1307 行版 `e59d7a96f23cee63`）----
CONTRACT_WISH_STATES = frozenset({"active", "ready", "linked", "completed", "cancelled"})
CONTRACT_RESEARCH_STATES = frozenset({"queued", "running", "ready", "failed", "unknown"})
CONTRACT_IMAGE_STATES = frozenset({"processing", "ready", "failed", "unknown"})
# §5.2。**这是第二份独立抄本**：I 的 `test_web_travel_contract.py` 里另有一份。
# 两份都可能抄错，**但抄错同一处的概率低得多**——可靠性来自两条互不复用的检查，
# 不是一条更用力的。所以这里**不 import 它那份**，也不解析合同 md。
CONTRACT_WAITING_REASONS = frozenset({
    "missing_funds", "quota_denied", "research_pending", "research_unknown", "research_failed",
    "fact_stale", "plan_stale", "fact_unverified", "fact_conflicting", "weather_unsuitable",
    "commitment_active", "maintenance",
})

# `none` 曾是决策侧 `ResearchStatus` 的哨兵（「还没登记」）。**2026-09-24 接口变更后它不存在了**：
# 研究侧整体归 A，`ResearchStatus` / `PlanState` / `WishFacts.research` 一并删除。
# **所以它的判据反过来了**：原先是「只该在决策侧、且允许的差异要正向钉住」，
# 现在是「**哪一侧都不该有**」——它若再出现就是回归。
SENTINEL_GONE = "none"

BOTH = "两边都要改：合同在 TRV-00 §5.1（本文件顶上抄了一份），实现在下面这两处。"


class TravelEnumContractTests(unittest.TestCase):
    """四组清单各查两个方向（实现多一个码要红、合同多一个码也要红），外加一条两写入方的分区不变量。

    **组数写在这里而不写死在别处**：今天已经两次见到「加了格子、标题没跟上」——
    标签不参与判断，所以它会变成一句不报错的假话。
    """

    def test_wish_states_agree_with_the_contract_both_ways(self) -> None:
        policy = {s.value for s in WishStatus}
        stored = set(storage.WISH_STATES)
        dto = {s.value for s in TravelWishStatus}
        self.assertEqual(CONTRACT_WISH_STATES, policy,
                         f"业务主状态：合同 vs 决策侧 `wish_policy.WishStatus` 对不上。{BOTH}")
        self.assertEqual(CONTRACT_WISH_STATES, stored,
                         f"业务主状态：合同 vs 存储侧 `web_travel.model.WISH_STATES` 对不上。{BOTH}")
        self.assertEqual(CONTRACT_WISH_STATES, dto,
                         f"业务主状态：合同 vs DTO `schemas.web.travel.TravelWishStatus` 对不上。{BOTH}")

    def test_waiting_reasons_agree_across_all_four_sides(self) -> None:
        """`waiting_reasons` 的**第二份独立检查**（第一份归 I）。

        这一条今天已经抓到过一次真东西：`plan_stale` 缺在存储侧，
        **是双向用例第一次跑显出来的，不是任何人记住的**。
        **搜词只能发现「多出来的」，发现不了「少掉的」**——只有取成集合做对称差才两个方向都查得到。
        """
        for label, values in (("决策侧 `wish_policy.WaitingReason`", {r.value for r in WaitingReason}),
                              ("存储侧 `web_travel.model.ALL_REASONS`", set(storage.ALL_REASONS)),
                              ("DTO `TravelWaitingReason`", {r.value for r in TravelWaitingReason})):
            with self.subTest(side=label):
                self.assertEqual(CONTRACT_WAITING_REASONS, values, f"等待原因：合同 vs {label} 对不上。{BOTH}")

    def test_research_states_agree_and_the_old_sentinel_is_gone_everywhere(self) -> None:
        """研究状态现在是**三方**（合同 ↔ 存储 ↔ DTO）：决策侧已**合法地**不再持有它。

        2026-09-24 接口变更：等待原因按写入方分两列，研究侧整体归 A，
        因此 `wish_policy.ResearchStatus` 连同 `PlanState`、`WishFacts.research` 一起删除。
        **降为三方不是覆盖变差，是那一侧真的不再有这个概念**——
        硬要留一个「决策侧研究状态」才是造假。

        `none` 那个哨兵随 `ResearchStatus` 一起消失了。**所以它现在的判据反过来了**：
        原先是「只该在决策侧」，现在是「**哪一侧都不该有**」——它若再出现就是回归。
        """
        stored = {storage.R_QUEUED, storage.R_RUNNING, storage.R_READY, storage.R_FAILED, storage.R_UNKNOWN}
        dto = {s.value for s in TravelResearchStatus}
        self.assertEqual(CONTRACT_RESEARCH_STATES, stored,
                         f"研究状态：合同 vs 存储侧 `web_travel.model.R_*` 对不上。{BOTH}")
        self.assertEqual(CONTRACT_RESEARCH_STATES, dto,
                         f"研究状态：合同 vs DTO `TravelResearchStatus` 对不上。{BOTH}")
        for label, values in (("合同", CONTRACT_RESEARCH_STATES), ("存储侧", stored), ("DTO", dto)):
            with self.subTest(side=label):
                self.assertNotIn(SENTINEL_GONE, values,
                                 f"{label}：哨兵 `{SENTINEL_GONE}` 已随 `ResearchStatus` 删除，不该再出现")

    def test_the_two_writers_partition_the_waiting_reasons_exactly(self) -> None:
        """**生活侧（B 写）与研究侧（A 写）必须恰好把 12 条等待原因分成两半，互不交叠。**

        这一条是 2026-09-24 那次接口变更的可执行形式，**它本来就能抓到那个坑**：
        B 原先算全部 12 条，而 A 的 `update_waiting_in` 只收生活侧三条
        （`if not reasons <= LIFE_REASONS: raise WishRejected`）。
        **两个后果，第二个才要命**：①写不进去；②B 重算的那份迟早与 A 存的不一致，
        而「要不要写」判的是 `waiting == wish.waiting`，于是**每一轮都判成「变了」、每一轮写一次**——
        **不报错，只是版本号一直涨、页面一直抖。**

        **为什么纯策略单测抓不到**：两边各自正确，**它们的判断从没在同一个进程里相遇过**。
        这条用例就是让它们相遇。
        """
        life, research = set(LIFE_SIDE), set(storage.RESEARCH_REASONS)
        self.assertEqual(life, set(storage.LIFE_REASONS),
                         "生活侧清单两边对不上：`wish_policy.LIFE_SIDE` vs `web_travel.model.LIFE_REASONS`。"
                         "写入方分列的前提就是这两份相同。")
        self.assertEqual(set(), life & research, "两侧出现交叠：迁移注释写明**互不覆盖**，交叠会让后写的一方冲掉前一方")
        self.assertEqual(CONTRACT_WAITING_REASONS, life | research,
                         f"两侧的并集不等于合同全集：有原因码没人写，或多出一个没人认领的。{BOTH}")

    def test_image_states_agree_and_that_comment_is_now_an_invariant(self) -> None:
        """`model.py` 上那句「与 schemas.web.social.PhotoStatus 同口径」是**注释**，注释不是不变量。

        此刻两边确实相等——但它是手抄的第二份，和 `waiting_reasons` 那份同族：
        **两份必须一致的清单，要用双向用例锁住，不能靠一次性核对。**
        """
        photo = {s.value for s in PhotoStatus}
        stored = set(storage.IMAGE_STATES)
        self.assertEqual(CONTRACT_IMAGE_STATES, photo,
                         f"手账图四态：合同 vs `schemas.web.social.PhotoStatus` 对不上。{BOTH}")
        self.assertEqual(CONTRACT_IMAGE_STATES, stored,
                         f"手账图四态：合同 vs `web_travel.model.IMAGE_STATES` 对不上。{BOTH}")

    def test_unknown_is_a_state_of_its_own_in_all_three_places(self) -> None:
        """`unknown` 在三处都必须独立存在——它的含义是**可能已经花过钱**，所以不重试；
        `failed` 是确定没成、可以重试。**折叠之后「没有自动重试」照样成立，但成立的原因变了。**
        """
        for label, values in (("合同·研究", CONTRACT_RESEARCH_STATES),
                              ("合同·手账图", CONTRACT_IMAGE_STATES),
                              ("DTO·研究", {s.value for s in TravelResearchStatus}),
                              ("存储侧·研究", {storage.R_UNKNOWN, storage.R_FAILED}),
                              ("存储侧·手账图", set(storage.IMAGE_STATES)),
                              ("PhotoStatus", {s.value for s in PhotoStatus})):
            with self.subTest(where=label):
                self.assertIn("unknown", values, f"{label}：`unknown` 被折叠掉了")
                self.assertIn("failed", values, f"{label}：`failed` 不见了，那 `unknown` 也就无从区分")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
