"""一条额度预占「计入已用」多少个单位——后台展示用，与 `web_platform/budget.py` 给计数器记账的规则逐条对应。

为什么需要这一层：`web_budget_reservations.actual_units` 这一列**不能直接当计量读**。
`_settle` 落列时写的是 `reserved if actual_units is None else min(actual, reserved)`，
对 `not_sent`（状态 released）也是这样——所以一条**确定没发出**的调用，列里常常是预占量 1，
而计数器那边按 `used = 0 if outcome == "not_sent"` 一个单位都没记。直接显示这一列，
就会把没发出的调用说成计过量（2026-09-23 在演示库里实测：released 3 行列值合计 4，计数器计 0）。

逐状态的对应（改 budget.py 的记账规则时要同步改这里；
`tests/test_admin_pet_ledgers.py::CountedUnitsAnchorTests` 用真实账本对着计数器核这张表，对不上会当场失败）：

| 状态 | 计入已用 | budget.py 里对应的那一步 |
|---|---|---|
| settled | 列值 | `_settle`：`used = reserved if actual is None else min(actual, reserved)`，同一个值落进列 |
| unknown | 列值 | 同上（按已确认发出的次数计；说不出发了几次就按预占全额） |
| released | 0 | `_settle`：`used = 0 if outcome == "not_sent"`；**列里的数不代表计量** |
| expired | 预占量 | `_expire_in_tx`：`used=reserved`（列此时为空） |
| reserved | 不计入（在途） | 在途记在 `inflight_units`，还没进已用 |
"""

from __future__ import annotations

# 同一张表的 SQL 版本（给按用途聚合用）。在途返回 0：它不是"已用"，在途另有计数。
COUNTED_UNITS_SQL = (
    "CASE status WHEN 'released' THEN 0 WHEN 'reserved' THEN 0 WHEN 'expired' THEN reserved_units "
    "ELSE COALESCE(actual_units, reserved_units) END"
)


def counted_units(status: str, reserved_units: int, actual_units: int | None) -> int | None:
    """None 表示还在途（没进已用）；其余是计数器按这一行记下的已用单位数。"""
    if status == "reserved":
        return None
    if status == "released":
        return 0
    if status == "expired":
        return int(reserved_units)
    return int(reserved_units if actual_units is None else actual_units)


# 口径：released（确定没发出）计 0——哪怕原始列里写着预占量；expired（预占过期）按预占全额计；在途不计入已用
COUNTED_NOTE = ("「计入用量」和额度计数同一个算法：确定没发出的计 0（哪怕记录里写着占用量）；"
                "占着的额度过期了按全额计；还在途的不计入已用。")
