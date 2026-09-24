"""游戏经济的只读对账与异常（方案 §3「游戏经济：查重复领取和异常资产」）。

判据不是后台另立的，每一条都能在领域代码里找到出处：

- **余额 ＝ 从 0 起全部 committed 流水金额之和**：`PetEconomyEngine.rebuild_derived_state` 就是这样重建钱包的
  （空钱包起步，逐条加 committed 流水的 travel_coin / star_dust / merit）。对不上＝余额被绕开账本改过，或者流水丢了。
- **流水首尾相接**：网页记账（`web_economy.adapter.apply_in`）在同一个写事务里读余额、写流水（带 before/after）、
  改余额，所以按**写入顺序**（rowid）排好的流水应当一条接一条：上一条的 after 等于下一条的 before，
  最后一条的 after 等于当前余额。用写入顺序而不用 created_at：到期结算等路径按业务时间记 created_at，不一定等于写入先后。
  这一条能指出**差额出现在哪两条流水之间**，比只报"总数不对"有用得多。
- **单条自洽**：after − before 应当等于这条的金额。
- **负余额**：`apply_in` 在余额不够时整笔拒绝，所以余额不该小于 0。
- **短时间内的重复人工补偿**：同一只宠物的后台补偿（单笔或批量）按时间排开，相邻两笔间隔不超过 24 小时的连成一组，
  一组两笔以上就标出来。这**不一定是错**
  ——可能是两件不同的事——所以只标「需要人判断」，列出每一笔的操作者与原因。

**只报不修。** 这里没有任何写：纠错要走冲正/补偿（新的一条流水），不在后台里重建或覆盖余额——
重建会把差额连同它的证据一起抹掉（方案 §3：不用 SQL 覆盖余额；纠错用冲正/补偿记录）。

规模：全表扫描，适合当前数据量。量大了要改成按宠物增量或定时快照（交接里记为剩余项）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt, utcnow
from .reversals import AdminReversals

CURRENCY_FIELDS = ("travel_coin", "star_dust", "merit")
ADMIN_SOURCES = ("admin.compensation", "admin.compensation.batch")
REPEAT_WINDOW = timedelta(hours=24)

RULES = {
    "balance_mismatch": "钱包余额不等于从 0 开始把所有已入账流水加起来的数（和游戏自己重建钱包的算法一样）。",
    "ledger_without_wallet": "有已入账的流水、加起来不是 0，却没有钱包记录。",
    "negative_balance": "钱包余额小于 0（记账时余额不够会整笔拒绝，余额不该为负）。",
    "entry_inconsistent": "单条流水的 after − before 不等于这条的金额。",
    "chain_gap": "按写入顺序相邻的两条流水首尾接不上：两次记账之间，余额被账本以外的东西改过。",
    "repeated_admin_compensation": "同一只宠物的后台补偿（单笔或批量）相邻两笔间隔不超过 24 小时的连成一组，一组两笔以上。"
                                   "不一定是错，需要人判断；已经冲正的那一笔不算在内。",
}
SEVERITY = {"balance_mismatch": "error", "ledger_without_wallet": "error", "negative_balance": "error",
            "entry_inconsistent": "error", "chain_gap": "warn", "repeated_admin_compensation": "review"}


@dataclass(slots=True)
class Finding:
    kind: str
    pet_id: str
    pet_name: str | None
    title: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def severity(self) -> str:
        return SEVERITY[self.kind]

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "severity": self.severity, "rule": RULES[self.kind]}


def _amounts(raw: str | None) -> dict[str, int]:
    try:
        data = json.loads(raw or "{}") or {}
    except ValueError:
        data = {}
    return {name: int(data.get(name) or 0) for name in CURRENCY_FIELDS}


def _coin(raw: str | None) -> int | None:
    """before/after 里的 travel_coin；这条流水没记就是 None（旧路径的流水可能不带），链条在这里断开、不硬比。"""
    try:
        data = json.loads(raw or "{}") or {}
    except ValueError:
        return None
    value = data.get("travel_coin") if isinstance(data, dict) else None
    return int(value) if isinstance(value, (int, float)) else None


class AdminEconomyChecks:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def run(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        with self.storage.connect() as conn:
            wallets = {r["pet_id"]: {name: int(r[name]) for name in CURRENCY_FIELDS}
                       for r in conn.execute("SELECT pet_id, travel_coin, star_dust, merit FROM pet_wallets")}
            names = {r["pet_id"]: r["name"] for r in conn.execute("SELECT pet_id, name FROM pets")}
            rows = conn.execute(
                "SELECT rowid AS seq, tx_id, pet_id, type, idempotency_key, amounts_json, before_json, after_json, source, operator, "
                "reason, status, created_at FROM economy_transactions ORDER BY pet_id, rowid").fetchall()
            internal = {row["idempotency_key"]: AdminReversals._internal_reason(conn, row["idempotency_key"])
                        for row in rows if row["source"] in ADMIN_SOURCES}

        by_pet: dict[str, list] = {}
        non_committed: dict[str, int] = {}
        # 已经被冲正的后台补偿（冲正流水的幂等键是 admin:reverse:<原流水号>）：不再算进「重复补偿」
        reversed_ids = {row["idempotency_key"].split(":", 2)[2] for row in rows
                        if row["status"] == "committed" and (row["idempotency_key"] or "").startswith("admin:reverse:")}
        for row in rows:
            if row["status"] != "committed":
                non_committed[row["status"]] = non_committed.get(row["status"], 0) + 1
                continue
            by_pet.setdefault(row["pet_id"], []).append(row)

        findings: list[Finding] = []
        unchained = 0
        for pet_id in sorted(set(wallets) | set(by_pet)):
            entries = by_pet.get(pet_id, [])
            name = names.get(pet_id)
            sums = {name_: 0 for name_ in CURRENCY_FIELDS}
            first_gap: dict[str, Any] | None = None
            previous = None  # (tx_id, after)
            for entry in entries:
                amounts = _amounts(entry["amounts_json"])
                for currency in CURRENCY_FIELDS:
                    sums[currency] += amounts[currency]
                before, after = _coin(entry["before_json"]), _coin(entry["after_json"])
                if before is None or after is None:
                    unchained += 1
                    previous = None
                    continue
                if after - before != amounts["travel_coin"]:
                    findings.append(Finding("entry_inconsistent", pet_id, name,
                                            f"流水 {entry['tx_id']} 自身对不上：{before} → {after}，金额却是 {amounts['travel_coin']}",
                                            {"tx_id": entry["tx_id"], "before": before, "after": after,
                                             "amount": amounts["travel_coin"], "source": entry["source"]}))
                if previous is not None and before != previous[1]:
                    gap = {"after_tx": previous[0], "before_tx": entry["tx_id"], "expected_before": previous[1],
                           "found_before": before, "delta": before - previous[1]}
                    findings.append(Finding("chain_gap", pet_id, name,
                                            f"{previous[0]} 之后余额是 {previous[1]}，{entry['tx_id']} 记账时却读到 {before}",
                                            gap))
                    first_gap = first_gap or gap
                previous = (entry["tx_id"], after)

            wallet = wallets.get(pet_id)
            if wallet is None:
                if any(sums.values()):
                    findings.append(Finding("ledger_without_wallet", pet_id, name, "有流水、没有钱包", {"ledger_sum": sums}))
                continue
            for currency in CURRENCY_FIELDS:
                if wallet[currency] != sums[currency]:
                    details: dict[str, Any] = {"currency": currency, "wallet": wallet[currency], "ledger_sum": sums[currency],
                                               "difference": wallet[currency] - sums[currency], "entries": len(entries)}
                    if currency == "travel_coin":
                        if first_gap is not None:
                            details["first_gap"] = first_gap
                        if previous is not None and previous[1] != wallet[currency]:
                            details["after_last_entry"] = {"tx_id": previous[0], "after": previous[1], "wallet_now": wallet[currency]}
                    title = (f"余额 {wallet[currency]}，流水之和 {sums[currency]}，差 {wallet[currency] - sums[currency]:+d}"
                             if entries else f"有余额 {wallet[currency]}，却没有任何流水")
                    findings.append(Finding("balance_mismatch", pet_id, name, f"{currency}：{title}", details))
                if wallet[currency] < 0:
                    findings.append(Finding("negative_balance", pet_id, name, f"{currency} 余额为 {wallet[currency]}",
                                            {"currency": currency, "wallet": wallet[currency]}))

            # 短时间内的重复人工补偿（按业务时间 created_at 看"间隔多久"，这里要的就是业务时间）
            admin = sorted((e for e in entries if e["source"] in ADMIN_SOURCES and _amounts(e["amounts_json"])["travel_coin"] > 0
                            and e["tx_id"] not in reversed_ids),
                           key=lambda e: parse_dt(e["created_at"]))
            cluster: list = []
            for entry in admin + [None]:
                if entry is not None and cluster and parse_dt(entry["created_at"]) - parse_dt(cluster[-1]["created_at"]) <= REPEAT_WINDOW:
                    cluster.append(entry)
                    continue
                if len(cluster) >= 2:
                    total = sum(_amounts(e["amounts_json"])["travel_coin"] for e in cluster)
                    findings.append(Finding(
                        "repeated_admin_compensation", pet_id, name,
                        f"{len(cluster)} 笔后台补偿、相邻间隔都不超过 24 小时，合计 {total} 星币",
                        {"total": total, "entries": [{"tx_id": e["tx_id"], "amount": _amounts(e["amounts_json"])["travel_coin"],
                                                       "source": e["source"], "operator": e["operator"], "reason": e["reason"],
                                                       "internal_reason": internal.get(e["idempotency_key"]),
                                                       "created_at": parse_dt(e["created_at"])} for e in cluster]}))
                cluster = [entry] if entry is not None else []

        order = {"error": 0, "warn": 1, "review": 2}
        findings.sort(key=lambda f: (order[f.severity], f.pet_id, f.kind))
        counts: dict[str, int] = {}
        for item in findings:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return {
            "as_of": now,
            "checked_pets": len(set(wallets) | set(by_pet)),
            "checked_entries": len(rows),
            "unchained_entries": unchained,
            "non_committed_entries": non_committed,
            "counts": counts,
            "pets_with_errors": len({f.pet_id for f in findings if f.severity == "error"}),
            "findings": [f.as_dict() for f in findings],
            "rules": RULES,
            "note": "只报不修：纠错要走冲正或补偿（新的一条流水），不在后台里重建或覆盖余额——那会把差额连同证据一起抹掉。",
            "scale_note": "全表扫描，适合当前数据量；量大了要改成按宠物增量或定时快照。",
        }
