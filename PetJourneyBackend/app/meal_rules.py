from __future__ import annotations

from datetime import datetime


MORNING_START_HOUR = 5
MORNING_END_HOUR = 11

BREAKFAST_TOKENS = (
    "早餐",
    "早饭",
    "早茶",
    "茶楼",
    "茶餐厅",
    "点心",
    "包子",
    "粥",
    "豆浆",
    "肠粉",
    "烧麦",
    "虾饺",
    "面包",
    "烘焙",
    "咖啡",
    "cafe",
    "coffee",
    "bakery",
    "brunch",
)

HEAVY_MEAL_TOKENS = (
    "海鲜",
    "大酒楼",
    "酒楼",
    "火锅",
    "烧烤",
    "烤肉",
    "烤鱼",
    "夜宵",
    "大排档",
)


def is_morning(dt: datetime) -> bool:
    hour = dt.astimezone().hour
    return MORNING_START_HOUR <= hour < MORNING_END_HOUR


def is_morning_appropriate_place(name: str, category: str, type_text: str = "") -> bool:
    text = f"{name} {category} {type_text}".lower()
    if category == "cafe":
        return True
    return any(token.lower() in text for token in BREAKFAST_TOKENS)


def is_heavy_meal_place(name: str, category: str = "", type_text: str = "") -> bool:
    text = f"{name} {category} {type_text}".lower()
    return any(token.lower() in text for token in HEAVY_MEAL_TOKENS)


def is_time_inconsistent_postcard(location: str, text: str, timestamp: datetime) -> bool:
    if not is_morning(timestamp):
        return False
    combined = f"{location} {text}"
    if is_morning_appropriate_place(combined, "", ""):
        return False
    return is_heavy_meal_place(combined, "", "")
