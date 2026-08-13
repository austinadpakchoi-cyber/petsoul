"""世界层端点。"""

from __future__ import annotations

from fastapi import APIRouter

from ..story_ticker import StoryTickerResponse, build_story_ticker

router = APIRouter()


@router.get("/api/v1/world/story_ticker", response_model=StoryTickerResponse)
def world_story_ticker(limit: int = 8) -> StoryTickerResponse:
    return build_story_ticker(limit=limit)
