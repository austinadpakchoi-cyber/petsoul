"""地点交互引擎门面：mission + 文案 mixin 聚合。"""

from .mission import PlaceInteractionMissionMixin
from .text import PlaceInteractionTextMixin


class PlaceInteractionEngine(
    PlaceInteractionMissionMixin,
    PlaceInteractionTextMixin,
):
    pass
