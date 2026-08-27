"""纪念品目录包（架构审计 P1-2：souvenir_catalog.py 535 行 > 400 建包）。

历史导入面保持不变：from app.souvenir_catalog import SouvenirTemplate / SouvenirPreset / build_souvenir_templates / 各预设表。
"""

from .models import SouvenirPreset, SouvenirTemplate
from .logic import build_souvenir_templates
from .data import (
    BAG_PRESETS,
    CITY_PRESETS,
    GLOBAL_TEMPLATES,
    PLACE_PRESETS,
    WORLDCUP_TEMPLATES,
)

__all__ = [
    "SouvenirTemplate",
    "SouvenirPreset",
    "build_souvenir_templates",
    "WORLDCUP_TEMPLATES",
    "CITY_PRESETS",
    "BAG_PRESETS",
    "PLACE_PRESETS",
    "GLOBAL_TEMPLATES",
]
