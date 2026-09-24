"""访客入口（0.4.0，不需要登录）：先逛逛星球——还在驿站生活、可以领养的居民此刻在做什么，公开的宠物主页与公开动态。

- 只读：不推进世界、不写任何记录、不调用模型或生图（居民此刻的位置按已经发生的行程推算）；
- 只给公开内容：居民的生活本来就公开；家庭里的宠物只有公开主页与家庭选择公开的动态，不给位置、不给家庭成员、不给私聊与叮嘱；
- 结果缓存 CACHE_SECONDS 秒，同一来源每分钟最多 RATE_PER_MINUTE 次（超过 429），访客页刷新不会让服务端反复计算；
- 注册前在这里选中的伙伴，注册时作为入口带上（/auth/register 的 entry），登录后由用户确认才领养。
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request
from fastapi.responses import FileResponse

from ...schemas.web.common import Capability, CapabilityStatus, DataOrigin, WebErrorCode
from ...schemas.web.pets import PetOrigin, PetPresence, PetSpecies, ProfileVisibility
from ...schemas.web.public import EntryRoute, PublicEntry, PublicPetView, PublicResident, PublicWorld
from ...schemas.web.social import Post, PostPage
from ...utils import utcnow
from ...web_platform import WebAPIError
from ...web_social import Viewer
from ._shared import cap, web_of, web_router

router = web_router("public")

CACHE_SECONDS = 30
RATE_PER_MINUTE = 120
VISITOR = Viewer(user_id="", pet_id=None, pet_name=None, owner_name="访客", pet_ids=())
ENTRIES = [
    PublicEntry(route=EntryRoute.browse, label="先逛逛", needs_login=False, note="看看星球上的居民在做什么，不用注册"),
    PublicEntry(route=EntryRoute.own_pet, label="带我的宠物来", needs_login=True, note="注册后上传 TA 的照片，经过接待再住进来"),
    PublicEntry(route=EntryRoute.adopt, label="认识一位新伙伴", needs_login=True, note="注册前选中的伙伴会被记住，登录后由你确认才领养"),
    PublicEntry(route=EntryRoute.invite, label="家人邀请我加入", needs_login=True, note="打开家人发来的邀请链接，确认后加入这个家庭"),
]
DOING = {PetPresence.at_home: "在驿站休息", PetPresence.in_transit: "在路上", PetPresence.returning: "在回驿站的路上"}


def capabilities(settings) -> list[Capability]:
    return [cap("public.world", "public", CapabilityStatus.available,
                "访客不登录可看：待领养居民此刻的生活与公开动态、公开宠物主页；只读、缓存 30 秒、按来源限流；不含任何私密内容")]


class _Cache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, object]] = {}

    def get(self, key: str, build):
        now = time.monotonic()
        with self._lock:
            found = self._items.get(key)
            if found and found[0] > now:
                return found[1]
        value = build()
        with self._lock:
            self._items[key] = (now + CACHE_SECONDS, value)
            if len(self._items) > 512:
                for stale in [k for k, (exp, _) in self._items.items() if exp <= now]:
                    self._items.pop(stale, None)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def invalidate(app) -> None:
    """居民被领养等改变公开世界的事发生后，立即清掉访客页缓存（不必等 30 秒）。"""
    state = getattr(app.state, "web_public_cache", None)
    if state is not None:
        state[0].clear()


class _Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def check(self, request: Request) -> None:
        # 部署时后端只在反向代理（Caddy）后面、不直接暴露公网：按代理转来的第一个 X-Forwarded-For 计数，
        # 否则所有访客都会算成代理的同一个地址、共用一份额度
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        source = forwarded or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(source, deque())
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= RATE_PER_MINUTE:
                raise WebAPIError(WebErrorCode.rate_limited, "访问太频繁了，请稍后再看。", 429, retryable=True)
            hits.append(now)


def _state(request: Request) -> tuple[_Cache, _Limiter]:
    app = request.app
    if not hasattr(app.state, "web_public_cache"):
        app.state.web_public_cache = (_Cache(), _Limiter())
    return app.state.web_public_cache


def _public_media(post: Post) -> Post:
    """访客看到的图片走公开媒体地址（只给已经公开的明信片与公开主页头像）。"""
    media = [m.model_copy(update={"url": m.url.replace("/api/v1/web/media/postcards/", "/api/v1/web/public/media/postcards/")}) for m in post.media]
    author = post.author
    if author.avatar_url:
        author = author.model_copy(update={"avatar_url": author.avatar_url.replace("/api/v1/web/media/pets/", "/api/v1/web/public/media/pets/")})
    return post.model_copy(update={"media": media, "author": author, "viewer_reacted": False})


def _posts(request: Request, pet_id: str, limit: int) -> list[Post]:
    return [_public_media(p) for p in web_of(request).social.pet_posts(VISITOR, pet_id).items[:limit]]


def _resident(request: Request, row: dict) -> PublicResident:
    web = web_of(request)
    presence, journey, visit = web.journeys.peek(row["pet_id"])
    place = visit.place.get("name") if presence is PetPresence.visiting and visit else None
    if presence is PetPresence.visiting and place:
        doing = f"在{place}"
    elif presence is PetPresence.in_transit and journey is not None:
        doing = f"在去{journey.title}的路上"
    else:
        doing = DOING.get(presence, "在驿站休息")
    return PublicResident(pet_id=row["pet_id"], candidate_id=row["candidate_id"], name=row["name"], species=PetSpecies(row["species"]),
                          personality=row["personality"], dream=row["dream"], origin=PetOrigin(row["origin"]), source_note=row["source_note"],
                          residence=row["residence"], city=row["city"], living_since=row["living_since"], presence=presence, doing=doing, place_name=place,
                          recent_posts=_posts(request, row["pet_id"], 3))


@router.get("/public/world", response_model=PublicWorld)
def public_world(request: Request) -> PublicWorld:
    """访客首页：入口（先逛逛 / 带我的宠物来 / 认识新伙伴 / 家人邀请）、居民此刻的生活、全星球最近的公开动态。"""
    cache, limiter = _state(request)
    limiter.check(request)

    def build() -> PublicWorld:
        web = web_of(request)
        rows = web.residents.public_list()
        residents = [_resident(request, row) for row in rows]
        recent = [_public_media(p) for p in web.social.feed(VISITOR, None, 12).items]
        return PublicWorld(server_time=utcnow(), entries=ENTRIES, residents=residents, recent_posts=recent, living_residents=len(rows),
                           cache_seconds=CACHE_SECONDS, data_origin=DataOrigin.live)

    return cache.get("world", build)


@router.get("/public/residents", response_model=list[PublicResident])
def public_residents(request: Request) -> list[PublicResident]:
    """还在驿站生活、可以领养的居民（此刻在哪、在做什么、最近的公开动态）。"""
    cache, limiter = _state(request)
    limiter.check(request)
    return cache.get("residents", lambda: [_resident(request, row) for row in web_of(request).residents.public_list()])


@router.get("/public/pets/{pet_id}", response_model=PublicPetView)
def public_pet(pet_id: str, request: Request) -> PublicPetView:
    """公开主页：居民（还可以领养时带上此刻的生活）或主页设为公开的宠物；其余一律 404（不区分是否存在）。"""
    cache, limiter = _state(request)
    limiter.check(request)

    def build() -> PublicPetView:
        web = web_of(request)
        record = web.pets.profile(pet_id)
        row = web.residents.public_row(pet_id)
        if record is None or (row is None and record.visibility is not ProfileVisibility.public):
            raise WebAPIError.not_found("这只宠物的公开主页")
        followers, count = web.social.counts(pet_id)
        profile = web.pets.public_profile(record, followers, count)
        if profile.avatar_url:
            profile = profile.model_copy(update={"avatar_url": profile.avatar_url.replace("/api/v1/web/media/pets/", "/api/v1/web/public/media/pets/")})
        return PublicPetView(profile=profile, resident=_resident(request, row) if row else None, adoptable=row is not None, posts=_posts(request, pet_id, 20))

    return cache.get(f"pet:{pet_id}", build)


@router.get("/public/pets/{pet_id}/posts", response_model=PostPage)
def public_pet_posts(pet_id: str, request: Request) -> PostPage:
    cache, limiter = _state(request)
    limiter.check(request)
    return cache.get(f"posts:{pet_id}", lambda: PostPage(items=_posts(request, pet_id, 50), next_cursor=None))


@router.get("/public/media/postcards/{photo_id}")
def public_postcard(photo_id: str, request: Request) -> FileResponse:
    """已经公开（发成了公开动态）的明信片。"""
    _state(request)[1].check(request)
    path = web_of(request).postcards.file_for(None, photo_id)
    if path is None:
        raise WebAPIError.not_found("这张明信片")
    return FileResponse(path, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=600", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                                 "X-Content-Type-Options": "nosniff"})


@router.get("/public/media/pets/{pet_id}/photo")
def public_pet_photo(pet_id: str, request: Request) -> FileResponse:
    """主页设为公开的宠物头像（私密与“仅关注者”的不给）。"""
    _state(request)[1].check(request)
    found = web_of(request).pets.photo_file(None, pet_id)
    if found is None:
        raise WebAPIError.not_found("这张照片")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "public, max-age=600", "X-Content-Type-Options": "nosniff"})
