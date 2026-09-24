"""平台调用成本：价格表（只追加）与区间估算。

读（价格与估算）要 `provider.read`；录价与作废要 `cost.manage`（默认只随平台负责人）。
这里的金额只有人民币 / 美元两种，各算各的；与游戏星币没有任何关系，也不在同一个页面里相加。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import PriceAddRequest, ReasonRequest, RelayImportRequest
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ...web_admin.pricing import BILLED_NOTE, CURRENCIES, UNIT_NOTE, default_window, parse_day
from ._shared import admin_of, admin_router, context, needs

router = admin_router("costs")


@router.get("/costs/prices")
def list_prices(request: Request, principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    services = admin_of(request)
    return {
        "prices": [row.as_dict() for row in services.pricing.prices()],
        "observed_scopes": services.pricing.observed_scopes(),
        "currencies": list(CURRENCIES),
        "can_manage": principal.has(Permission.COST_MANAGE),
        "unit_note": UNIT_NOTE,
        "billed_note": BILLED_NOTE,
        "history_note": "价格只追加：改价就录一条生效时间更晚的新价；录错了就作废那一条（留原因）。历史不删不改。",
    }


@router.post("/costs/prices", status_code=201)
def add_price(body: PriceAddRequest, request: Request,
              principal: AdminPrincipal = Depends(needs(Permission.COST_MANAGE, write=True))) -> dict:
    return admin_of(request).pricing.add(context(request, principal), provider=body.provider, purpose=body.purpose,
                                         currency=body.currency, unit_price=body.unit_price,
                                         effective_from=body.effective_from, source_note=body.source_note,
                                         model_note=body.model_note)


@router.post("/costs/prices/{price_id}/retire")
def retire_price(price_id: str, body: ReasonRequest, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.COST_MANAGE, write=True))) -> dict:
    return admin_of(request).pricing.retire(context(request, principal), price_id, reason=body.reason)


@router.get("/costs/estimate")
def estimate(request: Request, start: str | None = None, end: str | None = None,
             principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    """`start` / `end` 是 UTC 记账日（YYYY-MM-DD），默认最近 7 天；一次最多 31 天。只读，不调用任何供应商。"""
    default_start, default_end = default_window()
    return admin_of(request).pricing.estimate(start=parse_day(start, default_start), end=parse_day(end, default_end))


# ---- 经中转站的逐次调用回执（c84a 审查 ADM-COST-01）----
@router.get("/costs/consumption")
def consumption(request: Request, days: int = 30, principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    """四块分开：中转实测用量 / 按有来源价格估算 / 供应商账单确认 / 结果未确认·待对账。平台用量，不写访问审计。"""
    return admin_of(request).relay.consumption(days=max(1, min(int(days), 90)))


@router.post("/costs/relay-receipts/import")
def import_relay_receipts(body: RelayImportRequest, request: Request,
                          principal: AdminPrincipal = Depends(needs(Permission.COST_MANAGE, write=True))) -> dict:
    """离线导入（临时桥接）：只收白名单里的 PetSoul 专属客户端；重复不记两次、同号冲突留错不覆盖。"""
    return admin_of(request).relay.import_records(context(request, principal), body.records, source_note=body.source_note,
                                                  file_name=body.file_name)
