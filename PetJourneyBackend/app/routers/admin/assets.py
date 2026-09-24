"""素材库：上传（只接受员工本机的文件）、列表、取文件、下架。

**没有"给个 URL 让服务器去抓"的入口，也没有"给个服务器路径"的入口。**
那两种做法一旦存在，玩家参考照目录就只隔着一个字符串；素材只能从员工自己的机器上传上来。
"""

from __future__ import annotations

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from ...schemas.admin import AssetRetireRequest
from ...web_admin.assets import MAX_PIXELS, SOURCES, USAGE_SCOPES
from ...web_admin.errors import AdminAPIError, AdminErrorCode
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs

router = admin_router("assets")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("/assets")
def list_assets(request: Request, usage_scope: str | None = None, include_retired: bool = False, limit: int = 100,
                principal: AdminPrincipal = Depends(needs(Permission.ASSET_READ))) -> dict:
    services = admin_of(request)
    return {
        "assets": services.assets.list_assets(usage_scope=usage_scope, include_retired=include_retired, limit=limit),
        "sources": list(SOURCES),
        "usage_scopes": list(USAGE_SCOPES),
        "rules": [
            "只接受员工本机上传的 JPEG / PNG / WebP，不超过 5MB；服务器不会去抓任何 URL。",
            "入库前会比对它是不是某位玩家上传的宠物参考照（按图片内容比），是就拒绝——参考照属于主人，运营不能把它变成公共素材。",
            "来源与使用范围必填：说不清这张图哪来的、能用在哪，就不入库。",
            f"像素太多的图不收（上限约 {MAX_PIXELS // 10000:,} 万像素），防止一张图把服务器撑爆。",
        ],
    }


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: str, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.ASSET_READ))) -> dict:
    from ...web_admin.assets import _as_dict

    return {"asset": _as_dict(admin_of(request).assets.get(asset_id))}


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str, request: Request, thumb: bool = False,
               principal: AdminPrincipal = Depends(needs(Permission.ASSET_READ))) -> FileResponse:
    found = admin_of(request).assets.file_path(asset_id, thumb=thumb)
    if found is None:
        raise AdminAPIError.not_found("这个素材文件")
    path, content_type = found
    return FileResponse(path, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.post("/assets", status_code=201)
async def upload_asset(request: Request,
                       file: UploadFile = File(...),
                       source: str = Form(...),
                       source_note: str = Form(...),
                       usage_scope: str = Form(...),
                       license_note: str | None = Form(default=None),
                       principal: AdminPrincipal = Depends(needs(Permission.ASSET_MANAGE, write=True))) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AdminAPIError(AdminErrorCode.validation_failed, "素材文件不能超过 5MB。", 422, details={"field": "file"})
    services = admin_of(request)
    return services.assets.upload(context(request, principal), filename=file.filename or "upload", data=data,
                                  source=source, source_note=source_note, license_note=license_note,
                                  usage_scope=usage_scope)


@router.post("/assets/{asset_id}/retire")
def retire_asset(asset_id: str, body: AssetRetireRequest, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.ASSET_MANAGE, write=True))) -> dict:
    services = admin_of(request)
    return services.assets.retire(context(request, principal), asset_id, reason=body.reason,
                                  expected_version=body.expected_version)
