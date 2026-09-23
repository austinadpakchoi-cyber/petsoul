"""真实成图批次的金额闸门：**每一次发送之前**都要问"下一笔还付得起吗"。

停止条件写在文档里只是说明文字，挡不住任何东西。真正管用的是一个在发送点上
必须被调用的检查：它知道单价、币种、上限和已经花掉多少，算得出**下一笔之后**
会不会越线，越线就不让发。

刻意做成纯计算：不发请求、不碰供应商、不认识 SDK。执行器负责在每次发送前调用它。

计费口径（2026-09-23 核实的公开标价）：Seedream 4.5 按**成功出图的张数**计费，
0.25 元/张；审核等原因没出图的不计费。但"没出图"和"结果不明"不是一回事——
结果不明的那一笔可能已经产生费用，所以闸门按**最坏情况**把它算进已花。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import PhotoDirectorError


@dataclass(frozen=True, slots=True)
class Money:
    amount: float
    currency: str

    def __post_init__(self):
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool):
            raise PhotoDirectorError("amount_not_numeric")
        if self.amount < 0:
            raise PhotoDirectorError("amount_negative")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise PhotoDirectorError("currency_missing")


def parse_money(raw, *, field_name: str) -> Money:
    """把 {"unit"/"amount": 数字, "currency": "CNY"} 解析成金额。

    缺字段、非数字、缺币种都直接拒——**未知不得当成 0 元**。
    """
    if not isinstance(raw, dict):
        raise PhotoDirectorError(f"{field_name}_not_an_object")
    value = raw.get("unit", raw.get("amount"))
    if value is None:
        raise PhotoDirectorError(f"{field_name}_amount_missing")
    try:
        return Money(float(value), raw.get("currency", ""))
    except (TypeError, ValueError) as exc:
        raise PhotoDirectorError(f"{field_name}_amount_not_numeric") from exc


def validate_batch_cost(quote_raw, cap_raw, image_count: int) -> dict:
    """出图前的金额校验。任何一条不合格都进阻塞清单，不让批次标成可发送。"""
    problems: list[str] = []
    try:
        quote = parse_money(quote_raw, field_name="provider_quote")
    except PhotoDirectorError as exc:
        return {"ok": False, "problems": [str(exc)]}
    try:
        cap = parse_money(cap_raw, field_name="batch_cap")
    except PhotoDirectorError as exc:
        return {"ok": False, "problems": [str(exc)]}

    if quote.currency.upper() != cap.currency.upper():
        # 报价 CNY、上限 USD 直接比数值是错的，会放行一个实际超支好几倍的批次。
        problems.append(
            f"currency_mismatch:quote={quote.currency},cap={cap.currency}")
    if quote.amount <= 0:
        problems.append("provider_quote_must_be_positive")
    total = round(quote.amount * image_count, 6)
    if not problems and total > cap.amount:
        problems.append(
            f"estimated_total_exceeds_cap:{total}{quote.currency}>{cap.amount}{cap.currency}")
    return {
        "ok": not problems,
        "problems": problems,
        "unit": quote.amount,
        "currency": quote.currency,
        "image_count": image_count,
        "estimated_total": total,
        "cap": cap.amount,
    }


@dataclass
class BatchGuard:
    """执行器**必须**在每次发送前调用 `check_next()`，发送后调用 `record()`。

    `spent` 按最坏情况累加：确认成功当然算，结果不明也算——那一笔可能已经计费。
    """
    unit: float
    currency: str
    cap: float
    image_count: int
    spent: float = 0.0
    sent: int = 0
    unknown: int = 0
    stopped: str | None = None
    log: list = field(default_factory=list)

    @classmethod
    def from_spec(cls, quote_raw, cap_raw, image_count: int) -> "BatchGuard":
        checked = validate_batch_cost(quote_raw, cap_raw, image_count)
        if not checked["ok"]:
            raise PhotoDirectorError("batch_cost_invalid:" + ",".join(checked["problems"]))
        return cls(unit=checked["unit"], currency=checked["currency"],
                   cap=checked["cap"], image_count=image_count)

    @property
    def remaining(self) -> float:
        return round(self.cap - self.spent, 6)

    def check_next(self) -> None:
        """发送前的闸门。不通过就抛，执行器据此停批。"""
        if self.stopped:
            raise PhotoDirectorError(f"batch_stopped:{self.stopped}")
        if self.sent >= self.image_count:
            raise PhotoDirectorError("batch_image_count_reached")
        if round(self.spent + self.unit, 6) > self.cap:
            self.stop("cap_would_be_exceeded")
            raise PhotoDirectorError(
                f"next_call_would_exceed_cap:{self.spent}+{self.unit}>{self.cap}{self.currency}")

    def record(self, outcome: str, *, note: str = "") -> None:
        """记一次实际发送的结果。`unknown` 按已花计，并**立刻停批**。"""
        self.sent += 1
        if outcome in {"ok", "unknown"}:
            self.spent = round(self.spent + self.unit, 6)
        if outcome == "unknown":
            self.unknown += 1
            self.stop("unknown_result")
        self.log.append({"n": self.sent, "outcome": outcome,
                         "spent": self.spent, "note": note})

    def stop(self, reason: str) -> None:
        if not self.stopped:
            self.stopped = reason

    def summary(self) -> dict:
        return {
            "unit": self.unit, "currency": self.currency, "cap": self.cap,
            "planned_images": self.image_count, "sent": self.sent,
            "unknown": self.unknown, "spent_worst_case": self.spent,
            "remaining": self.remaining, "stopped": self.stopped,
            "log": list(self.log),
        }
