"""撤下 / 放回待领养居民（用户 2026-09-25 交给运营后台做；方案第九批与 I 对过，I 补了两处加强）。

撤下＝不再出现在领养卡、访客页，玩家也领养不了 TA；TA 照常在驿站生活（不暂停、不删除，身份与经历不变）。放回＝恢复。
- 领域上的写入口只有 `PetsService.set_listed_in`（领养卡表的上架列，迁移 0260）。本模块在**同一个事务**里调它、
  记下后台依据（`admin_resident_listing`，迁移 1590）、写审计。
- 只对还可以领养的居民生效：已被领养或正在领养的不符合条件（身份与经历必须连续），如实拒绝；本来就是这个状态也如实拒绝，不写一条假的变更。
- 原因必填；按版本拒绝并发；同一操作号重放不重复生效（AdminCommands.run）。访客页缓存由路由在成功后当场清掉。
"""

from __future__ import annotations

from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, utcnow
from ..web_platform.uow import unit_of_work
from .commands import ActorContext, require_reason
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission

# 撤下 / 放回对话框里「会发生什么」：只写核过的影响（居民名单接口一并返回，界面照抄，单一来源）
DELIST_EFFECTS = (
    "TA 不再出现在领养页的领养卡和访客页的居民名单上，玩家领养不了 TA；已经打开领养卡的玩家点领养会看到「找不到这位伙伴」。",
    "TA 照常在驿站生活：不暂停自主运行、不删除，身份、性格与公开经历都不变（要让 TA 别动，用「暂停」）。",
    "访客页当场更新，不等缓存过期。",
    "随时可以放回；放回后 TA 重新出现在领养卡和访客页。",
)
RELIST_EFFECTS = (
    "TA 重新出现在领养页的领养卡和访客页的居民名单上，玩家可以领养 TA。",
    "访客页当场更新，不等缓存过期。",
)


class AdminResidentListing:
    def __init__(self, storage: JourneyStorage, commands, audit, pets) -> None:
        self.storage = storage
        self.commands = commands
        self.audit = audit
        self.pets = pets  # 领域服务（web_pets.PetsService）：只用它的 set_listed_in

    def set_listed(self, ctx: ActorContext, candidate_id: str, *, listed: bool, reason: str, expected_version: int | None) -> dict[str, Any]:
        reason = require_reason(reason)
        action = "resident.relist" if listed else "resident.delist"

        def handler() -> dict:
            now = utcnow()
            with unit_of_work(self.storage) as conn:
                record = conn.execute("SELECT version FROM admin_resident_listing WHERE candidate_id = ?", (candidate_id,)).fetchone()
                version = int(record["version"]) if record else 0
                if expected_version is not None and expected_version != version:
                    raise AdminAPIError.version_conflict(expected_version, version)
                outcome = self.pets.set_listed_in(conn, candidate_id, listed)
                if outcome == "missing":
                    raise AdminAPIError.not_found("这位待领养居民")
                if outcome == "not_eligible":
                    raise AdminAPIError(AdminErrorCode.conflict, "这位居民已被领养或正在领养：身份与经历必须连续，不能撤下或放回。", 409,
                                        details={"candidate_id": candidate_id})
                if outcome == "unchanged":
                    raise AdminAPIError(AdminErrorCode.conflict, "TA 已经在领养名单上了。" if listed else "TA 已经撤下了。", 409,
                                        details={"candidate_id": candidate_id, "listed": listed})
                conn.execute(
                    "INSERT INTO admin_resident_listing (candidate_id, listed, reason, changed_by, changed_at, version) VALUES (?, ?, ?, ?, ?, 1) "
                    "ON CONFLICT(candidate_id) DO UPDATE SET listed = excluded.listed, reason = excluded.reason, "
                    "changed_by = excluded.changed_by, changed_at = excluded.changed_at, version = admin_resident_listing.version + 1",
                    (candidate_id, 1 if listed else 0, reason, ctx.staff_id, iso(now)))
                new_version = int(conn.execute("SELECT version FROM admin_resident_listing WHERE candidate_id = ?",
                                               (candidate_id,)).fetchone()["version"])
                self.audit.record_in(conn, status="succeeded", outcome="listed" if listed else "delisted",
                                     changes={"from": "delisted" if listed else "listed", "to": "listed" if listed else "delisted",
                                              "version": new_version},
                                     action=action, permission=Permission.RESIDENT_MANAGE.value, actor_staff_id=ctx.staff_id,
                                     actor_username=ctx.username, target_kind="candidate", target_id=candidate_id, reason=reason,
                                     operation_id=ctx.operation_id, request_id=ctx.request_id)
            return {"candidate_id": candidate_id, "listed": listed, "version": new_version,
                    "note": ("已放回：TA 重新出现在领养卡和访客页，玩家可以领养。" if listed
                             else "已撤下：TA 不再出现在领养卡和访客页，玩家领养不了；TA 照常在驿站生活，随时可以放回。")}

        return self.commands.run(ctx, action, {"candidate_id": candidate_id, "listed": listed, "reason": reason,
                                               "expected_version": expected_version}, handler)
