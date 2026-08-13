"""地点交互引擎：mission + 文案 mixin 聚合 + 门面 re-export。

历史导入面保持不变：
    from app.place_interactions import PlaceInteractionEngine
"""

from .facade import PlaceInteractionEngine

__all__ = ["PlaceInteractionEngine"]
