"""Mock 照片任务大脑（架构审计 P1-2 包化）。"""

from __future__ import annotations

from .protocol import PhotoMissionBrain

class MockPhotoMissionBrain:
    provider_name = "mock-photo-mission-brain"

    def __init__(self, settings: Settings):
        self.settings = settings

    def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
        return None

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "photo_mission_model": self.settings.photo_mission_model,
            "remote_configured": False,
            "remote_call_active": False,
            "remote_call_enabled": False,
            "last_remote_success": False,
            "last_remote_error": "",
            "timeout_seconds": self.settings.agent_timeout_seconds,
        }
