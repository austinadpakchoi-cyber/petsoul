"""寻味演示资料集（首发小样本）。

全部为明确的“示例”店与示例菜，不对应真实商家；证据 source_kind=fixture、observed_sample_count=0，
永不进入现实品质证据池（因此 Q 恒为未知）。营业时间/价格为演示设定，部分刻意留空以验证“未知不当作满足”。
真实菜单/获准评论接入后替换本文件的数据来源，算法与契约不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 味道维度与 TasteVector 对齐：-2..2
TRAITS = ("sweet", "salty", "spicy", "oily", "aromatic_spice", "rich_broth", "crispy")


@dataclass(frozen=True)
class DemoDish:
    dish_id: str
    name: str
    price_hkd: int | None
    traits: dict[str, int]
    ingredients: tuple[str, ...]
    trait_labels: tuple[str, ...]
    evidence: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (方面, 观察)


@dataclass(frozen=True)
class DemoBranch:
    branch_id: str
    name: str
    brand: str | None
    lat: float
    lng: float
    open_hours: tuple[int, int] | None  # 当地时间 [开, 关) 小时；None=未知
    closed_permanently: bool
    dishes: tuple[DemoDish, ...]


AREAS: dict[str, tuple[str, tuple[DemoBranch, ...]]] = {
    "hk-harbour": ("Asia/Hong_Kong", (
        DemoBranch("fixture:hk-clear-noodle", "示例·清汤面馆（西区店）", "示例清汤面馆", 22.2862, 114.1510, (11, 22), False, (
            DemoDish("fixture:hk-clear-noodle:clear-noodle", "清汤细面（示例）", 48, {"salty": 1, "rich_broth": -1, "oily": -2}, ("小麦", "葱"), ("汤底清", "面有嚼劲"),
                     (("面条口感", "（演示）面有嚼劲"), ("咸度", "（演示）一位食客觉得汤略咸"))),
            DemoDish("fixture:hk-clear-noodle:beef-broth", "浓汤牛骨面（示例）", 58, {"rich_broth": 2, "oily": 1, "salty": 1}, ("牛肉", "小麦"), ("汤底浓", "油润"),
                     (("汤底", "（演示）骨汤较浓"),)),
        )),
        DemoBranch("fixture:hk-congee", "示例·海港粥铺", None, 22.2840, 114.1560, None, False, (
            DemoDish("fixture:hk-congee:fish-congee", "鱼片粥（示例）", None, {"salty": -1, "oily": -2}, ("鱼", "米", "姜"), ("清淡", "绵"), ()),
        )),
        DemoBranch("fixture:hk-curry", "示例·街角咖喱小馆", None, 22.2875, 114.1545, (12, 21), False, (
            DemoDish("fixture:hk-curry:curry-beef", "咖喱牛腩饭（示例）", 68, {"spicy": 1, "aromatic_spice": 2, "rich_broth": 1, "oily": 1}, ("牛肉", "香菜", "米"), ("浓郁", "香料", "微辣"),
                     (("风味", "（演示）酱汁浓稠、香料明显"),)),
        )),
        DemoBranch("fixture:hk-closed-bakery", "示例·旧街面包房", None, 22.2850, 114.1600, (7, 19), True, (
            DemoDish("fixture:hk-closed-bakery:egg-tart", "蛋挞（示例）", 12, {"sweet": 2, "crispy": 1}, ("鸡蛋", "黄油"), ("甜", "酥"), ()),
        )),
    )),
    "macau-old-town": ("Asia/Macau", (
        DemoBranch("fixture:mo-porridge", "示例·巷口粥面", None, 22.1942, 113.5398, (8, 20), False, (
            DemoDish("fixture:mo-porridge:pork-congee", "猪骨粥（示例）", 42, {"salty": 0, "oily": -1}, ("猪肉", "米"), ("清淡",), (("口感", "（演示）米粒绵软"),)),
        )),
        DemoBranch("fixture:mo-pork-bun", "示例·猪扒包小铺", None, 22.1920, 113.5420, (10, 23), False, (
            DemoDish("fixture:mo-pork-bun:pork-bun", "猪扒包（示例）", 55, {"salty": 1, "oily": 2, "crispy": 2}, ("猪肉", "小麦"), ("香口", "酥脆", "油润"),
                     (("外皮", "（演示）面包外皮酥"),)),
        )),
        DemoBranch("fixture:mo-dessert", "示例·双皮奶甜品店", None, 22.1930, 113.5405, None, False, (
            DemoDish("fixture:mo-dessert:milk-pudding", "双皮奶（示例）", 38, {"sweet": 2}, ("牛奶", "鸡蛋"), ("甜", "滑"), ()),
        )),
    )),
    "tokyo-alley": ("Asia/Tokyo", (
        DemoBranch("fixture:tk-soba", "示例·巷子荞麦面", None, 35.6815, 139.7700, (11, 21), False, (
            DemoDish("fixture:tk-soba:zaru-soba", "冷荞麦面（示例）", 90, {"salty": 0, "oily": -2, "rich_broth": -1}, ("荞麦", "海苔"), ("清爽",), (("面条", "（演示）荞麦香"),)),
        )),
        DemoBranch("fixture:tk-ramen", "示例·深夜拉面", None, 35.6808, 139.7712, (18, 26), False, (
            DemoDish("fixture:tk-ramen:tonkotsu", "豚骨拉面（示例）", 110, {"rich_broth": 2, "oily": 2, "salty": 1}, ("猪肉", "小麦", "蛋"), ("汤底浓", "油润"),
                     (("汤底", "（演示）汤头浓厚"),)),
        )),
    )),
}

CITY_AREAS = {"香港": "hk-harbour", "澳门": "macau-old-town", "东京": "tokyo-alley"}
