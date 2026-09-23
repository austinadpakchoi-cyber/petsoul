"""证件卡包（0.2.4 追加）：PetSoul 世界内的身份、账户、护照、票据与驾驶证。

对齐说明 §5：编号稳定唯一、签发时间持久、同一事件只签发一次；卡面只是服务端记录的展示。
这些都是 PetSoul 世界里的证件或纪念票据，不代表现实订票、预订或现实资格。
驾考（爪爪驾校）的模型在 school.py 与 school_session.py（0.3.0）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import WebModel


class CredentialKind(str, Enum):
    identity_card = "identity_card"
    bank_card = "bank_card"
    care_profile = "care_profile"
    passport = "passport"
    driver_license = "driver_license"
    boarding_pass = "boarding_pass"
    transport_ticket = "transport_ticket"
    hotel_key = "hotel_key"


class CredentialStatus(str, Enum):
    not_obtained = "not_obtained"
    in_progress = "in_progress"
    active = "active"
    used = "used"
    expired = "expired"


class CredentialLink(WebModel):
    kind: str = Field(description="journey / leg / visit / exam / home")
    ref_id: str
    title: str
    at: datetime | None = None


class CredentialField(WebModel):
    label: str
    value: str


class CredentialSummary(WebModel):
    credential_id: str | None = Field(default=None, description="尚未获得时为空")
    kind: CredentialKind
    label: str = Field(description="宠物 ID / 星球银行卡 / 照护档案 / 护照 / 爪爪驾驶证 / 登机牌 / 船票车票 / 酒店房卡")
    status: CredentialStatus
    number: str | None = Field(default=None, description="稳定唯一的证件编号；签发后不变")
    issued_at: datetime | None = Field(default=None, description="持久保存的签发时间；刷新不会变成“今天签发”")
    title: str | None = None
    condition: str = Field(description="获得条件")
    private: bool = Field(default=False, description="只给主人看（照护档案等），不进公开卡片")
    links: list[CredentialLink] = Field(default_factory=list, description="关联的经历")


class LedgerEntry(WebModel):
    tx_id: str
    type: str
    delta: int
    reason: str
    created_at: datetime
    ref_kind: str | None = Field(default=None, description="这笔钱关联的业务：journey（旅费、工资、退款）/ order（集市订单）/ home（家园商店、欢迎礼）；其他为空",
                                 json_schema_extra={"x-additive": True})
    ref_id: str | None = Field(default=None, description="关联业务的编号，例如工资与旅费对应的 journey_id（0.4.1）", json_schema_extra={"x-additive": True})


class PassportStamp(WebModel):
    city: str
    stamped_at: datetime
    journey_id: str
    title: str


class CredentialDetail(WebModel):
    summary: CredentialSummary
    fields: list[CredentialField] = Field(default_factory=list, description="卡面信息（服务端给出，前端只负责排版）")
    balance: int | None = Field(default=None, description="星球银行卡：现有钱包余额（同一个账户，不另建余额）")
    ledger: list[LedgerEntry] = Field(default_factory=list, description="星球银行卡：最近的收入与支出")
    stamps: list[PassportStamp] = Field(default_factory=list, description="护照：到达后盖的纪念章")
    care_notes: list[str] = Field(default_factory=list, description="照护档案：主人确认过的习惯、安抚方式与叮嘱（私密）")


__all__ = [
    "CredentialKind",
    "CredentialStatus",
    "CredentialLink",
    "CredentialField",
    "CredentialSummary",
    "LedgerEntry",
    "PassportStamp",
    "CredentialDetail",
]
