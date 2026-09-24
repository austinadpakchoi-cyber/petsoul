"""把导演的输出交给图片请求——并且**不许静默丢字段**。

现网的生图入口（`web_providers/images.py` 的 `Illustrator.render`）今天只能接
一张参考图、没有负面提示词参数；底层适配器（`image_provider/seedream.py`）还会
按自己的 `REFERENCE_ROLE_ORDER` 重排参考，而那张表里没有 `companion_identity`。

如果直接把 `DirectedPhoto` 塞进去，负面词会消失、同伴参考会掉、顺序可能被改，
而调用方**什么都看不见**。所以这里先把"能送什么、会丢什么"算清楚：

  - `plan_delivery(...)` 返回一份 `DeliveryPlan`，`dropped` 里逐条写明丢了什么、为什么；
  - `strict=True`（默认）时，丢掉会改变画面语义的字段就直接抛错，宁可不出图；
  - 现网这套能力写在 `CURRENT_WEB_SINK` 里，A 扩能力之后改这一个常量即可。

本模块不发任何请求、不接触字节、不认识供应商 SDK。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import DirectedPhoto, PhotoDirectorError

# 丢掉这些会改变画面本身的意思，不能静默接受。
# 注意：**任何**被丢掉的参考图都算语义丢失，不管它是因为角色不认识（记作 `<role>`）
# 还是因为超出张数上限（记作 `reference:<role>`）。第二种曾经漏判过：
# 一个"字段全支持、但只接一张参考"的入口会在 strict 下悄悄把同伴丢掉。
SEMANTIC_FIELDS = frozenset({"negative_prompt", "reference_order"})
REFERENCE_ROLES = frozenset({"pet_identity", "companion_identity", "place_environment"})


def is_semantic_loss(item: str) -> bool:
    return (
        item in SEMANTIC_FIELDS
        or item in REFERENCE_ROLES
        or item.startswith("reference:")
    )


@dataclass(frozen=True, slots=True)
class SinkCapabilities:
    """图片入口今天真正能接住什么。改 A 的实现之后同步改这里。"""
    name: str
    max_references: int
    supports_negative_prompt: bool
    known_reference_roles: frozenset
    preserves_reference_order: bool
    allowed_sizes: frozenset = frozenset()


# 2026-09-23 只读核对的现网能力：
#   images.py:100  render(prompt, reference: tuple[bytes, str] | None, size="2048x2048")
#   images.py:122  唯一那张参考被写死成 role="pet_identity"
#   seedream.py:21 REFERENCE_ROLE_ORDER = {"pet_identity": 0, "place_environment": 1}，:86 按它重排
CURRENT_WEB_SINK = SinkCapabilities(
    name="web_providers.Illustrator.render",
    max_references=1,
    supports_negative_prompt=False,
    known_reference_roles=frozenset({"pet_identity", "place_environment"}),
    preserves_reference_order=False,
    allowed_sizes=frozenset({"2048x2048", "1440x2560"}),
)

# A 接上多参考与负面词之后应该长成的样子（写在这里当作对齐目标，不代表已经实现）
TARGET_SINK = SinkCapabilities(
    name="web_providers.Illustrator.render (proposed)",
    max_references=3,
    supports_negative_prompt=True,
    known_reference_roles=frozenset({"pet_identity", "companion_identity", "place_environment"}),
    preserves_reference_order=True,
    allowed_sizes=frozenset({"2048x2048", "1440x2560"}),
)


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    """真正会发出去的东西，以及被这个入口挡下的东西。"""
    prompt: str
    size: str
    negative_prompt: str | None
    references: tuple[tuple[int, str, str], ...]   # (position, role, reference_id)
    dropped: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def lossless(self) -> bool:
        return not self.dropped

    def evidence(self) -> dict:
        return {
            "size": self.size,
            "negative_prompt_sent": self.negative_prompt is not None,
            "references": [list(slot) for slot in self.references],
            "dropped": list(self.dropped),
            "notes": list(self.notes),
        }


def plan_delivery(
    photo: DirectedPhoto,
    sink: SinkCapabilities = CURRENT_WEB_SINK,
    *,
    strict: bool = True,
) -> DeliveryPlan:
    """算出这个入口实际能送什么。`strict` 下，任何语义性丢失直接抛错。"""
    dropped: list[str] = []
    notes: list[str] = []

    if sink.allowed_sizes and photo.size not in sink.allowed_sizes:
        raise PhotoDirectorError(f"size_not_supported_by_sink:{photo.size}")

    negative = photo.negative_prompt if sink.supports_negative_prompt else None
    if photo.negative_prompt and not sink.supports_negative_prompt:
        dropped.append("negative_prompt")
        notes.append(
            f"{sink.name} 没有负面提示词参数；这批负面词（卡通、人手、界面控件……）会整段消失"
        )

    unknown_roles = sorted(
        {slot.role for slot in photo.references} - set(sink.known_reference_roles)
    )
    for role in unknown_roles:
        dropped.append(role)
        notes.append(f"{sink.name} 不认识参考角色 {role}，底层会把它排到最后或丢掉")

    kept = [slot for slot in photo.references if slot.role in sink.known_reference_roles]
    if len(kept) > sink.max_references:
        overflow = kept[sink.max_references:]
        kept = kept[: sink.max_references]
        for slot in overflow:
            dropped.append(f"reference:{slot.role}")
            notes.append(f"{sink.name} 最多接 {sink.max_references} 张参考，{slot.role} 送不进去")

    if not sink.preserves_reference_order and len(kept) > 1:
        dropped.append("reference_order")
        notes.append("底层会按自己的角色表重排参考，导演给的顺序保不住")

    if not kept:
        raise PhotoDirectorError("no_reference_survives_sink")
    if kept[0].role != "pet_identity":
        raise PhotoDirectorError("identity_reference_must_be_first")

    plan = DeliveryPlan(
        prompt=photo.prompt,
        size=photo.size,
        negative_prompt=negative,
        references=tuple((slot.position, slot.role, slot.reference_id) for slot in kept),
        dropped=tuple(dropped),
        notes=tuple(notes),
    )
    if strict and any(is_semantic_loss(item) for item in plan.dropped):
        # 宁可不出图，也不发一张"负面词没生效、同伴不见了"却看不出来的照片。
        raise PhotoDirectorError("delivery_would_drop_fields:" + ",".join(plan.dropped))
    return plan


def describe_gap(sink: SinkCapabilities = CURRENT_WEB_SINK) -> dict:
    """现网能力与目标能力的差，给 A 看的对齐清单。"""
    return {
        "sink": sink.name,
        "max_references": {"now": sink.max_references, "needed": TARGET_SINK.max_references},
        "negative_prompt": {
            "now": sink.supports_negative_prompt,
            "needed": TARGET_SINK.supports_negative_prompt,
        },
        "reference_roles": {
            "now": sorted(sink.known_reference_roles),
            "needed": sorted(TARGET_SINK.known_reference_roles),
        },
        "preserves_reference_order": {
            "now": sink.preserves_reference_order,
            "needed": TARGET_SINK.preserves_reference_order,
        },
    }
