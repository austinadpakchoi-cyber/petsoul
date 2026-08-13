"""攻略研究草稿：Doubao 社媒情报的清洗后结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import SocialTravelFinding


@dataclass(frozen=True, slots=True)
class GuideResearchDraft:
    strategy: str
    findings: list[str]
    recommended_sources: list[str]
    raw_text: str
    research_brief: dict[str, Any] = field(default_factory=dict)
    social_findings: list[SocialTravelFinding] = field(default_factory=list)
    quality_gate_notes: list[str] = field(default_factory=list)
