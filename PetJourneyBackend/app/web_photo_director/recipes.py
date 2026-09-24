"""场景与配方：可以选的那一组"怎么拍"，以及每一种需要哪些已核验的事实。

一个 **Recipe** 是导演唯一能挑的单元：场景 + 镜头 + 构图 + 动作 + 必需事实 + 适用叙事模式。
把这些绑在一起，而不是让模型分别挑镜头和动作，是因为它们互相约束——
驾驶舱里不能手持自拍，镜面自拍必须有镜子，同伴抓拍必须真的有同伴在场。

`acceptance` 是给人看真图时用的逐条检查，不是程序能判定的东西；
它会进联系表，**不会**变成"这张图通过了"的结论。
"""
from __future__ import annotations

from types import MappingProxyType
from typing import NamedTuple

# --- 场景：空间属性决定天气怎么进画面，叙事模式决定它能属于哪类故事 ---


# 事实来源的两种状态。这是 P3 的收敛口径：
#   "target"       —— 四个目标场景。世界侧已经有对应的拍照事件，接线后就能用。
#   "fixture_only" —— 配方已经写好，但世界侧**还没有**产出它需要的已核验事实
#                     （没有"它在健身房"这种事件，也没有 `landmark_in_view` 这种天象/视线记录）。
# fixture_only 的场景只在评测 fixture 里可选；正式世界事件走到它会被直接拒绝。
# 这样配方库可以先写好，但**不要求其他窗口为了它去扩建所有世界玩法**。
FACT_SOURCES = frozenset({"target", "fixture_only"})


class Scene(NamedTuple):
    space: str            # indoor / outdoor / sealed
    mandatory: str        # 没有这条事实就不是这个场景
    objects: frozenset    # 这个场景允许出现的可选物件（仍需逐个核验）
    story_modes: frozenset
    setting: str          # 环境描述，把地点变成可辨认的画面
    fact_source: str = "fixture_only"


SCENES = MappingProxyType({
    "cafe": Scene(
        "indoor", "at_cafe", frozenset({"coffee_cup", "photographer_present"}),
        frozenset({"daily_life"}), "咖啡馆室内，有吧台、座位和客人的身影",
        fact_source="target"),
    "train": Scene(
        "indoor", "on_train", frozenset({"train_seat", "train_window", "audio_player"}),
        frozenset({"daily_life"}), "行进中的车厢，有座椅、行李架和窗外掠过的景色",
        fact_source="target"),
    "home": Scene(
        "indoor", "at_home", frozenset({"home_blanket", "photographer_present"}),
        frozenset({"daily_life"}), "它在 PetSoul 的家，院子与窝边熟悉的陈设",
        fact_source="target"),
    "courtyard": Scene(
        "outdoor", "at_courtyard", frozenset({"harvested_crop", "garden_bed"}),
        frozenset({"daily_life"}), "自家院子里的菜园，畦垄和工具都是平时用的那些"),
    "landmark": Scene(
        "outdoor", "at_landmark",
        frozenset({"landmark_in_view", "held_snack", "photographer_present"}),
        frozenset({"daily_life"}), "开阔的景点广场，周围有来往的游客"),
    "gym": Scene(
        "indoor", "at_gym",
        frozenset({"gym_mirror", "own_device", "headphones", "gym_bench"}),
        frozenset({"daily_life"}), "普通健身房，有哑铃架、长凳和橡胶地面"),
    "workshop": Scene(
        "indoor", "at_workshop",
        frozenset({"parked_vehicle", "hand_tool", "work_outfit", "photographer_present"}),
        frozenset({"daily_life"}), "车间里，地面有工具和零件，灯光是顶灯"),
    "flight_adventure": Scene(
        "sealed", "flight_adventure",
        frozenset({"flight_helmet", "earned_medal", "safety_harness"}),
        frozenset({"fictional_adventure", "film_scene"}), "虚构飞行器座舱，可见舱窗与天空",
        fact_source="target"),
    "ship_deck": Scene(
        "outdoor", "on_ship_deck", frozenset({"captain_hat", "ship_wheel"}),
        frozenset({"fictional_adventure", "film_scene"}), "木质甲板与桅杆，远处是海面"),
    "snow_field": Scene(
        "outdoor", "in_snow_field",
        frozenset({"winter_outfit", "photographer_present"}),
        frozenset({"fictional_adventure", "film_scene"}), "开阔的雪地，远处是雪坡与针叶林"),
    "aurora_camp": Scene(
        "outdoor", "at_aurora_camp",
        frozenset({"aurora_visible", "winter_outfit", "camp_light"}),
        frozenset({"daily_life", "fictional_adventure"}), "夜里的营地，帐篷边有一盏暖灯"),
})


# --- 事实 -> 画面里允许出现什么。未核验的事实进不来。---
FACT_TEXT = MappingProxyType({
    "at_cafe": "它已经到了这家咖啡馆",
    "on_train": "这次事件里它确实在列车上",
    "at_home": "它在 PetSoul 配置的家，不是现实中的住址",
    "at_courtyard": "它在自家院子的菜园里",
    "at_landmark": "它确实到了这个景点",
    "at_gym": "它在这家健身房里",
    "at_workshop": "它在这个车间里",
    "flight_adventure": "这是一次虚构的、安全的飞行冒险",
    "on_ship_deck": "这是一次虚构的航海剧情，它在甲板上",
    "in_snow_field": "这是一次虚构的雪地任务",
    "at_aurora_camp": "它在这个夜间营地",
    # 物件：每一件都必须单独核验过，不能由场景推出来
    "coffee_cup": "桌上有它点的那杯咖啡，杯子大小与它的体型相称",
    "train_seat": "有列车座椅",
    "train_window": "有列车车窗",
    "audio_player": "它已经拥有的那个播放设备在旁边",
    "home_blanket": "它已经拥有的那条毯子在旁边",
    "harvested_crop": "它刚摘下的那样菜在爪边",
    "garden_bed": "打理过的菜畦",
    "landmark_in_view": "这个地标此刻确实在它的视线里",
    "held_snack": "它拿着的那份已经买到的小吃",
    "gym_mirror": "场馆里的落地镜",
    "own_device": "它自己的那台通讯器，没有品牌标识",
    "headphones": "它已经拥有的那副耳机",
    "gym_bench": "训练凳",
    "parked_vehicle": "停着的那辆车",
    "hand_tool": "它手边那件工具",
    "work_outfit": "它已经拥有的那身工作服",
    "flight_helmet": "它已经配备的小号飞行头盔",
    "safety_harness": "扣好的安全带",
    "earned_medal": "它已经获得的那枚勋章",
    "captain_hat": "它这次剧情里戴的船长帽",
    "ship_wheel": "舵轮",
    "winter_outfit": "它已经拥有的那身保暖衣物",
    "camp_light": "营地那盏暖灯",
    "aurora_visible": "此刻的天象记录确认极光可见",
    "photographer_present": "确实有一位同伴在场，并且获准拍这张照片",
    "weather_sunny": "拍摄时核验到晴天",
    "weather_rainy": "拍摄时核验到下雨",
    "weather_cloudy": "拍摄时核验到多云",
    "weather_snowy": "拍摄时核验到下雪",
})


# 这些是"现场前提"，不是画面里能看见的东西：同伴在场是一个条件，
# 但画面里恰恰**不该**出现拍摄者。所以它进 requires，不进 visible_facts。
NON_VISIBLE_FACTS = frozenset({"photographer_present"})


class Recipe(NamedTuple):
    scene: str
    camera: str
    composition: str
    action: str
    requires: frozenset          # 必须已核验的事实（含场景的 mandatory）
    story_modes: frozenset       # 只在这些叙事模式下可选
    expression: str              # 默认表情；DNA 可以覆盖
    affinity: frozenset          # 让这只宠物更像它自己的 DNA 编码
    subjects: int = 1            # 2 = 双宠合影，需要第二份身份参考与各自授权
    acceptance: tuple = ()       # 人审要点，进联系表，不是程序结论


RECIPES = MappingProxyType({
    # ---------- 日常 ----------
    "cafe_observe_selfie": Recipe(
        "cafe", "front_selfie", "table_corner",
        "在咖啡馆里自在地待着，抬头看向镜头",
        frozenset({"at_cafe"}), frozenset({"daily_life"}), "curious",
        frozenset({"personality:curious", "habits:sniff_objects", "preferences:quiet_corner"}),
        acceptance=("脸与花纹对得上", "店内空间看得出来", "没有人手")),
    "cafe_drink_selfie": Recipe(
        "cafe", "front_selfie", "table_corner",
        "在这个平行世界里享用自己点的那杯咖啡，嘴凑近杯口，用的是它本来的爪子和动物身体",
        frozenset({"at_cafe", "coffee_cup"}), frozenset({"daily_life"}), "pleased",
        frozenset({"interests:coffee_aroma", "personality:playful"}),
        acceptance=("杯子比例与它的体型相称", "杯底完整落在桌面", "爪子与杯子没有互相穿透")),
    "cafe_friendshot": Recipe(
        "cafe", "friend_camera", "table_corner",
        "听见同伴叫它，略微转头，身体与椅面接触自然，前爪搭在桌沿",
        frozenset({"at_cafe", "photographer_present"}), frozenset({"daily_life"}), "relaxed",
        frozenset({"personality:reserved", "preferences:quiet_corner"}),
        acceptance=("椅子承重正确", "室内外天气分层", "没有硬写成自拍")),
    "cafe_detail_pov": Recipe(
        "cafe", "detail_pov", "close_object",
        "低头看着桌上那杯咖啡，前爪搭在杯子旁边",
        frozenset({"at_cafe", "coffee_cup"}), frozenset({"daily_life"}), "focused",
        frozenset({"habits:sniff_objects"}),
        acceptance=("爪子是动物的爪子", "杯子与桌面接触正确", "没有硬把脸塞进特写")),
    "train_watch_selfie": Recipe(
        "train", "front_selfie", "window_journey",
        # 键名保留 `train_watch_selfie` 不改：已有的 8 张真图与联系表都按这个键绑定，
        # 改键会切断那份证据与配方的对应关系。实际要什么以动作句与人审要点为准。
        "把脸凑近镜头，车窗和窗外流动的景色留在身后，保持正常的动物姿势",
        frozenset({"on_train", "train_window"}), frozenset({"daily_life"}), "curious",
        frozenset({"habits:look_out_window", "interests:rail_travel", "preferences:wide_view"}),
        acceptance=("车厢空间看得出来", "车窗与景色在身后，不是它正在注视的方向",
                    "没有多余肢体", "没有变成人身")),
    "train_window_mount": Recipe(
        "train", "fixed_companion_camera", "window_journey",
        "靠窗坐着听自己那台设备里的声音，双前爪自然放着",
        frozenset({"on_train", "train_seat", "train_window", "audio_player"}),
        frozenset({"daily_life"}), "relaxed",
        frozenset({"interests:rail_travel", "personality:calm"}),
        acceptance=("固定机位不抢它的前爪", "设备是它已经拥有的那台", "窗外景色与行进方向一致")),
    "home_rest_candid": Recipe(
        "home", "fixed_companion_camera", "home_low",
        "在家里熟悉的位置休息",
        frozenset({"at_home"}), frozenset({"daily_life"}), "relaxed",
        frozenset({"personality:reserved", "preferences:quiet_corner"}),
        acceptance=("家里的陈设有连续性", "姿态熟悉", "没有影棚灯")),
    "home_curl_candid": Recipe(
        "home", "fixed_companion_camera", "home_low",
        "蜷在已经属于它的那条毯子旁边，是自然的动物睡姿",
        frozenset({"at_home", "home_blanket"}), frozenset({"daily_life"}), "relaxed",
        frozenset({"habits:curl_up", "interests:home_comfort", "personality:calm"}),
        acceptance=("毯子是它已有的那条", "睡姿是动物的睡姿", "身体与毯面接触正确")),
    "home_duo_candid": Recipe(
        "home", "fixed_companion_camera", "home_low",
        "和家里的另一位伙伴挨在一起休息",
        frozenset({"at_home"}), frozenset({"daily_life"}), "relaxed",
        frozenset({"interests:home_comfort"}), subjects=2,
        acceptance=("两只各自的身份都对得上", "没有把两只混成一只", "体型关系合理")),
    "courtyard_harvest_selfie": Recipe(
        "courtyard", "front_selfie", "garden_bed",
        "刚摘完菜，举着收成凑到镜头前给主人报个喜",
        frozenset({"at_courtyard", "harvested_crop"}), frozenset({"daily_life"}), "pleased",
        frozenset({"interests:gardening", "personality:playful"}),
        acceptance=("菜是这次真的收到的那样", "爪子握持是动物的握法", "院子是自己家的院子")),
    "courtyard_detail_pov": Recipe(
        "courtyard", "detail_pov", "close_object",
        "前爪扒着刚摘下的那样菜看",
        frozenset({"at_courtyard", "harvested_crop"}), frozenset({"daily_life"}), "focused",
        frozenset({"interests:gardening", "habits:sniff_objects"}),
        acceptance=("土与菜的质感真实", "爪子没有变成人手", "没有硬要露脸")),
    "landmark_front_selfie": Recipe(
        "landmark", "front_selfie", "landmark_behind",
        "把通讯器举得有点近，差点只拍到自己，地标刚好在身后",
        frozenset({"at_landmark", "landmark_in_view"}), frozenset({"daily_life"}), "startled_playful",
        frozenset({"interests:sightseeing", "personality:playful", "preferences:close_camera"}),
        acceptance=("地标确实可辨", "人群有自然的运动模糊", "脸与花纹对得上")),
    "landmark_duo_selfie": Recipe(
        "landmark", "front_selfie", "landmark_behind",
        "和刚认识的朋友挤进同一个镜头，两张脸都凑得很近",
        frozenset({"at_landmark", "landmark_in_view"}), frozenset({"daily_life"}), "startled_playful",
        frozenset({"interests:sightseeing", "personality:playful"}), subjects=2,
        acceptance=("两只各自的身份都对得上", "谁在举设备是清楚的", "地标没有被两只挡完")),
    "gym_mirror_standing": Recipe(
        "gym", "mirror_selfie", "mirror_full",
        "站在镜子前，一只前爪握着自己的设备、背面朝镜子，另一只前爪轻扶旁边墙面",
        frozenset({"at_gym", "gym_mirror", "own_device"}), frozenset({"daily_life"}), "focused",
        frozenset({"personality:playful", "preferences:close_camera"}),
        acceptance=("镜面反射的逻辑正确", "只有一组镜像", "身材没有被换成人体")),
    "gym_mirror_bench": Recipe(
        "gym", "mirror_selfie", "bench_seated",
        "坐在训练凳上低头调整耳机，另一只前爪握着设备",
        frozenset({"at_gym", "gym_mirror", "own_device", "headphones", "gym_bench"}),
        frozenset({"daily_life"}), "relaxed",
        frozenset({"personality:calm"}),
        acceptance=("凳面承重正确", "耳机是它已有的那副", "背景是普通场馆不是豪华棚景")),
    "workshop_mechanic_friendshot": Recipe(
        "workshop", "friend_camera", "work_side",
        "认真对付手边那件活，工具握在前爪里",
        frozenset({"at_workshop", "parked_vehicle", "hand_tool", "photographer_present"}),
        frozenset({"daily_life"}), "focused",
        frozenset({"interests:tinkering", "personality:curious"}),
        acceptance=("工具握法是动物的握法", "车与它的体型关系合理", "没有出现拍摄者")),
    # ---------- 虚构冒险 / 影视 ----------
    "cockpit_focus": Recipe(
        "flight_adventure", "fixed_cockpit", "cockpit_wide",
        "参与这次虚构的飞行任务，坐在按它体型缩放的座舱里，前爪在操纵区域",
        frozenset({"flight_adventure"}),
        frozenset({"fictional_adventure", "film_scene"}), "focused",
        frozenset({"personality:calm", "personality:curious"}),
        acceptance=("固定机位没有抢走驾驶的前爪", "座舱完整、它没有受伤", "脸的身份稳定")),
    "cockpit_helmet_actioncam": Recipe(
        "flight_adventure", "fixed_cockpit", "cockpit_wide",
        "戴着已经配备的飞行头盔、安全带扣好，头盔按它的耳朵结构自然贴合",
        frozenset({"flight_adventure", "flight_helmet", "safety_harness"}),
        frozenset({"fictional_adventure", "film_scene"}), "startled_playful",
        frozenset({"interests:flying", "personality:playful"}),
        acceptance=("头盔没有改掉脸型与毛色", "只有一种表情", "剧情没有被当成现实事件")),
    "pirate_deck_selfie": Recipe(
        "ship_deck", "front_selfie", "deck_wide",
        "戴着这次剧情的船长帽在甲板上自拍，另一只前爪扶着帽檐",
        frozenset({"on_ship_deck", "captain_hat"}),
        frozenset({"fictional_adventure", "film_scene"}), "startled_playful",
        frozenset({"personality:playful"}),
        acceptance=("帽子与耳朵的关系自然", "甲板与海面可辨", "它没有受伤")),
    "snow_patrol_friendshot": Recipe(
        "snow_field", "friend_camera", "snow_open",
        "穿着保暖衣物站在雪地里，认真地看向同伴的镜头",
        frozenset({"in_snow_field", "winter_outfit", "photographer_present"}),
        frozenset({"fictional_adventure", "film_scene"}), "focused",
        frozenset({"personality:calm"}),
        acceptance=("雪面有真实的踩踏痕迹", "衣物是它已有的那身", "没有冻伤或受苦的表现")),
    "aurora_camp_selfie": Recipe(
        "aurora_camp", "front_selfie", "night_sky",
        "在营地灯旁举起通讯器，把身后的极光一起拍进来",
        frozenset({"at_aurora_camp", "aurora_visible", "winter_outfit"}),
        frozenset({"daily_life", "fictional_adventure"}), "pleased",
        frozenset({"interests:sightseeing", "preferences:wide_view"}),
        acceptance=("极光是这次天象记录里确认过的", "夜景闪光与环境光同时成立", "脸仍然可辨")),
})


TARGET_SCENES = tuple(sorted(k for k, v in SCENES.items() if v.fact_source == "target"))


def scene_of(name: str) -> Scene:
    return SCENES[name]


def recipes_for_scene(scene: str) -> tuple[str, ...]:
    return tuple(sorted(key for key, recipe in RECIPES.items() if recipe.scene == scene))


def all_fact_tokens() -> frozenset[str]:
    return frozenset(FACT_TEXT)
