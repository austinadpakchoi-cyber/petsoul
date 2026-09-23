"""独立验收（工作包 Q）的跨进程恢复合同：Q-C19 一次决策在**进程真的退出之后**能不能正确接着走。

非测试模块（不以 test 开头），discover 不收集。同一个临时库、**不同进程**、假供应商，不联网、不产生付费调用。

与 Q-C13 的区别（证明范围，别混起来）：
- Q-C13 第四步是在**同一个进程**里重建对象，只证明「编号存在库里、不在内存里」；
- 这一条是若干**真正独立的进程**先后打开同一个库：第一个在模型调用发出之后 `os._exit()`（没有任何清理、没有 finally），
  后面的都是全新解释器。它证明的是「持久化数据经历进程退出、重新启动之后仍然被正确接着处理」。
- 「同一条合同跑三次结果一致」证明的是**无漂移**，与这条要证明的东西无关，两者不能互相替代。

判定口径（2026-09-23 06:20 收紧）：`reserved` / `expired` / `unknown` **都不能证明请求没发出去**，
所以**超过一轮决策保留时限之后**重启，同样不许换编号重发。只有 `released / not_sent`（确定没离开本机）之后
才允许重开编号并再发一次——这条用另一只宠物做**正向对照**，免得把问题修成永久卡住。

**版本一致性**：每个子进程在开始时、结束前（被杀的那个在 `os._exit` 之前）各把被测文件的指纹写进记录文件，
由它自己持久化，不拿父进程最后看到的磁盘指纹代表三个进程实际执行的版本。
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from runtime_contract_harness import FAIL, GUARD, LEVEL_PROCESS, PASS, Q_ROOT, ContractResult, run_child, source_digests

BRAIN_SRC, RUNTIME_SRC = "app/web_agent/brain_life.py", "app/web_agent/runtime_view.py"
BUDGET_SRC, WIRING_SRC = "app/web_platform/budget.py", "app/web_agent/brain_wiring.py"
WATCHED = (BRAIN_SRC, RUNTIME_SRC, BUDGET_SRC, WIRING_SRC)

# 子进程里跑的那一段：打开同一个库、把远端模型换成会记账的假供应商、走一次真实的 BrainLife 决策。
# crash=1 时在调用发出之后立刻 os._exit(9)——不是抛异常，是进程真的没了，退避与清编号都不会执行。
CHILD = '''
import hashlib, json, os, sys
from datetime import datetime
from pathlib import Path

CONF = json.loads({conf!r})
sys.path[:0] = [CONF["tests"]]
NOW = datetime.fromisoformat(CONF["now"])
BACKEND = Path(CONF["backend"])


class FrozenClock:
    def __call__(self):
        return NOW


def digests():
    return {{name: hashlib.sha256((BACKEND / name).read_bytes()).hexdigest()[:16] for name in CONF["watched"]}}


def note(phase, extra=None):
    """把一行事实追加进记录文件并 fsync：哪个进程、第几步、什么阶段、当时的被测指纹。"""
    with open(CONF["record"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({{"step": CONF["step"], "phase": phase, "pid": os.getpid(), **(extra or {{}})}}, ensure_ascii=False) + "\\n")
        handle.flush()
        os.fsync(handle.fileno())


# 必须在 import 任何别的 app 模块**之前**换掉统一时间入口：那些模块都是 `from ..utils import utcnow`，
# 导入时就把函数对象绑死了；晚一步替换，后导入的模块拿到的还是真实时钟（判决会直接变成 deadline_passed）。
import app.utils as utils
utils.utcnow = FrozenClock()

from app.config import Settings
from app.main import create_app
from app.schemas.runtime_internal import DecisionFailureCode
from app.web_agent.decision.ports import ModelCallError

for name, module in list(sys.modules.items()):  # 保险：已经导入过的也换一遍
    if (name == "app" or name.startswith("app.")) and callable(getattr(module, "utcnow", None)):
        module.utcnow = utils.utcnow

note("start", {{"digests": digests()}})  # 这个进程实际执行的版本，由它自己记下来


class RecordingModel:
    """假模型。mode=not_sent 时请求**确定没离开本机**；否则算已经发出去（可能已计费）。不联网。"""

    available = True
    provider_label = "Q 跨进程恢复替身"
    max_call_seconds = 5.0

    def complete(self, messages, *, max_tokens):
        note("entered")
        if CONF["mode"] == "not_sent":
            raise ModelCallError(DecisionFailureCode.provider_error, "not_sent", "q-not-sent")
        note("dispatched")
        if CONF["crash"]:
            note("exit_crash", {{"digests": digests()}})  # 被杀之前先把版本落盘
            os._exit(9)  # 进程真的没了：没有 finally、没有退避、编号不会被清
        raise ModelCallError(DecisionFailureCode.provider_error, "unknown", "q-recovery-stub")


settings = Settings(database_path=Path(CONF["db"]), upload_dir=Path(CONF["uploads"]), web_private_media_dir=Path(CONF["private"]),
                    public_base_url="http://testserver", auth_secret=CONF["secret"], apple_auth_mode="mock", scheduler_enabled=False,
                    legacy_api_policy="open", economy_admin_token="admin-test-token", web_cookie_secure=False, web_demo_catalog=True)
app = create_app(settings)
life = app.state.web.brain_life
life.mode = "live"
life.brain.model = RecordingModel()
outcome = life.consider(CONF["pet"], NOW)
note("end", {{"digests": digests()}})
print("RESULT " + json.dumps({{"status": outcome.status, "reason": outcome.reason, "operation_id": outcome.operation_id}}, ensure_ascii=False))
'''


class RecoveryContractCases:
    """与 web_base.WebPlatformTestBase 组合使用（`_sql` 由 RuntimeContractCases 提供）。"""

    def _child(self, step: str, *, pet_id: str, now, record: Path, crash: bool = False, mode: str = "dispatch") -> dict:
        """在一个**全新的解释器**里打开同一个库走一次决策。返回子进程的退出码与它打印的结论。"""
        conf = {"db": str(self.settings.database_path), "uploads": str(self.settings.upload_dir),
                "private": str(self.settings.web_private_media_dir), "secret": self.settings.auth_secret,
                "tests": str(Path(__file__).resolve().parent), "backend": str(Path(__file__).resolve().parents[1]),
                "watched": list(WATCHED), "pet": pet_id, "now": now.isoformat(),
                "record": str(record), "step": step, "crash": bool(crash), "mode": mode}
        done = run_child(CHILD.format(conf=json.dumps(conf, ensure_ascii=False)), Q_ROOT / "tmp" / "recovery")
        line = next((row for row in done.stdout.splitlines() if row.startswith("RESULT ")), None)
        return {"step": step, "returncode": done.returncode, "result": json.loads(line[7:]) if line else None,
                "stderr_tail": (done.stderr or "").strip().splitlines()[-1][:160] if done.returncode not in (0, 9) else ""}

    def _decision_state(self, pet_id: str) -> dict:
        """从库里看这只宠物此刻的决策编号与全部 life_plan 预占（父进程只读，不参与决策）。"""
        conn = sqlite3.connect(self.settings.database_path)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT decision_operation_id FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()
            rows = conn.execute("SELECT operation_id, status, outcome FROM web_budget_reservations WHERE subject_scope = ? "
                                "AND purpose = 'life_plan' ORDER BY rowid", (f"pet:{pet_id}",)).fetchall()
            return {"open_operation_id": row["decision_operation_id"] if row else None,
                    "reservations": [dict(item) for item in rows]}
        finally:
            conn.close()

    def contract_c19_recovery_across_processes(self) -> ContractResult:
        """Q-C19：进程被杀之后，后面的进程打开同一个库必须接着原来那次操作走，一次都不重发；过了保留时限也一样。"""
        from datetime import timedelta

        from web_base import LUNCH_UTC, FakeClock

        guard0 = len(GUARD.attempts)
        clock = FakeClock(LUNCH_UTC).install(self)
        owner, pet = self._brain_owner("q-c19-owner")  # 账号与宠物由父进程按正式接口建好
        _, control_pet = self._brain_owner("q-c19-control")
        record = Q_ROOT / "tmp" / f"recovery-calls-{pet}.jsonl"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text("", encoding="utf-8")
        # 子进程的隔离根与调用记录都放在 Q 自己的 tmp 下，跑完就清掉，不留垃圾
        self.addCleanup(lambda: shutil.rmtree(Q_ROOT / "tmp" / "recovery", ignore_errors=True))
        self.addCleanup(lambda: record.unlink(missing_ok=True))

        def lines() -> list:
            return [json.loads(row) for row in record.read_text(encoding="utf-8").splitlines() if row.strip()]

        def count(phase: str) -> int:
            return len([row for row in lines() if row["phase"] == phase])

        steps = [self._child("1_crash_after_dispatch", pet_id=pet, now=clock.now, record=record, crash=True)]
        after_crash = {**self._decision_state(pet), "dispatched": count("dispatched")}
        steps.append(self._child("2_fresh_process", pet_id=pet, now=clock.now + timedelta(seconds=30), record=record))
        after_restart = {**self._decision_state(pet), "dispatched": count("dispatched")}
        steps.append(self._child("3_fresh_process_again", pet_id=pet, now=clock.now + timedelta(seconds=90), record=record))
        after_second_restart = {**self._decision_state(pet), "dispatched": count("dispatched")}
        # 关键一步：过了一轮决策的保留时限再重启。预占这时多半已经 expired——但那不证明请求没发出去
        steps.append(self._child("4_after_stale_window", pet_id=pet, now=clock.now + timedelta(minutes=20), record=record))
        after_stale = {**self._decision_state(pet), "dispatched": count("dispatched")}
        # 正向对照（跨进程）：另一只宠物，模型明确“没离开本机”。第一次之后预占整笔退回，第二次必须允许重开编号、允许再进一次调用
        steps.append(self._child("5_control_not_sent", pet_id=control_pet, now=clock.now, record=record, mode="not_sent"))
        control_first = {**self._decision_state(control_pet), "entered": count("entered")}
        steps.append(self._child("6_control_allowed_again", pet_id=control_pet, now=clock.now + timedelta(minutes=20),
                                 record=record, mode="not_sent"))
        control_second = {**self._decision_state(control_pet), "entered": count("entered")}

        first = after_crash["open_operation_id"]
        used = [step["result"]["operation_id"] if step["result"] else None for step in steps]
        seen_digests = [row["digests"] for row in lines() if "digests" in row]
        # 租期内的重启与“过了保留时限”的重启分开判，免得把已经修好的部分也一并说成不合格
        within = [after_restart, after_second_restart]
        checks = {
            "第一个进程确实是被杀掉的（不是正常返回）": steps[0]["returncode"] == 9 and steps[0]["result"] is None,
            "被杀之前那次调用确实发出去了": after_crash["dispatched"] == 1,
            "被杀之后编号与预占都留在库里": bool(first) and [r["status"] for r in after_crash["reservations"]] == ["reserved"],
            "保留时限内的两次重启沿用同一个编号": used[1:3] == [first] * 2,
            "保留时限内的两次重启都没有重发": [state["dispatched"] for state in within] == [1, 1],
            "保留时限内的两次重启都没有另起一笔预占": all(len(state["reservations"]) == 1 for state in within),
            "保留时限内在途没结清就不清编号": all(state["open_operation_id"] == first for state in within),
            "**过了保留时限**仍然沿用同一个编号": used[3] == first,
            "**过了保留时限**仍然一次都不重发": after_stale["dispatched"] == 1 and len(after_stale["reservations"]) == 1,
            "到期（expired）不当作“没发出”的证明": [r["status"] for r in after_stale["reservations"]] != []
                and all(r["status"] in ("reserved", "expired", "unknown") for r in after_stale["reservations"]),
            "正向对照：确定没发出之后允许重开编号": used[5] is not None and used[5] != used[4],
            "正向对照：确定没发出之后允许再进一次调用": control_second["entered"] == control_first["entered"] + 1,
            "正向对照：没发出的预占整笔退回": all(r["status"] == "released" and r["outcome"] == "not_sent"
                                                for r in control_second["reservations"]),
            "已发出那次的费用记录跨进程一直没被回滚": all(any(row["operation_id"] == first and row["status"] != "released"
                                                                and row["outcome"] != "not_sent" for row in state["reservations"])
                                                            for state in (after_crash, *within, after_stale)),
            "每个子进程都自报了被测指纹": len(seen_digests) >= len(steps),
            "各子进程实际执行的是同一个版本": all(item == seen_digests[0] for item in seen_digests),
            "所有子进程都正常收场（没有意外报错）": all(step["returncode"] in (0, 9) and not step["stderr_tail"] for step in steps),
        }
        return ContractResult(
            "Q-C19", "进程被杀之后重新启动：同一次决策接着走，一次都不重发；过了保留时限也一样", "CR-A2、CR-Q14、A07",
            LEVEL_PROCESS, "B（brain_life ＋ 决策编号）", PASS if all(checks.values()) else FAIL,
            "四个进程先后打开同一个库：编号始终是第一次那个、假供应商只被发出过 1 次、只有 1 笔预占；"
            "正向对照里确定没发出之后换新编号并允许再进一次调用",
            {"checks": checks, "first_operation_id_present": bool(first), "steps": steps, "after_crash": after_crash,
             "after_restart": after_restart, "after_second_restart": after_second_restart, "after_stale": after_stale,
             "control_first": control_first, "control_second": control_second, "digests_reported_by_children": seen_digests},
            ["父进程按正式接口建两只宠物（一只做恢复、一只做正向对照）并打开“模型回信”，之后只做观察",
             "第一个子进程（全新解释器）走一次真实决策；假供应商把“已发出”写进记录文件并 fsync，随后在 os._exit 之前先落盘自己的指纹，再 os._exit(9)",
             "第二、三个子进程（全新解释器，+30 秒 / +90 秒）打开同一个库再走一次",
             "第四个子进程（+20 分钟，**越过一轮决策的保留时限**）再来一次：预占多半已 expired，但仍然不许换编号重发",
             "第五、六个子进程用另一只宠物做正向对照：模型明确 not_sent → 预占整笔退回后，必须允许重开编号、允许再进一次调用",
             "每个子进程自己把起止指纹写进记录文件；父进程据此核对各进程实际执行的是同一个版本",
             "**证明范围**：这一条证明的是进程退出后重新启动的恢复；同一条合同跑三次一致只证明无漂移，两者不能互换"],
            source_digests(*WATCHED), len(GUARD.attempts) - guard0)


CONTRACTS = ("c19_recovery_across_processes",)
