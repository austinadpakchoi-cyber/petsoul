"""PetSoul 平行世界的常驻 NPC 宠物。

这是单机阶段的"社会感"来源:一批身份固定、跨天跨模块一致出现的模拟宠物。
朋友圈点赞、地图同伴都必须从这份注册表取身份——用户会记住 NPC,记住 = 世界是真的。

注意:iOS 端 JourneyMapView.swift 的 DemoCompanionPet.samples 和
MockPetJourneyService.mockSocialReactors 持有同一批身份的镜像,改这里要同步改那边。
真实多用户上线后,这份注册表退化为"低密度城市的补位居民"。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .schemas import MomentReaction, MomentSocialReactor


@dataclass(frozen=True, slots=True)
class NPCPet:
    id: str
    name: str
    species: str
    avatar_emoji: str
    personality: str
    favorite_action: str
    preferred_reaction: MomentReaction
    notes: tuple[str, ...]


NPC_CAST: tuple[NPCPet, ...] = (
    NPCPet(
        id="npc-nana-cat",
        name="Nana",
        species="cat",
        avatar_emoji="🐱",
        personality="安静观察型,喜欢在窗台看街",
        favorite_action="看橱窗",
        preferred_reaction=MomentReaction.like,
        notes=(
            "在附近的窗台看见了这一刻",
            "路过的时候多看了两眼",
            "把这条动态记在了今天的散步清单里",
        ),
    ),
    NPCPet(
        id="npc-tuanzi-dog",
        name="团子",
        species="dog",
        avatar_emoji="🐶",
        personality="热情跟随型,见谁都摇尾巴",
        favorite_action="等面包",
        # paw(摸摸)保留给主人专用,NPC 只用 like/hug
        preferred_reaction=MomentReaction.like,
        notes=(
            "也觉得这里适合慢慢待着",
            "闻到了同一阵面包香",
            "尾巴摇了好一会儿",
        ),
    ),
    NPCPet(
        id="npc-jiujiu-parrot",
        name="啾啾",
        species="parrot",
        avatar_emoji="🦜",
        personality="广播型,什么都想学着说一遍",
        favorite_action="学人说话",
        preferred_reaction=MomentReaction.hug,
        notes=(
            "从公共频道轻轻回应了一下",
            "把这句话学了一遍,还挺像",
            "在树梢上把这条消息转播给了风",
        ),
    ),
    NPCPet(
        id="npc-momo-rabbit",
        name="Momo",
        species="rabbit",
        avatar_emoji="🐰",
        personality="收藏型,喜欢把好东西记在小地图上",
        favorite_action="听风铃",
        preferred_reaction=MomentReaction.like,
        notes=(
            "把这一刻收藏进小地图",
            "耳朵朝这边竖了一下",
            "决定明天也去这个地方看看",
        ),
    ),
    NPCPet(
        id="npc-mili-hamster",
        name="米粒",
        species="hamster",
        avatar_emoji="🐹",
        personality="囤货型,路过什么都想带一点走",
        favorite_action="找补给",
        preferred_reaction=MomentReaction.hug,
        notes=(
            "偷偷把这一刻塞进了腮帮子",
            "在小本子上记下了这个补给点",
            "决定把今天的瓜子分你一颗",
        ),
    ),
    NPCPet(
        id="npc-lucky-dog",
        name="Lucky",
        species="dog",
        avatar_emoji="🐶",
        personality="乐天型,相信每条街都有好事发生",
        favorite_action="追光斑",
        preferred_reaction=MomentReaction.like,
        notes=(
            "在街角朝这边汪了一声",
            "觉得今天的运气又变好了一点",
            "决定把这条路加进明天的巡逻线",
        ),
    ),
)


def npc_reactors(
    *,
    city: str,
    scene_hash: str,
    source_type: str,
    mood: str,
    now: datetime,
) -> list[MomentSocialReactor]:
    """确定性抽取 1-3 位常驻 NPC 回应一条动态;同一条动态永远是同一批邻居。"""
    seed = sum(ord(ch) for ch in f"{city}-{scene_hash}-{source_type}-{mood}")
    count = 1 + seed % 3
    start = seed % len(NPC_CAST)
    reactors: list[MomentSocialReactor] = []
    for offset in range(count):
        npc = NPC_CAST[(start + offset) % len(NPC_CAST)]
        note = npc.notes[(seed + offset) % len(npc.notes)]
        reactors.append(
            MomentSocialReactor(
                id=npc.id,
                name=npc.name,
                species=npc.species,
                avatar_emoji=npc.avatar_emoji,
                reaction=npc.preferred_reaction,
                note=note,
                created_at=now + timedelta(seconds=18 + offset * 31),
            )
        )
    return reactors
