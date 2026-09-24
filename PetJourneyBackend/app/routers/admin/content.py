"""运营内容：草稿 → 校验 → 预览 → 发布 → 撤下 / 回退，以及"玩家侧现在读到的是哪一版"。

预览用的是**玩家侧真正会读到的那段投影**（announcement 走 live_announcements 的同一段字段、
adventure 走世界引擎真正会 format 的那段文字），不是另写一份好看的假渲染。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, Request

from ...schemas.admin import (
    ContentDraftRequest,
    ContentPublishRequest,
    ContentRollbackRequest,
    ContentSaveRequest,
    ContentWithdrawRequest,
)
from ...web_admin import labels as L
from ...web_admin.content import validate
from ...web_admin.errors import AdminAPIError, request_id_of
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs

router = admin_router("content")


def _audit_kwargs(ctx, action: str, permission: Permission, item_id: str, reason: str) -> dict:
    return {"action": action, "permission": permission.value, "actor_staff_id": ctx.staff_id,
            "actor_username": ctx.username, "target_kind": "content", "target_id": item_id, "reason": reason,
            "operation_id": ctx.operation_id, "request_id": ctx.request_id}


CONTENT_TYPE_INFO = [
    {"content_type": "announcement", "label": "平台公告", "kind": "standalone",
     "consumer": "玩家端通讯器页顶部的公告细条，以及「全部公告」页", "consumer_api": "GET /api/v1/web/announcements",
     "publishable": ["title", "body", "severity", "audience", "link", "image_asset_id"],
     "blocked": ["任意外链图（配图只能从素材库里选）"]},
    {"content_type": "adventure", "label": "冒险活动模板（现有）", "kind": "overlay",
     "consumer": "世界引擎在新冒险事件发生时取模板；已发生的事件不被改写",
     "publishable": ["title", "badge", "story"], "blocked": ["key", "触发规则"]},
    {"content_type": "crop", "label": "作物与物资（含杂货铺收购价）", "kind": "overlay",
     "consumer": "菜园地块、仓库、杂货铺收购价与居民订单奖励",
     "publishable": ["label", "unit_value", "grow_seconds"],
     "blocked": ["yield_units", "steal_total", "requires_seed"]},
    {"content_type": "job", "label": "打工岗位（工钱配置）", "kind": "overlay",
     "consumer": "打工结束那一刻按当时发布的工钱结算；已经结算的工资不变",
     "publishable": ["label", "pay", "hours"], "blocked": ["keyword", "habitats"]},
    {"content_type": "destination", "label": "出发站地点模板（文案与旅费）", "kind": "overlay",
     "consumer": "出发站的地点列表；出发那一刻把标题、城市、旅费写进这趟行程", "consumer_api": "/journey/destinations",
     "publishable": ["title", "city", "summary", "fee"],
     "blocked": ["outbound", "inbound", "venue", "wish_keywords", "food_area"]},
    {"content_type": "resident", "label": "原创待领养居民（文案）", "kind": "table",
     "consumer": "访客公开页与领养页；只改还没被领养的居民", "consumer_api": "/adoption/candidates",
     "publishable": ["personality", "dream", "source_note"], "blocked": ["name", "species", "pet_id"]},
]


@router.get("/content")
def list_content(request: Request, content_type: str | None = None,
                 principal: AdminPrincipal = Depends(needs(Permission.CONTENT_READ))) -> dict:
    services = admin_of(request)
    items = services.content.list_items(content_type)
    return {"items": [asdict(item) for item in items], "types": CONTENT_TYPE_INFO}


@router.get("/content-sources/{content_type}")
def content_sources(content_type: str, request: Request,
                    principal: AdminPrincipal = Depends(needs(Permission.CONTENT_EDIT))) -> dict:
    """新建草稿时可选的条目，以及每一条的**内置当前值**（拿它当草稿起点，也用来看差异）。

    覆盖层类型只能给已有条目发新版本；居民只列还没被领养的。公告没有内置条目，返回空清单。
    """
    from ...web_admin.content import OVERLAY_TYPES, builtin_body, builtin_keys, builtin_name

    services = admin_of(request)
    if content_type in OVERLAY_TYPES:
        return {"content_type": content_type,
                "sources": [{"slug": slug, "name": builtin_name(content_type, slug), "builtin": builtin_body(content_type, slug)}
                            for slug in sorted(builtin_keys(content_type))]}
    if content_type == "resident":
        return {"content_type": content_type,
                "sources": [{"slug": row["candidate_id"], "name": f"{row['name']}（{L.SPECIES.get(row['species'], row['species'])}）",
                              "identity": {"name": row["name"], "species": row["species"]},
                             "builtin": {"personality": row["personality"], "dream": row["dream"],
                                         "source_note": row["source_note"]}}
                            for row in services.content.resident_candidates()]}
    return {"content_type": content_type, "sources": []}


@router.get("/content/{item_id}")
def content_detail(item_id: str, request: Request,
                   principal: AdminPrincipal = Depends(needs(Permission.CONTENT_READ))) -> dict:
    services = admin_of(request)
    item = services.content.item(item_id)
    if item is None:
        raise AdminAPIError.not_found("这条内容")
    revisions = services.content.revisions(item_id)
    latest = revisions[0]["body"] if revisions else {}
    return {"item": asdict(item), "revisions": revisions, "publications": services.content.publications(item_id),
            "validation": [asdict(i) for i in validate(item.content_type, latest)],
            "live_body": services.content.revision_body(item_id, item.live_revision) if item.live_revision else None}


@router.post("/content/validate")
def validate_body(body: ContentDraftRequest, request: Request,
                  principal: AdminPrincipal = Depends(needs(Permission.CONTENT_EDIT))) -> dict:
    issues = validate(body.content_type, body.body)
    return {"ok": not issues, "issues": [asdict(i) for i in issues]}


@router.post("/content", status_code=201)
def create_content(body: ContentDraftRequest, request: Request,
                   principal: AdminPrincipal = Depends(needs(Permission.CONTENT_EDIT, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    item = services.content.create(content_type=body.content_type, slug=body.slug, title=body.title, body=body.body,
                                   actor=principal.staff.staff_id, note=body.note)
    services.audit.record(status="succeeded", outcome="draft:v1",
                          changes={"content_type": body.content_type, "slug": body.slug},
                          **_audit_kwargs(ctx, "content.create", Permission.CONTENT_EDIT, item.item_id, body.note or "新建草稿"))
    return {"item": asdict(item), "issues": [asdict(i) for i in validate(body.content_type, body.body)]}


@router.put("/content/{item_id}")
def save_draft(item_id: str, body: ContentSaveRequest, request: Request,
               principal: AdminPrincipal = Depends(needs(Permission.CONTENT_EDIT, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    item = services.content.save_draft(item_id, body=body.body, actor=principal.staff.staff_id,
                                       expected_version=body.expected_version, note=body.note)
    services.audit.record(status="succeeded", outcome=f"draft:v{item.draft_revision}",
                          changes={"draft_revision": item.draft_revision},
                          **_audit_kwargs(ctx, "content.save_draft", Permission.CONTENT_EDIT, item_id, body.note or "保存草稿"))
    return {"item": asdict(item), "issues": [asdict(i) for i in validate(item.content_type, body.body)]}


@router.get("/content/{item_id}/preview")
def preview(item_id: str, request: Request, revision: int | None = None,
            principal: AdminPrincipal = Depends(needs(Permission.CONTENT_READ))) -> dict:
    """预览＝按玩家侧真正会读到的形态渲染这一版。校验不过时同时给出问题清单。"""
    services = admin_of(request)
    item = services.content.item(item_id)
    if item is None:
        raise AdminAPIError.not_found("这条内容")
    target = revision or item.draft_revision or item.live_revision
    body = services.content.revision_body(item_id, target) if target else None
    if body is None:
        raise AdminAPIError.not_found(f"版本 v{target}")
    issues = [asdict(i) for i in validate(item.content_type, body)]
    consumer_api = None  # 玩家侧读取它的接口路径（技术细节；界面只在「显示技术代码」时显示）
    if item.content_type == "announcement":
        rendered = {"title": body.get("title", ""), "body": body.get("body", ""), "severity": body.get("severity", "info"),
                    "link": body.get("link"), "audience": body.get("audience", "all"),
                    "consumer": "玩家端通讯器页顶部的公告细条，以及「全部公告」页"}
        consumer_api = "GET /api/v1/web/announcements"
    elif item.content_type == "adventure":
        from ...web_journey.adventures import AdventureTemplate, render_story

        template = AdventureTemplate(key=item.slug, title=body.get("title", ""), badge=body.get("badge", ""),
                                     story=body.get("story", ""))
        try:
            sample = render_story(template, "小满", "蓝色的毯子")
        except (KeyError, IndexError, ValueError) as exc:
            sample = None
            issues.append({"field": "story", "message": f"按世界引擎的方式渲染会出错：{type(exc).__name__}。"})
        rendered = {"title": template.title, "badge": template.badge, "story_template": template.story,
                    "sample_render": sample, "sample_note": "示例用宠物名『小满』与物件『蓝色的毯子』；真实渲染用当事宠物。",
                    "consumer": "世界引擎在新冒险事件发生时取模板"}
    elif item.content_type == "crop":
        from ...web_farm.service import CROPS

        base = CROPS.base_of(item.slug)
        grow = body.get("grow_seconds", base.grow_seconds)
        rendered = {"label": body.get("label", base.label), "unit_value": body.get("unit_value", base.unit_value),
                    "grow_seconds": grow, "grow_readable": f"{grow // 60} 分 {grow % 60} 秒",
                    "yield_units": f"{base.yield_units}（不可发布，保持内置值）",
                    "steal_total": f"{base.steal_total}（不可发布，保持内置值）",
                    "shop_line": f"杂货铺按每单位 {body.get('unit_value', base.unit_value)} 星币收购",
                    "consumer": "菜园地块、仓库、杂货铺与居民订单"}
    elif item.content_type == "job":
        from ...web_journey.local import JOBS

        base = JOBS.base_of(item.slug)
        pay = body.get("pay", base.pay)
        hours = body.get("hours", base.hours)
        rendered = {"label": body.get("label", base.label), "pay": pay, "hours": hours,
                    "worked_line": f"{body.get('label', base.label)}，干了 {hours} 小时，工钱 {pay} 星币",
                    "consumer": "打工结束那一刻按当时发布的工钱结算；已经结算的工资不变"}
    elif item.content_type == "destination":
        from ...web_journey.catalog import DESTINATIONS

        base = DESTINATIONS.base_of(item.slug)
        rendered = {"title": body.get("title", base.title), "city": body.get("city", base.city),
                    "summary": body.get("summary", base.summary), "fee": body.get("fee", base.fee),
                    "total_minutes": f"{base.total_minutes}（不可发布：由各段时长算出）",
                    "modes": "、".join(L.TRANSPORT_MODE.get(mode, mode) for mode in base.modes) + "（不可发布）",
                    "venue": f"{base.venue.name}（不可发布：场所身份是事实）",
                    "consumer": "出发站的地点列表；已经出发的行程按出发时的那一版"}
        consumer_api = "/journey/destinations"
    else:  # resident
        candidate = next((row for row in services.content.resident_candidates(only_available=False)
                          if row["candidate_id"] == item.slug), None)
        # 是谁：写成一句人话（物种、能不能领养都换成说法），不给界面一个对象
        identity = (f"{candidate['name']}（{L.SPECIES.get(candidate['species'], candidate['species'])}，"
                    f"{L.ADOPTION_AVAILABILITY.get(candidate['availability'], candidate['availability'])}）") if candidate else None
        if candidate is not None and candidate["availability"] != "available":
            state = L.ADOPTION_AVAILABILITY.get(candidate["availability"], candidate["availability"])
            issues.append({"field": "slug", "message": f"这位居民现在是「{state}」，发布会被跳过（身份与经历必须连续）。"})
        rendered = {"identity": identity, "personality": body.get("personality", ""), "dream": body.get("dream", ""),
                    "source_note": body.get("source_note"),
                    "identity_note": "名字与物种属于身份，运营改不了；这里只是让你看清在给谁改文案。",
                    "consumer": "访客公开页与领养页"}
        consumer_api = "/adoption/candidates"
    return {"item": asdict(item), "revision": target, "body": body, "rendered": rendered,
            "consumer_api": consumer_api, "issues": issues, "publishable": not issues}


@router.post("/content/{item_id}/publish")
def publish(item_id: str, body: ContentPublishRequest, request: Request,
            principal: AdminPrincipal = Depends(needs(Permission.CONTENT_PUBLISH, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    kwargs = _audit_kwargs(ctx, "content.publish", Permission.CONTENT_PUBLISH, item_id, body.reason)

    def handler() -> dict:
        try:
            result = services.content.publish(item_id, revision=body.revision, reason=body.reason, actor=principal.staff.staff_id,
                                              operation_id=ctx.operation_id, expected_version=body.expected_version,
                                              effective_at=body.effective_at, expires_at=body.expires_at,
                                              audit=services.audit, audit_kwargs=kwargs)
        except AdminAPIError as exc:
            # 被拒绝的发布要留痕；发布事务整笔回滚了，里面那条审计也跟着回滚，所以在事务外补记。
            services.audit.record(status="denied", outcome=exc.code.value,
                                  changes={"revision": body.revision, "details": exc.details}, **kwargs)
            raise
        return {**result, "note": "玩家侧从这一刻起读到的是这一版；之前已经发生的事实不变。"}

    return services.commands.run(ctx, "content.publish",
                                 {"item_id": item_id, "revision": body.revision, "reason": body.reason,
                                  "expected_version": body.expected_version}, handler)


@router.post("/content/{item_id}/withdraw")
def withdraw(item_id: str, body: ContentWithdrawRequest, request: Request,
             principal: AdminPrincipal = Depends(needs(Permission.CONTENT_PUBLISH, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    return services.commands.run(
        ctx, "content.withdraw", {"item_id": item_id, "reason": body.reason, "expected_version": body.expected_version},
        lambda: services.content.withdraw(item_id, reason=body.reason, actor=principal.staff.staff_id,
                                          operation_id=ctx.operation_id, expected_version=body.expected_version,
                                          audit=services.audit,
                                          audit_kwargs=_audit_kwargs(ctx, "content.withdraw", Permission.CONTENT_PUBLISH, item_id, body.reason)))


@router.post("/content/{item_id}/rollback")
def rollback(item_id: str, body: ContentRollbackRequest, request: Request,
             principal: AdminPrincipal = Depends(needs(Permission.CONTENT_PUBLISH, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    return services.commands.run(
        ctx, "content.rollback",
        {"item_id": item_id, "to_revision": body.to_revision, "reason": body.reason, "expected_version": body.expected_version},
        lambda: services.content.rollback(item_id, to_revision=body.to_revision, reason=body.reason,
                                          actor=principal.staff.staff_id, operation_id=ctx.operation_id,
                                          expected_version=body.expected_version, audit=services.audit,
                                          audit_kwargs=_audit_kwargs(ctx, "content.rollback", Permission.CONTENT_PUBLISH, item_id, body.reason)))


@router.get("/content-live/announcements")
def live_announcements(request: Request,
                       principal: AdminPrincipal = Depends(needs(Permission.CONTENT_READ))) -> dict:
    """后台自查：玩家端此刻真正会读到什么。与玩家 API 走同一个函数，不是另算一遍。"""
    services = admin_of(request)
    return {"anonymous": services.content.live_announcements(signed_in=False),
            "signed_in": services.content.live_announcements(signed_in=True),
            "consumer": "GET /api/v1/web/announcements"}
