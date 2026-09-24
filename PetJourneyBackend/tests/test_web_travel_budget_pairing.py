"""研究端口与额度账本必须成对（TRV-03；I 核出的 fail-open 耦合）。真实迁移建库与任务队列、**假**研究端口，0 次付费调用。

原先 `_reserve_in` 在没有账本时 `return None`，也就是不预占就继续发。今天不出事，只是因为没接端口就走不到那一行。
两层各钉一条，各看自己的可观察量：
  - 构造期（I 要的那一道）：`install_travel` 接了端口、没接账本 → 当场报错，不等到第一次发送；
  - 运行期：绕开 install、直接构造服务 → 在预占那一步抛出，**端口一次没被调**，没有意图回执、没有预占。
"""

from __future__ import annotations

import unittest

from travel_wish_fakes import FakeResearchPort, TravelResearchTestBase

from app.web_travel import install_travel


class TravelBudgetPairingTests(TravelResearchTestBase):
    def test_install_refuses_a_research_port_without_a_ledger(self) -> None:
        with self.assertRaises(ValueError):
            install_travel(self.storage, self.tasks, research_port=FakeResearchPort())
        travel = install_travel(self.storage, self.tasks, research_port=FakeResearchPort(), ledger=self.ledger)
        self.assertIs(travel.research.ledger, self.ledger, "对照：一起接就能装上")

    def test_a_service_built_around_install_without_a_ledger_never_sends(self) -> None:
        self.research.ledger = None
        self.propose()
        self.research.run_pending()

        self.assertEqual(self.port.calls, [], "没有账本：端口一次都没被调")
        self.assertEqual((self.receipts(), self.reservations()), ([], []), "没有意图回执、没有预占")
        task = self.task()
        self.assertEqual((task["status"], task["last_error"]), ("queued", "ResearchMisconfigured"), "按队列规则退避重试，错误名可查")


if __name__ == "__main__":
    unittest.main()
