"""冒险事件模板：接入同一段旅程与同一只宠物（同一套世界事件、通讯与收藏），不另起互不相干的世界。

- 触发来自真实世界事件（到店与居民互动、轮渡/航班到站），不是随机抽奖；
- 奖励由规则结算：一枚绑定宠物、不可交易的勋章；故事只做表达，不改写奖励或职业；
- 主人确认过、允许在私密通讯里使用的物件（例如“蓝色的毯子”）可以出现在故事里；没有就不编；
- 个性化英雄图需要生图供应商（付费、未授权）→ 能力如实标为未配置，故事以文字与原创徽章呈现。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdventureTemplate:
    key: str
    title: str
    badge: str
    story: str  # {pet} 宠物名；{keepsake} 主人确认过的物件短语（可为空）


ADVENTURES: dict[str, AdventureTemplate] = {
    "cafe_detective": AdventureTemplate(
        key="cafe_detective",
        title="咖啡馆小侦探",
        badge="小侦探勋章",
        story="店里的鹦鹉居民说它的杯垫不见了。{pet}{keepsake}顺着桌脚的奶泡印一路找，在窗帘后面找到了——原来是被风吹过去的。鹦鹉送了{pet}一枚小侦探勋章。",
    ),
    "ferry_sailor": AdventureTemplate(
        key="ferry_sailor",
        title="海上小水手",
        badge="海上小水手勋章",
        story="海獭船长请{pet}帮忙看着船头的风向旗。{pet}{keepsake}认真站了一整段航程，船长说它是今天最称职的小水手。",
    ),
    "flight_pilot": AdventureTemplate(
        key="flight_pilot",
        title="小小飞行员",
        badge="小小飞行员勋章",
        story="喵航的机长邀请{pet}去驾驶舱门口数云朵。{pet}{keepsake}数到第四十七朵时飞机开始下降，机长给它别上了一枚小小飞行员勋章。",
    ),
}

MODE_ADVENTURE = {"ferry": "ferry_sailor", "flight": "flight_pilot"}


def render_story(template: AdventureTemplate, pet_name: str, keepsake: str | None) -> str:
    phrase = f"带着你准备的{keepsake}，" if keepsake else ""
    return template.story.format(pet=pet_name, keepsake=phrase)
