"""寻味领域（R0：服务边界 + 上下文/证据纯函数；评分排序实现待用户分配）。

独立于 ``street_rank.py``：地点停留建议与餐食品质证据是两件事。
"""

from .context import (
    REAL_QUALITY_SOURCES,
    FoodContextError,
    public_preference_view,
    real_quality_evidence,
    recommendation_freshness,
    validate_request_context,
)
from .service import FoodDiscoveryService

__all__ = [
    "REAL_QUALITY_SOURCES",
    "FoodContextError",
    "FoodDiscoveryService",
    "public_preference_view",
    "real_quality_evidence",
    "recommendation_freshness",
    "validate_request_context",
]
