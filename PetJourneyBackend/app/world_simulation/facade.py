"""世界模拟引擎门面：快照 + 时间线 mixin 聚合。"""

from .snapshot import WorldSimulationSnapshotMixin
from .timeline import WorldSimulationTimelineMixin


class WorldSimulationEngine(
    WorldSimulationSnapshotMixin,
    WorldSimulationTimelineMixin,
):
    provider_name = "world-simulation-engine"
