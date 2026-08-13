"""宠物攻略引擎：按场景域 mixin 聚合 + 门面 re-export。

历史导入面保持不变：
    from app.pet_guide_engine import PetGuideEngine
"""

from .authoring import PetGuideAuthoringMixin
from .base import PetGuideEngineBaseMixin
from .prompts import PetGuidePromptsMixin
from .scoring import PetGuideScoringMixin
from .stops import PetGuideStopsMixin


class PetGuideEngine(
    PetGuideEngineBaseMixin,
    PetGuideAuthoringMixin,
    PetGuideScoringMixin,
    PetGuideStopsMixin,
    PetGuidePromptsMixin,
):
    pass


__all__ = ["PetGuideEngine"]
