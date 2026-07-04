from __future__ import annotations

from ..memory_store import MemoryStore
from .moment_store import CommunicatorMomentStore
from .schemas import MomentReaction, MomentReactionResponse


class CommunicatorMomentReactionHandler:
    provider_name = "communicator-moment-reaction-handler"

    def __init__(self, store: CommunicatorMomentStore, memory_store: MemoryStore):
        self.store = store
        self.memory_store = memory_store

    def react(self, *, pet_id: str, moment_id: str, reaction: MomentReaction) -> MomentReactionResponse:
        moment = self.store.upsert_reaction(pet_id=pet_id, moment_id=moment_id, reaction=reaction)
        label = {
            MomentReaction.like: "喜欢",
            MomentReaction.paw: "摸摸",
            MomentReaction.hug: "抱抱",
        }[reaction]
        self.memory_store.add_memory(
            pet_id=pet_id,
            kind="moment_reaction",
            title=f"你对朋友圈点了{label}",
            content=f"你对「{moment.text}」回应了：{label}。这会成为 TA 之后选择停留和分享时的一点偏好信号。",
            salience=0.56,
            source="communicator_moment_reaction",
            metadata={"moment_id": moment_id, "reaction": reaction.value, "source_type": moment.source_type.value},
        )
        return MomentReactionResponse(
            success=True,
            moment_id=moment_id,
            reaction=reaction,
            message={
                MomentReaction.like: "TA 好像知道你喜欢这一刻。",
                MomentReaction.paw: "TA 好像感受到你摸了摸它。",
                MomentReaction.hug: "TA 把这个抱抱轻轻收好了。",
            }[reaction],
        )
