"""员工权限：动作级权限 + 角色（一组权限）。服务端默认拒绝，逐请求核查。

两条底线写在类型里，不靠约定：
- 玩家会话与员工会话是两套 cookie、两张表、两条解析路径。玩家身份（含家庭管理员）在这里**没有任何映射**，
  所以"普通玩家 / 家庭 admin 拿到平台权限"不是靠检查挡住的，而是根本不存在那条路径；
- `PRIVATE_READ` 不属于任何默认角色。要看私聊/叮嘱原文、下载参考图，必须由平台负责人单独授权，
  本批**没有任何角色带它**，相关字段一律脱敏。
"""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    # 只读
    OPS_READ = "ops.read"                  # 运行首页、环境与版本
    USER_READ = "user.read"                # 用户 / 家庭搜索与详情（脱敏）
    PET_READ = "pet.read"                  # 宠物诊断
    TASK_READ = "task.read"                # 任务 / 照片详情
    PROVIDER_READ = "provider.read"        # 供应商调用与用量
    ECONOMY_READ = "economy.read"          # 游戏币流水
    REPORT_READ = "report.read"            # 举报队列
    CONTENT_READ = "content.read"          # 内容草稿与发布历史
    ASSET_READ = "asset.read"              # 素材库（含内部素材）
    AUDIT_READ = "audit.read"              # 审计查询
    PRIVATE_READ = "private.read"          # 私密正文 / 参考图（默认不给任何角色）

    # 写
    ACCOUNT_FREEZE = "account.freeze"      # 冻结 / 解冻玩家账号
    ACCOUNT_REVOKE_SESSION = "account.revoke_session"
    REPORT_ACTION = "report.action"        # 公开内容下架 / 恢复 / 不处理
    PROVIDER_PAUSE = "provider.pause"      # 暂停 / 恢复新增 AI 调用
    TASK_RECOVER = "task.recover"          # 条件内的失败任务恢复
    PET_MAINTAIN = "pet.maintain"          # 暂停 / 恢复一只宠物的自主运行（写运行表的维护列）；默认给运维
    CONTENT_EDIT = "content.edit"          # 草稿与校验
    CONTENT_PUBLISH = "content.publish"    # 发布 / 撤下 / 回退
    ASSET_MANAGE = "asset.manage"          # 上传 / 下架素材（玩家参考照永远进不来）
    ECONOMY_GRANT = "economy.grant"        # 单笔游戏补偿（只动游戏账本）
    ECONOMY_GRANT_BATCH = "economy.grant_batch"  # 提交与执行批量补偿（与单笔分开发）
    ECONOMY_APPROVE = "economy.approve"    # 审批批量补偿；提交人不能自批
    ECONOMY_REVERSE = "economy.reverse"    # 冲正一笔后台补偿（整笔、一次、不能冲自己发的）；默认给经济负责人
    COST_MANAGE = "cost.manage"            # 维护供应商价格表（只追加：录新价 / 作废录错的）；默认只随平台负责人
    STAFF_MANAGE = "staff.manage"          # 员工与角色


class Role(str, Enum):
    platform_owner = "platform_owner"
    support = "support"
    moderator = "moderator"
    content_editor = "content_editor"
    content_publisher = "content_publisher"
    economy_ops = "economy_ops"
    economy_lead = "economy_lead"
    sre = "sre"
    auditor = "auditor"


P = Permission

_READ_BASICS = {P.OPS_READ, P.USER_READ, P.PET_READ}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.platform_owner: frozenset(
        set(Permission) - {P.PRIVATE_READ}  # 负责人也不默认带私密正文权限；它要单独授予
    ),
    Role.support: frozenset(_READ_BASICS | {P.TASK_READ, P.ECONOMY_READ, P.AUDIT_READ, P.ACCOUNT_FREEZE, P.ACCOUNT_REVOKE_SESSION}),
    Role.moderator: frozenset({P.USER_READ, P.REPORT_READ, P.AUDIT_READ, P.REPORT_ACTION}),
    Role.content_editor: frozenset({P.OPS_READ, P.CONTENT_READ, P.CONTENT_EDIT, P.ASSET_READ, P.ASSET_MANAGE}),
    Role.content_publisher: frozenset({P.OPS_READ, P.CONTENT_READ, P.CONTENT_EDIT, P.CONTENT_PUBLISH,
                                       P.ASSET_READ, P.ASSET_MANAGE}),
    # 经济运营：能发单笔、能提交批量，但**批不了**自己提的批次（没有 approve 权限）。
    Role.economy_ops: frozenset({P.OPS_READ, P.USER_READ, P.PET_READ, P.ECONOMY_READ, P.ECONOMY_GRANT,
                                 P.ECONOMY_GRANT_BATCH, P.AUDIT_READ}),
    # 经济负责人：只审批，不提交。双人原则靠"两条权限分开发"+"不能自批"两道一起保证。
    # 冲正也给负责人：发补偿的人（经济运营）冲不了，冲正的人发不了——双人原则落在权限分配上，另有「不能冲自己发的」兜底。
    # pet.read：决定冲不冲正，要能打开这只宠物的账本看前因后果（只读，不含私密内容）。
    Role.economy_lead: frozenset({P.OPS_READ, P.USER_READ, P.PET_READ, P.ECONOMY_READ, P.ECONOMY_APPROVE, P.ECONOMY_REVERSE,
                                  P.AUDIT_READ}),
    Role.sre: frozenset(_READ_BASICS | {P.TASK_READ, P.PROVIDER_READ, P.AUDIT_READ, P.PROVIDER_PAUSE, P.TASK_RECOVER, P.PET_MAINTAIN}),
    Role.auditor: frozenset(
        {P.OPS_READ, P.USER_READ, P.PET_READ, P.TASK_READ, P.PROVIDER_READ, P.ECONOMY_READ, P.REPORT_READ,
         P.CONTENT_READ, P.ASSET_READ, P.AUDIT_READ}
    ),
}

# 写权限清单：给"影响预览"和审计用，也用于在界面上把只读角色的按钮如实标成不可用。
WRITE_PERMISSIONS = frozenset(
    {P.ACCOUNT_FREEZE, P.ACCOUNT_REVOKE_SESSION, P.REPORT_ACTION, P.PROVIDER_PAUSE, P.TASK_RECOVER, P.PET_MAINTAIN,
     P.CONTENT_EDIT, P.CONTENT_PUBLISH, P.ASSET_MANAGE, P.ECONOMY_GRANT, P.ECONOMY_GRANT_BATCH,
     P.ECONOMY_APPROVE, P.ECONOMY_REVERSE, P.COST_MANAGE, P.STAFF_MANAGE}
)


def permissions_for(roles) -> frozenset[Permission]:
    """把角色展开成权限集合。无法识别的角色名直接忽略（不放行，也不让整个会话失败）。"""
    granted: set[Permission] = set()
    for name in roles:
        try:
            role = Role(name)
        except ValueError:
            continue
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)


def role_catalog() -> list[dict]:
    return [
        {"role": role.value, "permissions": sorted(permission.value for permission in perms)}
        for role, perms in ROLE_PERMISSIONS.items()
    ]
