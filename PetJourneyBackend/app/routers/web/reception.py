"""注册接待 / 入住叮嘱 / 受控记忆（引导便笺模式；接待模型未配置时不伪装自由对话）。

0.4.0 家庭：接待与叮嘱是每位家人自己的（个人层）：每位家人都可以为同一只宠物做自己的接待、确认自己的叮嘱，
别的家人看不到；一只宠物的入住进度只记录把它加进家的那次接待。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...reception.store import ReceptionError
from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.home import HomeWelcome
from ...schemas.web.reception import (
    CareNote,
    IntakeConfirmationRequest,
    IntakeConfirmationResult,
    MemoryCorrectionRequest,
    MemoryCorrectionResult,
    ReceptionSession,
    ReceptionStartRequest,
    ReceptionTurnRequest,
)
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...web_providers.readiness import llm_ready
from ...web_household import Action
from ._shared import cap, idempotent, require_pet, web_of, web_router

router = web_router("reception")


def capabilities(settings) -> list[Capability]:
    return [
        cap("reception.session", "reception", CapabilityStatus.available, "引导便笺模式：原话原样进入待确认便笺，规则只给建议"),
        cap("reception.model_conversation", "reception", CapabilityStatus.available if llm_ready(settings) else CapabilityStatus.not_configured,
            "主人选择后由对话模型回应（便笺仍只摘录原话）" if llm_ready(settings) else "接待模型未配置；不伪装自由对话"),
        cap("reception.confirmation", "reception", CapabilityStatus.available),
        cap("reception.home_welcome", "reception", CapabilityStatus.available),
        cap("reception.voice", "reception", CapabilityStatus.disabled, "语音不在首发范围"),
    ]


def _translate(exc: ReceptionError) -> WebAPIError:
    if exc.reason == "not_found":
        return WebAPIError.not_found("这次接待或叮嘱")
    if exc.reason == "version_conflict":
        return WebAPIError.version_conflict(current=exc.current)
    if exc.reason == "closed":
        return WebAPIError(WebErrorCode.draft_expired, exc.message, 410)
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details={"reason": exc.reason})


def _own_pet(request: Request, principal: WebPrincipal, pet_id: str, action: Action = Action.view) -> None:
    """当前有效的家庭成员（不是成员 404）。"""
    require_pet(request, principal, pet_id, action=action)


@router.post("/reception/sessions", response_model=ReceptionSession, status_code=201, dependencies=[Depends(require_csrf)])
def start_reception(body: ReceptionStartRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                    idempotency_key: str = Depends(require_idempotency_key)) -> ReceptionSession:
    _own_pet(request, principal, body.pet_id, Action.care)
    return web_of(request).reception.start(principal.user_id, body.pet_id, body.branch, use_model=body.use_model)


@router.get("/reception/sessions/{session_id}", response_model=ReceptionSession)
def get_reception(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> ReceptionSession:
    try:
        return web_of(request).reception.get(principal.user_id, session_id)
    except ReceptionError as exc:
        raise _translate(exc) from exc


@router.post("/reception/sessions/{session_id}/turns", response_model=ReceptionSession, dependencies=[Depends(require_csrf)])
def add_turn(session_id: str, body: ReceptionTurnRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
             idempotency_key: str = Depends(require_idempotency_key)) -> ReceptionSession:
    def handler() -> ReceptionSession:
        try:
            return web_of(request).reception.add_turn(principal.user_id, session_id, body.text, body.expected_revision)
        except ReceptionError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"reception.turn:{session_id}", idempotency_key, body.model_dump(), ReceptionSession, handler)


@router.post("/reception/sessions/{session_id}/skip", response_model=ReceptionSession, dependencies=[Depends(require_csrf)])
def skip_reception(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> ReceptionSession:
    try:
        return web_of(request).reception.skip(principal.user_id, session_id)
    except ReceptionError as exc:
        raise _translate(exc) from exc


@router.post("/reception/confirmations", response_model=IntakeConfirmationResult, dependencies=[Depends(require_csrf)])
def confirm_notes(body: IntakeConfirmationRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                  idempotency_key: str = Depends(require_idempotency_key)) -> IntakeConfirmationResult:
    def handler() -> IntakeConfirmationResult:
        try:
            return web_of(request).reception.confirm(principal.user_id, body)
        except ReceptionError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, "reception.confirm", idempotency_key, body.model_dump(mode="json"), IntakeConfirmationResult, handler)


@router.get("/pets/{pet_id}/care-notes", response_model=list[CareNote])
def list_care_notes(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> list[CareNote]:
    _own_pet(request, principal, pet_id)
    return web_of(request).reception.notes(principal.user_id, pet_id)


@router.post("/care-notes/{note_id}/corrections", response_model=MemoryCorrectionResult, dependencies=[Depends(require_csrf)])
def correct_note(note_id: str, body: MemoryCorrectionRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                 idempotency_key: str = Depends(require_idempotency_key)) -> MemoryCorrectionResult:
    def handler() -> MemoryCorrectionResult:
        try:
            return web_of(request).reception.correct(principal.user_id, note_id, body)
        except ReceptionError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"reception.correct:{note_id}", idempotency_key, body.model_dump(mode="json"), MemoryCorrectionResult, handler)


@router.get("/pets/{pet_id}/home-welcome", response_model=HomeWelcome)
def home_welcome(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> HomeWelcome:
    _own_pet(request, principal, pet_id)
    welcome = web_of(request).reception.home_welcome(principal.user_id, pet_id)
    if welcome is None:
        raise WebAPIError.not_found("已确认的欢迎细节")
    return welcome
