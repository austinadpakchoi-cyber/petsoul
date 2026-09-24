"""独立验收（并行工作包 Q）：证据判定器自测 + 已接入批次的运行层合同。

- JudgeSelfTest：用人工构造的证据样本检验 scripts/verify_runtime_evidence.py 的判定（PASS/FAIL/PENDING/UNPROVEN/BLOCKED），
  并确认判定输出里不出现消息原文、不读取白名单以外的文件。只证明判定器有效，不证明产品通过。
- RuntimeAcceptanceContracts：只收已经接入、应当通过的合同（INTEGRATED）。其余合同（过期接管、旧结果拒绝、回执丢失、撤权在途、
  GET 纯读、到家等模型……）按集成窗口的要求不进默认 discover，由 `python scripts/verify_runtime_evidence.py contracts` 显式运行，
  FAIL/BLOCKED 写进 Q 的证据与报告，不 skip；对应批次接入并实际通过后再移进 INTEGRATED。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_contract_cases import CONTRACTS, RuntimeContractCases
from runtime_contract_harness import GUARD, PASS, Q_ROOT, RESULTS
from web_base import WebPlatformTestBase

_SPEC = importlib.util.spec_from_file_location("q_verify_runtime_evidence", Path(__file__).resolve().parents[2] / "scripts" / "verify_runtime_evidence.py")
judge_module = sys.modules.setdefault(_SPEC.name, importlib.util.module_from_spec(_SPEC))  # dataclass 需要模块已登记
_SPEC.loader.exec_module(judge_module)

# 已接入并实际通过的合同：全部进默认 discover 防回归（2026-09-23 03:49 前 15 条全部 PASS；05:13 追加 c14 进程租约围栏）。
# Q-C12 在 05:20 那一版 FAIL（正式撤权接口不递增 privacy_epoch），identity 修好后于 05:40 复验通过，才移进来。
# 2026-09-23 07:45：c10 / c11 / c15 在 A 宣布的稳定候选（9 份实现指纹逐个一致）上复验通过，已纳入这里防回归。
# 2026-09-23 07:55：B 重出稳定指纹表（runtime_store 410695f2 / runtime_view 1ba2b4f2 / web_agent_wiring dbbbdf67，
#   brain_life 6cd250de、brain_wiring 8c7651d8 等未改动），磁盘逐个一致，且 B 自 08:00 起冻结这批文件。
#   c13 / c19 在这组指纹上复验通过，一并纳入；c14 的结论同时重新绑定到这组指纹。
# 2026-09-23 08:15（协调单 COORD-0802-Q）：补上 C 交给 Q 独立收口的三项——
#   c20（CR-C10 围栏叠加，含进程内两种变异自证）、c21（CR-C9 借车券同事务）、c22（CR-C8 真正整轮中止），
#   三条均通过并一并纳入。至此 Q 的全部合同都在默认 discover 里：没有“显式运行才跑”的遗留项。
# 以后再出现没通过的合同，先留在 `python scripts/verify_runtime_evidence.py contracts`，FAIL 写进 Q 的证据与报告，不 skip。
INTEGRATED = ("c1a_queue_takeover", "c1b_reply_claim_crash", "c2_stale_results", "c3a_receipt_lost", "c3b_salary_sink_failure",
              "c3c_key_across_lifecycle", "c3d_takeover_race", "c4_household_isolation", "c5_revoke_in_flight", "c6_get_is_pure",
              "c7a_arrival_waits_for_model", "c7b_model_down_still_settles", "c7c_worker_blocked_by_model", "c8_api_link_fields",
              "c9_budget_without_tables", "c14_lease_fence", "c12_commit_boundary",
              "c16_fair_rotation", "c17_failure_backoff", "c18_single_decider",
              "c12b_timezone_keeps_revocation", "c15_partial_send_metering",
              "c10_photo_unknown_result", "c11_redraw_is_all_or_nothing",
              "c13_decision_operation_id", "c19_recovery_across_processes",
              "c20_fence_stacking", "c21_voucher_same_transaction", "c22_round_really_stops",
              # Q-C23 已**退役**（2026-09-24），继任者是下面的 `c34_access_boundary_in_flight`。
              # 旧规则「关掉『生成照片』即停图」随取消逐次授权询问而不复存在；函数体已从
              # runtime_contract_media.py 移除（那里有完整说明与旧证据指引），旧证据保留不动。
              "c24_photo_is_atomic",
              "c26_photo_command_facts_and_idempotency", "c27_image_quota_two_layers",
              "c28_photo_requests_are_visible", "c25_worker_uses_director_output",
              "c29_image_consumers_insert_in_one_transaction",
              "c30_budget_reconcile_after_clarification",
              "c31_unknown_counts_actual_sends",
              # 2026-09-24：叮嘱用途（c32）、旧载荷与在途撤回（c33）、以及 c23 的继任者 c34
              "c32_note_purposes_do_not_leak", "c33_late_changes_and_legacy_payloads",
              "c34_access_boundary_in_flight",
              # 2026-09-24：已付费结果的认领（c35 两条链路 ＋ c36 四个边界）
              "c35_paid_result_is_reclaimed_on_retry", "c36_reclaim_edge_cases",
              "c37_character_reclaim_edges",
              "c38_id_photo_reclaim_and_unknown")
PRIVATE = "Q-不应出现在判定输出里的原文"
NOW = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)


def _contract_test(name: str):
    def test(self) -> None:
        with GUARD.active():
            result = getattr(self, f"contract_{name}")()
        RESULTS.append(result)
        self.assertEqual(result.status, PASS, result.as_message())

    test.__name__ = f"test_{name}"
    return test


def contract_suite(names: list[str]) -> unittest.TestSuite:
    """给脚本入口用：把指定合同（含未接入的）临时组装成一个 TestCase。类不放进模块命名空间，discover 看不到。"""
    unknown = sorted(set(names) - set(CONTRACTS))
    if unknown:
        raise ValueError(f"未知合同：{unknown}")
    case = type("RuntimeContractRun", (RuntimeContractCases, WebPlatformTestBase), {f"test_{n}": _contract_test(n) for n in names})
    return unittest.defaultTestLoader.loadTestsFromTestCase(case)


class RuntimeAcceptanceContracts(RuntimeContractCases, WebPlatformTestBase):
    """已接入批次的运行层合同（隔离 SQLite、新账号、禁网替身）。"""


for _name in INTEGRATED:
    setattr(RuntimeAcceptanceContracts, f"test_{_name}", _contract_test(_name))


def _sample() -> dict:
    """一份“理想”证据（假设 DTO 已补齐关联字段、也采集了重启证据）；各场景在它上面改动。文本字段一律是不应被输出的原文。"""
    t = lambda minutes: (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    job, cafe, ferry, visit = "jn-q-job", "jn-q-cafe", "jn-q-ferry", "vs-q-cafe"
    report = {
        "base": "http://127.0.0.1:18763/api/v1/web", "ops": {"environment": "real-local", "world": {"runner": "worker", "lease_alive": True}},
        "pets": {"pet1": "PJ-A", "adopted": "PJ-B", "pet3": "PJ-C"},
        "A_register": {"step": "needs_companion", "households": [], "entry": {"kind": "adopt", "pending_adoption": {"pet_id": "PJ-B"}}},
        "A_home": {"step": "active", "cards": [{"kind": k, "issued_at": t(-299)} for k in ("identity_card", "bank_card", "care_record")],
                   "entry_still_pending": False},
        "A_household": {"adopted_resident_keeps_pet_id": True, "no_pet_id_without_choice": 409, "pets": [{"pet_id": p} for p in ("PJ-A", "PJ-B", "PJ-C")]},
        "A_relogin": {"logged_out_status": 401, "wallets_before": {"PJ-A": 12, "PJ-B": 0}, "wallets_after": {"PJ-A": 12, "PJ-B": 0}, "pets_after": 2},
        "B": {"statuses": {"B1": 200, "B2": 409}, "one_winner": True, "loser_cannot_see_winner_pet": 404, "loser_cannot_read_messages": 404,
              "A_cannot_see_B_pet": 404},
        "C_model": {"reply": {"composed_by": "model", "created_at": t(-280), "text": PRIVATE}},
        "D_cafe": {"legs": [{"time_source": "world_rule"}], "place": {"provider": "world", "place_id": "world:cafe", "name": PRIVATE}},
        "E_trip": {"ferry": [{"reference_id": "ref:1", "world_reference": "ref:1"}, {"reference_id": "ref:2", "world_reference": "ref:2"}], "wallet_after": 8},
        "F_job_started": {"pet_id": "PJ-B", "journey_id": job, "work_until": t(-60)},
        "H_duplicate": {"same_journey": True, "charged": 8},
        "H_insufficient": {"move_in": 200, "balance_before": 0, "balance_after": 0, "status": 409, "code": "INSUFFICIENT_FUNDS"},
        "H_one_place": {"status": 409, "reason": "already_traveling"},
        "family": {"joined_role": "caregiver", "private_message_hidden_from_A": True, "family_channel_same_for_both": True,
                   "caregiver_changes_settings": 403, "after_removal_status": 404},
        "A_reception": {"candidates": [{"text": PRIVATE}]},
    }
    return {
        "00-report.json": report,
        "05-D-cafe.json": {"snapshot": {"journey_id": cafe, "pet_id": "PJ-A", "planned_visit_id": visit}},
        "07-E-trip.json": {"journey_id": ferry, "fee_ledger": [{"tx_id": "tx-e", "delta": -40, "ref_id": f"web:travel_fee:{ferry}", "reason": PRIVATE}]},
        "08-C-model.json": {"sent": {"message_id": "msg-in", "created_at": t(-285), "text": PRIVATE},
                            "reply": {"message_id": "msg-out", "created_at": t(-280), "channel": "private", "sender": "pet", "composed_by": "model",
                                      "reply_to": "msg-in", "text": PRIVATE}},
        "11-F-job-verify.json": {"checked_at": t(-30), "jobs": [{"journey_id": job, "status": "done", "paid": True, "pay": 16}],
                                 "salary_entries": [{"tx_id": "tx-1", "type": "web_job_income", "delta": 16, "ref_id": f"web:job:{job}", "reason": PRIVATE},
                                                    {"tx_id": "tx-0", "type": "web_job_income", "delta": 16, "ref_id": "web:job:jn-earlier"}],
                                 "done_messages": [{"channel": "family", "created_at": t(-59), "source_event_id": f"{job}:work_done", "text": PRIVATE}]},
        "12-D-recheck.json": {"place": {"provider": "amap", "place_id": "amap:X", "name": PRIVATE}, "legs": [{"time_source": "routed_estimate"}]},
        "13-chain.json": {"journey_id": cafe, "posts": [{"visit_id": visit, "text": PRIVATE}], "timeline": [{"ref_id": cafe, "title": PRIVATE}],
                          "fee_ledger": [{"tx_id": "tx-f", "delta": -8, "ref_id": f"web:travel_fee:{cafe}"}],
                          "family_messages": [{"created_at": t(-250), "channel": "family", "source_event_id": f"{cafe}:departed", "text": PRIVATE}]},
        "14-F-restart.json": {"journey_id": job, "restarts": [{"at": t(-120), "holder_before": "h:1", "holder_after": "h:2"}]},
    }


def _strip_links(sample: dict) -> None:
    """退回到现有 DTO：流水、消息没有关联字段，回信没有 reply_to，也没有重启证据。"""
    for name, key in (("11-F-job-verify.json", "salary_entries"), ("11-F-job-verify.json", "done_messages"), ("13-chain.json", "fee_ledger"),
                      ("13-chain.json", "family_messages"), ("07-E-trip.json", "fee_ledger")):
        for row in sample[name][key]:
            for link in judge_module.ASSOC:
                row.pop(link, None)
    sample["08-C-model.json"]["reply"].pop("reply_to")
    sample.pop("14-F-restart.json")


F = "11-F-job-verify.json"
SCENARIOS = (
    ("理想样本", lambda s: None, {"C1": PASS, "E2": PASS, "F1": PASS, "F2": PASS, "F3": PASS, "H2": PASS, "CH1": PASS}, PASS),
    ("回信是模板", lambda s: s["08-C-model.json"]["reply"].update(composed_by="template"), {"C1": "FAIL", "C2": PASS}, "FAIL"),
    ("同一份工作两条工资", lambda s: s[F]["salary_entries"].append(dict(s[F]["salary_entries"][0], tx_id="tx-dup")), {"F1": "FAIL"}, "FAIL"),
    ("现有 DTO 没有关联字段", _strip_links, {"E2": "UNPROVEN", "F1": "UNPROVEN", "F2": "UNPROVEN", "F3": "UNPROVEN", "H2": "UNPROVEN",
                                          "CH1": "UNPROVEN", "C3": "UNPROVEN"}, "UNPROVEN"),
    ("打工还没到期", lambda s: s["00-report.json"]["F_job_started"].update(work_until=(NOW + timedelta(minutes=30)).isoformat()),
     {"F1": "PENDING", "F2": "PENDING", "F3": "PENDING"}, "PENDING"),
    ("两边都没抢到", lambda s: s["00-report.json"]["B"].update(statuses={"B1": 409, "B2": 409}, one_winner=False), {"B1": "FAIL"}, "FAIL"),
    ("非成员看到了别人的宠物", lambda s: s["00-report.json"]["B"].update(A_cannot_see_B_pet=200), {"B2": "FAIL"}, "FAIL"),
    ("证据里有未去敏的口令", lambda s: s["08-C-model.json"]["sent"].update(password="plain"), {"C1": "BLOCKED", "C2": "BLOCKED"}, "BLOCKED"),
    ("环境不是 real-local", lambda s: s["00-report.json"]["ops"].update(environment="demo"), {"ENV": "BLOCKED", "C1": "BLOCKED", "D1": "BLOCKED"}, "BLOCKED"),
    ("到期了还没采集 verify-job", lambda s: s.pop(F), {"F1": "UNPROVEN", "F2": "UNPROVEN"}, "UNPROVEN"),
    ("没有等到回信", lambda s: s["08-C-model.json"].update(reply=None), {"C1": "UNPROVEN", "C2": "UNPROVEN"}, "UNPROVEN"),
    ("同一趟旅程扣了两次", lambda s: s["13-chain.json"]["fee_ledger"].append({"tx_id": "tx-f2", "ref_id": "web:travel_fee:jn-q-cafe"}), {"H2": "FAIL"}, "FAIL"),
    ("到期后没入账", lambda s: s[F]["jobs"][0].update(paid=False), {"F1": "FAIL"}, "FAIL"),
    ("证据文件损坏", lambda s: s.update({"00-report.json": "{not json"}), {"ENV": "BLOCKED", "A1": "BLOCKED"}, "BLOCKED"),
)


class JudgeSelfTest(unittest.TestCase):
    def test_judge_reaches_expected_verdicts_without_leaking_text(self) -> None:
        Q_ROOT.joinpath("tmp").mkdir(parents=True, exist_ok=True)
        for name, mutate, expected, expected_overall in SCENARIOS:
            with self.subTest(name), tempfile.TemporaryDirectory(dir=Q_ROOT / "tmp") as folder:
                sample = json.loads(json.dumps(_sample()))
                mutate(sample)
                for file_name, payload in sample.items():
                    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
                    Path(folder, file_name).write_text(text, encoding="utf-8")
                Path(folder, "accounts.json").write_text("{判定器不应读取这个文件", encoding="utf-8")
                evidence = judge_module.load_evidence(Path(folder))
                cases = judge_module.judge(evidence, NOW, timedelta(minutes=10))
                got = {c.case_id: c.status for c in cases if c.case_id in expected}
                self.assertEqual(got, expected)
                self.assertEqual(judge_module.overall(cases), expected_overall)
                document = json.dumps(judge_module.result_document(cases, evidence, NOW, timedelta(minutes=10)), ensure_ascii=False, default=str)
                self.assertNotIn(PRIVATE, document, "判定输出不能带出消息原文、接待原话或地点名")
                self.assertNotIn("plain", document, "未去敏字段只报路径，不报取值")


if __name__ == "__main__":
    unittest.main()
