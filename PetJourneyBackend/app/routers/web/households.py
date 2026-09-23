"""家庭共同照顾（0.4.0）：家庭详情、成员与角色、退出/移除、家庭设置、邀请（创建/列表/撤销/预览/接受）、每位家人和宠物之间的称呼。

- 一只宠物只属于一个家庭；一个家庭可以有多位成员、多只宠物；称呼（妈妈、哥哥……）不带权限，权限只看角色（admin / caregiver）；
- 邀请令牌只在创建时返回一次，服务端只存摘要；有有效期、可撤销、只能用一次；接受邀请不会复制宠物、不重复发奖励；
- 移除成员立即生效（每次请求都重新检查成员关系）；家庭至少保留一位管理员。
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, Request, Response

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.household import (
    HouseholdBrief,
    HouseholdDetail,
    HouseholdInvite,
    HouseholdMember,
    HouseholdRole,
    HouseholdSettings,
    HouseholdSettingsRequest,
    InviteCreated,
    InviteCreateRequest,
    InvitePreview,
    InviteStatus,
    InviteTokenRequest,
    MemberRoleRequest,
    PetRelationship,
    PetRelationshipRequest,
)
from ...utils import utcnow
from ...web_household import Action, HouseholdError, Role
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_principal
from ...web_platform.session import optional_principal
from ._shared import cap, household_error, require_household, require_pet, web_of, web_router

router = web_router("households")


def capabilities(settings) -> list[Capability]:
    return [
        cap("households.members", "households", CapabilityStatus.available, "一个家庭多位成员（管理员/共同照顾者）、多只宠物；移除立即生效；至少保留一位管理员"),
        cap("households.invites", "households", CapabilityStatus.available, "邀请链接：只存令牌摘要、有有效期、可撤销、只能用一次"),
        cap("households.relationships", "households", CapabilityStatus.available, "每位家人和每只宠物之间的称呼（只是称呼，不带权限）"),
    ]


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HouseholdError as exc:
        raise household_error(exc) from exc


def _invite(view: dict) -> HouseholdInvite:
    return HouseholdInvite(invite_id=view["invite_id"], household_id=view["household_id"], role=HouseholdRole(view["role"]), relation_hint=view["relation_hint"],
                           status=InviteStatus(view["status"]), created_at=view["created_at"], expires_at=view["expires_at"], accepted_at=view["accepted_at"])


def _detail(request: Request, user_id: str, household_id: str) -> HouseholdDetail:
    web = web_of(request)
    access = web.households.access_household(user_id, household_id)
    brief = web.homes.household_brief(user_id, household_id)
    if access is None or brief is None:
        raise WebAPIError.not_found("这个家庭")
    storage = request.app.state.storage
    members = []
    for m in web.households.members_of(household_id):
        user = storage.get_user(m.user_id)
        members.append(HouseholdMember(user_id=m.user_id, display_name=(user.display_name if user and user.display_name else "一位家人"),
                                       role=HouseholdRole(m.role.value), joined_at=m.joined_at, is_you=m.user_id == user_id))
    row = web.households.household_row(household_id)
    home = web.homes.by_household(household_id)
    generated = web.households.setting(household_id, "generated_photos")
    messages = web.households.setting(household_id, "pet_messages")
    creator_prefs = web.identity.prefs(row["created_by"]) if row else {"generated_photos": False, "pet_messages": True}
    settings = HouseholdSettings(name=row["name"] if row else None, caregivers_can_spend=bool(row["caregivers_can_spend"]) if row else True,
                                 generated_photos=bool(creator_prefs["generated_photos"] if generated is None else generated),
                                 pet_messages=bool(creator_prefs["pet_messages"] if messages is None else messages),
                                 public_posts=bool(home and home.public_posts))
    permissions = [a.value for a in Action if access.allows(a)]
    return HouseholdDetail(household=brief, members=members, settings=settings, your_permissions=permissions, version=int(row["version"]) if row else 1)


@router.get("/households", response_model=list[HouseholdBrief])
def my_households(request: Request, principal: WebPrincipal = Depends(require_principal)) -> list[HouseholdBrief]:
    """我所在的家庭（每个家庭里的宠物、它们的入住进度与此刻位置）。"""
    return web_of(request).homes.households_of(principal.user_id)


@router.get("/households/{household_id}", response_model=HouseholdDetail)
def household_detail(household_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> HouseholdDetail:
    require_household(request, principal, household_id)
    return _detail(request, principal.user_id, household_id)


@router.patch("/households/{household_id}/settings", response_model=HouseholdDetail, dependencies=[Depends(require_csrf)])
def update_household_settings(household_id: str, body: HouseholdSettingsRequest, request: Request,
                              principal: WebPrincipal = Depends(require_principal)) -> HouseholdDetail:
    """家庭设置（管理员）：名字、共同照顾者能否使用宠物账户、写实照片（付费生图）、家庭频道新鲜事、公开动态。"""
    web = web_of(request)
    require_household(request, principal, household_id, action=Action.manage)
    _call(web.households.update_settings, principal.user_id, household_id, name=body.name, caregivers_can_spend=body.caregivers_can_spend,
          generated_photos=body.generated_photos, pet_messages=body.pet_messages)
    if body.public_posts is not None:
        web.homes.set_public_posts(household_id, body.public_posts)
    return _detail(request, principal.user_id, household_id)


@router.put("/households/{household_id}/members/{user_id}/role", response_model=HouseholdDetail, dependencies=[Depends(require_csrf)])
def set_member_role(household_id: str, user_id: str, body: MemberRoleRequest, request: Request,
                    principal: WebPrincipal = Depends(require_principal)) -> HouseholdDetail:
    """改成员角色（管理员）。最后一位管理员不能降为共同照顾者（409 last_admin）。"""
    _call(web_of(request).households.set_role, principal.user_id, household_id, user_id, Role(body.role.value), utcnow())
    return _detail(request, principal.user_id, household_id)


@router.delete("/households/{household_id}/members/{user_id}", status_code=204, dependencies=[Depends(require_csrf)])
def remove_member(household_id: str, user_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Response:
    """管理员移除成员，或自己退出（user_id 填自己）。立即生效：下一次请求起就看不到这个家庭的宠物；最后一位管理员不能退出/被移除。"""
    _call(web_of(request).households.remove, principal.user_id, household_id, user_id, utcnow())
    return Response(status_code=204)


@router.post("/households/{household_id}/invites", response_model=InviteCreated, status_code=201, dependencies=[Depends(require_csrf)])
def create_invite(household_id: str, body: InviteCreateRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> InviteCreated:
    """发出邀请（管理员）。令牌只在这里返回一次（服务端只存摘要，重试会得到一个新邀请，旧的可以撤销）。"""
    view, token = _call(web_of(request).households.create_invite, principal.user_id, household_id, Role(body.role.value), body.relation_hint, utcnow(),
                        timedelta(hours=body.ttl_hours))
    return InviteCreated(invite=_invite(view), token=token, join_path=f"/join?invite={token}")


@router.get("/households/{household_id}/invites", response_model=list[HouseholdInvite])
def list_invites(household_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> list[HouseholdInvite]:
    return [_invite(v) for v in _call(web_of(request).households.invites_of, principal.user_id, household_id)]


@router.delete("/households/{household_id}/invites/{invite_id}", response_model=HouseholdInvite, dependencies=[Depends(require_csrf)])
def revoke_invite(household_id: str, invite_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> HouseholdInvite:
    web = web_of(request)
    invite = _call(web.households.invite, invite_id)
    if invite["household_id"] != household_id:
        raise WebAPIError.not_found("这个邀请")
    return _invite(_call(web.households.revoke_invite, principal.user_id, invite_id, utcnow()))


@router.post("/invites/preview", response_model=InvitePreview)
def preview_invite(body: InviteTokenRequest, request: Request, principal: WebPrincipal | None = Depends(optional_principal)) -> InvitePreview:
    """打开邀请链接时的预览（不登录也能看）：谁邀请的、家里有哪几只宠物、角色、有没有过期。不会自动加入。"""
    web = web_of(request)
    view = _call(web.households.invite_by_token, body.token)
    household = web.households.household_row(view["household_id"])
    inviter = request.app.state.storage.get_user(view["created_by"])
    names = [p.name for p in (web.pets.profile(pid) for pid in web.households.pets_of(view["household_id"])) if p]
    member = principal is not None and web.households.access_household(principal.user_id, view["household_id"]) is not None
    return InvitePreview(invite_id=view["invite_id"], status=InviteStatus(view["status"]), role=HouseholdRole(view["role"]), relation_hint=view["relation_hint"],
                         expires_at=view["expires_at"], household_name=household["name"] if household else None,
                         inviter_name=(inviter.display_name if inviter and inviter.display_name else "一位家人"), pet_names=names, already_member=member)


@router.post("/invites/accept", response_model=HouseholdDetail, dependencies=[Depends(require_csrf)])
def accept_invite(body: InviteTokenRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> HouseholdDetail:
    """接受邀请（需要登录，由用户点确认）。同一个人重复点返回同一结果；已被别人用过 409 invite_used；过期 409 invite_expired。"""
    web = web_of(request)
    view = _call(web.households.accept, principal.user_id, body.token, utcnow())
    web.entries.resolve(principal.user_id, utcnow())
    return _detail(request, principal.user_id, view["household_id"])


@router.get("/pets/{pet_id}/relationship", response_model=PetRelationship)
def read_relationship(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> PetRelationship:
    """你和这只宠物之间：TA 怎么称呼你、你们是什么关系（只属于你和 TA，别的家人各有各的）。"""
    require_pet(request, principal, pet_id)
    row = web_of(request).households.relationship(pet_id, principal.user_id) or {}
    return PetRelationship(pet_id=pet_id, owner_title=row.get("owner_title"), relation_label=row.get("relation_label"), updated_at=row.get("updated_at"))


@router.put("/pets/{pet_id}/relationship", response_model=PetRelationship, dependencies=[Depends(require_csrf)])
def save_relationship(pet_id: str, body: PetRelationshipRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> PetRelationship:
    require_pet(request, principal, pet_id, action=Action.care)
    row = _call(web_of(request).households.set_relationship, principal.user_id, pet_id, body.owner_title, body.relation_label, utcnow())
    return PetRelationship(pet_id=pet_id, owner_title=row.get("owner_title"), relation_label=row.get("relation_label"), updated_at=row.get("updated_at"))
