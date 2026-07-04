from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import PetDNA


DNA_DIMENSIONS: tuple[str, ...] = (
    "owner_title",
    "personality",
    "favorite_places",
    "hobby",
    "catchphrase",
    "voice_style",
)


@dataclass(frozen=True, slots=True)
class InterviewTurn:
    empathy: str
    next_question: str
    should_end: bool
    collected_dna: PetDNA | None
    missing_fields: list[str]
    ritual_stage: str


@dataclass(slots=True)
class InterviewState:
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    covered_dimensions: set[str] = field(default_factory=set)
    last_feedback: str | None = None


class PetDNAInterviewEngine:
    provider_name = "mock-pet-dna-interview"

    def next_turn(self, state: InterviewState, user_message: str) -> InterviewTurn:
        normalized = user_message.strip()
        next_dimension = self._next_dimension(state)
        state.conversation_history.append({"role": "user", "content": normalized})
        if next_dimension:
            state.covered_dimensions.add(next_dimension)

        missing = [dimension for dimension in DNA_DIMENSIONS if dimension not in state.covered_dimensions]
        should_end = not missing and len(state.conversation_history) >= 4
        collected_dna = self._fallback_dna(state) if should_end else None
        question = "我大概听见 TA 的样子了。最后，你希望手机用什么语气帮你翻译 TA 的原声或小信号？"
        if missing:
            question = self._question_for(missing[0])

        return InterviewTurn(
            empathy="我会慢慢记下来，不需要一次说得很完整。",
            next_question=question,
            should_end=should_end,
            collected_dna=collected_dna,
            missing_fields=missing,
            ritual_stage="collecting_dna" if not should_end else "ready_to_connect",
        )

    def _next_dimension(self, state: InterviewState) -> str | None:
        for dimension in DNA_DIMENSIONS:
            if dimension not in state.covered_dimensions:
                return dimension
        return None

    def _question_for(self, dimension: str) -> str:
        questions = {
            "owner_title": "TA 平时会怎么叫你？比如妈妈、爸爸、主人、姐姐，或者你们之间独有的称呼。",
            "personality": "TA 的性格是什么样的？可以像讲故事一样说，不用选标签。",
            "favorite_places": "如果 TA 在另一个世界继续旅行，你觉得哪些地方会让 TA 愿意停一停？",
            "hobby": "TA 最容易被什么吸引？声音、气味、阳光、屏幕，或者某个小习惯都可以。",
            "catchphrase": "有没有一句你想到 TA 时会浮出来的话，或者一个很短的记忆关键词？",
            "voice_style": "以后翻译 TA 的原声或小信号时，你希望语气更像小纸条、随手拍，还是认真汇报？",
        }
        return questions.get(dimension, "再跟我说一点 TA 的事情吧。")

    def _fallback_dna(self, state: InterviewState) -> PetDNA:
        joined = " ".join(item["content"] for item in state.conversation_history if item["content"])
        return PetDNA(
            personality=joined[:80] or "温柔、好奇，会按自己的节奏探索",
            favorite_places=["安静的小店", "有阳光的街角"],
            hobby=["观察来往的人", "闻新的气味"],
            catchphrase="我在这里玩一会儿，也在想你。",
            voice_style="像发来一张随手拍照片，语气轻轻的但很认真。",
        )
