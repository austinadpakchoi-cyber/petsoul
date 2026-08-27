from __future__ import annotations

import random
from datetime import datetime, timezone

from pydantic import BaseModel

# 公共世界故事条：首启界面用它替代统计数字，让世界先"活"起来。
# 确定性生成（按小时轮换种子），不依赖 LLM，不绑定任何具体宠物。

_ANCHORS = (
    ("东京", "便利店门口", "躲雨"),
    ("京都", "鸭川边", "看鹭鸶站在浅水里"),
    ("厦门", "沙坡尾的猫街", "闻刚出炉的花生汤"),
    ("雷克雅未克", "港口的旧灯塔下", "等极光醒过来"),
    ("巴黎", "面包店的暖气口", "数刚出炉的可颂"),
    ("清迈", "夜市的灯串下", "追一只慢吞吞的甲虫"),
    ("旧金山", "缆车站的坡道上", "看雾从海上爬进街道"),
    ("首尔", "汉江边的草坡", "把爪印留在傍晚的沙地上"),
)

_SPECIES = ("一只小猫", "一只小狗", "一只鹦鹉", "一只兔子", "一只仓鼠")

_TEMPLATES = (
    "{species}刚在{city}{spot}{doing}。",
    "{species}在{city}{spot}停了很久，只为了{doing}。",
    "{city}的{spot}，{species}正{doing}。",
)


class StoryTickerItem(BaseModel):
    id: str
    text: str
    city: str


class StoryTickerResponse(BaseModel):
    generated_at: datetime
    items: list[StoryTickerItem]


def build_story_ticker(*, limit: int = 8, now: datetime | None = None) -> StoryTickerResponse:
    moment = now or datetime.now(timezone.utc)
    seed = moment.strftime("%Y%m%d%H")
    rng = random.Random(seed)
    anchors = list(_ANCHORS)
    rng.shuffle(anchors)

    items: list[StoryTickerItem] = []
    for index, (city, spot, doing) in enumerate(anchors[: max(1, min(limit, len(anchors)))]):
        species = _SPECIES[rng.randrange(len(_SPECIES))]
        template = _TEMPLATES[rng.randrange(len(_TEMPLATES))]
        items.append(
            StoryTickerItem(
                id=f"story-{seed}-{index}",
                text=template.format(species=species, city=city, spot=spot, doing=doing),
                city=city,
            )
        )
    return StoryTickerResponse(generated_at=moment, items=items)
