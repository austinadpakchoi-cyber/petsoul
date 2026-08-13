"""攻略研究引擎门面：基础路由 + 证据处理 mixin 聚合。"""

from .engine_base import TravelGuideResearchEngineBaseMixin
from .evidence import TravelGuideResearchEvidenceMixin


class TravelGuideResearchEngine(
    TravelGuideResearchEngineBaseMixin,
    TravelGuideResearchEvidenceMixin,
):
    provider_name = "travel-guide-research-router"

