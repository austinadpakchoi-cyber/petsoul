"""攻略研究：Doubao 社媒情报检索 + 证据包评分 + 门面 re-export。

历史导入面保持不变：
    from app.travel_research import (
        DoubaoArkClient,
        GuideResearchDraft,
        TravelGuideResearchEngine,
        build_travel_guide_research_engine,
    )
"""

from .doubao_client import DoubaoArkClient
from .draft import GuideResearchDraft
from .facade import TravelGuideResearchEngine
from .factory import build_travel_guide_research_engine

__all__ = [
    "DoubaoArkClient",
    "GuideResearchDraft",
    "TravelGuideResearchEngine",
    "build_travel_guide_research_engine",
]
