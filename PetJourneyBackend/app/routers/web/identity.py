"""会话 / 注册 / 登录 / 退出 / 入住阶段 / 入住激活 / 设置。

0.4.0：注册不再等于“立刻建立一只宠物”，可以带着入口（先逛逛 / 接我的宠物 / 选中的待领养伙伴 / 家庭邀请）注册，
登录后由页面恢复并请用户确认；入住针对某一只宠物；设置分成个人偏好（私聊用模型、时区）与家庭设置（公开动态、写实照片、主动消息，
由家庭管理员决定）。"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from fastapi import Depends, Request, Response

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.identity import (
    LoginRequest,
    MoveInRequest,
    OnboardingState,
    RegisterRequest,
    SessionState,
    SessionUser,
    SettingsUpdate,
    SettingsView,
)
from ...schemas.web.common import AuthMethod
from ...schemas.web.pets import ProfileVisibility
from ...utils import utcnow
from ...web_household import Action, HouseholdError
from ...web_identity import InvalidCredentials, RateLimited, UsernameTaken
from ...web_platform import WebAPIError, WebPrincipal, optional_principal, require_csrf, require_principal
from ...web_platform.session import clear_session_cookies, issue_web_session, set_session_cookies
from ._shared import cap, household_error, require_pet, web_of, web_router

router = web_router("identity")


def capabilities(settings) -> list[Capability]:
    configured = bool(settings.auth_secret)
    status = CapabilityStatus.available if configured else CapabilityStatus.not_configured
    return [
        cap("identity.session_read", "identity", CapabilityStatus.available),
        cap("identity.password_registration", "identity", status, "用户名+密码（scrypt）；邮箱验证/找回尚未提供"),
        cap("identity.email_recovery", "identity", CapabilityStatus.not_implemented, "邮件验证与找回未接入"),
        cap("identity.onboarding", "identity", CapabilityStatus.available),
    ]


def _session_state(request: Request, user_id: str, method: AuthMethod, expires_at=None) -> SessionState:
    web = web_of(request)
    user = request.app.state.storage.get_user(user_id)
    return SessionState(authenticated=True, user=SessionUser(user_id=user_id, display_name=user.display_name if user else None,
                                                             username=web.identity.username_of(user_id), auth_method=method),
                        csrf_required=method is AuthMethod.web_password, expires_at=expires_at, onboarding=web.homes.onboarding(user_id))


def _client_key(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _start_session(request: Request, response: Response, user_id: str) -> SessionState:
    settings = request.app.state.settings
    if not settings.auth_secret:
        raise WebAPIError.capability_unavailable("identity.password_registration", CapabilityStatus.not_configured)
    issued = issue_web_session(settings.auth_secret, user_id, settings.web_session_ttl_seconds)
    web_of(request).identity.record_session(issued.session_id, user_id, issued.expires_at)
    set_session_cookies(response, issued, secure=settings.web_cookie_secure)
    return _session_state(request, user_id, AuthMethod.web_password, issued.expires_at)


@router.get("/session", response_model=SessionState)
def read_session(request: Request, principal: WebPrincipal | None = Depends(optional_principal)) -> SessionState:
    if principal is None:
        return SessionState(authenticated=False)
    web_of(request).identity.touch_active(principal.user_id, utcnow())  # 主人来过（主动消息据此判断；每 10 分钟最多写一次）
    return _session_state(request, principal.user_id, principal.auth_method, principal.expires_at)


@router.post("/auth/register", response_model=SessionState, status_code=201)
def register(body: RegisterRequest, request: Request, response: Response) -> SessionState:
    if not request.app.state.settings.auth_secret:
        raise WebAPIError.capability_unavailable("identity.password_registration", CapabilityStatus.not_configured)
    web = web_of(request)
    try:
        user_id = web.identity.register(body.username, body.password, body.display_name)
    except UsernameTaken as exc:
        raise WebAPIError(WebErrorCode.username_taken, "这个用户名已经有人用了。", 409) from exc
    if body.entry is not None:
        invite_id = None
        if body.entry.kind.value == "invite" and body.entry.invite_token:
            try:
                invite_id = web.households.invite_by_token(body.entry.invite_token)["invite_id"]
            except HouseholdError:
                invite_id = None  # 令牌无效：只记入口，不暴露令牌是否存在过
        target = body.entry.pet_id if body.entry.kind.value == "adopt" else None
        web.entries.record(user_id, body.entry.kind.value, target, invite_id, utcnow())  # 只记下来，等用户登录后确认，不自动领养/加入
    return _start_session(request, response, user_id)


@router.post("/auth/login", response_model=SessionState)
def login(body: LoginRequest, request: Request, response: Response) -> SessionState:
    try:
        user_id = web_of(request).identity.authenticate(body.username, body.password, _client_key(request))
    except RateLimited as exc:
        raise WebAPIError(WebErrorCode.rate_limited, "尝试次数太多，请几分钟后再试。", 429, retryable=True) from exc
    except InvalidCredentials as exc:
        raise WebAPIError(WebErrorCode.invalid_credentials, "用户名或密码不对。", 401) from exc
    return _start_session(request, response, user_id)


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, principal: WebPrincipal | None = Depends(optional_principal)) -> Response:
    """吊销当前网页会话并清除 cookie；Bearer 客户端（iOS）由客户端自行丢弃令牌。"""
    if principal is not None and principal.session_id:
        web_of(request).identity.revoke_session(principal.session_id)
    clear_session_cookies(response, secure=request.app.state.settings.web_cookie_secure)
    response.status_code = 204
    return response


@router.get("/onboarding", response_model=OnboardingState)
def onboarding_state(request: Request, principal: WebPrincipal = Depends(require_principal)) -> OnboardingState:
    return web_of(request).homes.onboarding(principal.user_id)


@router.post("/onboarding/move-in", response_model=OnboardingState, dependencies=[Depends(require_csrf)])
def move_in(body: MoveInRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> OnboardingState:
    """这只宠物住进它的家（家第一次入住时同时激活家）；与接待分开；不会自动出发旅行。重复调用幂等。

    - habitat 只在家第一次入住、还没选过地方时生效，由家庭管理员决定，而且只能选开放的片区（真实交通与地点已接通）；
      之后再加进来的宠物住进同一个家，habitat 被忽略；
    - 还在外面的宠物（例如刚领养、仍在旅途中的星球居民）不会瞬移：等 TA 回到驿站再入住（409 pet_away）。"""
    pet_home = require_pet(request, principal, body.pet_id, action=Action.care)
    web = web_of(request)
    now = utcnow()
    step = web.homes.join_step(pet_home.pet_id, pet_home.home)
    if step.value != "moved_in":
        web.journeys.advance_pet(pet_home.pet_id, now)
        if web.journeys.repo.active_for_pet(pet_home.pet_id) is not None:
            raise WebAPIError(WebErrorCode.conflict, "TA 还在外面，等 TA 回到驿站再接回家。", 409, details={"reason": "pet_away", "pet_id": pet_home.pet_id})
    if pet_home.activated_at is None and body.habitat and web.home_places.chosen_at(pet_home.home_id) is None:
        if not pet_home.access.allows(Action.manage):
            raise WebAPIError(WebErrorCode.forbidden, "家的位置由家庭管理员决定。", 403, details={"reason": "manage_required"})
        try:
            web.home_places.assign(pet_home.home_id, body.habitat, now, open_only=True)  # 希望这个家在哪（只在第一次入住时按这里分配）
        except ValueError as exc:
            raise WebAPIError(WebErrorCode.validation_failed, str(exc), 422, details={"reason": "habitat_not_supported"}) from exc
    public_posts = body.public_posts if pet_home.activated_at is None else pet_home.public_posts
    if web.homes.move_in(pet_home, public_posts, now):
        web.residents.moved_home(pet_home.pet_id, now)  # 领养的星球居民：从驿站搬进新家（不是居民时什么也不做）
    web.credentials.ensure_basics(principal.user_id, pet_home.pet_id)  # 入住即签发身份卡、银行卡、照护档案（签发时间＝入住时间；卡包与时间线里可见）
    web.entries.resolve(principal.user_id, now)
    return web.homes.onboarding(principal.user_id)


def _settings_pet(request: Request, principal: WebPrincipal, pet_id: str | None):  # noqa: ANN202
    """设置页对应的那只宠物：显式 pet_id；没给时默认唯一的那只，不止一只时只读展示第一只（修改仍要求指明）。"""
    web = web_of(request)
    if pet_id:
        return require_pet(request, principal, pet_id)
    pets = web.households.accessible_pets(principal.user_id)
    if not pets:
        return None
    return require_pet(request, principal, pets[0][0])


def _settings_view(request: Request, principal: WebPrincipal, pet_id: str | None = None) -> SettingsView:
    web = web_of(request)
    user_id = principal.user_id
    pet_home = _settings_pet(request, principal, pet_id)
    profile = web.pets.profile(pet_home.pet_id) if pet_home else None
    user = request.app.state.storage.get_user(user_id)
    prefs = web.identity.prefs(user_id)
    household = web.households.household_row(pet_home.household_id) if pet_home else None
    generated = prefs["generated_photos"] if household is None or household["generated_photos"] is None else bool(household["generated_photos"])
    pet_messages = prefs["pet_messages"]  # 个人：TA 主动找我私聊；家庭频道里的新鲜事由家庭设置决定（/households/{id}）
    chat, illustrator = web.providers.chat, web.providers.illustrator
    return SettingsView(username=web.identity.username_of(user_id), display_name=user.display_name if user else None,
                        public_posts=bool(pet_home and pet_home.public_posts), profile_visibility=profile.visibility.value if profile else "private",
                        bio=profile.bio if profile else None, intent_layer_mode=web.intent.mode.value,
                        model_replies=prefs["model_replies"], model_replies_available=chat.available, model_provider=chat.provider_label if chat.available else None,
                        generated_photos=generated, generated_photos_available=illustrator.available,
                        image_provider=illustrator.provider_label if illustrator.available else None,
                        pet_messages=pet_messages, timezone=prefs["timezone"])


@router.get("/settings", response_model=SettingsView)
def read_settings(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> SettingsView:
    return _settings_view(request, principal, pet_id)


@router.patch("/settings", response_model=SettingsView, dependencies=[Depends(require_csrf)])
def update_settings(body: SettingsUpdate, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> SettingsView:
    """个人偏好（私聊用模型、TA 主动找我私聊、时区）谁都能改自己的；公开动态、写实照片、宠物公开范围属于家庭，只有家庭管理员能改；
    简介属于宠物，家人都能改。"""
    web = web_of(request)
    household_fields = any(v is not None for v in (body.public_posts, body.generated_photos, body.profile_visibility))
    pet_home = require_pet(request, principal, pet_id, action=Action.manage if household_fields else Action.care) \
        if household_fields or body.bio is not None else None
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except Exception as exc:  # noqa: BLE001 - 非 IANA 名称
            raise WebAPIError(WebErrorCode.validation_failed, "时区名称不正确。", 422, details={"reason": "invalid_timezone"}) from exc
    if body.model_replies is not None or body.timezone is not None or body.pet_messages is not None:
        web.identity.set_prefs(principal.user_id, model_replies=body.model_replies, pet_messages=body.pet_messages, timezone=body.timezone)
    if pet_home is not None:
        if body.public_posts is not None:
            web.homes.set_public_posts(pet_home.household_id, body.public_posts)
        if body.generated_photos is not None:
            try:
                web.households.update_settings(principal.user_id, pet_home.household_id, generated_photos=body.generated_photos)
            except HouseholdError as exc:
                raise household_error(exc) from exc
        if body.profile_visibility is not None or body.bio is not None:
            web.pets.update_profile(principal.user_id, pet_home.pet_id, ProfileVisibility(body.profile_visibility) if body.profile_visibility else None, body.bio)
    return _settings_view(request, principal, pet_home.pet_id if pet_home else pet_id)
