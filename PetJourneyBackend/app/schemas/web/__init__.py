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
from .character import *  # noqa: F401,F403
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
from .map import *  # noqa: F401,F403
from .world import *  # noqa: F401,F403
from .moderation import *  # noqa: F401,F403
from .travel import *  # noqa: F401,F403

from . import character, common, companion_media, credentials, farm, food, home, household, identity, intent, journey, market, ops, pets, public, reception, school, school_session, social, transport
from . import map as map_schema  # `map` 是内置名，模块级绑定会遮蔽 map()，所以取别名
from . import moderation, travel, world

# **只有列进这里的模块才会进生成物**（`scripts/gen_web_contract.py` 读的就是它）。
# 光加 `from .x import *` 和 `__all__` 都不够——那两样让模型**可导入**，这一行才让它**进契约**。
# 漏了不会报错：契约里静静地少一个模型，只有数模型个数才看得出来。
CONTRACT_MODULES = (common, identity, household, pets, character, home, farm, market, journey, transport, companion_media, food, reception, social, intent, credentials, school,
                    school_session, public, ops, map_schema, world, moderation, travel)
