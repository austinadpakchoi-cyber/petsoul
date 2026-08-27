"""照片任务大脑协议与上下文（架构审计 P1-2 包化）。"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any, Protocol

from ..schemas import AgentStatus

@dataclass(frozen=True, slots=True)
class PhotoMissionContext:
    pet: PetRecord
    place: PlaceSignal
    activity: WorldActivity | None
    weather: str
    now: datetime
    time_of_day: str
    worldcup_event: bool = False


@dataclass(frozen=True, slots=True)
class PhotoMissionDraft:
    interaction_type: str
    title: str
    detail: str
    pet_action: str
    emotional_tone: str
    dwell_minutes: int
    camera_perspective: PhotoPerspective
    scene_anchor: str
    landmark_hints: list[str]
    local_detail_hints: list[str]
    crowd_hints: list[str]
    image_prompt: str
    postcard_text: str
    safety_notes: list[str]
    model: str
    provider: str

class PhotoMissionBrain(Protocol):
    provider_name: str

    def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
        ...

    def config_snapshot(self) -> dict[str, str | bool | float]:
        ...
