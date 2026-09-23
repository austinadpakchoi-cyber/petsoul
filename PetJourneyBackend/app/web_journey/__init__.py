"""网页旅程：目的地目录、门到门时间线、世界事件、到访与店内活动、明信片。"""

from .catalog import DESTINATIONS
from .postcards import PostcardService
from .events import WorldEvent, WorldEventSink
from .repository import JourneyRecord, LegRecord, VisitRecord
from .service import JourneyError, WebJourneyService
from .settlement import FAST, SLOW
from .snapshot import JourneySnapshotBuilder, window_of

__all__ = [
    "DESTINATIONS",
    "FAST",
    "SLOW",
    "JourneyError",
    "JourneyRecord",
    "JourneySnapshotBuilder",
    "LegRecord",
    "PostcardService",
    "VisitRecord",
    "WebJourneyService",
    "WorldEvent",
    "WorldEventSink",
    "window_of",
]
