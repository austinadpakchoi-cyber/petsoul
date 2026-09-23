"""私密通讯：家人与宠物。client_message_id 即幂等键；宠物回复按其真实状态延后可见；公开动态不搬运私密对话。

0.4.0：每位家人看到的会话＝自己与 TA 的私聊 + 家庭频道（世界事件来信、明信片、攻略、新鲜事），每条带 channel；
别的家人的私聊看不到；被移出家庭后立刻不能再读写这只宠物的会话。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.social import MessageSummary, MessageThread, SendMessageRequest
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_principal
from ...web_providers.readiness import llm_ready
from ...web_household import Action
from ._shared import cap, redraw, require_pet, web_of, web_router

router = web_router("communicator")


def capabilities(settings) -> list[Capability]:
    mode = getattr(settings, "intent_layer_mode", "off")
    return [
        cap("communicator.messages", "communicator", CapabilityStatus.available,
            "主人开启“模型回信”后由对话模型按已确认叮嘱回复，否则模板回应" if llm_ready(settings) else "模板回应；未调用语言模型"),
        cap("intent.layer", "intent", CapabilityStatus.disabled if mode == "off" else CapabilityStatus.available, f"意图判断层 mode={mode}；" + ("已配置主模型判断器可用于影子评估（见 docs/contracts/INTENT-EVAL-20260922.md）" if llm_ready(settings) else "主模型未接通") + "；Jev 未接入"),
    ]


def _own(request: Request, principal: WebPrincipal, pet_id: str, action: Action = Action.view) -> None:
    """当前有效的家庭成员才能读写这只宠物的会话（不是成员 404）。"""
    require_pet(request, principal, pet_id, action=action)


@router.get("/communicator/{pet_id}/messages", response_model=MessageThread)
def list_messages(pet_id: str, request: Request, cursor: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> MessageThread:
    _own(request, principal, pet_id)
    web = web_of(request)
    return web.communicator.thread(principal.user_id, pet_id)


@router.post("/communicator/{pet_id}/messages/{message_id}/retry-photo", response_model=MessageThread, dependencies=[Depends(require_csrf)])
def retry_photo(pet_id: str, message_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> MessageThread:
    """插画没画成时由家人重试（重新排队，不重复发勋章或消息）。"""
    _own(request, principal, pet_id, Action.care)
    web = web_of(request)
    redraw(web, web.communicator.illustration_retrying(principal.user_id, pet_id, message_id),
           web.communicator.photo_state_for(principal.user_id, pet_id, message_id), "可以重画的插画")
    return web.communicator.thread(principal.user_id, pet_id)


@router.post("/communicator/{pet_id}/messages", response_model=MessageSummary, dependencies=[Depends(require_csrf)])
def send_message(pet_id: str, body: SendMessageRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> MessageSummary:
    _own(request, principal, pet_id, Action.care)
    try:
        return web_of(request).communicator.send(principal.user_id, pet_id, body.client_message_id, body.text)
    except PermissionError as exc:
        raise WebAPIError.not_found("这条消息") from exc
