"""研究发布前那道复核（`research._publish_in` 开头：心愿还开着、轮次没变）为什么走不到：把证明的地基钉成用例（TRV-03；Q 复核时指出）。

那道复核只在有效的领取围栏里执行。按 Q 的写入点分类，能改心愿状态或轮次的只有这几处：
  - `update_waiting_in`、`set_research_waiting_in`：状态由 `status_for` 现算，**关不掉**（非开放状态原样返回，开放状态只在 active 与 ready 之间取值）；
  - `cancel_in`：取消，同一事务作废 queued 与 running 的研究任务，围栏随之失效；
  - `link_journey_in`：关联，要求 ready；研究在排或在跑期间研究侧挂着 research_pending，心愿是 active；
  - `complete_in`：完成，只收 linked。journey_id 只由关联写入，关联后回不到开放态，所以它碰不到研究在跑的心愿；
  - 换轮次：只有重做（`retry_in`）写 research_round，研究在排或在跑时拒绝。
流程侧的三条不变量各有用例：取消作废在跑任务（test_web_travel_research）；在跑时拒绝重做、重查期间不是 ready（test_web_travel_commands）。
这里钉的是**写入点本身**：新增或改动一个写入点，这里当场红。那时请先按上面的分类归类；若它能在研究在排或在跑时关掉心愿、或换轮次，
就给那道复核补一条真触发用例，再更新本表。「A 到不了，因为 B 先挡住了」这种传递性论证，B 那一步也得钉住（Q 的话）。

**扫描的边界**：认的是字面 SQL 里的表名，以及 `update_wish_in`、`set_research_waiting_in` 这两个名字的调用。
表名在运行时拼出来的写法看不见；`store._insert` 只做 INSERT／INSERT OR IGNORE，关不掉已有的心愿。

不联网、0 次付费调用。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from travel_wish_fakes import TravelResearchTestBase

import app
from app.web_platform.uow import unit_of_work
from app.web_travel.model import ACTIVE, CANCELLED, COMPLETED, LINKED, MISSING_FUNDS, READY, status_for

APP = Path(app.__file__).resolve().parent
MESSAGE = ("写入点变了。研究发布前那道复核（research._publish_in 开头）走不到，靠的就是这张表：先按本文件开头的分类归类；"
           "若它能在研究在排或在跑时关掉心愿、或换轮次，给那道复核补一条真触发用例，再更新本表。")

# (文件, 所在函数, 关键字实参, status 实参的写法)；"**" 表示把 **fields 透传下去
UPDATE_WISH_CALLS = {
    ("web_travel/service.py", "update_waiting_in", ("life_detail_json", "life_waiting_json", "reconsider_after", "status"), "status"),
    ("web_travel/service.py", "cancel_in", ("status",), "CANCELLED"),
    ("web_travel/service.py", "link_journey_in", ("journey_id", "status"), "LINKED"),
    ("web_travel/service.py", "complete_in", ("status",), "COMPLETED"),
    ("web_travel/service.py", "set_research_waiting_in", ("**", "research_waiting_json", "status"), "status"),
}
# `set_research_waiting_in` 把 **fields 原样交给 update_wish_in：它的调用方传进去的，同样是写入点
RESEARCH_WAITING_CALLS = {
    ("web_travel/research.py", "retry_in", ("research_round",)),
    ("web_travel/research.py", "_publish_in", ("plan_revision",)),
    ("web_travel/research.py", "_set_reason_in", ()),
}
COMPUTED = ("update_waiting_in", "set_research_waiting_in")  # 这两处写的 status 必须是 status_for 现算的
WRITE_VERBS = ("UPDATE WEB_TRAVEL_WISHES", "DELETE FROM WEB_TRAVEL_WISHES", "REPLACE INTO WEB_TRAVEL_WISHES")


def _trees():
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path.relative_to(APP).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _walk(tree):
    """(最近一层所在函数, 节点)。"""
    found = []

    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            found.append((owner, child))
            visit(child, owner)

    visit(tree, "<module>")
    return found


def _calls(tree, name: str):
    for owner, node in _walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
            if called == name:
                yield owner, node


def _keywords(call: ast.Call) -> tuple[str, ...]:
    return tuple(sorted("**" if k.arg is None else k.arg for k in call.keywords))


class WishWritePointTests(unittest.TestCase):
    def test_every_write_to_a_wish_is_one_of_the_classified_kinds(self) -> None:
        sql, updates, research, computed = set(), set(), set(), {}
        for rel, tree in _trees():
            for owner, node in _walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = " ".join(node.value.split()).upper()
                    if any(verb in text for verb in WRITE_VERBS):
                        sql.add((rel, owner))
            for owner, call in _calls(tree, "update_wish_in"):
                status = next((ast.unparse(k.value) for k in call.keywords if k.arg == "status"), None)
                updates.add((rel, owner, _keywords(call), status))
            for owner, call in _calls(tree, "set_research_waiting_in"):
                research.add((rel, owner, _keywords(call)))
            for owner, node in _walk(tree):
                if owner in COMPUTED and isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "status" for t in node.targets):
                    computed.setdefault(owner, []).append(isinstance(node.value, ast.Call) and getattr(node.value.func, "id", None) == "status_for")

        self.assertEqual(sql, {("web_travel/store.py", "update_wish_in")}, MESSAGE)
        self.assertEqual(updates, UPDATE_WISH_CALLS, MESSAGE)
        self.assertEqual(research, RESEARCH_WAITING_CALLS, MESSAGE)
        self.assertEqual(computed, {name: [True] for name in COMPUTED}, "这两处的 status 必须是 status_for 现算的；" + MESSAGE)


PLAN_MESSAGE = ("计划表的写入点变了。「这版计划已被别的旅程关联」那道守卫（service.link_journey_in 里 link_plan_in 返回 False）走不到，"
                "靠的就是这张表：先想清楚它是不是因此可达；可达就给它补一条真触发用例，再更新本表。")
PLAN_WRITE_VERBS = ("UPDATE WEB_TRAVEL_PLANS", "DELETE FROM WEB_TRAVEL_PLANS", "INTO WEB_TRAVEL_PLANS")


class PlanWritePointTests(unittest.TestCase):
    """「这版计划已被别的旅程关联」那道守卫为什么走不到：计划行的 journey_id 只在心愿同一事务里变成 linked 时写入，
    而 linked 回不到 ready（下面 ClosedStateTests）。这里钉前一半的地基：
    计划表只有一处 UPDATE、只被关联调用；插计划只有研究发布一处；新计划出生时不带旅程。"""

    def test_a_plans_journey_is_written_only_by_linking(self) -> None:
        sql, links, inserts, birth = set(), set(), set(), []
        for rel, tree in _trees():
            for owner, node in _walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = " ".join(node.value.split()).upper()
                    if any(verb in text for verb in PLAN_WRITE_VERBS):
                        sql.add((rel, owner))
                if rel == "web_travel/facts.py" and owner == "build_plan" and isinstance(node, ast.Dict):
                    birth += [ast.unparse(v) for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "journey_id"]
            links |= {(rel, owner) for owner, _ in _calls(tree, "link_plan_in")}
            inserts |= {(rel, owner) for owner, _ in _calls(tree, "insert_plan_in")}

        self.assertEqual(sql, {("web_travel/store.py", "link_plan_in")}, PLAN_MESSAGE)
        self.assertEqual(links, {("web_travel/service.py", "link_journey_in")}, PLAN_MESSAGE)
        self.assertEqual(inserts, {("web_travel/research.py", "_publish_in")}, PLAN_MESSAGE)
        self.assertEqual(birth, ["None"], "新计划出生时不带旅程；" + PLAN_MESSAGE)


class ClosedStateTests(unittest.TestCase):
    def test_a_closed_wish_never_reopens_by_recomputing_its_status(self) -> None:
        """`status_for` 对非开放状态原样返回：关联、完成、取消后，等待原因怎么变都回不到 active／ready。
        这是「有 journey_id 的心愿只可能是 linked 或 completed」的一半；另一半（journey_id 只由关联写入）由上一条的表钉着。"""
        for closed in (LINKED, COMPLETED, CANCELLED):
            for waiting in ((), (MISSING_FUNDS,)):
                for has_plan in (True, False):
                    with self.subTest(closed=closed, waiting=waiting, has_plan=has_plan):
                        self.assertEqual(status_for(closed, waiting, has_plan), closed)
        self.assertEqual((status_for(ACTIVE, (), True), status_for(READY, (MISSING_FUNDS,), True)), (READY, ACTIVE), "对照：开放态照常现算")


class CompletionReplayTests(TravelResearchTestBase):
    def test_completing_again_changes_nothing(self) -> None:
        """`complete_in` 只收 linked（Q 点名要的那条）。已完成的心愿再收到同一趟旅程的结束（世界事件重放），状态、版本号、时间都不动。
        去掉 `status = linked` 条件，这条会红：重放会把已完成的心愿再「完成」一次，版本号往上跳。"""
        self.propose()
        self.research.run_pending()
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-1")
        with unit_of_work(self.storage) as conn:
            first = self.wishes.complete_in(conn, "jr-1")
        before = [tuple(r) for r in self.query("SELECT status, wish_revision, updated_at FROM web_travel_wishes")]
        with unit_of_work(self.storage) as conn:
            again = self.wishes.complete_in(conn, "jr-1")

        self.assertEqual((first.status, again), (COMPLETED, None))
        self.assertEqual([tuple(r) for r in self.query("SELECT status, wish_revision, updated_at FROM web_travel_wishes")], before)


if __name__ == "__main__":
    unittest.main()
