"""路由层共享辅助：请求解析与 404 归一（架构审计 P1-3 从 http_utils 迁出）。

路由辅助归 routers 层：可以 import 引擎层异常与 fastapi，不属于公共底层。
"""

from __future__ import annotations

import json

from fastapi import HTTPException

from ..agent_engine import (
    PetNotFoundError,
    ThoughtNotFoundError,
    TravelQuestNotFoundError,
)
from ..schemas import PetDNA


def parse_dna(raw: str) -> PetDNA:
    """创建宠物时解析 DNA JSON（路由层请求解析）。"""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"dna must be JSON: {exc}") from exc
    return PetDNA.model_validate(payload)


def with_not_found(factory):
    """把引擎层的「不存在」异常统一转成 404。"""
    try:
        return factory()
    except PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pet not found") from exc
    except ThoughtNotFoundError as exc:
        raise HTTPException(status_code=404, detail="thought translation not found") from exc
    except TravelQuestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="travel quest not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="resource not found") from exc
