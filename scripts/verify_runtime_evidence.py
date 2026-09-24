#!/usr/bin/env python3
"""PetSoul 独立验收（并行工作包 Q）：真实验收证据判定器 + 运行层合同回归入口。离线、只读、禁网。

    python scripts/verify_runtime_evidence.py judge [--evidence-dir DIR] [--now 2026-09-22T17:30:00Z] [--grace-minutes 10] [--json-out PATH]
    python scripts/verify_runtime_evidence.py contracts [--only c4_household_isolation ...] [--json-out PATH] [--keep]
    python scripts/verify_runtime_evidence.py selftest

judge：判定 scripts/real_acceptance.py 写出的去敏证据（PetJourneyBackend/data/web-real-acceptance/evidence/NN-*.json）。
- 只读白名单文件（EVIDENCE_FILES），绝不读取 accounts.json、auth-secret、run.json、日志或数据库；不连接任何服务；
- 每个文件解析后只保留白名单字段（FIELDS），其余立即丢弃；不输出消息原文、DNA、接待原话、用户名或 user_id；
- 发现未去敏的口令/令牌类字段时相关用例判 BLOCKED，只报字段路径；
- 结论 PASS / FAIL / PENDING（业务还没到期，不判成功也不判失败）/ UNPROVEN（缺能证明结论的关联证据）/ BLOCKED（证据不可读、
  不安全或前提不满足）。整体取最严重者 FAIL > BLOCKED > UNPROVEN > PENDING > PASS；退出码 0 PASS、1 FAIL、2 BLOCKED、3 UNPROVEN、4 PENDING、64 用法错误；
- “恰好一次”只按工作实例/旅程/源事件关联字段计数；账户流水总数、余额差、消息文案只作旁证，不能代替关联证据。

contracts：在隔离 SQLite、新账号、禁网模型替身下跑 Q-C1…Q-C7 合同（用例在 PetJourneyBackend/tests/runtime_contract_cases.py）。
尚未接入的合同不进默认 unittest discover（集成窗口要求），由这里显式运行，FAIL/BLOCKED 如实写进证据，不 skip。退出码 0 全部 PASS、1 有 FAIL、2 有 BLOCKED/ERROR。

selftest：用人工构造的样本自测判定器（PetJourneyBackend/tests/test_web_runtime_acceptance.py::JudgeSelfTest）；只证明判定器有效，不证明产品通过。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "PetJourneyBackend"
Q_ROOT = BACKEND / "data" / "reviews" / "q-4d18-20260922"
DEFAULT_EVIDENCE = BACKEND / "data" / "web-real-acceptance" / "evidence"
ACCEPTANCE_SCRIPT = ROOT / "scripts" / "real_acceptance.py"
# 核对断言覆盖时读的脚本版本；脚本变了要重新核对 OBSERVATION_ONLY
ACCEPTANCE_SCRIPT_SHA256 = "1f1e9e0d4423b1fa2129c737a5d7a6f7b105c61e89e5491ac097adf4ba56056d"

PASS, FAIL, PENDING, UNPROVEN, BLOCKED = "PASS", "FAIL", "PENDING", "UNPROVEN", "BLOCKED"
SEVERITY = {PASS: 0, PENDING: 1, UNPROVEN: 2, BLOCKED: 3, FAIL: 4}
EXIT_CODE = {PASS: 0, FAIL: 1, BLOCKED: 2, UNPROVEN: 3, PENDING: 4}
SCRUBBED = "[不记录]"
SENSITIVE_KEY = re.compile(r"^(token|password|csrf|cookie|join_path|secret|api_?key|authorization|auth_secret|access_token|refresh_token|invite_token)$"
                           r"|(_token|_secret|_password)$", re.IGNORECASE)
ASSOC = ("ref_id", "journey_id", "work_id", "job_id", "source_ref", "source_event_id", "idempotency_key", "reply_to", "in_reply_to")
LEVEL_HTTP = "集成（real-local 本地 HTTP 实跑；非线上）"
LEVEL_REAL = "真实供应商（real-local 本地；非线上）"
LEVEL_NATURAL = "自然时间（real-local 本地；非线上）"

# ---- 白名单：读哪些文件、每个文件取哪些字段（a.b[].c；len:a.b 只取列表长度）----
EVIDENCE_FILES = ("00-report.json", "05-D-cafe.json", "07-E-trip.json", "08-C-model.json", "09-family.json", "10-B-isolation.json",
                  "11-F-job-verify.json", "12-D-recheck.json", "13-chain.json", "14-F-restart.json", "15-linkage.json",
                  "24-brain-real-model.json", "27-brain-real-model-live.json")
# 15 号是原窗口从验收库只读导出的关联表（账本按幂等键、消息按 source_event_id）。Q 只用它做关联计数，不读它的判定结论
# （20/21 号是原窗口自己的判定，Q 不读）。注意：这是库级导出，不代表接口已经下发这些字段，CR-Q1/CR-Q2 仍然成立。
LINKAGE_KEYS = ("D", "E", "F")
FIELDS: dict[str, tuple[str, ...]] = {
    "00-report.json": (
        "base", "started_at", "finished_at", "ops.environment", "ops.world.runner", "ops.world.lease_alive", "ops.world.last_error",
        "ops.providers[].provider", "ops.providers[].state", "pets.pet1", "pets.adopted", "pets.pet3",
        "A_register.step", "len:A_register.households", "A_register.entry.kind", "A_register.entry.pending_adoption.pet_id",
        "A_home.step", "A_home.cards[].kind", "A_home.cards[].issued_at", "A_home.entry_still_pending",
        "A_household.adopted_resident_keeps_pet_id", "A_household.no_pet_id_without_choice", "A_household.pets[].pet_id",
        "A_relogin.logged_out_status", "A_relogin.wallets_before", "A_relogin.wallets_after", "A_relogin.pets_after",
        "B.statuses", "B.one_winner", "B.loser_cannot_see_winner_pet", "B.loser_cannot_read_messages", "B.A_cannot_see_B_pet",
        "C_model.reply.composed_by", "C_model.reply.created_at", "C_model.dna_version",
        "D_cafe.legs[].time_source", "D_cafe.place.provider", "D_cafe.place.place_id",
        "E_trip.ferry[].reference_id", "E_trip.ferry[].world_reference", "E_trip.ferry[].world_service", "E_trip.wallet_after",
        "F_job_started.pet_id", "F_job_started.journey_id", "F_job_started.work_from", "F_job_started.work_until", "F_job_started.home_at",
        "H_duplicate.same_journey", "H_duplicate.charged",
        "H_insufficient.move_in", "H_insufficient.balance_before", "H_insufficient.balance_after", "H_insufficient.status", "H_insufficient.code",
        "H_one_place.status", "H_one_place.reason",
        "family.joined_role", "family.private_message_hidden_from_A", "family.family_channel_same_for_both", "family.caregiver_changes_settings",
        "family.after_removal_status",
    ),
    "05-D-cafe.json": ("snapshot.journey_id", "snapshot.pet_id", "snapshot.planned_visit_id"),
    # 远行的旅费流水：验收脚本目前不采集；将来补采时按 journey_id 关联判定
    "07-E-trip.json": ("journey_id", "pet_id", "fee_ledger[].tx_id", "fee_ledger[].delta", *(f"fee_ledger[].{k}" for k in ASSOC)),
    "08-C-model.json": ("sent.message_id", "sent.created_at", "reply.message_id", "reply.created_at", "reply.channel", "reply.sender",
                        "reply.composed_by", "reply.reply_to", "reply.in_reply_to"),
    "09-family.json": ("joined_role", "private_message_hidden_from_A", "family_channel_same_for_both", "caregiver_changes_settings", "after_removal_status"),
    "10-B-isolation.json": ("statuses", "one_winner", "loser_cannot_see_winner_pet", "loser_cannot_read_messages", "A_cannot_see_B_pet"),
    "11-F-job-verify.json": ("checked_at", "jobs[].journey_id", "jobs[].status", "jobs[].paid", "jobs[].pay",
                             "salary_entries[].tx_id", "salary_entries[].type", "salary_entries[].delta", *(f"salary_entries[].{k}" for k in ASSOC),
                             "done_messages[].channel", "done_messages[].created_at", *(f"done_messages[].{k}" for k in ASSOC)),
    "12-D-recheck.json": ("checked_at", "place.provider", "place.place_id", "legs[].time_source"),
    # 13 号由验收脚本经接口采集：0.4.1 起流水带 ref_kind/ref_id、来信带 source_event_id，可以按接口层判定
    "13-chain.json": ("checked_at", "journey_id", "posts[].visit_id", "posts[].source_event_id", "timeline[].ref_id", "fee_ledger[].tx_id",
                      "fee_ledger[].delta", "fee_ledger[].type", "fee_ledger[].ref_kind", *(f"fee_ledger[].{k}" for k in ASSOC),
                      "family_messages[].created_at", "family_messages[].message_id", "family_messages[].channel",
                      *(f"family_messages[].{k}" for k in ASSOC)),
    # I 的真实模型验证（scripts/verify_brain_live.py）：全新临时库、固定时钟、只配对话模型，跑完即删。Q 只复核字段，不重跑、不新增付费调用
    **{name: ("模式", "模型供应商", "模型可用", "结论.status", "结论.composed_by", "结论.destination_key", "结论.operation_id",
              "真实调用次数.之前", "真实调用次数.之后", "真的成行了吗.journey_id", "运行记录.last_decision_by", "记录时间")
       for name in ("24-brain-real-model.json", "27-brain-real-model-live.json")},
    # 重启证据：重启前后的世界租约持有者/任务领取代数，指向同一份工作
    "14-F-restart.json": ("journey_id", "restarts[].at", "restarts[].holder_before", "restarts[].holder_after",
                          "restarts[].claim_generation_before", "restarts[].claim_generation_after"),
    "15-linkage.json": ("exported_at", "read_mode", "c_reply.message_id", "c_reply.composed_by", "c_reply.sender", "c_reply.channel", "c_reply.reply_to",
                        *(f"journeys.{k}.{p}" for k in LINKAGE_KEYS for p in
                          ("journey.journey_id", "journey.lifecycle", "journey.fee", "ledger[].idempotency_key", "ledger[].type", "ledger[].delta",
                           "messages[].source_event_id", "messages[].channel", "messages[].audience", "events[].event_key"))),
}
# 验收脚本里“只记录观察值、没有断言/不会失败退出”的路径（行号对应 ACCEPTANCE_SCRIPT_SHA256），以及现在由哪个用例判定
# 2026-09-23：原窗口给验收脚本加了自己的判定器（scripts/real_acceptance_judge.py，写 20/21 号），run / verify-job 按判定返回退出码。
# 下面这些是当初“只记录不判定”的路径；Q 独立判定同样的条件，不读 20/21 号的结论。
OBSERVATION_ONLY = (
    ("run():217-222", "领养后入住等待 pet_away：等满 3600 秒仍 409 也继续往下走", "A3"),
    ("run():201、210-212、226-229", "A_register / A_home / A_household 只记录，不判定", "A1、A2、A3"),
    ("run():256-257", "H_duplicate：same_journey=false 或扣款不是一次都不会失败；扣款用余额差，没有关联到这趟旅程", "H1、H2"),
    ("run():274-275", "H_one_place 只记录状态码与原因", "H3"),
    ("run():283-291", "C：composed_by 为 model 或 template 都算找到回复；等不到回复也不失败", "C1、C2"),
    ("run():307-312", "family：角色、私聊隔离、频道一致、权限、移除都只记录", "FAM1"),
    ("run():327-341", "B：两边都 409 时仍把 B2 当赢家继续；one_winner 与三个 404 只记录", "B1、B2"),
    ("run():333-337", "H_insufficient：状态码、错误码、余额前后只记录", "H4"),
    ("run():350-351", "A_relogin：退出后状态码与重登前后余额只记录", "A4"),
    ("run():265-270", "E：参考班次与动物世界编号的对应、扣款次数没有判定", "E1、E2"),
    ("verify_job():412-427", "工资按 type 过滤整个账户流水、消息按“干完啦”文案过滤；没有按这份工作断言恰好一次", "F1、F2"),
    ("chain():380-400", "只收集地图、频道、动态、时间线、流水，没有逐条断言它们指向同一趟行程", "CH1"),
)


def _unsafe_paths(value: Any, path: str = "") -> list[str]:
    """未去敏的口令/令牌类字段路径（只看键名与“是否为占位”，不输出取值）。"""
    found: list[str] = []
    items = value.items() if isinstance(value, dict) else ((None, v) for v in value) if isinstance(value, list) else ()
    for key, item in items:
        here = f"{path}.{key}".lstrip(".") if key is not None else f"{path}[]"
        if key is not None and SENSITIVE_KEY.search(str(key)) and item not in (None, "", SCRUBBED):
            found.append(here)
        found += _unsafe_paths(item, here)
    return found


def pick(data: Any, path: str) -> Any:
    """按 a.b[].c 取值；列表里缺失的元素保留为 None（保持对齐）；缺失返回 None。"""
    if "[]" in path:
        head, _, tail = path.partition("[]")
        items = pick(data, head)
        if not isinstance(items, list):
            return None
        return [pick(item, tail.lstrip(".")) if tail else item for item in items]
    node = data
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def project(data: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in fields:
        value = pick(data, spec[4:] if spec.startswith("len:") else spec)
        out[spec] = (len(value) if isinstance(value, list) else None) if spec.startswith("len:") else value
    return out


@dataclass
class Loaded:
    name: str
    status: str  # ok / missing / unreadable / unsafe
    fields: dict[str, Any] = field(default_factory=dict)
    problem: str | None = None


def load_evidence(directory: Path) -> dict[str, Loaded]:
    loaded: dict[str, Loaded] = {}
    for name in EVIDENCE_FILES:
        path = directory / name
        if not path.is_file():
            loaded[name] = Loaded(name, "missing")
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            loaded[name] = Loaded(name, "unreadable", problem=type(exc).__name__)
            continue
        unsafe = _unsafe_paths(raw)
        loaded[name] = Loaded(name, "unsafe", problem="未去敏字段：" + ", ".join(unsafe[:10])) if unsafe else Loaded(name, "ok", project(raw, FIELDS[name]))
        del raw
    return loaded


@dataclass
class Case:
    case_id: str
    title: str
    level: str
    acceptance: str
    owner: str
    gating: bool = True
    note: str | None = None
    checks: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        return max((c["status"] for c in self.checks), key=SEVERITY.__getitem__) if self.checks else UNPROVEN

    def add(self, name: str, status: str, observed: Any = None, expected: Any = None, note: str | None = None) -> None:
        self.checks.append({"name": name, "status": status, "observed": observed, "expected": expected, "note": note})


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _need(case: Case, loaded: Loaded, keys: list[str]) -> bool:
    """证据可用且所需字段都在；否则记 UNPROVEN（缺）或 BLOCKED（不可读/不安全）并返回 False。"""
    if loaded.status == "missing":
        case.add(f"{loaded.name} 存在", UNPROVEN, observed="缺文件")
    elif loaded.status != "ok":
        case.add(f"{loaded.name} 可安全读取", BLOCKED, observed=loaded.problem)
    elif any(loaded.fields.get(k) is None for k in keys):
        case.add("所需字段齐全", UNPROVEN, observed={"缺字段": [k for k in keys if loaded.fields.get(k) is None]})
    else:
        return True
    return False


def _eq(case: Case, name: str, observed: Any, expected: Any) -> None:
    case.add(name, PASS if observed == expected else FAIL, observed=observed, expected=expected)


def _rows(loaded: Loaded, prefix: str) -> list[dict]:
    """把 prefix[].x 并列字段拼回行（只含白名单字段）。"""
    columns = {k[len(prefix) + 3:]: v for k, v in loaded.fields.items() if k.startswith(f"{prefix}[].") and isinstance(v, list)}
    size = max((len(v) for v in columns.values()), default=0)
    return [{name: (values[i] if i < len(values) else None) for name, values in columns.items()} for i in range(size)]


def _source_rows(api_rows: list[dict], db_rows: list[dict]) -> tuple[list[dict], str]:
    """优先用接口采集的证据；接口证据没有关联字段时才退回验收库导出，并如实标出层级。"""
    if any(r.get(k) for r in api_rows for k in ASSOC):
        return api_rows, "接口证据（13-chain：验收脚本读接口采集）"
    return db_rows, "库级导出（15-linkage：验收库只读导出，不代表接口下发）"


def _linkage_of(link: Loaded, journey_id: str | None) -> str | None:
    """15 号关联表里哪一段对应这趟旅程（按 journey_id 找，不依赖 D/E/F 这些标签）。"""
    if link.status != "ok" or not journey_id:
        return None
    return next((f"journeys.{k}" for k in LINKAGE_KEYS if link.fields.get(f"journeys.{k}.journey.journey_id") == journey_id), None)


def _linked(rows: list[dict], target: str) -> int | None:
    """按关联字段数出指向 target（旅程/工作/源事件）的条数；条目根本没有关联字段时返回 None（UNPROVEN）。"""
    key = next((k for k in ASSOC if any(r.get(k) for r in rows)), None)
    if key is None:
        return None
    return sum(1 for r in rows if isinstance(r.get(key), str) and (r[key] == target or r[key].endswith(f":{target}") or r[key].startswith(f"{target}:")))


def judge(evidence: dict[str, Loaded], now: datetime, grace: timedelta) -> list[Case]:
    report, model, cafe, chain = (evidence[n] for n in ("00-report.json", "08-C-model.json", "05-D-cafe.json", "13-chain.json"))
    get = report.fields.get
    cases: list[Case] = []
    env = Case("ENV", "证据来自 real-local 环境（真实供应商用例的前提）", LEVEL_REAL, "§1 环境", "I")
    if _need(env, report, ["ops.environment"]):
        env.add("ops.environment", PASS if get("ops.environment") == "real-local" else BLOCKED, get("ops.environment"), "real-local")
    cases.append(env)
    real = env.status == PASS

    a1 = Case("A1", "新账号注册：先不建宠物，入口记住访客页选中的伙伴且未自动领养", LEVEL_HTTP, "A", "I")
    if _need(a1, report, ["A_register.step", "len:A_register.households", "A_register.entry.kind"]):
        _eq(a1, "注册后 step", get("A_register.step"), "needs_companion")
        _eq(a1, "注册后家庭数", get("len:A_register.households"), 0)
        _eq(a1, "入口类型", get("A_register.entry.kind"), "adopt")
        _eq(a1, "入口带回选中的伙伴", bool(get("A_register.entry.pending_adoption.pet_id")), True)
    a2 = Case("A2", "入住：状态 active，身份卡、银行卡、照护档案都已签发", LEVEL_HTTP, "A", "I",
              note="入住会把注册入口标为已处理（EntryStore：完成领养/建宠/接受邀请后标记），entry_still_pending 只观察不判定")
    if _need(a2, report, ["A_home.step", "A_home.cards[].issued_at"]):
        _eq(a2, "入住后 step", get("A_home.step"), "active")
        issued = get("A_home.cards[].issued_at") or []
        a2.add("证件都有签发时间", PASS if len(issued) >= 3 and all(issued) else FAIL, {"证件数": len(issued), "有签发时间": sum(1 for i in issued if i)}, ">= 3 且都有")
    a3 = Case("A3", "一个家多只宠物：领养保留 pet_id；多宠时不指明宠物 409", LEVEL_HTTP, "A、§3", "I")
    if _need(a3, report, ["A_household.adopted_resident_keeps_pet_id", "A_household.no_pet_id_without_choice", "A_household.pets[].pet_id"]):
        _eq(a3, "领养后 pet_id 不变", get("A_household.adopted_resident_keeps_pet_id"), True)
        _eq(a3, "不指明宠物的状态码", get("A_household.no_pet_id_without_choice"), 409)
        _eq(a3, "同一个家里不同宠物数", len(set(get("A_household.pets[].pet_id"))), 3)
    a4 = Case("A4", "退出后 401；重新登录后宠物与各自余额一致", LEVEL_HTTP, "A", "I")
    if _need(a4, report, ["A_relogin.logged_out_status", "A_relogin.wallets_before", "A_relogin.wallets_after", "A_relogin.pets_after"]):
        before = get("A_relogin.wallets_before")
        _eq(a4, "退出后读取家的状态码", get("A_relogin.logged_out_status"), 401)
        a4.add("重登前后每只宠物余额一致", PASS if before and before == get("A_relogin.wallets_after") else FAIL, {"一致": before == get("A_relogin.wallets_after")})
        _eq(a4, "重登后宠物数", get("A_relogin.pets_after"), len(before or {}))
    cases += [a1, a2, a3, a4]

    b_src, bp = (report, "B.") if get("B.statuses") is not None else (evidence["10-B-isolation.json"], "")
    b1 = Case("B1", "两个新账号同时领养同一位居民：只有一个成功", LEVEL_HTTP, "B", "I")
    if _need(b1, b_src, [f"{bp}statuses", f"{bp}one_winner"]):
        statuses = b_src.fields[f"{bp}statuses"]
        _eq(b1, "两个请求的状态码", sorted(v for v in statuses.values() if isinstance(v, int)) if isinstance(statuses, dict) else statuses, [200, 409])
        _eq(b1, "脚本记录的 one_winner", b_src.fields[f"{bp}one_winner"], True)
    b2 = Case("B2", "非成员看不到别人的宠物与消息（404）", LEVEL_HTTP, "B", "I")
    keys = [f"{bp}{k}" for k in ("loser_cannot_see_winner_pet", "loser_cannot_read_messages", "A_cannot_see_B_pet")]
    if _need(b2, b_src, keys):
        for key in keys:
            _eq(b2, key.split(".")[-1], b_src.fields[key], 404)
    cases += [b1, b2]

    c1 = Case("C1", "本次私聊回信由真实模型生成（composed_by=model）", LEVEL_REAL, "C", "I")
    c2 = Case("C2", "通讯可回复（model 或 template 均可）", LEVEL_REAL, "C", "I")
    c3 = Case("C3", "回信能追溯到这条输入（reply_to / 输入边界）", LEVEL_REAL, "A18（运行方案）", "I", gating=False,
              note="MessageSummary 目前不下发 reply_to；需 I 在 DTO 追加后才能判定")
    composer, reply_at = model.fields.get("reply.composed_by"), parse_time(model.fields.get("reply.created_at"))
    if not real:
        c1.add("前提：real-local 环境", BLOCKED, get("ops.environment"))
    elif _need(c1, model, ["sent.created_at"]):
        if reply_at is None:
            c1.add("观察到 TA 的回信", UNPROVEN, "没有回信记录", note="等待窗口内没有回信；不能据此判定模型可用")
        else:
            _eq(c1, "回信发送方", model.fields.get("reply.sender"), "pet")
            _eq(c1, "回信频道", model.fields.get("reply.channel"), "private")
            sent_at = parse_time(model.fields["sent.created_at"])
            c1.add("回信晚于这条消息", PASS if sent_at and reply_at >= sent_at else FAIL, "时间先后")
            c1.add("composed_by", PASS if composer == "model" else FAIL if composer == "template" else UNPROVEN, composer, "model",
                   "template 只证明通讯可回复，不能算真实模型回信" if composer == "template" else None)
    if _need(c2, model, ["sent.created_at"]):
        c2.add("有 TA 的私聊回信", PASS if composer in ("model", "template") else UNPROVEN, composer)
    if _need(c3, model, ["sent.message_id"]):
        api_link = model.fields.get("reply.reply_to") or model.fields.get("reply.in_reply_to")
        replied_to = api_link or evidence["15-linkage.json"].fields.get("c_reply.reply_to")
        source = "接口证据（08-C-model）" if api_link else "库级导出（15-linkage c_reply）"
        c3.note = f"证据层级：{source}。接口层的 reply_to 另由合同 Q-C8 在隔离库里直接核对过" if replied_to else c3.note
        c3.add("回信关联的输入", UNPROVEN if replied_to is None else PASS if replied_to == model.fields["sent.message_id"] else FAIL,
               "接口 MessageSummary 与 15 号 c_reply 都没有 reply_to" if replied_to is None else {"对应上了": replied_to == model.fields["sent.message_id"], "来源": source})
    cases += [c1, c2, c3]

    recheck = evidence["12-D-recheck.json"]
    d1 = Case("D1", "附近活动用真实地点，路程有来源（D 复跑：新账号、家在中环）", LEVEL_REAL, "D", "I")
    if not real:
        d1.add("前提：real-local 环境", BLOCKED, get("ops.environment"))
    elif _need(d1, recheck, ["place.provider", "legs[].time_source"]):
        provider = recheck.fields["place.provider"]
        d1.add("地点供应商", PASS if provider in ("amap", "google") and recheck.fields.get("place.place_id") else FAIL, provider, "amap/google + place_id")
        sources = recheck.fields["legs[].time_source"]
        d1.add("每段路程都有时间来源", PASS if sources and all(sources) else FAIL, sources)
    d2 = Case("D2", "主流程里的附近活动：地图失败时落到“星球内的地方”并有标注", LEVEL_REAL, "D", "I", gating=False,
              note="验收文档已说明西贡那次高德连接被重置后按规则落到星球内；这里只核对落点有明确标注")
    if _need(d2, report, ["D_cafe.place.provider"]):
        d2.add("落点来源有标注", PASS if get("D_cafe.place.provider") in ("amap", "google", "world") else FAIL, get("D_cafe.place.provider"))
    e1 = Case("E1", "远行：参考班次与动物世界编号可追溯", LEVEL_REAL, "E", "I")
    if not real:
        e1.add("前提：real-local 环境", BLOCKED, get("ops.environment"))
    elif _need(e1, report, ["E_trip.ferry[].reference_id", "E_trip.ferry[].world_reference"]):
        refs, worlds = get("E_trip.ferry[].reference_id"), get("E_trip.ferry[].world_reference")
        e1.add("船段数（去程＋回程）", PASS if len(refs) >= 2 else FAIL, len(refs), ">= 2")
        e1.add("动物世界编号指向参考班次", PASS if refs and all(r and r == w for r, w in zip(refs, worlds)) else FAIL, [r == w for r, w in zip(refs, worlds)])
    trip, link = evidence["07-E-trip.json"], evidence["15-linkage.json"]
    e2 = Case("E2", "Q 的 E2：远行（港澳）扣款恰好一次（按这趟旅程关联）", LEVEL_REAL, "E", "I",
              note="与 I 判定器里的 E2（出发前按作息改签或取消退款）不是同一项；那项由 I 的等待进程在 22:21Z 之后判。"
                   "本项关联证据来自 15 号验收库导出（库级），07 号接口证据没有采集旅费流水")
    if _need(e2, trip, ["journey_id"]):
        journey_id = trip.fields["journey_id"]
        prefix = _linkage_of(link, journey_id)
        rows = [r for r in _rows(link, f"{prefix}.ledger") if r.get("type") == "web_travel_fee"] if prefix else _rows(trip, "fee_ledger")
        count = _linked(rows, journey_id)
        e2.add("这趟旅程的旅费流水条数", UNPROVEN if count is None else PASS if count == 1 else FAIL,
               {"扣款后余额（旁证）": get("E_trip.wallet_after"), "有关联流水": False} if count is None else {"条数": count, "金额": [r.get("delta") for r in rows]}, 1,
               "缺按 journey_id 关联的旅费流水" if count is None else None)
        fee = link.fields.get(f"{prefix}.journey.fee") if prefix else None
        if count == 1 and fee:
            _eq(e2, "扣款金额等于行程票价", rows[0].get("delta"), -fee)
    cases += [d1, d2, e1, e2]

    h1 = Case("H1", "同一幂等键重复出发只成立一次", LEVEL_HTTP, "H", "I")
    if _need(h1, report, ["H_duplicate.same_journey"]):
        _eq(h1, "两次返回同一趟旅程", get("H_duplicate.same_journey"), True)
    h2 = Case("H2", "重复出发只扣一次钱（按这趟旅程关联）", LEVEL_HTTP, "H", "I")
    if _need(h2, cafe, ["snapshot.journey_id"]):
        journey_id = cafe.fields["snapshot.journey_id"]
        prefix = _linkage_of(link, journey_id)
        api_rows = [r for r in _rows(chain, "fee_ledger") if r.get("type") in (None, "web_travel_fee")] if chain.status == "ok" else []
        db_rows = [r for r in _rows(link, f"{prefix}.ledger") if r.get("type") == "web_travel_fee"] if prefix else []
        rows, source = _source_rows(api_rows, db_rows)
        h2.note = f"关联证据层级：{source}"
        count = _linked(rows, journey_id)
        h2.add("这趟旅程的旅费流水条数", UNPROVEN if count is None else PASS if count == 1 else FAIL,
               {"余额差（旁证）": get("H_duplicate.charged"), "流水条目有关联字段": False} if count is None else {"条数": count, "金额": [r.get("delta") for r in rows], "来源": source},
               1, "余额差是账户级旁证，不能证明这趟旅程只扣一次" if count is None else None)
        charged = get("H_duplicate.charged")
        if count == 1 and rows[0].get("delta") is not None and charged is not None:  # 两边都有才比；缺字段不当作不一致
            _eq(h2, "扣款金额与余额差一致", -rows[0]["delta"], charged)
        if count == 1 and rows[0].get("ref_kind") is not None:
            _eq(h2, "流水的 ref_kind", rows[0]["ref_kind"], "journey")
    h3 = Case("H3", "在外面的宠物不能再出发", LEVEL_HTTP, "H", "I")
    if _need(h3, report, ["H_one_place.status"]):
        _eq(h3, "状态码", get("H_one_place.status"), 409)
        _eq(h3, "原因", get("H_one_place.reason"), "already_traveling")
    h4 = Case("H4", "旅费不够时远行不成立、余额不变", LEVEL_HTTP, "H", "I",
              note="“没有生成行程”无法从 map_status 判断：领养来的居民领养前就有旅程记录，/journey/map 可能返回旧旅程")
    if _need(h4, report, ["H_insufficient.move_in", "H_insufficient.status"]):
        if get("H_insufficient.move_in") != 200:
            h4.add("前提：赢家的居民已入住", UNPROVEN, get("H_insufficient.move_in"), 200)
        else:
            _eq(h4, "状态码", get("H_insufficient.status"), 409)
            _eq(h4, "错误码", get("H_insufficient.code"), "INSUFFICIENT_FUNDS")
            before = get("H_insufficient.balance_before")
            h4.add("余额前后不变（账户级旁证：可证伪、不能单独证实）", PASS if before is not None and before == get("H_insufficient.balance_after") else FAIL,
                   {"before": before, "after": get("H_insufficient.balance_after")})
    cases += [h1, h2, h3, h4]

    fam_src, fp = (report, "family.") if get("family.joined_role") is not None else (evidence["09-family.json"], "")
    fam = Case("FAM1", "家庭：邀请成为共同照顾者、私聊隔离、频道一致、权限与移除", LEVEL_HTTP, "§3", "I")
    expect = {"joined_role": "caregiver", "private_message_hidden_from_A": True, "family_channel_same_for_both": True,
              "caregiver_changes_settings": 403, "after_removal_status": 404}
    if _need(fam, fam_src, [f"{fp}{k}" for k in expect]):
        for key, value in expect.items():
            _eq(fam, key, fam_src.fields[f"{fp}{key}"], value)
    cases.append(fam)
    cases += _judge_job(evidence, report, now, grace)

    ch = Case("CH1", "同一趟行程在动态、时间线、家庭频道、流水里互相指向", LEVEL_HTTP, "§0②（chain）", "I")
    if _need(ch, chain, ["journey_id"]):
        journey_id, refs, visits = chain.fields["journey_id"], chain.fields.get("timeline[].ref_id") or [], chain.fields.get("posts[].visit_id") or []
        ch.add("时间线条目都指向这趟旅程", UNPROVEN if not refs else PASS if all(r == journey_id for r in refs) else FAIL, len(refs))
        planned = cafe.fields.get("snapshot.planned_visit_id") if cafe.status == "ok" and cafe.fields.get("snapshot.journey_id") == journey_id else None
        ch.add("公开动态指向这趟旅程的到访", UNPROVEN if not (visits and planned) else PASS if all(v == planned for v in visits) else FAIL,
               len(visits) if planned else "chain 的旅程不是 05 号证据那趟，缺少到访号可比对")
        prefix = _linkage_of(link, journey_id)
        messages, message_source = _source_rows(_rows(chain, "family_messages"), _rows(link, f"{prefix}.messages") if prefix else [])
        fees, fee_source = _source_rows([r for r in _rows(chain, "fee_ledger") if r.get("type") in (None, "web_travel_fee")],
                                        [r for r in _rows(link, f"{prefix}.ledger") if r.get("type") == "web_travel_fee"] if prefix else [])
        ch.note = f"来信证据层级：{message_source}；流水证据层级：{fee_source}"
        linked_messages, linked_fees = _linked(messages, journey_id), _linked(fees, journey_id)
        ch.add("家庭频道来信指向这趟旅程", UNPROVEN if linked_messages is None else PASS if linked_messages >= 1 else FAIL,
               "条目没有关联字段" if linked_messages is None else linked_messages)
        ch.add("旅费流水指向这趟旅程", UNPROVEN if linked_fees is None else PASS if linked_fees == 1 else FAIL,
               "条目没有关联字段" if linked_fees is None else linked_fees, 1)
        if messages:
            sources = [m.get("source_event_id") for m in messages if m.get("source_event_id")]
            ch.add("同一个源事件没有重复来信", PASS if len(set(sources)) == len(sources) and sources else FAIL,
                   {"来信条数": len(sources), "不同源事件": len(set(sources))})
            channels = {m.get("channel") for m in messages if m.get("channel")}
            if channels:  # 证据里带频道才判；没有这个字段不当作不合格
                ch.add("这趟旅程的来信都在家庭频道", PASS if channels <= {"family"} else FAIL, sorted(channels))
    cases.append(ch)

    brain = Case("BRAIN1", "自主决策用真实模型（复核 I 的临时库验证：shadow 与 live 各一次）", "真实供应商（全新临时库＋固定时钟＋单次调用；不是自然时间，也不是线上）",
                 "R4、A21", "I", gating=False,
                 note="Q 没有重跑、没有新增付费调用，只复核 I 写出的证据字段；结论只覆盖那个临时库里的那一次，"
                      "不能升级为 18763 自然时间运行或线上证明")
    for name, expect in (("24-brain-real-model.json", "proposed"), ("27-brain-real-model-live.json", "departed")):
        evidence_file = evidence[name]
        if _need(brain, evidence_file, ["结论.composed_by", "模式"]):
            mode = evidence_file.fields["模式"]
            brain.add(f"{mode}：由真实模型作出选择", PASS if evidence_file.fields["结论.composed_by"] == "model" else FAIL,
                      evidence_file.fields["结论.composed_by"], "model")
            brain.add(f"{mode}：这次决策的状态", PASS if evidence_file.fields.get("结论.status") == expect else FAIL,
                      evidence_file.fields.get("结论.status"), expect)
            brain.add(f"{mode}：真实调用次数", PASS if evidence_file.fields.get("真实调用次数.之后") == 1 else UNPROVEN,
                      {"之前": evidence_file.fields.get("真实调用次数.之前"), "之后": evidence_file.fields.get("真实调用次数.之后")}, 1,
                      "证据只记了调用后的计数；调用前为空（此前没有记录）")
            if expect == "departed":
                brain.add("live：模型的选择真的变成了行程（只在那个临时库里）", PASS if evidence_file.fields.get("真的成行了吗.journey_id") else FAIL,
                          bool(evidence_file.fields.get("真的成行了吗.journey_id")), True)
    cases.append(brain)
    return cases


def _judge_job(evidence: dict[str, Loaded], report: Loaded, now: datetime, grace: timedelta) -> list[Case]:
    """F：自然时间打工（工资恰好一次、家庭来信恰好一次、中途重启的证据）。未到期（含宽限）一律 PENDING。"""
    f1 = Case("F1", "自然时间打工：这份工作的工资恰好入账一次", LEVEL_NATURAL, "F", "I",
              note="11 号证据自述：salary_entries 与 done_messages 来自验收库只读关联导出（库级），jobs 来自接口")
    f2 = Case("F2", "自然时间打工：家庭频道“干完活”来信恰好一次", LEVEL_NATURAL, "F", "I",
              note="同上：按源事件的计数来自库级导出")
    f3 = Case("F3", "打工期间重启 API 与任务进程的证据（前后持有者、同一份工作）", LEVEL_NATURAL, "F", "I")
    if not all([_need(c, report, ["F_job_started.journey_id", "F_job_started.work_until"]) for c in (f1, f2, f3)]):
        return [f1, f2, f3]
    journey_id, due = report.fields["F_job_started.journey_id"], parse_time(report.fields["F_job_started.work_until"])
    if due is None or now < due + grace:
        for c in (f1, f2, f3):
            c.add("业务到期", PENDING if due else UNPROVEN, {"now": _iso(now), "work_until": _iso(due) if due else None, "grace_minutes": int(grace.total_seconds() // 60)},
                  note="还没到期（含宽限），不判成功也不判失败" if due else "工作结束时间无法解析")
        return [f1, f2, f3]
    verify = evidence["11-F-job-verify.json"]
    checked = parse_time(verify.fields.get("checked_at")) if verify.status == "ok" else None
    for case in (f1, f2):
        if verify.status == "missing":
            case.add("verify-job 证据", UNPROVEN, "已到期但还没有 11-F-job-verify.json", note="由原窗口在打工结束后运行 verify-job 采集")
        elif verify.status != "ok":
            case.add("verify-job 证据可安全读取", BLOCKED, verify.problem)
        elif checked is None or checked < due:
            case.add("核对时间晚于工作结束", UNPROVEN, verify.fields.get("checked_at"), f">= {_iso(due)}")
    if verify.status == "ok" and checked is not None and checked >= due:
        job = next((j for j in _rows(verify, "jobs") if j.get("journey_id") == journey_id), None)
        if job is None:
            f1.add("工作记录里有这份工作", UNPROVEN, "jobs 里没有这趟 journey_id")
        else:
            f1.add("这份工作已结束且标记已入账", PASS if job.get("status") == "done" and job.get("paid") is True else FAIL,
                   {"status": job.get("status"), "paid": job.get("paid")}, {"status": "done", "paid": True})
            salaries = _rows(verify, "salary_entries")
            count = _linked(salaries, journey_id)
            f1.add("按这份工作关联的工资条数", UNPROVEN if count is None else PASS if count == 1 else FAIL,
                   {"按类型过滤的整个账户工资条数（旁证）": len(salaries), "条目有关联字段": False} if count is None else count, 1,
                   "LedgerEntry 只有 tx_id/type/delta/reason/created_at；按类型或文案计数不能证明这份工作恰好一次" if count is None else None)
        messages = _rows(verify, "done_messages")
        count = _linked(messages, journey_id)
        f2.add("按源事件关联的“干完活”来信条数", UNPROVEN if count is None else PASS if count == 1 else FAIL,
               {"按文案筛出的条数（旁证）": len(messages), "条目有关联字段": False} if count is None else count, 1,
               "MessageSummary 不下发 source_event_id；按文案计数不能证明恰好一次" if count is None else None)
    restart = evidence["14-F-restart.json"]
    if restart.status == "missing":
        f3.add("重启证据", UNPROVEN, "没有 14-F-restart.json", note="只看到工资到账不能证明经历过重启；需要重启前后的持有者/领取代数，且指向同一份工作")
    elif _need(f3, restart, ["journey_id", "restarts[].holder_before", "restarts[].holder_after"]):
        _eq(f3, "重启证据指向这份工作", restart.fields["journey_id"], journey_id)
        before, after = restart.fields["restarts[].holder_before"], restart.fields["restarts[].holder_after"]
        f3.add("每次重启前后持有者不同", PASS if before and all(b and a and b != a for b, a in zip(before, after)) else FAIL, len(before))
    return [f1, f2, f3]


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def overall(cases: list[Case]) -> str:
    return max([c.status for c in cases if c.gating] or [UNPROVEN], key=SEVERITY.__getitem__)


def result_document(cases: list[Case], evidence: dict[str, Loaded], now: datetime, grace: timedelta) -> dict[str, Any]:
    digest = hashlib.sha256(ACCEPTANCE_SCRIPT.read_bytes()).hexdigest() if ACCEPTANCE_SCRIPT.is_file() else None
    status = overall(cases)
    return {"judged_at": _iso(now), "grace_minutes": int(grace.total_seconds() // 60), "overall": status, "exit_code": EXIT_CODE[status],
            "levels_not_covered": ["线上（没有任何部署证据）"], "evidence_files": {n: e.status for n, e in evidence.items()},
            "cases": [{"case_id": c.case_id, "title": c.title, "status": c.status, "gating": c.gating, "level": c.level, "acceptance": c.acceptance,
                       "owner": c.owner, "note": c.note, "checks": c.checks} for c in cases],
            "observation_only_paths": [{"where": w, "what": t, "now_judged_by": j} for w, t, j in OBSERVATION_ONLY],
            "acceptance_script": {"sha256": digest, "matches_reviewed_version": digest == ACCEPTANCE_SCRIPT_SHA256}}


def print_table(document: dict[str, Any], key: str = "cases") -> None:
    for case in document[key]:
        flag = "" if case.get("gating", True) else "（仅提示，不计入整体）"
        print(f"- {case.get('case_id') or case.get('contract_id'):<7} {case['status']:<8} {case['title']}{flag} ｜ {case['level']}")
        for check in case.get("checks", []):
            if check["status"] != PASS:
                observed = json.dumps(check["observed"], ensure_ascii=False, default=str)[:220]
                print(f"      · {check['status']:<8} {check['name']}：{observed}" + (f" ｜ {check['note']}" if check["note"] else ""))


def _bootstrap(run_root: Path):
    """合同回归与自测前：先隔离环境（必须早于第一次 import app），再把后端与测试目录加入 sys.path。"""
    sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
    import runtime_contract_harness as harness

    info = harness.isolate(run_root)
    return harness, info


def _app_digests() -> dict[str, str]:
    """app/ 下每个 .py 的 SHA-256[:16]。取两次（导入前／跑完后）就能看出跑的过程中实现有没有被改。"""
    import hashlib

    return {str(path.relative_to(BACKEND)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()[:16] for path in sorted((BACKEND / "app").rglob("*.py"))}


def run_contracts(names: list[str] | None, json_out: Path | None, keep: bool) -> int:
    run_root = Q_ROOT / "tmp" / f"contracts-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    at_load = _app_digests()  # **导入 app 之前**：这才是这个进程真正加载的那一版
    harness, info = _bootstrap(run_root)
    import runtime_contract_cases as cases
    import test_web_runtime_acceptance as suite_module

    requested = names or list(cases.CONTRACTS)
    try:
        outcome = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite_module.contract_suite(requested))
    finally:
        if not keep:
            shutil.rmtree(run_root, ignore_errors=True)
    results = [{**r.__dict__, "status": r.status} for r in harness.RESULTS]
    # 用例自身没走到判定（前置请求失败、断言在返回结论之前炸了）：列为 ERROR，不当作 PASS 或 FAIL。
    # failures 也要收——只收 errors 的话，前置断言失败会变成“这条合同没出现在结果里”，整体还报 PASS。
    judged = {r["contract_id"].lower().replace("-", "") for r in results}  # Q-C12 → qc12
    for test, trace in list(outcome.errors) + list(outcome.failures):
        name = test.id().rsplit(".", 1)[-1]  # test_c12_commit_boundary
        if any(key.endswith(name.split("_")[1]) for key in judged):
            continue  # 这条合同已经给出了 FAIL/BLOCKED 结论，assertEqual 只是把它抛出来，不重复记一条
        results.append({"contract_id": name, "title": "用例执行出错（未得到合同结论）", "status": "ERROR",
                        "level": "-", "observed": trace.strip().splitlines()[-1][:300], "checks": []})
    if len(results) < len(requested):  # 少一条就是少一条证据：不能让“没跑到”看起来像“通过”
        results.append({"contract_id": "RUN", "title": f"请求 {len(requested)} 条，只拿到 {len(results)} 条结论", "status": "BLOCKED",
                        "level": "-", "observed": {"requested": requested, "verdicts": [r["contract_id"] for r in results],
                                                   "tests_run": outcome.testsRun}, "checks": []})
    # 跑的过程中被改过的实现：谁的合同引用到，就在那条上标出来——这一轮不作为那个版本的稳定验收
    at_end = _app_digests()
    drifted = sorted({name for name in set(at_load) | set(at_end) if at_load.get(name) != at_end.get(name)})
    for r in results:
        touched = sorted(set(drifted) & set((r.get("sources") or {})))
        if touched:
            r["version_drift"] = {name: {"at_load": at_load.get(name), "at_end": at_end.get(name)} for name in touched}
    if any(r.get("version_drift") for r in results):
        results.append({"contract_id": "RUN", "title": "跑的过程中实现被改动：这一轮不绑稳定版本", "status": "BLOCKED", "level": "-",
                        "observed": {"drifted": drifted}, "checks": []})
    worst = "FAIL" if any(r["status"] == FAIL for r in results) else "BLOCKED" if any(r["status"] in (BLOCKED, "ERROR") for r in results) else PASS
    referenced = sorted({name for r in results for name in (r.get("sources") or {})})
    document = {"run_at": _iso(datetime.now(timezone.utc)), "overall": worst, "isolation": info, "network_attempts_total": len(harness.GUARD.attempts),
                "requested": requested, "tests_run": outcome.testsRun,
                # 结论绑的是**导入 app 之前**取的这一份；跑完的那一份只用来看有没有漂移
                "implementation_at_load": {name: at_load.get(name) for name in referenced},
                "implementation_drifted_during_run": drifted,
                "levels_not_covered": ["真实供应商", "自然时间", "线上"], "contracts": results}
    print(f"合同回归 {document['run_at']}  整体：{worst}  禁网拦截 {document['network_attempts_total']} 次")
    for r in results:
        print(f"- {r['contract_id']:<7} {r['status']:<8} {r['title']} ｜ {r['level']}")
        if r["status"] != PASS:
            print(f"      · 观察：{json.dumps(r['observed'], ensure_ascii=False, default=str)[:400]}")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(document, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {PASS: 0, "FAIL": 1}.get(worst, 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    judge_cmd = sub.add_parser("judge", help="判定一份证据目录")
    judge_cmd.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    judge_cmd.add_argument("--now", help="判定时刻（ISO 8601，默认当前 UTC）")
    judge_cmd.add_argument("--grace-minutes", type=int, default=10, help="到期后再等多久才判定（任务进程每 30 秒一轮）")
    judge_cmd.add_argument("--json-out", type=Path, help="完整结论写成 JSON（只含白名单字段）")
    contracts_cmd = sub.add_parser("contracts", help="隔离环境里跑运行层合同回归")
    contracts_cmd.add_argument("--only", nargs="*", help="只跑这些合同（名字见 runtime_contract_cases.CONTRACTS）")
    contracts_cmd.add_argument("--json-out", type=Path)
    contracts_cmd.add_argument("--keep", action="store_true", help="保留临时数据库（默认跑完删除）")
    sub.add_parser("selftest", help="用人工构造的样本自测判定器")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 64 if exc.code else 0
    if args.action == "contracts":
        return run_contracts(args.only, args.json_out, args.keep)
    if args.action == "selftest":
        run_root = Q_ROOT / "tmp" / f"selftest-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        try:
            _bootstrap(run_root)
            import test_web_runtime_acceptance as suite_module

            outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(suite_module.JudgeSelfTest))
        finally:
            shutil.rmtree(run_root, ignore_errors=True)
        return 0 if outcome.wasSuccessful() else 1
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if now is None or not args.evidence_dir.is_dir():
        print("用法错误：--now 需要 ISO 时间；--evidence-dir 必须是已存在的目录", file=sys.stderr)
        return 64
    grace = timedelta(minutes=max(args.grace_minutes, 0))
    evidence = load_evidence(args.evidence_dir)
    document = result_document(judge(evidence, now, grace), evidence, now, grace)
    print(f"判定时间 {document['judged_at']}（宽限 {document['grace_minutes']} 分钟）  整体：{document['overall']}  退出码 {document['exit_code']}")
    print("证据文件：" + "，".join(f"{k}={v}" for k, v in document["evidence_files"].items()))
    print_table(document)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(document, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return document["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
