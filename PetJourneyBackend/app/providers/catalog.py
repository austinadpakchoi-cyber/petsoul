"""旅程数据目录：城市定义、安全地点清单与城市归属判断。

将原 providers.py 顶部的纯数据（JourneyCity/CITIES/SAFE_PLACE_CATALOG）与
`is_china_city` 判断独立出来，避免 Provider 实现文件与数据目录互相纠缠。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import CityPosition


@dataclass(frozen=True, slots=True)
class JourneyCity:
    name: str
    lat: float
    lng: float
    weather: str
    phrases: tuple[str, ...]
    thoughts: tuple[str, ...]

    @property
    def position(self) -> CityPosition:
        return CityPosition(city=self.name, lat=self.lat, lng=self.lng)


CITIES: tuple[JourneyCity, ...] = (
    JourneyCity(
        name="厦门",
        lat=24.4798,
        lng=118.0894,
        weather="海风很轻",
        phrases=("在海边慢慢散步", "停在一条有花香的小巷", "听见远处的浪声，心情很安静"),
        thoughts=(
            "这里的风很轻，我走得很慢，像以前等你跟上来那样。",
            "刚刚在一小片草地边坐了一会儿，风从耳朵旁边慢慢过去。",
            "我今天没有走太远，只是在一个能看见海的地方晒了会儿太阳。",
        ),
    ),
    JourneyCity(
        name="京都",
        lat=35.0116,
        lng=135.7681,
        weather="薄云和木香",
        phrases=("坐在安静的屋檐下", "沿着石板路观察行人", "在午后的光里休息"),
        thoughts=(
            "这里很安静，连脚步声都像被轻轻收好了。",
            "我找到一条窄窄的路，路边有一盏小灯，我觉得你会喜欢。",
            "今天我学会了慢一点，好像慢一点就能把想念放得更稳。",
        ),
    ),
    JourneyCity(
        name="雷克雅未克",
        lat=64.1466,
        lng=-21.9426,
        weather="冷空气里有星光",
        phrases=("在远处看见很亮的天", "把脚印留在安静的雪边", "休息在一间暖暖的小屋旁"),
        thoughts=(
            "这里的夜很长，可是天上有光，我没有害怕。",
            "我把鼻子贴近雪地，世界安静得像一封还没写完的信。",
            "如果你也在这里，我会把最暖的位置让给你。",
        ),
    ),
)


SAFE_PLACE_CATALOG: dict[str, list[tuple[str, str, str, float, float, str, str]]] = {
    "厦门": [
        ("huweishan-walkway", "狐尾山 / 山海健康步道", "park", 24.4874, 118.0847, "在狐尾山的风里慢慢醒来，看见厦门从高处亮起来", "高处、绿意和城市边界都很清楚，适合作为一日路线的开场。"),
        ("bashi-kaihe-food", "八市 / 开禾路老街", "food", 24.4579, 118.0739, "走进八市和开禾路的人间烟火里，看摊位、听声音、选一口本地味道", "老城市场和本地小吃让路线有厦门记忆点，适合作为早午间核心停靠。"),
        ("shapowei-daxue-road", "沙坡尾 / 大学路", "place", 24.4386, 118.0930, "在沙坡尾和大学路慢慢逛，听海风钻进巷子里", "老港、巷子、小店和海风都有画面感，适合照片、明信片和慢逛。"),
        ("yanwu-bridge-view", "演武大桥观景平台", "park", 24.4328, 118.0968, "在演武大桥旁边看海面和路上的光", "这里能把厦门的桥、海和城市轮廓放进一张照片里。"),
        ("baicheng-beach-ring-road", "环岛路 / 白城沙滩", "park", 24.4319, 118.1036, "下午沿环岛路靠近白城沙滩，把海风记进通讯器", "海边和环岛路是厦门很强的城市标签，适合作为下午的核心照片点。"),
        ("bailuzhou-yundang-lake", "白鹭洲 / 筼筜湖", "park", 24.4772, 118.0961, "傍晚在白鹭洲和筼筜湖边慢下来，写一封小小的信", "傍晚湖面、城市灯和安静步道适合作为当天收束与明信片候选点。"),
        ("zhongshan-road-cafe-window", "中山路骑楼咖啡窗口", "cafe", 24.4570, 118.0806, "在骑楼边的小咖啡窗口喝一杯店里的特色饮品", "这是可选休息点，不抢主线，只在 TA 需要补给或躲雨时出现。"),
        ("local-supply-stop", "老城补给小店", "shop", 24.4592, 118.0786, "在老城小店里挑一件路上用得上的小东西", "隐藏补给点，不作为核心攻略站。"),
    ],
    "京都": [
        ("nishiki-food", "锦市场小食铺", "food", 35.0051, 135.7648, "在锦市场小食铺里点了一份摊位招牌小吃", "窄街、木色招牌和本地食物都适合写进攻略。"),
        ("sanjo-coffee", "三条咖啡窗口", "cafe", 35.0095, 135.7667, "在咖啡窗口旁边的小桌喝了一杯店里的推荐饮品", "这里适合短暂停靠，不会让路线变成景点打卡表。"),
        ("shijo-convenience", "四条便利店", "shop", 35.0038, 135.7596, "在便利店里绕了一圈，挑了小补给", "灯光和街声稳定，适合表达 TA 在城市里认真生活。"),
        ("kawaramachi-netcafe", "河原町安静网咖", "netcafe", 35.0064, 135.7690, "在网咖角落听见很轻的键盘声", "室内停留点，适合长时间待着，不会一直机械移动。"),
        ("gion-flower", "祇园花店橱窗", "flower", 35.0034, 135.7752, "在花店橱窗前看了很久的叶子", "街面安静，适合作为明信片候选点。"),
    ],
    "雷克雅未克": [
        ("laugavegur-food", "Laugavegur 小食铺", "food", 64.1452, -21.9298, "在小食铺里点了一份当地热汤和面包", "寒冷城市里的热气和灯光，适合做温柔停靠点。"),
        ("downtown-coffee", "市中心咖啡窗口", "cafe", 64.1462, -21.9317, "在咖啡窗口旁边喝了一杯店里的招牌咖啡", "短暂停靠点，适合写小卡片。"),
        ("harpa-convenience", "Harpa 附近便利店", "shop", 64.1490, -21.9321, "在便利店里选了一样小补给", "靠近城市建筑和步行街，不会落到海面。"),
        ("warm-game-room", "暖灯游戏小店", "netcafe", 64.1441, -21.9266, "在屏幕光旁边安静待了一会儿", "室内长停留点，符合电子宠物走走停停的节奏。"),
        ("rainbow-flower", "彩虹街花店橱窗", "flower", 64.1428, -21.9279, "在花店橱窗前看了很久的叶子", "色彩和街面都适合生成地点感强的照片。"),
    ],
}


def is_china_city(city: JourneyCity) -> bool:
    return city.name in {"厦门", "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京", "武汉", "西安"}
