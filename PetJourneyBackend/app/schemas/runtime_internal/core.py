"""基础类型：时钟、语义版本、主活动引用、受众范围。只用标准库。"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

ActivityKind = Literal["not_activated", "at_home", "local_activity", "work", "travel", "visit", "exam", "unknown"]
AudienceKind = Literal["household", "private", "public"]


@runtime_checkable
class Clock(Protocol):
    """生产用真实时钟，测试注入假时钟。策略函数显式接收 now，不在函数深处取宿主机本地时间。"""

    def now_utc(self) -> datetime:
        """带时区的 UTC 时刻；持久化与业务比较只用它。"""
        ...

    def monotonic(self) -> float:
        """只用于进程内持续时间（超时、耗时），不写库、不跨进程比较。"""
        ...


@dataclass(frozen=True, slots=True)
class Versions:
    """一次读取时的语义版本戳，全部来自可信存储（由集成者投影，不由调用方自报）。

    提交前用 stale_fields 与最新版本比较，变了的字段说明哪类前提已经失效。
    地图进度、剩余分钟这类连续变化不递增任何版本。
    """

    runtime_epoch: int  # 每宠运行归属代数：切换推进者、失效旧任务时递增
    activity_epoch: int  # 主活动变化（出门、到站、开工、收工、回家）时递增
    dna_version: int  # 共用 DNA 版本（web_pet_dna.version）
    privacy_epoch: int  # 用途授权变化、记忆撤回或删除时递增
    membership_epoch: int  # 家庭成员加入、角色变化、移除时递增；没有家庭的居民固定为 0
    itinerary_version: int | None = None  # 当前行程计划版本（改签、重规划时递增）；没有行程为 None

    def stale_fields(self, current: Versions) -> tuple[str, ...]:
        """与最新版本相比已经变了的字段名。self.itinerary_version 为 None 时不比较行程。"""
        changed = []
        for item in fields(self):
            mine = getattr(self, item.name)
            if item.name == "itinerary_version" and mine is None:
                continue
            if getattr(current, item.name) != mine:
                changed.append(item.name)
        return tuple(changed)


@dataclass(frozen=True, slots=True)
class ActivityRef:
    """当前主活动：引用已有领域记录（旅程、交通段、到访、工作、考试），不另建位置表。"""

    kind: ActivityKind
    ref: str | None  # 例如 "journey:jn-…"、"leg:jn-…:3"、"visit:…"、"home:…"；在家空闲可为 None
    started_at: datetime | None = None
    ends_at: datetime | None = None  # 有明确结束边界的活动（交通段、打工、到访）才有
    interruptible: bool = True  # 家人建议或新决策能否打断：在船上、正式考试中为 False


@dataclass(frozen=True, slots=True)
class AudienceScope:
    """可见或授权范围。

    household：全家（需要 household_id）；private：某位家人与这只宠物（需要 user_id）；public：访客可见。
    没有家庭的待领养居民，生活规划用 public。缺少必要的编号直接报错，不能默认为有权限。
    """

    kind: AudienceKind
    household_id: str | None = None
    user_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "household" and not self.household_id:
            raise ValueError("household 受众必须带 household_id")
        if self.kind == "private" and not self.user_id:
            raise ValueError("private 受众必须带 user_id")
