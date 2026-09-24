"""世界角色资产（CR-PLAYER-CHARACTER-01）。接口面由 I 定，实现归 A；本文件 I 已整份 RELEASE 给 A。

## 三条路由，各自的硬约束

    GET  /pets/{pet_id}/character              纯读。**绝不触发生成、绝不发供应商请求。**
    POST /pets/{pet_id}/character/regenerate   可选的「调整形象」。带幂等键，重复提交不二次付费。
    GET  /media/characters/{asset_id}          受权限保护的图片。越权读要挡下，不是 CDN 直链。

**GET 不出图**这一条是硬的：家园每次渲染都会打第一条路由，若它能触发生成，
刷新页面就会烧钱。首次生成由**上传成功事件**自动触发（`web_pets/service.py::create_own`
在它自己的写事务里调 `on_pet_photo_stored`），不在这里。逐次授权询问已于 2026-09-23 由用户决定取消。

批次二的其余五个姿态（开关默认关）同样不在这里触发：它们在中性站姿生效的那个事务里登记。
GET 只把 active 那一套里**已就绪**的姿态放进 `active.assets`，其余姿态的进度放进 `poses`。

## 授权

三条都走 `require_pet`——每次请求重查有效成员关系，**被移出家庭的成员立刻失去访问**。
角色继承对应宠物/家庭的可见性，不因为"角色是生成的"就放宽。
`/media/characters/{asset_id}` **按 asset 反查其宠物再裁定**，不只验登录。

## 与已有能力的关系

复用 `web_platform` 的任务、租约、预占与 `unknown` 语义，不另起一套：
同一事件重放不新建第二次付费操作；`reserved/expired/unknown` 都不构成「没发出」。
费用走平台 API 账本，**与游戏金币、旅费无关**。
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from fastapi.responses import FileResponse

from ...schemas.web.character import (CharacterAsset, CharacterCandidate, CharacterIdPhoto, CharacterPose,
                                      CharacterPoseProgress, CharacterRegenerateCommand, CharacterRegenerateResult,
                                      CharacterSet, CharacterState, CharacterStatus, ContentBox, GroundAnchor, IdPhotoSource)
from ...schemas.web.common import Capability, CapabilityStatus
from ...utils import parse_dt
from ...web_character.model import ALL_REASONS
from ...web_platform import (WebAPIError, WebPrincipal, require_csrf, require_idempotency_key,
                             require_principal)
from ._shared import cap, require_pet, web_router, web_of

logger = logging.getLogger("petsoul.web.character")
router = web_router("character")


def _reason(value: str | None) -> str | None:
    """原因码送出去之前再看一眼：不在已发布的码表里就**留痕**。

    为什么还要这一道：契约与实现之间已经有一条双向不变量守着，但它比的是**常量表**。
    谁在代码里直接写个字面量，常量表里不会出现，不变量就看不见——
    `already_queued` 当初就是这么漏的（`service.py` 里硬编码，前端只好自己猜着映射）。

    **不拦**：拦了就是为一个文案问题让整个响应 500，玩家看到的更糟。
    这里只让它出现在日志里，好过它安安静静地被当成人话显示给主人。
    """
    if value is not None and value not in ALL_REASONS:
        logger.warning("character reason not in the published table: %r", value)
    return value


def _asset(item) -> CharacterAsset:
    """服务层的资产 → 契约 DTO。`measured=True` 是实话：边界与锚点都是从 alpha 通道实测出来的，
    不是导演给的估计值（见 `web_character/validate.py`）。"""
    box, anchor = item.content_box, item.anchor
    return CharacterAsset(
        asset_id=item.asset_id, pose=CharacterPose(item.pose), url=item.url or "",
        content_sha256=item.content_sha256 or "", content_type=item.content_type or "image/png",
        width=item.width or 0, height=item.height or 0,
        content_box=ContentBox(left=box[0], top=box[1], right=box[2], bottom=box[3]),
        anchor=GroundAnchor(x=anchor[0], y=anchor[1], measured=True),
        has_alpha=item.has_alpha, opaque_ratio=item.opaque_ratio or 0.0)


def _id_photo(view) -> CharacterIdPhoto | None:
    """证件照纯读结果 → 契约 DTO。`absent`（从没有过、也没有基准照）时给 null，前端退回原照。"""
    if view.status == CharacterStatus.absent.value:
        return None
    return CharacterIdPhoto(status=CharacterStatus(view.status), source=IdPhotoSource(view.source) if view.source else None,
                            url=view.url, avatar_url=view.avatar_url, width=view.width, height=view.height,
                            content_sha256=view.content_sha256, reference_version=view.reference_version,
                            revision=view.revision, reason=_reason(view.reason), task_id=view.task_id)


def _state_of(pet_id: str, view, id_photo=None) -> CharacterState:
    active = None
    if view.active is not None:
        # 中性站姿在前，其余已就绪的姿态跟在后面——**都来自 active 这一套**，前端找不到某个姿态就回落到这里的中性站姿
        active = CharacterSet(character_set_id=view.active.set_id, pet_id=pet_id, revision=view.active.revision,
                              reference_version=view.active.reference_version, style_version=view.active.style_version,
                              assets=[_asset(view.active), *(_asset(extra) for extra in view.extras)],
                              published_at=parse_dt(view.published_at))
    poses = [CharacterPoseProgress(pose=CharacterPose(item.pose), status=CharacterStatus(item.state),
                                   reason=_reason(item.reason), task_id=item.task_id) for item in view.poses]
    candidate = None
    if view.candidate is not None:
        candidate = CharacterCandidate(status=CharacterStatus(view.state), pose=CharacterPose(view.candidate.pose),
                                       reference_version=view.candidate.reference_version,
                                       style_version=view.candidate.style_version,
                                       queued_at=parse_dt(view.candidate.created_at), reason=_reason(view.reason),
                                       task_id=view.candidate.task_id)
    # 在建任务还没完就不能再排一个（重复点击、丢回执都落在这条上）；没有在建但被挡住时，原因放 blocked_reason。
    busy = view.state in (CharacterStatus.queued.value, CharacterStatus.running.value)
    return CharacterState(pet_id=pet_id, status=CharacterStatus(view.state), active=active, candidate=candidate,
                          can_regenerate=not busy and view.blocked_reason is None,
                          blocked_reason=None if candidate is not None else _reason(view.blocked_reason), poses=poses,
                          id_photo=_id_photo(id_photo) if id_photo is not None else None)


@router.get("/pets/{pet_id}/character", response_model=CharacterState)
def character_state(pet_id: str, request: Request,
                    principal: WebPrincipal = Depends(require_principal)) -> CharacterState:
    """纯读当前角色状态与已生效资产。

    没有任务时返回 `status=absent`，**前端据此不显示假进度**。
    有 `active` 就返回它，即使 `candidate` 正在失败——旧形象不因新任务出错而消失。
    """
    access = require_pet(request, principal, pet_id)
    character = web_of(request).character
    return _state_of(access.pet_id, character.view(access.pet_id), character.id_photo.view(access.pet_id))


@router.post("/pets/{pet_id}/character/regenerate", response_model=CharacterRegenerateResult,
             dependencies=[Depends(require_csrf), Depends(require_idempotency_key)])
def character_regenerate(pet_id: str, body: CharacterRegenerateCommand, request: Request,
                         principal: WebPrincipal = Depends(require_principal)) -> CharacterRegenerateResult:
    """主人主动发起的「调整形象」。**正常路径不需要它**——首次由上传自动触发。

    幂等键覆盖重复点击与丢回执（平台按 `Idempotency-Key` **请求头**复用回执，与全仓其它写路由一致；
    请求体里曾有的 `idempotency_key` 字段已由 I 从契约删除）；已有在建任务时明确拒绝并说明，而不是再排一个。
    **一律整套重做**：`body.pose` 暂不区分取值——只重画某一个姿态，它就和同套的站姿不再出自同一张参考。
    `unknown` 状态下**不得**把这里当成自动补发入口：要由主人显式发起才算新的付费尝试，
    而这条路由正是"主人显式发起"本身。`note` 首批只作为主人的说明收下，不进提示词——
    自由文本进提示词会绕过封闭词表，那是另一批的事。
    """
    access = require_pet(request, principal, pet_id)
    accepted, state, detail = web_of(request).character.regenerate(access.pet_id, principal.user_id)
    return CharacterRegenerateResult(accepted=accepted, status=CharacterStatus(state),
                                     task_id=detail if accepted else None, reason=None if accepted else _reason(detail))


@router.get("/media/characters/{asset_id}")
def character_media(asset_id: str, request: Request,
                    principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    """受权限保护的角色图片：先按 `asset_id` 反查所属宠物，再用 `require_pet` 裁定，最后才给文件。

    **先反查再裁定**的顺序不能反过来：拿 `asset_id` 直接给文件就等于"知道 id 的人都能看"。
    找不到与无权看都回同一个 404——不告诉外人这个 id 存不存在。
    """
    found = web_of(request).character.media_path(asset_id)
    if found is None:
        raise WebAPIError.not_found("这个形象")
    path, content_type, pet_id = found
    require_pet(request, principal, pet_id)
    return FileResponse(path, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.post("/pets/{pet_id}/id-photo/regenerate", response_model=CharacterRegenerateResult,
             dependencies=[Depends(require_csrf), Depends(require_idempotency_key)])
def id_photo_regenerate(pet_id: str, request: Request,
                        principal: WebPrincipal = Depends(require_principal)) -> CharacterRegenerateResult:
    """主人显式重画证件照（前端放进「调整形象」）。**正常路径不需要它**：新宠物上传或领养后自动生成。

    用户 2026-09-24 定了存量宠物不批量补，所以**存量宠物也靠这里补**。额度、幂等键与「调整形象」相同；
    已有在排、在画的就拒绝（`already_queued`），不再排一个；没照片的宠物复用基准照，这里会如实拒绝并给原因。
    """
    access = require_pet(request, principal, pet_id)
    accepted, state, detail = web_of(request).character.id_photo.regenerate(access.pet_id, principal.user_id)
    return CharacterRegenerateResult(accepted=accepted, status=CharacterStatus(state),
                                     task_id=detail if accepted else None, reason=None if accepted else _reason(detail))


@router.get("/media/id-photos/{asset_id}")
def id_photo_media(asset_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    """证件用图（竖幅 3:4、浅蓝纯底）。与角色图同一个规矩：**先按 asset 反查宠物，再用 `require_pet` 裁定**。"""
    return _id_photo_file(request, principal, asset_id, avatar=False)


@router.get("/media/id-photos/{asset_id}/avatar")
def id_photo_avatar(asset_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    """地图头像（256×256，从证件照上方正方形缩成）。可见性与证件用图完全相同。"""
    return _id_photo_file(request, principal, asset_id, avatar=True)


def _id_photo_file(request: Request, principal: WebPrincipal, asset_id: str, *, avatar: bool) -> FileResponse:
    found = web_of(request).character.id_photo.media_path(asset_id, avatar=avatar)
    if found is None:
        raise WebAPIError.not_found("这张证件照")  # 找不到与无权看回同一个 404：不告诉外人这个 id 存不存在
    path, content_type, pet_id = found
    require_pet(request, principal, pet_id)
    return FileResponse(path, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


def capabilities(settings) -> list[Capability]:
    return [
        cap("character.state", "character", CapabilityStatus.available,
            "读 TA 的世界角色：已生效的一套（含已就绪的其余姿态）、在建的那次、以及为什么还没有。GET 不触发生成。"),
        cap("character.regenerate", "character", CapabilityStatus.available,
            "可选的「调整形象」，整套重做。首次角色由上传成功后自动排队，主人不必点。"),
        cap("character.media", "character", CapabilityStatus.available,
            "角色图片按宠物可见性保护；移出家庭即失去访问。"),
        cap("character.id_photo", "character", CapabilityStatus.available,
            "每只宠物一张证件照（护照、居民证、驾照都用）：新宠物自动生成，主人可重画；地图头像是它裁出的 256×256 小图。"),
    ]
