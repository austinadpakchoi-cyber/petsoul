"""证件卡包：身份卡、星球银行卡、照护档案、护照（纪念章）、爪爪驾驶证、登机牌、船票车票、酒店房卡。

卡面只是服务端记录的展示：编号、签发时间与关联经历都来自持久记录；尚未获得的证件也列出来，并写明获得条件。
照护档案只给主人看；银行卡的余额与流水就是现有钱包账户，不另建余额。
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.credentials import (
    CredentialDetail,
    CredentialField,
    CredentialKind,
    CredentialLink,
    CredentialStatus,
    CredentialSummary,
    LedgerEntry,
    PassportStamp,
)
from ...utils import utcnow
from ...web_credentials import CATALOG
from ...web_credentials_wiring import care_notes
from ...web_journey.illustrations import SPECIES_CN
from ...web_platform import WebAPIError, WebPrincipal, require_principal
from ._shared import cap, require_pet, web_of, web_router

router = web_router("credentials")
logger = logging.getLogger(__name__)
STATUS_TEXT = {"active": "有效", "in_progress": "在途", "used": "已使用"}


def capabilities(settings) -> list[Capability]:
    return [
        cap("credentials.wallet", "credentials", CapabilityStatus.available,
            "身份卡、银行卡、照护档案随入住签发；护照、登机牌、船票车票随真实行程签发；驾驶证在驾考通过后签发；编号与签发时间持久"),
        cap("credentials.hotel_key", "credentials", CapabilityStatus.not_implemented, "目前的旅程都是当天往返，没有过夜入住"),
    ]


def _summary(row: dict, now: datetime) -> CredentialSummary:
    info = CATALOG[row["kind"]]
    from ...web_credentials.service import CredentialService

    return CredentialSummary(credential_id=row["credential_id"], kind=CredentialKind(row["kind"]), label=info.label,
                             status=CredentialStatus(CredentialService.status_of(row, now)), number=row["number"], issued_at=row["issued_at"],
                             title=row["title"], condition=info.condition, private=info.private,
                             links=[CredentialLink(kind=link["kind"], ref_id=link["ref_id"], title=link["title"], at=link.get("at")) for link in row["links"]])


def summaries(request: Request, user_id: str, pet_id: str) -> list[CredentialSummary]:
    web = web_of(request)
    web.credentials.ensure_basics(user_id, pet_id)
    now = utcnow()
    try:
        web.driving.reconcile(pet_id, now)  # 旧数据里“场景考试已通过却没有驾驶证”的记录：打开卡包时就补签
    except Exception:  # noqa: BLE001 - 补签失败不影响看卡包；驾考阶段显示“签发中”，定时器会再试
        logger.exception("driving license reconcile failed pet=%s", pet_id)
    rows = web.credentials.rows(user_id, pet_id)
    obtained = {row["kind"] for row in rows}
    result = [_summary(row, now) for row in sorted(rows, key=lambda r: (list(CATALOG).index(r["kind"]), r["issued_at"]))]
    stage = web.driving.stage(pet_id)
    for kind, info in CATALOG.items():
        if kind not in obtained:
            learning = ("wish", "enrolled", "theory_passed", "license_pending")
            status = CredentialStatus.in_progress if kind == "driver_license" and stage in learning else CredentialStatus.not_obtained
            result.append(CredentialSummary(kind=CredentialKind(kind), label=info.label, status=status, condition=info.condition, private=info.private))
    return result


@router.get("/credentials", response_model=list[CredentialSummary])
def list_credentials(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[CredentialSummary]:
    """这只宠物的卡包（?pet_id= 指明；只照顾一只时可省略）。证件属于宠物本身，全家成员看到同一份；照护档案里的叮嘱只给写下它的那位家人。"""
    home = require_pet(request, principal, pet_id, activated=True)
    return summaries(request, principal.user_id, home.pet_id)


@router.get("/credentials/{credential_id}", response_model=CredentialDetail)
def credential_detail(credential_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> CredentialDetail:
    web = web_of(request)
    row = web.credentials.get(principal.user_id, credential_id)
    if row is None or not web.pets.is_member(principal.user_id, row["pet_id"]):
        raise WebAPIError.not_found("这张证件")
    now = utcnow()
    record = web.pets.profile(row["pet_id"])
    name, species = (record.name, SPECIES_CN.get(record.species.value, "小动物")) if record else ("TA", "小动物")
    issued = row["issued_at"].strftime("%Y-%m-%d")
    kind = row["kind"]
    detail = CredentialDetail(summary=_summary(row, now))
    home = web.homes.by_pet(row["pet_id"])
    place = web.home_places.get(home.home_id) if home else None
    if kind == "identity_card":
        detail.fields = [CredentialField(label=l, value=v) for l, v in (("名字", name), ("物种", species), ("星球编号", row["number"]),
                                                                          ("住在", place.display if place else "星球"), ("入住日期", issued))]
    elif kind == "bank_card":
        detail.fields = [CredentialField(label=l, value=v) for l, v in (("户名", f"{name} 的星球账户"), ("卡号", row["number"]), ("开户日期", issued), ("币种", "星币"))]
        detail.balance = web.economy.wallet(row["pet_id"]).balance
        detail.ledger = [_ledger(tx) for tx in request.app.state.storage.list_economy_transactions(row["pet_id"], limit=20)]
    elif kind == "care_profile":
        detail.fields = [CredentialField(label="名字", value=name), CredentialField(label="建档日期", value=issued)]
        detail.care_notes = care_notes(web.dna, web.reception, principal.user_id, row["pet_id"])
    elif kind == "passport":
        detail.fields = [CredentialField(label=l, value=v) for l, v in (("名字", name), ("物种", species), ("护照号", row["number"]), ("签发日期", issued),
                                                                          ("签发地", place.city if place else "星球"))]
        detail.stamps = [PassportStamp(**stamp) for stamp in web.credentials.stamps(row["pet_id"])]
    elif kind == "driver_license":
        data = row["data"]
        scores = data.get("scores") or {}
        exams = "　".join(f"{label} {scores[key]} 分" for key, label in (("s1", "科一"), ("s2", "科二"), ("s3", "科三"), ("s4", "科四")) if scores.get(key) is not None)
        if not exams:  # 旧版驾考（理论＋场景）
            exams = f"理论 {data.get('theory_score') or '-'}　场景驾驶 {data.get('practical_score', '-')} 分"
        detail.fields = [CredentialField(label=l, value=str(v)) for l, v in (
            ("名字", name), ("准驾车型", f"{data.get('class', 'C')}（星球小型车）"), ("证号", row["number"]), ("初次领取", issued), ("成绩", exams),
            ("签发机构", "爪爪驾校（PetSoul 星球交通局）"), ("说明", "PetSoul 世界的证件，不代表现实驾驶资格；不能交易或转赠"))]
    elif kind in ("boarding_pass", "transport_ticket"):
        data = row["data"]
        status = STATUS_TEXT.get(detail.summary.status.value, "")
        detail.fields = [CredentialField(label=l, value=v) for l, v in (("承运", data.get("carrier", "")), ("班次", data.get("code") or "-"),
                                                                          ("出发", data.get("origin", "")), ("到达", data.get("destination", "")),
                                                                          ("日期", data.get("departure", "")[:10]), ("座位", data.get("seat", "")), ("状态", status))]
    return detail


LEDGER_REFS = {"job": "journey", "travel_fee": "journey", "travel_refund": "journey", "order": "order", "shop": "home", "welcome_gift": "home"}


def _ledger_ref(key: str | None) -> tuple[str | None, str | None]:
    """按账本幂等键认出这笔钱属于哪项业务（web:job:<journey>、web:order:<order>……）；认不出就不给，不猜。"""
    parts = (key or "").split(":")
    kind = LEDGER_REFS.get(parts[1]) if len(parts) >= 3 and parts[0] == "web" else None
    return (kind, parts[2]) if kind else (None, None)


def _ledger(tx) -> LedgerEntry:
    before = (tx.before or {}).get("travel_coin", 0) or 0
    after = (tx.after or {}).get("travel_coin", 0) or 0
    ref_kind, ref_id = _ledger_ref(tx.idempotency_key)
    return LedgerEntry(tx_id=tx.tx_id, type=tx.type.value, delta=int(after) - int(before), reason=tx.reason, created_at=tx.created_at,
                       ref_kind=ref_kind, ref_id=ref_id)
