"""爪爪驾校（0.3.0）：驾校总览、课程、报名、练习与正式考局、作答、操作上传与复算、交卷、放弃、历史、领证仪式。

正式成绩只由操作与规则决定：科一科四服务端批改；科二科三服务端按操作记录复算；客户端上报的分数一律无效。
每科首次考试＋一次补考，两次不过冷却 7×24 小时；正式考局 begin 后才计次；结算只做一次。规格见 docs/contracts/DRIVING-SCHOOL-v1.md。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.school import DrivingSchoolStatus, SchoolCurriculum, SessionBrief
from ...schemas.web.school_session import (
    AbandonRequest,
    AnswerRequest,
    AnswerResult,
    CeremonyResult,
    InputChunk,
    InputResult,
    SchoolSession,
    SessionCreateRequest,
)
from ...utils import utcnow
from ...web_driving import DrivingError
from ...web_driving.curriculum import PET_LINES, curriculum
from ...web_driving.sessions import history as school_history
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...web_household import Action
from ._shared import cap, idempotent, require_pet, web_of, web_router
from .credentials import summaries

router = web_router("driving")
NOT_FOUND = {"session_not_found"}
INVALID = {"invalid_item", "question_not_in_paper", "invalid_answer", "invalid_input", "confirm_required"}


def capabilities(settings) -> list[Capability]:
    return [cap("driving.school", "driving", CapabilityStatus.available,
                "爪爪驾校：主人陪练陪考；四科（小课堂、倒车入库/侧方停车/弯道、小城路线、情境判断）；每科一次补考，两次不过冷却 7 天；服务端复算；拿证解锁自驾")]


def _translate(exc: DrivingError) -> WebAPIError:
    details = {"reason": exc.reason, **exc.details}
    if exc.reason in NOT_FOUND:
        return WebAPIError(WebErrorCode.not_found, exc.message, 404, details=details)
    if exc.reason in INVALID:
        return WebAPIError(WebErrorCode.validation_failed, exc.message, 422, details=details)
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details=details)


def _pet(request: Request, principal: WebPrincipal, pet_id: str | None = None) -> str:
    """学车的那只宠物（?pet_id= 指明；只照顾一只时可省略）。每只宠物各有自己的驾校进度和驾照；陪练、陪考的是当前这位家人。"""
    return require_pet(request, principal, pet_id, activated=True, action=Action.care).pet_id


def _status(request: Request, user_id: str, pet_id: str) -> DrivingSchoolStatus:
    status = web_of(request).driving.status(user_id, pet_id, utcnow())
    status["license"] = next((c for c in summaries(request, user_id, pet_id) if c.kind.value == "driver_license" and c.credential_id), None)
    return DrivingSchoolStatus.model_validate(status)


def _call(fn, *args):
    try:
        return fn(*args)
    except DrivingError as exc:
        raise _translate(exc) from exc


@router.get("/driving", response_model=DrivingSchoolStatus)
def driving_status(request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> DrivingSchoolStatus:
    """驾校总览：阶段、四科状态（锁定 / 可考 / 考试中 / 冷却中 / 已通过）、本轮机会、冷却截止时间、未结束的考局、驾照与借车券。"""
    return _status(request, principal.user_id, _pet(request, principal, pet_id))


@router.get("/driving/curriculum", response_model=SchoolCurriculum)
def driving_curriculum(request: Request, principal: WebPrincipal = Depends(require_principal)) -> SchoolCurriculum:
    """课程：教练、四科说明、教学步骤、扣分项与红线（开考前必须展示）、操作说明、补考规则、按性格的台词。"""
    return SchoolCurriculum.model_validate({**curriculum(), "pet_lines": PET_LINES})


@router.post("/driving/enroll", response_model=DrivingSchoolStatus, dependencies=[Depends(require_csrf)])
def enroll(request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> DrivingSchoolStatus:
    """陪 TA 报名爪爪驾校（TA 有了愿望一天后也会自己报名）。已报名时是空操作。"""
    pet_id = _pet(request, principal, pet_id)
    web_of(request).driving.enroll(principal.user_id, pet_id, utcnow(), by_owner=True)
    return _status(request, principal.user_id, pet_id)


@router.post("/driving/sessions", response_model=SchoolSession, dependencies=[Depends(require_csrf)])
def create_session(body: SessionCreateRequest, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None,
                   idempotency_key: str = Depends(require_idempotency_key)) -> SchoolSession:
    """建立练习或正式考局（preparing，不计次）。正式考局检查解锁、本轮机会、冷却与未结束的考局；同一科已有未结束的正式考局时原样返回它。"""
    pet_id = _pet(request, principal, pet_id)

    def handler() -> SchoolSession:
        view = _call(web_of(request).driving.create_session, principal.user_id, pet_id, body.subject.value, body.mode.value, body.item, utcnow())
        return SchoolSession.model_validate(view)

    return idempotent(request, principal, "driving.session", idempotency_key, {**body.model_dump(mode="json"), "pet_id": pet_id}, SchoolSession, handler)


@router.get("/driving/sessions/{session_id}", response_model=SchoolSession)
def get_session(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> SchoolSession:
    """考局：题目（不含答案）或场地配置、已保存的作答或操作（续考时恢复）、服务端复算快照、结果。"""
    return SchoolSession.model_validate(_call(web_of(request).driving.session, _pet(request, principal, pet_id), session_id))


@router.post("/driving/sessions/{session_id}/begin", response_model=SchoolSession, dependencies=[Depends(require_csrf)])
def begin(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> SchoolSession:
    """资源加载完成、点“开始”：正式考局从这一刻起计次。重复调用无副作用。"""
    return SchoolSession.model_validate(_call(web_of(request).driving.begin, _pet(request, principal, pet_id), session_id, utcnow()))


@router.put("/driving/sessions/{session_id}/answers", response_model=AnswerResult, dependencies=[Depends(require_csrf)])
def answer(session_id: str, body: AnswerRequest, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> AnswerResult:
    """科一科四逐题保存作答（同一题再保存会覆盖）。练习立即返回讲解；正式考试交卷前不给任何提示。"""
    result = _call(web_of(request).driving.answer, _pet(request, principal, pet_id), session_id, body.question_id, body.answer.model_dump(), utcnow())
    return AnswerResult.model_validate(result)


@router.post("/driving/sessions/{session_id}/inputs", response_model=InputResult, dependencies=[Depends(require_csrf)])
def inputs(session_id: str, body: InputChunk, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> InputResult:
    """科二科三上传一段操作，服务端复算后返回判定事件、扣分与快照；完全相同的重发原样返回；不连续返回 409（reason=gap / resync）。"""
    pet_id = _pet(request, principal, pet_id)
    events = [event.model_dump() for event in body.events]
    result = _call(web_of(request).driving.inputs, principal.user_id, pet_id, session_id, body.item_index, body.from_tick, body.upto_tick, events, utcnow())
    return InputResult.model_validate(result)


@router.post("/driving/sessions/{session_id}/pause", response_model=SchoolSession, dependencies=[Depends(require_csrf)])
def pause(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> SchoolSession:
    """记录暂停（切后台、断线、主动暂停）。回来按服务端记录接着考。"""
    return SchoolSession.model_validate(_call(web_of(request).driving.pause, _pet(request, principal, pet_id), session_id, utcnow()))


@router.post("/driving/sessions/{session_id}/submit", response_model=SchoolSession, dependencies=[Depends(require_csrf)])
def submit(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> SchoolSession:
    """科一科四交卷结算（只结算一次，重复请求返回同一结果）。科二科三开完或失败时会自动结算。"""
    return SchoolSession.model_validate(_call(web_of(request).driving.submit, _pet(request, principal, pet_id), session_id, utcnow()))


@router.post("/driving/sessions/{session_id}/abandon", response_model=SchoolSession, dependencies=[Depends(require_csrf)])
def abandon(session_id: str, body: AbandonRequest, request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> SchoolSession:
    """放弃：已经开始的正式考试计为本次不通过（需要 confirm=true）；还没开始的正式考局与练习直接作废，不计次。"""
    return SchoolSession.model_validate(_call(web_of(request).driving.abandon, _pet(request, principal, pet_id), session_id, body.confirm, utcnow()))


@router.get("/driving/history", response_model=list[SessionBrief])
def history(request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> list[SessionBrief]:
    """这只宠物最近的练习与考试（家里每位家人陪的都算；只给家人看，默认不公开）。"""
    return [SessionBrief.model_validate(b) for b in school_history(web_of(request).driving.storage, principal.user_id, _pet(request, principal, pet_id))]


@router.post("/driving/ceremony", response_model=CeremonyResult, dependencies=[Depends(require_csrf)])
def ceremony(request: Request, principal: WebPrincipal = Depends(require_principal), pet_id: str | None = None) -> CeremonyResult:
    """领证仪式：教练盖爪印章，TA 接过证件，你们合影。只做一次（生成“领证合影”收藏）；再次打开只是回看。"""
    web = web_of(request)
    pet_id = _pet(request, principal, pet_id)
    result = _call(web.driving.ceremony, principal.user_id, pet_id, utcnow())
    card = next((c for c in summaries(request, principal.user_id, pet_id) if c.credential_id == result["license_id"]), None)
    if card is None:
        raise WebAPIError(WebErrorCode.conflict, "驾驶证正在签发，稍后再来领。", 409, details={"reason": "license_pending"})
    return CeremonyResult(license=card, memento=web.collection.item_of(principal.user_id, pet_id, "license_photo"),
                          voucher=web.collection.item_of(principal.user_id, pet_id, "car_voucher"), pet_says=result["pet_says"], first_time=result["first_time"])
