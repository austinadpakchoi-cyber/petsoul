"""PetSoul 照片导演（包 P）。

把一件**已经提交**的世界事件编排成一条可直接发给生图供应商的指令：
参考照锁外貌，经授权的 DNA 决定动作与取景，场景/地点/天气/当地时间决定环境与光线。

边界（有意为之）：
  - 不写任何业务表、不建调度器、不发图片请求、不重试生图；
  - 不扩公共 Web schema，本包的类型都是内部契约；
  - 模型只能在封闭词表里挑取景方式，改不了宠物、城市、地点、事件或已拥有的东西；
  - 每个照片事件最多一次导演文本请求，且走自己的预算，不混进图片额度。
"""
from .batch import BatchGuard, validate_batch_cost
from .contracts import (
    CompanionReference,
    DirectedPhoto,
    IdentityReference,
    MediaReference,
    PhotoAccess,
    PhotoContext,
    PhotoDirectorError,
    PhotoDNA,
    PhotoVersions,
    ReferenceSlot,
    SceneDraft,
    SceneFact,
    SceneFacts,
    TextCallRecord,
)
from .delivery import CURRENT_WEB_SINK, DeliveryPlan, SinkCapabilities, describe_gap, plan_delivery
from .director import PhotoDirector
from .memo import DirectorMemo
from .port import DirectorBudget, DirectorChat
from .privacy import project_photo_dna
from .readiness import Readiness, readiness, require_ready
from .recipes import RECIPES, SCENES

__all__ = [
    "BatchGuard",
    "CURRENT_WEB_SINK",
    "CompanionReference",
    "DeliveryPlan",
    "DirectorMemo",
    "DirectedPhoto",
    "DirectorBudget",
    "DirectorChat",
    "IdentityReference",
    "MediaReference",
    "PhotoAccess",
    "PhotoContext",
    "PhotoDNA",
    "PhotoDirector",
    "PhotoDirectorError",
    "PhotoVersions",
    "RECIPES",
    "Readiness",
    "ReferenceSlot",
    "SCENES",
    "SceneDraft",
    "SceneFact",
    "SceneFacts",
    "SinkCapabilities",
    "TextCallRecord",
    "describe_gap",
    "plan_delivery",
    "project_photo_dna",
    "readiness",
    "require_ready",
    "validate_batch_cost",
]
