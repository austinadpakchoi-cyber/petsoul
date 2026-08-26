from __future__ import annotations

from dataclasses import dataclass

from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class FeedbackEffect:
    message: str
    event_title: str
    event_detail: str
    thought_tone: str


class JourneyFeedbackPolicy:
    def resolve(self, pet: PetRecord, liked: bool) -> FeedbackEffect:
        if liked:
            return FeedbackEffect(
                message=f"已为你收藏这段攻略。{pet.name} 的旅程不会被打断，TA 还在按自己的节奏探索。",
                event_title="你收藏了一段攻略",
                event_detail="这是你的旅行偏好，不会决定 TA 对这个地方的感受。",
                thought_tone="guide_saved",
            )
        return FeedbackEffect(
            message=f"知道了，这类攻略会少推荐给你。{pet.name} 仍然可以自己喜欢、停留或离开。",
            event_title="你略过了这类攻略",
            event_detail="通讯器会少给你推荐类似地点，但 TA 的旅程仍然自由。",
            thought_tone="guide_skipped",
        )
