"""Transport 服务边界（R0 只定义接口；实现由用户分配的交通模块窗口完成）。

实现要求（见 TRANSPORT-COMPANION-SYSTEM.md §3–§6、§11）：
- TransportReference（现实参考）与 WorldService（喵航 Cat222 等原创身份）分表，映射有唯一约束
  与 mapping_version；同一运营实例的不同宠物共用同一 WorldService；
- 首版 verified_timetable：确认行程时保存所选版本；无法核实不编班次，暂停确认或给估算选项；
- 门到门 JourneyLeg：接驳/候乘/登乘/主交通/出站；下一站冲突用 ``timeline.schedule_after_leg`` 顺延；
- 读取快照不隐式发起付费查询、不产生新班次、不重置会话；真实查询走 ``WebTaskQueue``；
- 抵达事件幂等且优先于媒体控制；到站 ≠ 归家；
- 迁移编号区间 0700–0799。
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.web.transport import JourneyLeg, JourneyMapSnapshot, PetArrivalContext


class TransportService(Protocol):
    def journey_map(self, user_id: str, pet_id: str) -> JourneyMapSnapshot: ...

    def leg(self, user_id: str, leg_id: str) -> JourneyLeg: ...

    def arrival_context(self, user_id: str, pet_id: str) -> PetArrivalContext | None:
        """供 FoodDiscovery 消费：门到门可行到达、停留窗口、行程版本。"""
        ...
