"""搜索用户 → 看家庭和宠物 → 诊断宠物没动静 / 照片没出来 → 执行允许的处置。

这条路径上的每个 GET 都只读既有事实；查看个人数据会写一条访问审计（这是审计，不是业务写入）。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, Request

from ...schemas.admin import AccountFreezeRequest, GrantRequest, ReasonRequest
from ...web_admin.diagnosis import photo_view
from ...web_admin.errors import AdminAPIError, request_id_of
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs, trace_read

router = admin_router("users")


@router.get("/search")
def search(request: Request, q: str = "", limit: int = 25,
           principal: AdminPrincipal = Depends(needs(Permission.USER_READ))) -> dict:
    services = admin_of(request)
    users = services.directory.search_users(q, limit)
    pets = services.directory.search_pets(q, limit)
    if q.strip():
        trace_read(request, principal, Permission.USER_READ, "user.search", "query", q.strip()[:64],
                   hits_users=len(users), hits_pets=len(pets))
    return {"query": q, "users": [asdict(u) for u in users], "pets": pets,
            "note": "没有命中就是空；后台不会为了填页面造数据。"}


@router.get("/users/{user_id}")
def user_detail(user_id: str, request: Request,
                principal: AdminPrincipal = Depends(needs(Permission.USER_READ))) -> dict:
    services = admin_of(request)
    detail = services.directory.user_detail(user_id)
    if detail is None:
        raise AdminAPIError.not_found("这个账号")
    trace_read(request, principal, Permission.USER_READ, "user.detail", "user", user_id)
    audit_entries = services.audit.recent_for_target("user", user_id, limit=20)
    return {
        "user": asdict(detail.user),
        "prefs": detail.prefs,
        "sessions": detail.sessions,
        "households": [asdict(h) for h in detail.households],
        "homes": services.belongings.homes_of_user(user_id),  # 链到「家里的东西」（仓库、菜地、偷菜记录）
        "freeze": detail.freeze,
        "recent_admin_actions": [asdict(e) for e in audit_entries],
        "redaction_note": "私聊、私人叮嘱、DNA 正文与参考图都不在这里；看这些需要单独的「看私密正文」权限，"
                          "本批没有任何角色带它。",
    }


@router.get("/users/{user_id}/ledger-summary")
def user_ledger_summary(user_id: str, request: Request,
                        principal: AdminPrincipal = Depends(needs(Permission.USER_READ))) -> dict:
    """这位用户名下各只宠物的两本账汇总。两段各要各的权限：星币段要 economy.read，调用段要 provider.read；
    只给有权限的那几段，一段都没有就拒绝——不因为能看用户就顺带看到钱。"""
    services = admin_of(request)
    economy = principal.has(Permission.ECONOMY_READ)
    calls = principal.has(Permission.PROVIDER_READ)
    if not (economy or calls):
        services.audit.record(action=f"denied:{request.method} {request.url.path}", status="denied",
                              actor_staff_id=principal.staff.staff_id, actor_username=principal.staff.username,
                              permission=f"{Permission.ECONOMY_READ.value}|{Permission.PROVIDER_READ.value}",
                              request_id=request_id_of(request), changes={"roles": list(principal.staff.roles)})
        raise AdminAPIError.forbidden(f"{Permission.ECONOMY_READ.value} 或 {Permission.PROVIDER_READ.value}",
                                      "看两本账汇总要「看星币流水与家里的库存」或「看调用用量与平台成本」权限。")
    if services.directory.user_detail(user_id) is None:
        raise AdminAPIError.not_found("这个账号")
    trace_read(request, principal, Permission.USER_READ, "user.ledger_summary", "user", user_id,
               sections=[name for name, on in (("economy", economy), ("calls", calls)) if on])
    return services.overview.user_ledger_summary(user_id, economy=economy, calls=calls)


@router.get("/pets/{pet_id}/diagnosis")
def pet_diagnosis(pet_id: str, request: Request,
                  principal: AdminPrincipal = Depends(needs(Permission.PET_READ))) -> dict:
    services = admin_of(request)
    result = services.diagnosis.pet(pet_id)
    if result is None:
        raise AdminAPIError.not_found("这只宠物")
    trace_read(request, principal, Permission.PET_READ, "pet.diagnosis", "pet", pet_id)
    brief = services.directory.pet_brief(pet_id)
    owner = services.directory.pet_owner(pet_id)
    payload = asdict(result)
    payload["photos"] = [photo_view(photo) for photo in result.photos]
    return {**payload, "pet": asdict(brief) if brief else None, "owner_user_id": owner,
            "read_only_note": "这次查询按当前事实评估了一次心跳，没有执行、没有记录、没有调用任何模型，也没有推进世界。"}


@router.get("/photos/{illustration_id}")
def photo_detail(illustration_id: str, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.TASK_READ))) -> dict:
    services = admin_of(request)
    photo = services.diagnosis.photo(illustration_id)
    if photo is None:
        raise AdminAPIError.not_found("这张照片的记录")
    trace_read(request, principal, Permission.TASK_READ, "photo.detail", "illustration", illustration_id)
    return {**photo_view(photo),
            "semantics": {
                "ready": "已经出图。",
                "processing": "在排队或正在画。",
                "failed": "明确没画成；额度已经结清或退回，可以做一次受控恢复。",
                "unknown": "已经发出去、结果没确认。不是失败，也不是没发送：不自动重发、不抹掉费用记录，"
                           "要处理先去供应商那边确认。",
            }}


@router.get("/photos")
def pending_photos(request: Request, limit: int = 50,
                   principal: AdminPrincipal = Depends(needs(Permission.TASK_READ))) -> dict:
    photos = admin_of(request).diagnosis.pending_photos(limit)
    return {"photos": [photo_view(p) for p in photos]}


# ---- 写操作 ----
@router.get("/users/{user_id}/freeze/preview")
def freeze_preview(user_id: str, request: Request,
                   principal: AdminPrincipal = Depends(needs(Permission.ACCOUNT_FREEZE))) -> dict:
    return admin_of(request).commands.freeze_preview(user_id)


@router.post("/users/{user_id}/freeze")
def set_freeze(user_id: str, body: AccountFreezeRequest, request: Request,
               principal: AdminPrincipal = Depends(needs(Permission.ACCOUNT_FREEZE, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.set_account_frozen(context(request, principal), user_id, frozen=body.frozen,
                                                reason=body.reason, expected_version=body.expected_version)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: str, body: ReasonRequest, request: Request,
                    principal: AdminPrincipal = Depends(needs(Permission.ACCOUNT_REVOKE_SESSION, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.revoke_user_sessions(context(request, principal), user_id, reason=body.reason)


@router.post("/photos/{illustration_id}/recover")
def recover_photo(illustration_id: str, body: ReasonRequest, request: Request,
                  principal: AdminPrincipal = Depends(needs(Permission.TASK_RECOVER, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.recover_photo(context(request, principal), illustration_id, reason=body.reason,
                                           diagnosis=services.diagnosis)


@router.get("/economy/grant/preview")
def grant_preview(request: Request, pet_id: str, amount: int = 20, player_note: str | None = None,
                  principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_GRANT))) -> dict:
    return admin_of(request).commands.grant_preview(pet_id, amount, player_note)


@router.post("/economy/grant")
def grant(body: GrantRequest, request: Request,
          principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_GRANT, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.grant_coins(context(request, principal), body.pet_id, body.amount, reason=body.reason,
                                         player_note=body.player_note)
