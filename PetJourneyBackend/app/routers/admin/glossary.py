"""把代码说成人话需要的两份小数据：词表与员工名字（方案 §5：不把原始代码当日常界面）。

两个接口都只要求已登录的员工（`signed_in`），不要求具体权限——它们不含任何玩家数据：
- `/labels`：`app/web_admin/labels.py` 的静态词表；
- `/staff/names`：员工号 → 用户名与显示名（账本的操作者、批次的提交人这些地方显示名字，不显示员工号）。
  只给名字与是否停用，不给角色、权限、登录时间——那些仍然只在「员工与角色」页，要 staff.manage。
两个接口都不写访问审计：读的不是个人数据，写审计只会把真正的访问记录淹没。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...web_admin import labels as L
from ...web_admin.identity import AdminPrincipal
from ._shared import admin_of, admin_router, signed_in

router = admin_router("glossary")


@router.get("/labels")
def labels(principal: AdminPrincipal = Depends(signed_in)) -> dict:
    return {"families": L.FAMILIES,
            "silence_hints": {code: hint for code, (_, hint) in L.SILENCE.items()},
            "note": "没收录的代码界面会照原样显示并标「未收录」；词表与领域里的枚举由用例双向核对。"}


@router.get("/staff/names")
def staff_names(request: Request, principal: AdminPrincipal = Depends(signed_in)) -> dict:
    with admin_of(request).identity.storage.connect() as conn:
        rows = conn.execute("SELECT staff_id, username, display_name, status FROM admin_staff ORDER BY username").fetchall()
    return {"staff": {row["staff_id"]: {"username": row["username"], "display_name": row["display_name"],
                                         "disabled": row["status"] != "active"} for row in rows},
            # 旧版经济引擎（economy_engine，旧接口）写的操作人：不是本后台的员工，也不是新版玩家流程
            "operators": {"web": "玩家那一侧自己产生（不是员工操作）",
                          "pet": "旧版接口：宠物自己", "owner": "旧版接口：主人", "admin": "旧版接口的管理口令（不是本后台的员工）"}}
