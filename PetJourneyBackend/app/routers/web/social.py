"""星球圈：动态流、宠物主页帖子、动态详情与评论线程、点赞/评论（明确行动者）、关注、撤下、屏蔽、举报。

0.4.0：以宠物身份行动（点赞、评论、关注）要用 ?pet_id= 指明是哪一只（只照顾一只时可省略）；以主人身份不需要。
自家宠物（同一家庭）的非公开动态成员都能看到，也都能撤下。"""

from __future__ import annotations

from fastapi import Depends, Request, Response

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.social import (
    BlockRequest,
    Comment,
    CommentPage,
    CommentRequest,
    FollowRequest,
    FriendSummary,
    Post,
    PostPage,
    ReactionRequest,
    ReportRequest,
)
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...web_social import SocialError, Viewer
from ._shared import cap, idempotent, require_pet, web_of, web_router

router = web_router("social")


@router.get("/friends", response_model=list[FriendSummary])
def friends(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[FriendSummary]:
    """TA 在外面遇到的朋友（只给这只宠物的家人）。真实宠物要双方同一时间在同一地点才算遇到；星球居民明确标注。"""
    home = require_pet(request, principal, pet_id, activated=True)
    return [FriendSummary.model_validate(f) for f in web_of(request).friends.friends(principal.user_id, home.pet_id)]


def capabilities(settings) -> list[Capability]:
    return [
        cap("social.feed", "social", CapabilityStatus.available, "动态只来自真实世界事件；主人入住时选择是否公开"),
        cap("social.reactions", "social", CapabilityStatus.available),
        cap("social.moderation", "social", CapabilityStatus.available, "撤下/屏蔽/举报已记录；人工审核流程未建立"),
    ]


def viewer_of(request: Request, principal: WebPrincipal, pet_id: str | None = None) -> Viewer:
    """看的人：本人 + 所在家庭的全部宠物；以宠物身份行动时的那只宠物要显式给出（只照顾一只时默认它）。
    给出的 pet_id 必须是自家的宠物（不能冒用别家宠物的身份），否则 404。"""
    web = web_of(request)
    pet_ids = tuple(p for p, _ in web.households.accessible_pets(principal.user_id))
    acting = pet_id if pet_id else (pet_ids[0] if len(pet_ids) == 1 else None)
    if pet_id and pet_id not in pet_ids:
        raise WebAPIError.not_found("这只宠物")
    profile = web.pets.profile(acting) if acting else None
    return Viewer(user_id=principal.user_id, pet_id=acting, pet_name=profile.name if profile else None, owner_name="主人", pet_ids=pet_ids)


def _translate(exc: SocialError) -> WebAPIError:
    if exc.reason == "not_found":
        return WebAPIError.not_found("这条内容")
    return WebAPIError.forbidden(exc.message)


@router.get("/circle/feed", response_model=PostPage)
def circle_feed(request: Request, cursor: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> PostPage:
    web = web_of(request)  # 只读：别家宠物的到访结束由任务进程结算后出现在动态里
    return web.social.feed(viewer_of(request, principal), cursor)


@router.get("/pets/{pet_id}/posts", response_model=PostPage)
def pet_posts(pet_id: str, request: Request, cursor: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> PostPage:
    web = web_of(request)
    return web.social.pet_posts(viewer_of(request, principal), pet_id)


@router.get("/posts/{post_id}", response_model=Post)
def get_post(post_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Post:
    try:
        return web_of(request).social.post(viewer_of(request, principal), post_id)
    except SocialError as exc:
        raise _translate(exc) from exc


@router.get("/posts/{post_id}/comments", response_model=CommentPage)
def post_comments(post_id: str, request: Request, cursor: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> CommentPage:
    try:
        return web_of(request).social.comments(viewer_of(request, principal), post_id)
    except SocialError as exc:
        raise _translate(exc) from exc


@router.post("/posts/{post_id}/reactions", response_model=Post, dependencies=[Depends(require_csrf)])
def react(post_id: str, body: ReactionRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal),
          idempotency_key: str = Depends(require_idempotency_key)) -> Post:
    def handler() -> Post:
        try:
            return web_of(request).social.react(viewer_of(request, principal, pet_id), post_id, body.as_actor)
        except SocialError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"social.react:{post_id}", idempotency_key, {**body.model_dump(mode="json"), "pet_id": pet_id}, Post, handler)


@router.post("/posts/{post_id}/comments", response_model=Comment, status_code=201, dependencies=[Depends(require_csrf)])
def comment(post_id: str, body: CommentRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal),
            idempotency_key: str = Depends(require_idempotency_key)) -> Comment:
    def handler() -> Comment:
        try:
            return web_of(request).social.comment(viewer_of(request, principal, pet_id), post_id, body.as_actor, body.text, body.reply_to_comment_id)
        except SocialError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"social.comment:{post_id}", idempotency_key, {**body.model_dump(mode="json"), "pet_id": pet_id}, Comment, handler)


@router.delete("/posts/{post_id}", status_code=204, dependencies=[Depends(require_csrf)])
def remove_post(post_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Response:
    try:
        web_of(request).social.remove_post(viewer_of(request, principal), post_id)
    except SocialError as exc:
        raise _translate(exc) from exc
    return Response(status_code=204)


@router.delete("/comments/{comment_id}", status_code=204, dependencies=[Depends(require_csrf)])
def remove_comment(comment_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Response:
    try:
        web_of(request).social.remove_comment(viewer_of(request, principal), comment_id)
    except SocialError as exc:
        raise _translate(exc) from exc
    return Response(status_code=204)


@router.post("/pets/{pet_id}/follow", status_code=204, dependencies=[Depends(require_csrf)])
def follow(pet_id: str, body: FollowRequest, request: Request, as_pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> Response:
    """关注是宠物之间的关系：as_pet_id 指明是自家哪一只去关注（只照顾一只时可省略）。"""
    try:
        web_of(request).social.follow(viewer_of(request, principal, as_pet_id), pet_id, body.follow)
    except SocialError as exc:
        raise _translate(exc) from exc
    return Response(status_code=204)


@router.post("/blocks", status_code=204, dependencies=[Depends(require_csrf)])
def block(body: BlockRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Response:
    web = web_of(request)
    target = web.social.author_user_of_post(body.post_id) if body.post_id else web.social.author_user_of_comment(body.comment_id) if body.comment_id else None
    if target is None:
        raise WebAPIError.not_found("要屏蔽的作者")
    try:
        web.social.block(viewer_of(request, principal), target)
    except SocialError as exc:
        raise _translate(exc) from exc
    return Response(status_code=204)


@router.post("/reports", status_code=204, dependencies=[Depends(require_csrf)])
def report(body: ReportRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Response:
    web_of(request).social.report(viewer_of(request, principal), body.target_kind, body.target_id, body.reason)
    return Response(status_code=204)
