"""运行状态（给运维与联调的人看，0.4.0）：环境、数据在哪、供应商“已配置 / 真的调通过”、世界任务在不在跑、能力、前端怎么连。

只在本机访问或带管理令牌时返回；不含任何密钥、用户数据或请求正文。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import Capability, WebModel


class ProviderState(str, Enum):
    disabled = "disabled"  # 总开关关闭（默认：测试与演示不产生付费调用）
    not_configured = "not_configured"  # 总开关开了但没有密钥
    configured = "configured"  # 有配置，但还没有成功调用过
    verified = "verified"  # 最近真的调通过
    failing = "failing"  # 最近一次调用失败（且之后没有成功过）


class ProviderHealth(WebModel):
    provider: str = Field(description="llm / amap / amap_static / google / image")
    label: str
    state: ProviderState
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = Field(default=None, description="脱敏后的错误摘要")
    calls_today: int = 0
    daily_cap: int | None = None


class WorldRunnerStatus(WebModel):
    runner: str = Field(description="embedded（API 进程内）/ worker（独立任务进程）/ off")
    interval_seconds: float
    running_here: bool = Field(description="这个 API 进程里的世界线程是否在跑")
    lease_alive: bool = Field(description="有没有进程持有有效租约（正在推进世界）")
    lease_holder_role: str | None = None
    lease_pid: int | None = None
    last_tick_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None
    ticks: int = 0
    due_lag_seconds: int | None = Field(default=None, description="最老一件已到期但还没登记的世界事实等了多少秒；持续变大说明这条线卡住了（0.4.1）",
                                        json_schema_extra={"x-additive": True})


class OutboxHealth(WebModel):
    consumer: str = Field(description="世界事件下游：communicator / social / collection / credentials / guides / friends")
    pending: int = 0
    delivered: int = 0
    dead_letter: int = Field(default=0, description="重试用尽、需要人看的条数")
    oldest_pending_seconds: int | None = Field(default=None, description="最老一条待投递等了多少秒；持续变大说明这个下游卡住了")


class RuntimeDueItem(WebModel):
    ref: str = Field(description="到期事项的引用，例如 journey:<旅程编号>、reply:<会话>；不含正文")
    kind: str = Field(description="journey / reply / cooldown / other")
    due_at: datetime
    commitment: bool = Field(default=False, description="对家人的承诺（工钱、待回复）：不能被延期或丢弃")


class PetRuntimeStatus(WebModel):
    """一只宠物此刻的运行详情（只给本机或管理令牌）：用来回答“TA 为什么这么安静”。

    不含私聊正文、DNA 原文、提示词或密钥；只有引用、时间与状态码。
    """

    pet_id: str
    as_of: datetime
    realm_id: str
    household_id: str | None = None
    timezone: str | None = Field(default=None, description="TA 此刻所在地的时区；认不出就是空，运行层会明确报不可用，不套用默认城市")
    region_id: str | None = None
    scene_ref: str | None = Field(default=None, description="家园 / 驿站 / 店铺 / 交通段的引用")
    activity_kind: str
    activity_ref: str | None = None
    activity_ends_at: datetime | None = None
    interruptible: bool = True
    sleep_window: list[str] = Field(default_factory=list, description="当地作息（入睡, 起床），来自 DNA 画像；未知为空")
    versions: dict[str, int | None] = Field(default_factory=dict, description="语义版本代数：思考开始时记下，提交时再比一次")
    due_items: list[RuntimeDueItem] = Field(default_factory=list)
    next_check_at: datetime | None = None
    next_review_at: datetime | None = Field(
        default=None,
        description="上一次决定时写下的「到这个时刻再重新考虑」。与 next_check_at 不是一回事："
                    "next_check_at 是**此刻**按当前事实算出来的下次查看时间，next_review_at 是**当时那次决定**留下的有效期"
                    "（例如「先留在家，两小时后再看」）。两者都可能为空。")
    silence_reason: str | None = Field(default=None, description="安静的原因：正常生活 / 暂无新决策 / 额度延期 / 依赖不可用 / 任务卡住 / 维护")
    last_evaluated_at: datetime | None = None
    last_decision_at: datetime | None = None
    last_decision_by: str | None = Field(default=None, description="model / rule_fallback / rule")
    maintenance: bool = False
    heartbeat_action: str | None = Field(default=None, description="按当前事实立刻评估一次心跳的结论（只读，不执行）")
    heartbeat_reasons: list[str] = Field(default_factory=list)
    cognition_enabled: bool = Field(default=False, description="这只宠物的家庭是否同意把共用资料交给模型")
    brain_mode: str = Field(description="off / shadow / live")


class FrontendHint(WebModel):
    data_mode: str = Field(description="前端应使用的数据模式：live 只走本后端；fixture 是演示数据，不连后端")
    api_base: str
    dev_proxy_target: str = Field(description="vite dev/preview 的代理目标（PETSOUL_DEV_API_TARGET）")
    note: str


class OpsStatus(WebModel):
    environment: str = Field(description="dev / demo / real-local / staging / production（只是标签，不改变行为）")
    server_time: datetime
    backend_version: str
    database: str = Field(description="正在使用的数据库文件（相对后端目录；目录外时为绝对路径）")
    media_dir: str
    sqlite_wal: bool
    providers_enabled: bool
    providers: list[ProviderHealth]
    world: WorldRunnerStatus
    cognition: WorldRunnerStatus | None = Field(default=None, description="认知线（可能调模型的表达与回复）：与世界线分开的线程和租约，卡住不影响到期结算（0.4.1）",
                                                json_schema_extra={"x-additive": True})
    applied_migrations: int
    last_migration: str | None = None
    capabilities: list[Capability]
    frontend: FrontendHint
    tasks: dict[str, int] = Field(default_factory=dict, description="后台任务：到期未领、领取中、租期已过仍在跑、用完次数、最老到期等待秒数（0.4.1）",
                                  json_schema_extra={"x-additive": True})
    outbox: list[OutboxHealth] = Field(default_factory=list, description="世界事件各下游的投递情况（0.4.1）", json_schema_extra={"x-additive": True})


__all__ = ["ProviderState", "ProviderHealth", "WorldRunnerStatus", "OutboxHealth", "RuntimeDueItem", "PetRuntimeStatus", "FrontendHint", "OpsStatus"]
