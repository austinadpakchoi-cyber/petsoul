"""MemoryPolicy：在检索 / 摘要 / 生成 **之前** 按归属、确认、版本、用途过滤。

禁止先把全部私人记录交给模型再用提示词要求“别说出来”。任何消费者（家园欢迎、
通讯、旅途活动、寻味、生图、公开故事、后台任务）都只能拿到 ``project_memory`` 的结果。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..schemas.web.home import HomeWelcome, WelcomeDetail, WelcomeDetailKind
from ..schemas.web.reception import (
    CandidateKind,
    CareNote,
    CareNoteSlot,
    MemoryGrant,
    MemoryProjection,
    MemoryPurpose,
    ProjectedNote,
    SaveTarget,
)

POLICY_VERSION = "memory-policy-r0-1"

# 这些种类永远不进入宠物/NPC/公开/寻味投影：主人私人倾诉与模型推测。
NEVER_PROJECTED_KINDS = frozenset({CandidateKind.owner_private, CandidateKind.inference})

_WELCOME_SLOTS = {
    CareNoteSlot.owner_title: WelcomeDetailKind.owner_title,
    CareNoteSlot.favorite_object: WelcomeDetailKind.favorite_object,
    CareNoteSlot.interaction_boundary: WelcomeDetailKind.interaction_boundary,
}


def project_memory(
    *,
    pet_id: str,
    purpose: MemoryPurpose,
    notes: Iterable[CareNote],
    grants: Iterable[MemoryGrant],
    now: datetime,
) -> MemoryProjection:
    """调用方必须已按 (user_id, pet_id) 取回记录；本函数再做一次宠物与用途过滤。"""
    note_list = list(notes)
    superseded = {note.supersedes_note_id for note in note_list if note.supersedes_note_id}
    active_grants = {
        (grant.note_id, grant.note_version, grant.purpose)
        for grant in grants
        if grant.revoked_at is None
    }
    items: list[ProjectedNote] = []
    for note in note_list:
        if note.pet_id != pet_id:
            continue
        if note.target is not SaveTarget.give_to_pet:
            continue
        if note.kind in NEVER_PROJECTED_KINDS:
            continue
        if note.revoked_at is not None or note.note_id in superseded:
            continue
        if purpose not in note.purposes:
            continue
        if (note.note_id, note.version, purpose) not in active_grants:
            continue
        items.append(
            ProjectedNote(
                note_id=note.note_id,
                note_version=note.version,
                kind=note.kind,
                text=note.text,
                slot=note.slot,
                slot_value=note.slot_value,
            )
        )
    return MemoryProjection(
        pet_id=pet_id, purpose=purpose, items=items, policy_version=POLICY_VERSION, generated_at=now
    )


def build_home_welcome(
    projection: MemoryProjection,
    *,
    projection_version: int,
    confirmation_id: str | None = None,
) -> HomeWelcome:
    """只消费 home_interaction 投影；只兑现当前 capability 支持的槽位。"""
    if projection.purpose is not MemoryPurpose.home_interaction:
        raise ValueError("HomeWelcome 只能由 home_interaction 投影生成")
    details: list[WelcomeDetail] = []
    title: str | None = None
    for item in projection.items:
        kind = _WELCOME_SLOTS.get(item.slot) if item.slot else None
        if kind is None:
            continue
        if kind is WelcomeDetailKind.owner_title and item.slot_value:
            title = item.slot_value
        details.append(
            WelcomeDetail(kind=kind, text=item.text, note_id=item.note_id, note_version=item.note_version)
        )
    greeting = f"{title}，我到家啦。" if title else "我到家啦，这里闻起来像你。"
    return HomeWelcome(
        pet_id=projection.pet_id,
        confirmation_id=confirmation_id,
        projection_version=projection_version,
        greeting=greeting,
        details=details,
    )
