"""PetSoul 网页契约（当前 0.2.0）的服务端 DTO（/api/v1/web）。

本包是 `docs/contracts/WEB-CONTRACT-v0.2.md` 的唯一代码来源：
`scripts/gen_web_contract.py` 从这里生成 JSON Schema 与前端
`PetJourneyWeb/src/shared/contracts/generated.ts`，`--check` 模式检测漂移。

不被 `app/schemas/__init__.py` re-export：网页 DTO 与旧 iOS Codable 契约互不干扰。
新增模型后必须加入对应文件的 ``__all__``，否则不会进入生成物。
"""

from .common import *  # noqa: F401,F403
from .identity import *  # noqa: F401,F403
from .pets import *  # noqa: F401,F403
from .home import *  # noqa: F401,F403
from .journey import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .companion_media import *  # noqa: F401,F403
from .food import *  # noqa: F401,F403
from .reception import *  # noqa: F401,F403
from .social import *  # noqa: F401,F403
from .farm import *  # noqa: F401,F403
from .intent import *  # noqa: F401,F403
from .market import *  # noqa: F401,F403
from .credentials import *  # noqa: F401,F403
from .school import *  # noqa: F401,F403
from .school_session import *  # noqa: F401,F403
from .household import *  # noqa: F401,F403
from .public import *  # noqa: F401,F403
from .ops import *  # noqa: F401,F403

from . import common, companion_media, credentials, farm, food, home, household, identity, intent, journey, market, ops, pets, public, reception, school, school_session, social, transport

CONTRACT_MODULES = (common, identity, household, pets, home, farm, market, journey, transport, companion_media, food, reception, social, intent, credentials, school,
                    school_session, public, ops)
