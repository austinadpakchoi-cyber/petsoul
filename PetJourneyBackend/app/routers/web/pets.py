"""建立专属伙伴（上传自己的宠物 / 专属领养）、宠物 DNA、公开主页、私有媒体访问。

0.4.0 家庭：一只宠物只属于一个家庭，一个家庭可以有多位成员、多只宠物。
- POST /pets 与 /adoption/adopt 不带 household_id → 新建家庭（本人成为管理员）；带 household_id → 加进这个家庭（需要管理员）；
- 访问宠物（DNA、照片、主页“是不是自家的”）只看当前有效的家庭成员关系，被移出后立刻失效；
- DNA 分共用层（带版本号，?expected_version= 防止无声覆盖）与每位家人各自的个人层（称呼、小暗号）。"""

from __future__ import annotations

import hashlib
import json
from zoneinfo import ZoneInfo

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.social import PhotoStatus
from ...schemas.web.pets import (AdoptionCandidate, AdoptRequest, AdoptResult, PetBehavior, PetDNA, PetDNAView,
                                 PetPrivateSummary, PetPublicProfile, PetSpecies, PhotoNarrative, PhotoRequestCommand,
                                 PhotoRequestResult, PhotoRequestView, PhotoScene)
from ...web_agent.profile import FIELD_LABELS
from ...web_household import Action, HouseholdError
from ...web_pets import AdoptionTaken, AlreadyHasCompanion, CandidateNotFound, MediaRejected
from ...web_pets.dna import DNAConflict
from ...utils import parse_dt, utcnow
from ...web_journey.photo_command import (SCENE_ACTIONS, active_leg, is_train_leg, registration_of, registrations,
                                          setting_for, source_key_of)
from ...web_platform.runtime_epochs import versions_in
from ...web_platform.uow import unit_of_work
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ._shared import cap, household_error, idempotent, redraw, require_household, require_pet, web_of, web_router
from .public import invalidate as invalidate_public

router = web_router("pets")

MEDIA_REASONS = {"empty": "图片是空的。", "too_large": "图片太大了（上限 5MB）。", "unsupported_type": "只支持 JPEG / PNG / WebP 图片。"}


def capabilities(settings) -> list[Capability]:
    return [
        cap("pets.create_own", "pets", CapabilityStatus.available, "私有存储、魔数校验与元数据剥离；尚未做解码重编码"),
        cap("pets.adoption", "pets", CapabilityStatus.available, "原创伙伴池；待领养居民领养前就在星球上生活（稳定 pet_id），领养保留身份；原子占用，同一只只属于一个家庭"),
        cap("pets.real_archive_adoption", "pets", CapabilityStatus.not_implemented, "真实原型档案需有核实材料，未提供"),
        cap("pets.public_profile", "social", CapabilityStatus.available),
        cap("pets.dna", "pets", CapabilityStatus.available, "主人描述并确认的性格、说话方式与小习惯；TA 说话时读取；私密字段只用于私信；同时整理出作息、出门与工作倾向（behavior，可追溯到原话，处理否定与纠正）"),
    ]


def _summary(request: Request, pet_id: str) -> PetPrivateSummary:
    web = web_of(request)
    record = web.pets.profile(pet_id)
    home = web.homes.by_pet(pet_id)
    return PetPrivateSummary(pet_id=pet_id, home_id=home.home_id if home else None, name=record.name, species=record.species, photo_url=web.pets.photo_url(record),
                             origin=record.origin, owner_title=None, presence=web.presence(pet_id), photo_generated=web.pets.photo_generated(pet_id))


@router.post("/pets", response_model=PetPrivateSummary, status_code=201, dependencies=[Depends(require_csrf)])
async def create_own_pet(
    request: Request,
    name: str = Form(..., min_length=1, max_length=24),
    species: PetSpecies = Form(...),
    photo: UploadFile | None = File(default=None),
    household_id: str | None = Form(default=None),
    principal: WebPrincipal = Depends(require_principal),
    idempotency_key: str = Depends(require_idempotency_key),
) -> PetPrivateSummary:
    """建立归属（未入住），**不**开启旅程。照片私有存储，只经鉴权接口访问。
    household_id 为空：新建家庭与家（本人成为管理员；一个账号只能建立一个家庭，已有时 409 household_exists）；
    给出 household_id：加进这个家庭（需要是它的管理员），与家里其他宠物共用一个家。"""
    data = await photo.read() if photo is not None else None
    payload = {"name": name.strip(), "species": species.value, "photo": hashlib.sha256(data).hexdigest() if data else None, "household_id": household_id}
    if household_id:
        require_household(request, principal, household_id, action=Action.manage)

    def handler() -> PetPrivateSummary:
        try:
            record = web_of(request).pets.create_own(principal.user_id, name, species, data, household_id)
        except HouseholdError as exc:
            raise household_error(exc) from exc
        except AlreadyHasCompanion as exc:
            raise WebAPIError(WebErrorCode.already_has_companion, "每个账号先陪伴一只专属伙伴。", 409) from exc
        except MediaRejected as exc:
            raise WebAPIError(WebErrorCode.media_rejected, MEDIA_REASONS.get(exc.reason, "图片无法使用。"), 422, details={"reason": exc.reason}) from exc
        return _summary(request, record.pet_id)

    return idempotent(request, principal, "pets.create", idempotency_key, payload, PetPrivateSummary, handler)


@router.get("/adoption/candidates", response_model=list[AdoptionCandidate])
def adoption_candidates(request: Request, principal: WebPrincipal = Depends(require_principal)) -> list[AdoptionCandidate]:
    """领养卡（未登录的访客走 /public/residents，看到的是同一批居民的公开生活）。"""
    return web_of(request).pets.candidates()


@router.post("/adoption/adopt", response_model=AdoptResult, dependencies=[Depends(require_csrf)])
def adopt(body: AdoptRequest, request: Request, principal: WebPrincipal = Depends(require_principal), idempotency_key: str = Depends(require_idempotency_key)) -> AdoptResult:
    """领养一位伙伴：不带 household_id 新建家庭；带上则领养进这个家庭（需要管理员）。已经在星球上生活的居民保留 pet_id、性格与公开经历；
    正在外面的居民不会瞬移，等 TA 回到驿站后再入住新家。"""
    if body.household_id:
        require_household(request, principal, body.household_id, action=Action.manage)

    def handler() -> AdoptResult:
        try:
            result = web_of(request).pets.adopt(principal.user_id, body.candidate_id, body.household_id)
            web_of(request).entries.resolve(principal.user_id, utcnow())  # 注册前选中的伙伴：确认领养后入口就算处理完了
            invalidate_public(request.app)  # 访客页不再把 TA 列为可领养
            return result
        except HouseholdError as exc:
            raise household_error(exc) from exc
        except AdoptionTaken as exc:
            raise WebAPIError(WebErrorCode.adoption_taken, "这位伙伴刚刚有了自己的家。每一位只属于一个家庭。", 409) from exc
        except AlreadyHasCompanion as exc:
            raise WebAPIError(WebErrorCode.already_has_companion, "每个账号先陪伴一只专属伙伴。", 409) from exc
        except CandidateNotFound as exc:
            raise WebAPIError.not_found("这位伙伴") from exc

    return idempotent(request, principal, "pets.adopt", idempotency_key, body.model_dump(), AdoptResult, handler)


def _own_pet(request: Request, principal: WebPrincipal, pet_id: str, action: Action = Action.view):
    """自家的宠物（当前有效的家庭成员）；不是成员 404，角色不够 403。"""
    require_pet(request, principal, pet_id, action=action)
    record = web_of(request).pets.profile(pet_id)
    if record is None:
        raise WebAPIError.not_found("这只宠物")
    return record


def _behavior(request: Request, pet_id: str) -> PetBehavior | None:
    """由 DNA 原话整理出的行为倾向（与作息、自主生活、主动消息用的是同一份），每条都带原话出处。"""
    profile_of = web_of(request).profile_of
    if profile_of is None:
        return None
    profile = profile_of(pet_id)

    def evidence(items) -> list[dict]:
        return [{"field": e.field, "field_label": FIELD_LABELS.get(e.field, e.field), "phrase": e.phrase, "polarity": e.polarity, "note": e.note,
                 "implied": e.implied} for e in items]

    return PetBehavior.model_validate({
        "rules_version": profile.rules_version, "rhythm": profile.rhythm, "sleep_start": f"{profile.sleep_start:%H:%M}", "wake": f"{profile.wake:%H:%M}",
        "sociability": profile.sociability, "curious": profile.curious, "outings_per_day": profile.outings_per_day, "chattiness": profile.chattiness,
        "learn_rate": profile.learn_rate, "summary": list(profile.reasons), "unclassified": list(profile.unclassified), "sources": list(profile.sources),
        "traits": [{"key": t.key, "label": t.label, "status": t.status, "evidence": evidence(t.evidence)} for t in profile.traits],
        "preferences": [{"key": p.key, "label": p.label, "weight": p.weight, "evidence": evidence(p.evidence), "notes": list(p.notes)} for p in profile.preferences],
    })


def _dna_view(request: Request, principal: WebPrincipal, pet_id: str) -> PetDNAView:
    found = web_of(request).dna.record(principal.user_id, pet_id)
    if found is None:
        return PetDNAView(pet_id=pet_id, dna=PetDNA(), confirmed=False, behavior=_behavior(request, pet_id))
    return PetDNAView(pet_id=pet_id, dna=found.dna, confirmed=found.confirmed, draft_sources=[] if found.confirmed else found.sources, updated_at=found.updated_at,
                      behavior=_behavior(request, pet_id), version=found.version,
                      updated_by_you=(found.updated_by == principal.user_id) if found.updated_by else None)


@router.get("/pets/{pet_id}/dna", response_model=PetDNAView)
def read_dna(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> PetDNAView:
    """宠物 DNA（只给这只宠物的家人）。没保存过时返回按已有资料整理的草稿（confirmed=false），页面应提示“待你确认”。
    dna 里的 owner_title 与 shared_memories 是你自己的那一份（见 personal_fields），其余是全家共用的（version）。
    behavior：由这份 DNA 整理出的作息、出门与工作倾向，每条都带原话出处；说不准的原话列在 unclassified，不强行归类。"""
    _own_pet(request, principal, pet_id)
    return _dna_view(request, principal, pet_id)


@router.put("/pets/{pet_id}/dna", response_model=PetDNAView, dependencies=[Depends(require_csrf)])
def save_dna(pet_id: str, body: PetDNA, request: Request, expected_version: int | None = None,
             principal: WebPrincipal = Depends(require_principal)) -> PetDNAView:
    """整体保存（即确认）。保存后 TA 在私信与主动消息里按这份 DNA 说话，作息与出门倾向也立刻按新的来（见返回的 behavior）。
    expected_version：读到的共用版本号；家人在这之后改过 → 409 dna_version_conflict（带 current_version），页面应重新读取再改。
    **还没保存过时传 0**：版本从 1 起（`web_pets/dna.py:137` 写死 1），所以 0 撞不上任何已存在的记录——
    两位家人同时首存时，后到的那位会看见先到的那一版（检查在 `BEGIN IMMEDIATE` 里、由写锁排序），
    `1 != 0` 当场冲突。**这个窗口是关上的，不是缩小的。**
    **不传 `expected_version` 则完全不检查**：记录已存在也直接覆盖。那是留给「明知要覆盖」的调用方的口子，
    **正常的编辑页面应当一律传**（首存传 0，之后传读到的版本号）。
    称呼与小暗号只写进你自己的那一份，不会覆盖其他家人的。"""
    _own_pet(request, principal, pet_id, Action.care)
    try:
        web_of(request).dna.save(principal.user_id, pet_id, body, utcnow(), expected_version)
    except DNAConflict as exc:
        # 文案里不出现「DNA」：那是**代码里的名字**，界面上这一页叫「TA 的档案」（6c2b 2026-09-24 指出）。
        # 主人看到的词应当和它在界面上看到的一致。**`reason` 码不动**——`dna_version_conflict`
        # 是契约里的稳定标识，前端按它分支；**给人看的话和给程序看的码，改的自由度不一样。**
        raise WebAPIError(WebErrorCode.conflict, "家人刚改过 TA 的档案，先看看最新的再改。", 409,
                          details={"reason": "dna_version_conflict", "current_version": exc.current_version}) from exc
    return _dna_view(request, principal, pet_id)


def _follows(request: Request, principal: WebPrincipal, pet_id: str) -> bool:
    """查看者家里（任何一个家庭）有没有哪只宠物关注了 TA。"""
    web = web_of(request)
    return any(web.social.is_follower(mine, pet_id) for mine, _ in web.households.accessible_pets(principal.user_id))


@router.get("/pets/{pet_id}/profile", response_model=PetPublicProfile)
def pet_public_profile(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> PetPublicProfile:
    web = web_of(request)
    record = web.pets.profile(pet_id)
    follower = _follows(request, principal, pet_id)
    if record is None:
        raise WebAPIError.not_found("这只宠物的公开主页")
    full = web.pets.can_view(principal.user_id, record, follower)
    # 主页私密但家庭同意公开动态：只给动态作者的最小名片（名字/物种/计数），不给头像与简介。
    if not full and not web.social.public_posts_of(pet_id):
        raise WebAPIError.not_found("这只宠物的公开主页")
    followers, posts = web.social.counts(pet_id)
    profile = web.pets.public_profile(record, followers, posts).model_copy(update={"viewer_follows": follower, "is_own": web.pets.is_member(principal.user_id, pet_id)})
    return profile if full else profile.model_copy(update={"avatar_url": None, "bio": None})


@router.get("/media/pets/{pet_id}/photo", include_in_schema=True)
def pet_photo(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    web = web_of(request)
    found = web.pets.photo_file(principal.user_id, pet_id, _follows(request, principal, pet_id))
    if found is None:
        raise WebAPIError.not_found("这张照片")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/media/illustrations/{illustration_id}")
def illustration(illustration_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    """冒险插画（生图结果）只给这只宠物的家人。"""
    found = web_of(request).illustrations.file_for(principal.user_id, illustration_id)
    if found is None:
        raise WebAPIError.not_found("这张插画")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/media/postcards/{photo_id}")
def postcard(photo_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    path = web_of(request).postcards.file_for(principal.user_id, photo_id)
    if path is None:
        raise WebAPIError.not_found("这张明信片")
    return FileResponse(path, media_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=300", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})


def _scene_fact(token: str, pet_id: str, household_id: str, event_id: str) -> dict:
    """一条**已核验**的场景事实，按照片导演的结构给。

    `verified` 恒为 True：这里只放核验得住的（在家＝真的在家，列车的窗与座由已核验的 mode 蕴含）。
    拿不准的一律不放进来——导演那边"没核验过的事实等于没有"，宁可 hold 也不编。
    依据写在 payload 的 `fact_basis` 里，供诊断查阅。
    """
    return {"fact_id": f"{event_id}:{token}", "token": token, "pet_id": pet_id,
            "household_id": household_id, "event_id": event_id, "verified": True}


def _request_id_of(conn, source_key: str) -> str:
    """这次摄影请求的稳定标识。用插画记录的主键：它唯一、不变，也正是媒体地址里的那一段。"""
    row = conn.execute("SELECT illustration_id FROM web_illustrations WHERE source_event_id = ?", (source_key,)).fetchone()
    return row["illustration_id"] if row is not None else source_key


def _photo_view(web, row) -> PhotoRequestView:
    """把一条登记翻成页面能用的样子。**四态里的 unknown 用 A 的 `outcome_of` 判**，不另写一套。"""
    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    status = row["status"]
    if status == "failed":
        status = web.illustrations.outcome_of(row["task_id"]) or "failed"  # failed / unknown
    narrative = payload.get("narrative") or PhotoNarrative.daily_life.value
    shown = payload.get("captured_at_display") or payload.get("captured_at") or row["created_at"]
    return PhotoRequestView(
        request_id=row["illustration_id"], task_id=row["task_id"],
        scene=PhotoScene(payload.get("scene_key") or PhotoScene.home.value), narrative=PhotoNarrative(narrative),
        fictional=narrative == PhotoNarrative.fictional_adventure.value, captured_at=parse_dt(shown),
        place=payload.get("place") or "", city=payload.get("city") or "",
        photo_status=PhotoStatus(status),
        image_url=f"/api/v1/web/media/illustrations/{row['illustration_id']}" if status == "ready" else None,
        can_retry=status in ("failed", "unknown"))


def _prior_registration(conn, source_key: str) -> PhotoRequestResult | None:
    """按稳定编号找**已经提交过**的那次拍照登记，用首次写下的内容重建响应。

    地点、城市、叙事、拍摄时刻**一律取首次持久化的值**，不按重放这一刻的现状重新拼——
    否则一张在家拍的照片会被改写成"在列车上"。
    """
    row = conn.execute(
        "SELECT t.task_id, t.payload_json, i.illustration_id FROM web_tasks t "
        "LEFT JOIN web_illustrations i ON i.task_id = t.task_id WHERE t.dedupe_key = ?",
        (f"illustration:{source_key}",)).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload_json"])
    scene_key = payload.get("scene_key")
    narrative = payload.get("narrative") or PhotoNarrative.daily_life.value
    shown = payload.get("captured_at_display") or payload.get("captured_at")
    if not scene_key or not shown:
        return None  # 不是这条命令登记的（或旧数据缺字段）：不硬猜，当成没有原登记
    return PhotoRequestResult(request_id=row["illustration_id"] or source_key, task_id=row["task_id"],
                              scene=PhotoScene(scene_key), narrative=PhotoNarrative(narrative),
                              fictional=narrative == PhotoNarrative.fictional_adventure.value,
                              captured_at=parse_dt(shown), place=payload.get("place") or "", city=payload.get("city") or "")


def _first_captured_at(conn, task_id: str | None):
    """读回**首次登记**时写下的拍摄时刻。

    接手一次没写完回执的请求时，`request_photo_in` 会命中既有的 dedupe 拿回原来那个任务——
    这时响应里的时刻必须是**主人当初按下那一刻**，不是接手这一刻。
    否则一张中午拍的照片会被记成六分钟后的，导演按错的时刻去画光线。
    """
    if not task_id:
        return None
    row = conn.execute("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
    stored = json.loads(row["payload_json"]).get("captured_at") if row else None
    return parse_dt(stored) if stored else None


def _versions_drifted(expected, current) -> bool:
    """两次读到的语义代数有没有变。字段以 `runtime_epochs.versions_in` 给出的为准，逐个比。"""
    fields = ("runtime_epoch", "activity_epoch", "privacy_epoch", "membership_epoch", "dna_version", "itinerary_version")
    return any(getattr(expected, f, None) != getattr(current, f, None) for f in fields)


@router.post("/pets/{pet_id}/photo-request", response_model=PhotoRequestResult, dependencies=[Depends(require_csrf)])
def photo_request(pet_id: str, body: PhotoRequestCommand, request: Request, principal: WebPrincipal = Depends(require_principal),
                  idempotency_key: str = Depends(require_idempotency_key)) -> PhotoRequestResult:
    """主人说「给我拍一张」。**只管 home / train / flight_adventure 三个场景**——
    到咖啡馆拍照仍由行程里的到访活动触发，那条路不变。

    **两种拒绝不要混成一个**：
    - **这里的 409** ＝ 状态根本不成立（TA 现在不在家 / 不在列车上）。**命令不成立，连事件都不写**，没有任何付费可能。
    - 照片导演那边的 **hold** ＝ 命令成立、记录已写，但事实不齐 / 授权被撤 / 参考照不合法，于是不出图。
    两者都**不回退旧模板**：拒了就是拒了，不会偷偷换一张模板图糊弄过去。

    `flight_adventure` 是主人明确选的**虚构主题**：不写世界事件、不进旅程历史、不扣旅费、不发勋章；
    但它**会**留下可恢复的插画记录（`web_illustrations`），主人刷新页面还能看到这次请求。

    排队、额度预占与在途撤权复核全部沿用既有的 `request_photo_in` 那条链，这里**不另造费用账本**。
    """
    home = require_pet(request, principal, pet_id, activated=True, action=Action.care)
    web = web_of(request)
    scene = body.scene.value

    wants_fiction = body.scene is PhotoScene.flight_adventure
    if wants_fiction and body.narrative is not PhotoNarrative.fictional_adventure:
        raise WebAPIError(WebErrorCode.validation_failed, "虚构的飞行冒险要主人明确选这个主题，不会自动当成日常照片。", 422,
                          details={"scene": scene, "expected_narrative": PhotoNarrative.fictional_adventure.value})
    if not wants_fiction and body.narrative is not PhotoNarrative.daily_life:
        raise WebAPIError(WebErrorCode.validation_failed, "这个场景只拍日常，不能标成虚构冒险。", 422,
                          details={"scene": scene, "expected_narrative": PhotoNarrative.daily_life.value})

    source_key = source_key_of(principal.user_id, home.pet_id, scene, idempotency_key)

    def handler() -> PhotoRequestResult:
        """**场景核验在这里面**，不在外面。

        放外面会有一个很难发现的洞：首单成立之后 TA 出门了，主人（或客户端重试）拿同一个 key 重放，
        外层核验先判"现在不在家"就 409 了——**原来那次的结果被丢掉**，主人再也拿不回自己的照片。
        幂等的含义是"同一个 key 取回同一次操作"，不是"每次都按当下状态重判一次"。
        访问权限不在这里面：那是每次请求都要查的，已经在上面的 `require_pet` 做过。
        """
        # **先看有没有已经提交过的那次登记**（COORD-I-RECOVERY-INTERSECTION）。
        # 回执丢了、人又已经离家时，如果直接按当下状态重判，就会判"现在不在家"而 409——
        # 可主人那次请求早就成立了、任务还躺在库里，**那是把已经成立的事弄丢，不是防重复收费**。
        # 所以：有原登记就照**首次持久下来的内容**重建响应；只有确实没有，才当成一条新命令。
        # 访问授权不在这里放松——`require_pet` 每次请求都查过了。
        with request.app.state.storage.connect() as conn:
            prior = _prior_registration(conn, source_key)
        if prior is not None:
            return prior

        now = utcnow()
        # 状态一律读 B 的运行投影，不用 `journeys.peek` 的 presence（COORD-B 的口径）：
        # presence 的 at_home 把"真的在家闲着"和"行程已定、正在家里收拾等出门"混在一起，
        # 而后者 `primary_activity` 会带上 ends_at＝出门时刻且 interruptible=False——**那种此刻不该拍**。
        # 没激活/没入住时 kind 是 not_activated 而不是 at_home，所以只认正向判断。
        projector = getattr(web, "projector", None)
        if projector is None:
            raise WebAPIError(WebErrorCode.not_configured, "这个环境没有启用运行投影，暂时不能主动拍照。", 503,
                              details={"capability": "pets.photo_request"})
        state = projector.state(home.pet_id, now)
        activity = state.primary_activity
        kind = getattr(activity, "kind", None)
        kind = getattr(kind, "value", kind)
        place_row = web.home_places.get(home.home_id)
        city, timezone_name = place_row.city, state.timezone or place_row.timezone

        if body.scene is PhotoScene.home:
            if kind != "at_home":
                raise WebAPIError(WebErrorCode.conflict, "TA 现在不在家，这张要等回家再拍。", 409,
                                  details={"scene": scene, "activity": kind})
            if activity is not None and not activity.interruptible:
                raise WebAPIError(WebErrorCode.conflict, "TA 正准备出门，这会儿别打断，等安顿下来再拍。", 409,
                                  details={"scene": scene, "activity": kind, "reason": "not_interruptible"})
        leg = None
        if body.scene is PhotoScene.train:
            journey = web.journeys.repo.active_for_pet(home.pet_id) if kind == "travel" else None
            with request.app.state.storage.connect() as conn:
                leg = active_leg(conn, journey.journey_id, now) if journey else None
            if not is_train_leg(leg):
                raise WebAPIError(WebErrorCode.conflict, "TA 现在不在列车上，这张要等上车之后再拍。", 409,
                                  details={"scene": scene, "activity": kind,
                                           "leg_mode": leg["mode"] if leg is not None else None})
            destination = json.loads(leg["destination_json"])
            city = (journey.city if journey else None) or city
            timezone_name = destination.get("timezone") or timezone_name  # 途中按**当前这一段的落点**算时刻，不是家所在地

        setting = setting_for(scene, city=city, place_label=place_row.display)
        household_id = web.households.household_of_pet(home.pet_id) or ""
        captured_at = now.astimezone(ZoneInfo(timezone_name)) if timezone_name else now
        expected = state.versions
        with unit_of_work(request.app.state.storage) as conn:
            # **同一个写事务里再核一次代数**：上面那些状态是在事务外读的，读完到写入之间世界可能已经变了
            # （撤权、换行程、被移出家庭）。这道护栏让"判断"和"登记"落在同一份事实上，
            # 不让事务外的一次 peek 成为最后一道判断。
            current = versions_in(conn, home.pet_id)
            if _versions_drifted(expected, current):
                raise WebAPIError(WebErrorCode.version_conflict, "刚才这一瞬间情况变了，请刷新后再试一次。", 409,
                                  details={"scene": scene, "reason": "state_changed_before_commit"})
            task_id = web.illustrations.request_photo_in(
                conn, principal.user_id, home.pet_id, source_key,
                place=setting.place, city=setting.city, scene=SCENE_ACTIONS[scene],
                captured_at=captured_at, scene_key=scene, narrative=body.narrative.value,
                captured_at_display=captured_at.isoformat(), household_id=household_id,
                place_id=f"photo-request:{scene}", place_timezone=timezone_name, revision=1,
                # 这条来路是**主人下的命令**，不是世界上发生的事件。写 world_event 会把主人选的虚构飞行
                # 记成"真的发生过"——照片导演为此专门加了围栏（world_event_cannot_be_fictional）。
                event_origin="owner_directed",
                scene_facts=[_scene_fact(f, home.pet_id, household_id, source_key) for f in setting.facts],
                fact_basis=setting.basis)
            first_seen = _first_captured_at(conn, task_id)
            if first_seen is not None:  # 接手时拿回**首次**那一刻，并换回这次算好的展示时区
                captured_at = first_seen.astimezone(ZoneInfo(timezone_name)) if timezone_name else first_seen
            request_id = _request_id_of(conn, source_key)
        return PhotoRequestResult(request_id=request_id, task_id=task_id, scene=body.scene, narrative=body.narrative,
                                  fictional=setting.fictional, captured_at=captured_at, place=setting.place, city=setting.city)

    return idempotent(request, principal, f"photo-request:{home.pet_id}", idempotency_key, body.model_dump(mode="json"), PhotoRequestResult, handler)


@router.get("/pets/{pet_id}/photo-requests", response_model=list[PhotoRequestView])
def photo_requests(pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> list[PhotoRequestView]:
    """主人主动拍的那些照片，现在各是什么样（新的在前）。

    **纯读**：读它不会驱动任务、不会发起任何供应商调用，也不会把 `unknown` 悄悄改写成别的状态。
    刷新页面靠它恢复；**不要拿重发 POST 当状态轮询**——那只会原样拿回第一次的受理结果。
    只给这只宠物的家人；不是这家的人看到的是 404，不泄露存在与否。
    """
    home = require_pet(request, principal, pet_id)
    web = web_of(request)
    with request.app.state.storage.connect() as conn:
        rows = registrations(conn, home.pet_id)
    return [_photo_view(web, row) for row in rows]


@router.post("/pets/{pet_id}/photo-requests/{request_id}/retry-image", response_model=list[PhotoRequestView],
             dependencies=[Depends(require_csrf)])
def retry_photo_request(pet_id: str, request_id: str, request: Request,
                        principal: WebPrincipal = Depends(require_principal)) -> list[PhotoRequestView]:
    """没画成（或结果没确认）时重画。走的是和其它三个重画入口**同一套**凭据与四态语义：
    `failed` / `unknown` 才真的重排；`processing` / `ready` 回当前状态（200，不是 404）；
    任务号对不上或不能重试才是 404。返回这只宠物当前的全部摄影请求，页面直接刷新。
    """
    home = require_pet(request, principal, pet_id, action=Action.care)
    web = web_of(request)
    with request.app.state.storage.connect() as conn:
        row = registration_of(conn, home.pet_id, request_id)
        if row is None:
            raise WebAPIError.not_found("这次摄影请求")
        attempts = conn.execute("SELECT attempts FROM web_tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
    state = row["status"]
    ticket = f"{row['task_id']}#{attempts['attempts']}" if attempts is not None and state == "failed" else None
    redraw(web, ticket, state, "可以重画的摄影请求")
    with request.app.state.storage.connect() as conn:
        rows = registrations(conn, home.pet_id)
    return [_photo_view(web, r) for r in rows]
