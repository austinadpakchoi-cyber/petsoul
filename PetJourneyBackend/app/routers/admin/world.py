"""把还没进后台的管理项接进来（方案 §3）：宠物的东西、家里的东西、系统运行。

全部只读：不推进世界、不调模型、不改任何状态。查看个人相关的数据写一条访问审计（审计，不是业务写入）。
不取任何正文——哪些字段不取，写在 `app/web_admin/belongings.py` 开头，用例逐条断言。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import ResidentListingRequest
from ...web_admin.errors import AdminAPIError
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ..web.public import invalidate as invalidate_public
from ._shared import admin_of, admin_router, context, needs, needs_any, trace_read

router = admin_router("world")


@router.get("/pets/{pet_id}/belongings")
def pet_belongings(pet_id: str, request: Request,
                   principal: AdminPrincipal = Depends(needs(Permission.PET_READ))) -> dict:
    result = admin_of(request).belongings.pet(pet_id)
    if result is None:
        raise AdminAPIError.not_found("这只宠物")
    trace_read(request, principal, Permission.PET_READ, "pet.belongings", "pet", pet_id)
    return result


@router.get("/homes/{home_id}")
def home_detail(home_id: str, request: Request,
                principal: AdminPrincipal = Depends(needs(Permission.USER_READ))) -> dict:
    """菜地与偷菜记录要 user.read；**仓库（库存与变动）另要 economy.read**——不因为能看用户就顺带看到资产。"""
    pantry = principal.has(Permission.ECONOMY_READ)
    result = admin_of(request).belongings.home(home_id, pantry=pantry)
    if result is None:
        raise AdminAPIError.not_found("这个家")
    trace_read(request, principal, Permission.USER_READ, "home.detail", "home", home_id, sections=["farm", "steals"] + (["pantry", "orders"] if pantry else []))
    if not pantry:
        result["pantry_note"] = "仓库里的东西属于游戏资产，要「看星币流水与家里的库存」权限才能看。"
    return result


@router.get("/users/{user_id}/social")
def user_social(user_id: str, request: Request, principal: AdminPrincipal = Depends(needs(Permission.USER_READ))) -> dict:
    """这位玩家发过的动态与评论（公开范围里的前 40 个字）、拉黑与被拉黑、关注、点赞、举报与被举报的次数。"""
    services = admin_of(request)
    if services.directory.user_detail(user_id) is None:
        raise AdminAPIError.not_found("这个账号")
    trace_read(request, principal, Permission.USER_READ, "user.social", "user", user_id)
    return services.social.user(user_id)


@router.get("/residents")
def residents(request: Request, principal: AdminPrincipal = Depends(needs_any(Permission.USER_READ, Permission.CONTENT_READ))) -> dict:
    """待领养居民名单：客服（「我想领养的那只怎么没了」）与内容运营（居民档案）都要看，所以两条权限任一即可。

    **被哪位玩家领养**是玩家信息：只给有 user.read 的人；只有 content.read 的内容运营看得到档案与状态，看不到领养人。
    """
    players = principal.has(Permission.USER_READ)
    trace_read(request, principal, Permission.USER_READ if players else Permission.CONTENT_READ,
               "resident.list", "residents", "all", adopters=players)
    result = admin_of(request).residents.list()
    if not players and result["residents"]:
        for row in result["residents"]:
            row.update(adopted_by=None, adopted_by_name=None, adopted_household_id=None, adopted_home_id=None)
        result["adopters_note"] = "被哪位玩家领养属于玩家信息，要「查用户与家庭」权限才能看。"
    return result


@router.post("/residents/{candidate_id}/listing")
def set_resident_listing(candidate_id: str, body: ResidentListingRequest, request: Request,
                         principal: AdminPrincipal = Depends(needs(Permission.RESIDENT_MANAGE, write=True))) -> dict:
    """撤下 / 放回一位待领养居民（不删除、不暂停）。成功后当场清掉访客页缓存，玩家那一侧不等 30 秒。"""
    result = admin_of(request).listing.set_listed(context(request, principal), candidate_id, listed=body.listed,
                                                  reason=body.reason, expected_version=body.expected_version)
    invalidate_public(request.app)
    return result


@router.get("/system")
def system_status(request: Request, principal: AdminPrincipal = Depends(needs(Permission.OPS_READ))) -> dict:
    return admin_of(request).system.status()
