"""旅程引擎门面——通过多重继承聚合各场景 mixin。

原 ``app/agent_engine.py`` 单类 1548 行 / 60 余方法，属 God File 反模式。
这里按场景域拆分为独立 mixin，``JourneyEngine`` 在此聚合，对外 API 保持不变：
历史调用方 ``from app.agent_engine import JourneyEngine``（以及
``PetNotFoundError`` / ``ThoughtNotFoundError`` / ``TravelQuestNotFoundError``）继续可用。
"""

from __future__ import annotations

from .base import JourneyEngineBaseMixin
from .economy import EconomyMixin
from .exceptions import PetNotFoundError, ThoughtNotFoundError, TravelQuestNotFoundError
from .feedback import FeedbackMixin
from .helpers import JourneyEngineHelpersMixin
from .lifecycle import LifecycleMixin
from .memory import MemoryMixin
from .memory_recording import MemoryRecordingMixin
from .owner_interaction import OwnerInteractionMixin
from .photo import PhotoMixin
from .souvenirs import SouvenirsMixin
from .trace import TraceMixin
from .travel_bag import TravelBagMixin
from .travel_quest import TravelQuestMixin
from .world import WorldSimulationMixin


class JourneyEngine(
    JourneyEngineBaseMixin,
    JourneyEngineHelpersMixin,
    TraceMixin,
    LifecycleMixin,
    MemoryRecordingMixin,
    TravelQuestMixin,
    TravelBagMixin,
    SouvenirsMixin,
    EconomyMixin,
    WorldSimulationMixin,
    PhotoMixin,
    MemoryMixin,
    FeedbackMixin,
    OwnerInteractionMixin,
):
    pass


__all__ = [
    "JourneyEngine",
    "PetNotFoundError",
    "ThoughtNotFoundError",
    "TravelQuestNotFoundError",
]
