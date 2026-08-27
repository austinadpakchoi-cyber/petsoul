"""照片任务大脑工厂（架构审计 P1-2 包化）。"""

from __future__ import annotations

from ..config import Settings
from .mock import MockPhotoMissionBrain
from .openai import OpenAICompatiblePhotoMissionBrain
from .protocol import PhotoMissionBrain

def build_photo_mission_brain(settings: Settings) -> PhotoMissionBrain:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAICompatiblePhotoMissionBrain(settings)
    return MockPhotoMissionBrain(settings)
