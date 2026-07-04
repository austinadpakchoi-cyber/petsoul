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


LATE_NIGHT_START_HOUR = 22

LATE_NIGHT_INAPPROPRIATE_TOKENS = (
    "早茶",
    "早餐",
    "早饭",
    "brunch",
    "茶楼",
    "点心",
    "肠粉",
    "豆浆",
)


def meal_window(dt: datetime) -> str:
    hour = dt.astimezone().hour
    if MORNING_START_HOUR <= hour < MORNING_END_HOUR:
        return "breakfast"
    if 11 <= hour < 14:
        return "lunch"
    if 14 <= hour < 17:
        return "tea"
    if 17 <= hour < 21:
        return "dinner"
    return "late_night"


def is_place_plausible_at(dt: datetime, name: str, category: str = "", type_text: str = "") -> bool:
    """时段合理性护栏：清晨不去火锅烧烤，深夜不去早茶铺。"""
    window = meal_window(dt)
    if window == "breakfast":
        return not is_heavy_meal_place(name, category, type_text)
    if window == "late_night":
        text = f"{name} {category} {type_text}".lower()
        return not any(token.lower() in text for token in LATE_NIGHT_INAPPROPRIATE_TOKENS)
    return True


def is_time_inconsistent_postcard(location: str, text: str, timestamp: datetime) -> bool:
    if not is_morning(timestamp):
        return False
    combined = f"{location} {text}"
    if is_morning_appropriate_place(combined, "", ""):
        return False
    return is_heavy_meal_place(combined, "", "")
