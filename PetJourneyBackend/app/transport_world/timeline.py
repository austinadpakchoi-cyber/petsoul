"""交通时间线纯函数：服务器时间决定进度；交通时长不因下一站或媒体而压缩。

旧代码差异（只读记录，本包不修改旧引擎）：
- ``world_simulation/timeline.py`` 的 move_end 取“下一站开始”与“按时长计算”中较早者，会压短交通；
  新时间线用 ``schedule_after_leg`` 顺延后续活动；
- ``transport_reality/mock.py::_candidate_endpoint`` 在起终点间按比例插值中转坐标——
  这类节点必须 ``TransportNode.verified=False`` 并以 ``PositionBasis.schematic`` 呈现；
- ``transport_schedule/openai_provider.py`` 名称含 WebSearch 但无实时网络：其输出不能标
  ``verified_timetable``；
- 原始承运人/班次直接进展示：新界面只展示 ``WorldService``。
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta

from ..schemas.web.common import LatLng
from ..schemas.web.transport import LegTimes


def effective_departure(times: LegTimes) -> datetime:
    return times.actual_departure_utc or times.estimated_departure_utc or times.planned_departure_utc


def effective_arrival(times: LegTimes) -> datetime:
    return times.actual_arrival_utc or times.estimated_arrival_utc or times.planned_arrival_utc


def leg_progress(times: LegTimes, now: datetime) -> float:
    """0..1；只由服务器时间与已确认时间线决定（打开网页、媒体播放、金币都不影响）。"""
    start = effective_departure(times)
    end = effective_arrival(times)
    total = (end - start).total_seconds()
    if total <= 0:
        return 1.0 if now >= end else 0.0
    return min(1.0, max(0.0, (now - start).total_seconds() / total))


def remaining(times: LegTimes, now: datetime) -> timedelta:
    return max(timedelta(0), effective_arrival(times) - now)


def schedule_after_leg(next_stop_start: datetime, leg_arrival: datetime, buffer: timedelta) -> datetime:
    """下一站最早开始时间：不早于本段可行抵达 + 缓冲。冲突时顺延下一站，绝不截短交通。"""
    return max(next_stop_start, leg_arrival + buffer)


def _haversine_m(a: LatLng, b: LatLng) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def position_along(route: list[LatLng], progress: float) -> tuple[LatLng, float]:
    """按路线几何长度插值当前位置与航向（度）。这是模拟线路位置，不是车辆实时定位。"""
    if not route:
        raise ValueError("route is empty")
    if len(route) == 1:
        return route[0], 0.0
    lengths = [_haversine_m(route[i], route[i + 1]) for i in range(len(route) - 1)]
    total = sum(lengths) or 1.0
    target = min(max(progress, 0.0), 1.0) * total
    walked = 0.0
    for index, seg in enumerate(lengths):
        a, b = route[index], route[index + 1]
        if walked + seg >= target or index == len(lengths) - 1:
            ratio = 0.0 if seg == 0 else (target - walked) / seg
            ratio = min(max(ratio, 0.0), 1.0)
            point = LatLng(lat=a.lat + (b.lat - a.lat) * ratio, lng=a.lng + (b.lng - a.lng) * ratio)
            heading = math.degrees(math.atan2(b.lng - a.lng, b.lat - a.lat)) % 360
            return point, heading
        walked += seg
    return route[-1], 0.0


def world_service_key(
    provider: str,
    operating_instance_id: str,
    service_date: date,
    origin_node_id: str,
    destination_node_id: str,
    segment_seq: int,
) -> str:
    """动物世界身份映射的内部唯一键：运营实例/运行日/起终节点/段序，不能只用“222”。"""
    return "|".join(
        [provider, operating_instance_id, service_date.isoformat(), origin_node_id, destination_node_id, str(segment_seq)]
    )


def derive_service_number(key: str, digits: int = 3) -> str:
    """由唯一键确定性派生展示编号的建议值；正式映射仍须写入持久化注册表（唯一约束 + 版本）。"""
    value = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return str(value % (10**digits)).zfill(digits)
