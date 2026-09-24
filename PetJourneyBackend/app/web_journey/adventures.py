"""冒险事件模板：接入同一段旅程与同一只宠物（同一套世界事件、通讯与收藏），不另起互不相干的世界。

- 触发来自真实世界事件（到店与居民互动、轮渡/航班到站），不是随机抽奖；
- 奖励由规则结算：一枚绑定宠物、不可交易的勋章；故事只做表达，不改写奖励或职业；
- 主人确认过、允许在私密通讯里使用的物件（例如“蓝色的毯子”）可以出现在故事里；没有就不编；
- 个性化英雄图需要生图供应商（付费、未授权）→ 能力如实标为未配置，故事以文字与原创徽章呈现。

运营发布的版本覆盖（2026-09-23，运营后台窗口 adm1 追加）：
`ADVENTURES` 是一份带覆盖层的目录（`app/content_overlay.py`）——取模板时先问一次已发布版本，
没有就用下面的内置模板。可发布的只有 `PUBLISHABLE_FIELDS` 里那三项文案；key 与触发规则不可发布。
既有调用方 `ADVENTURES[key]` 的写法与语义都不变；没注册解析器时（独立任务进程、旧测试）行为与过去完全一致。

为什么覆盖放在“取模板”这一刻：冒险事件在**发生时**把标题、勋章与故事写进事件数据，随后落进
`web_world_events` 与各自的消费记录。所以发新版本只影响此后新发生的冒险，已经发生过的一条都不改——
回滚也因此不会改写历史。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..content_overlay import OverlayCatalog

CONTENT_TYPE = "adventure"


@dataclass(frozen=True)
class AdventureTemplate:
    key: str
    title: str
    badge: str
    story: str  # {pet} 宠物名；{keepsake} 主人确认过的物件短语（可为空）
    revision: int | None = None  # 来自运营发布版本时是版本号；内置模板为 None


# 可发布的字段：标题、勋章名、故事。key 与触发规则不可发布（那是世界规则，不是文案）。
PUBLISHABLE_FIELDS = ("title", "badge", "story")


def merge(base: AdventureTemplate, body: dict) -> AdventureTemplate:
    return replace(base, title=body.get("title") or base.title, badge=body.get("badge") or base.badge,
                   story=body.get("story") or base.story, revision=body.get("revision"))


ADVENTURES: dict[str, AdventureTemplate] = OverlayCatalog(CONTENT_TYPE, merge, {
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
})

# 内置模板的键：运营后台只允许给已有模板发新版本，不许凭空造新活动类型（首版范围）。
BUILT_IN_ADVENTURES = frozenset(dict.keys(ADVENTURES))

MODE_ADVENTURE = {"ferry": "ferry_sailor", "flight": "flight_pilot"}


def render_story(template: AdventureTemplate, pet_name: str, keepsake: str | None) -> str:
    phrase = f"带着你准备的{keepsake}，" if keepsake else ""
    return template.story.format(pet=pet_name, keepsake=phrase)
