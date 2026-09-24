"""爪爪驾校：主人陪考，宠物拿证（四科、每科一次补考、两次不过冷却 7×24 小时、服务端复算、拿证解锁自驾）。"""

from .curriculum import RULES_VERSION
from .replay import Replay
from .errors import DrivingError
from .service import DrivingService

__all__ = ["DrivingError", "DrivingService", "RULES_VERSION", "Replay"]
