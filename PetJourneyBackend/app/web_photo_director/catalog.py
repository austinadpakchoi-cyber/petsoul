"""封闭词表：取景可以选，世界事实不能改。

键是稳定标识（用于校验与缓存），值是会被编译进提示词的中文片段。
改值 = 改照片长相，所以由 PROMPT_VERSION 标记版本；改键 = 改契约，需要迁移缓存键。

场景与配方在 `recipes.py`，这里只放"怎么拍"的词汇。

为什么用中文：配置的生图供应商是 Seedream（字节），现有线上提示词
（`web_journey/illustrations.py`）也是中文。一条提示词里中英混排会明显削弱遵循度。

摄影方向来自用户 2026-09-23 给的参考照片与 `PetSoul_Photo_Prompt_Pack_v1`，
外加公开的 Seedream 4/4.5 提示词指南。参考照共有、而旧模板恰好做反的三点：

  1. 背景要**认得出来**。地标、车厢、器械架、极光——你能看出它在哪。
     旧模板每张都写"背景虚化"，得到的是没有故事的证件照。
  2. 镜头**又广又近**。脸占画面大部分，鼻子与最近的前爪因透视显得稍大。
     这种畸变正是"它自己举着拍的"的来源。
  3. 照片**略微不完美**。手持的倾斜、人群的运动模糊、夜里的硬闪光。
     干净的影棚渲染一眼就假。

编译顺序（Seedream 指南：靠前的内容权重更高）：
主体+动作 → 镜头/构图 → 环境 → 光线 → 身份锁 → 事实；负面词单独一个字段。
"""
from types import MappingProxyType

PROMPT_VERSION = "photo-director-prompt-v2"

# --- 叙事模式：同一只宠物的日常、虚构冒险与影视片场必须分开 ---
STORY_MODES = frozenset({"daily_life", "fictional_adventure", "film_scene"})
STORY_MODE_TEXT = MappingProxyType({
    # 日常不需要声明——说了也不改变画面，只占长度。
    "daily_life": "",
    "fictional_adventure": "这是一次虚构冒险剧情，不是现实事件",
    "film_scene": "这是一幕影视创作画面，不是现实事件",
})

DNA_FIELDS = MappingProxyType({
    "personality": frozenset({"curious", "reserved", "playful", "calm"}),
    "habits": frozenset({"head_tilt", "curl_up", "look_out_window", "sniff_objects"}),
    "interests": frozenset({"coffee_aroma", "rail_travel", "home_comfort", "flying",
                            "gardening", "tinkering", "sightseeing"}),
    "preferences": frozenset({"quiet_corner", "wide_view", "close_camera"}),
})

SPECIES = frozenset({"dog", "cat", "rabbit", "hamster", "bird", "parrot"})
SPECIES_CN = MappingProxyType({
    "dog": "狗", "cat": "猫", "rabbit": "兔子",
    "hamster": "仓鼠", "bird": "小鸟", "parrot": "鹦鹉",
})

# 外貌取值。刻意保持封闭：这是**已确认**的特征，不是模型可以自由发挥的地方。
# 2026-09-23 补：原来只有黑/白/棕/橘四种毛色，遇到银渐层这类常见猫就描述不了。
APPEARANCE = MappingProxyType({
    "black_coat": "黑色毛", "white_coat": "白色毛", "brown_coat": "棕色毛",
    "orange_coat": "橘色毛", "grey_coat": "灰色毛", "silver_coat": "银灰色毛",
    "cream_coat": "奶油色毛",
    "tabby_markings": "虎斑花纹", "ticked_coat": "细密的渐层针毛",
    "white_chest": "胸口一块白毛", "white_belly": "白色的肚子",
    "brown_eyes": "棕色眼睛", "green_eyes": "绿色眼睛", "amber_eyes": "琥珀色眼睛",
    "pink_nose": "粉色鼻头",
    "floppy_ears": "垂耳", "upright_ears": "立耳", "white_paws": "白色爪子",
    "long_whiskers": "很长的白胡须",
})

# --- 六种镜头模式：互斥编译 ---
# 关键在于"谁在拍"。旧链路的毛病是不管哪种情形都统一追加 first-person selfie，
# 于是驾驶舱里的宠物也被要求腾出一只前爪举相机。
CAMERAS = MappingProxyType({
    "front_selfie": "它自己举着拍的前置广角自拍：脸占画面大部分，鼻子和前爪因广角显得稍大，一只前爪伸向画面边缘外",
    "mirror_selfie": "镜像自拍：整张画面是镜中的反射，只有一组镜像，不要在镜外再复制一个它",
    "friend_camera": "在场同伴拍的生活照，视线高度、距离稍远，它双前爪自由，画面里没有拍摄者",
    "fixed_companion_camera": "桌面或支架上的固定机位，它双前爪完全自由，没有举相机的动作",
    "fixed_cockpit": "仪表台上的固定机位朝向它，运动相机式广角近景，前爪留在操纵区域",
    "detail_pov": "第一人称细节特写：主要是它的前爪与手边的物件，脸可以不完整入镜",
})
# 手机/设备在画面里的状态，按镜头模式分别声明，避免互相污染
CAMERA_DEVICE = MappingProxyType({
    "front_selfie": "设备在画外",
    "mirror_selfie": "镜中可见设备背面，无品牌标识",
    "friend_camera": "画面里没有手机",
    "fixed_companion_camera": "画面里没有手机",
    "fixed_cockpit": "画面里没有手机",
    "detail_pov": "画面里没有手机",
})
# 需要"确实有人在场拍"的镜头。没有这条事实就不能选这种镜头，不能虚构一个摄影者。
CAMERAS_NEEDING_PHOTOGRAPHER = frozenset({"friend_camera"})
# 需要"它自己拥有可用设备"的镜头
CAMERAS_NEEDING_DEVICE = frozenset({"front_selfie", "mirror_selfie"})
# 脸可能不完整入镜的镜头：身份锁要相应放宽，不能声称"脸型一致"
CAMERAS_WITHOUT_FACE = frozenset({"detail_pov"})

LENS = MappingProxyType({
    "front_selfie": "24mm 广角手持，光圈约 f/2.8，近大远小的透视明显",
    "mirror_selfie": "26mm 手持，光圈约 f/2.2，镜面反射的清晰度略低于直接拍摄",
    "friend_camera": "35mm 手持，光圈约 f/2.8，景深适中",
    "fixed_companion_camera": "35mm 固定机位，光圈约 f/2.8，画面稳定",
    "fixed_cockpit": "20mm 固定广角，光圈约 f/2.8，边缘有轻微畸变",
    "detail_pov": "28mm 近摄，光圈约 f/2.0，对焦在手边的物件上",
})

COMPOSITIONS = MappingProxyType({
    "table_corner": "它靠近画面一侧的桌沿，身后留出店内空间",
    "window_journey": "车窗和座椅把它框在画面里，车厢往后延伸出纵深",
    "home_low": "低机位的亲近构图，家里熟悉的角落仍然看得见",
    "cockpit_wide": "座舱内的较宽视角，按它的体型缩放，脸和原本的身体都完整可见",
    "landmark_behind": "它占据画面前景中央，地标在它身后完整可辨，中间有走动的人群",
    "mirror_full": "落地镜里它的完整身形，背景是场馆的真实陈设",
    "bench_seated": "它坐在器械凳上，镜中能看到凳面与它接触的关系",
    "work_side": "从侧前方拍，它和正在处理的部件在同一个画面里",
    "garden_bed": "它在菜畦旁，身后是打理过的院子",
    "deck_wide": "甲板与桅杆在它身后展开，远处能看到海面",
    "snow_open": "开阔雪地，它在画面中景，脚下有真实的踩踏痕迹",
    "night_sky": "它在画面下方偏一侧，上方留给夜空",
    "close_object": "物件在画面近处占主要面积，它的前爪与之接触",
})

EXPRESSIONS = MappingProxyType({
    "curious": "专注好奇的表情，耳朵朝前",
    "relaxed": "放松的表情，眼神柔和",
    "head_tilt": "自然地微微歪头",
    "focused": "专注自在，没有害怕或受伤",
    "pleased": "带着点得意的神气",
    "startled_playful": "眼睛略睁大、嘴微张的惊讶，是好玩的那种，不是害怕",
})

# --- 背景可读性：与旧模板最大的差别 ---
BACKGROUND_RULE = "背景轻微失焦但仍认得出是哪里，不要糊成纯色或证件照"

# --- 时段 -> 光线。由事件的当地墙上时间推出，不是生成时刻。---
DAYPARTS = (
    (5, 7, "dawn"), (7, 11, "morning"), (11, 15, "midday"),
    (15, 17, "afternoon"), (17, 19, "golden"), (19, 21, "dusk"),
)
NIGHT_DAYPARTS = frozenset({"night", "dusk"})
DAYPART_LIGHT = MappingProxyType({
    "dawn": "清晨青蓝微光，阴影柔和",
    "morning": "上午自然光，方向清楚，阴影干净",
    "midday": "正午顶光，对比强，阴影短而硬",
    "afternoon": "下午侧光，暖调，影子拉长",
    "golden": "黄金时刻低角度暖光，带一圈轮廓光",
    "dusk": "黄昏蓝调时分，环境灯已亮",
    "night": "夜晚，脸被相机闪光灯打亮略过曝，背景只剩点点暖灯",
})

# --- 天气 -> 光线与空气。只有被核验过的天气才会进来，且必须按空间与昼夜分层。---
WEATHER_LIGHT = MappingProxyType({
    "weather_sunny": "晴天，阳光直接，阴影边缘清晰",
    "weather_rainy": "下雨，空气发灰，表面湿亮反光",
    "weather_cloudy": "多云，光被云层散开，没有硬阴影",
    "weather_snowy": "在下雪，空气发白，地面积雪反光",
})
# 夜里没有太阳。不分开写，"晴天，阳光直接"会出现在半夜的照片里。
WEATHER_NIGHT = MappingProxyType({
    "weather_sunny": "夜空晴朗，能看见星星",
    "weather_rainy": "夜里在下雨，灯光在湿地面上拉出反光",
    "weather_cloudy": "夜里多云，天光被云挡住",
    "weather_snowy": "夜里在下雪，雪花在灯光里看得见",
})
# 室内：天气只出现在窗外，室内的它和陈设保持干燥。
# 毛湿、爪印这类痕迹要有"此前确实淋过雨"的事件支持，不能由当下天气推出来。
WEATHER_INDOOR = MappingProxyType({
    "weather_sunny": "窗外是晴天，室内是自然的窗光",
    "weather_rainy": "窗外在下雨，雨滴在窗玻璃外侧，街面有相符的反光；室内的它和座位保持干燥",
    "weather_cloudy": "窗外多云，室内光线柔和，没有硬阴影",
    "weather_snowy": "窗外在下雪，室内的它和座位保持干燥温暖",
})
WEATHER_INDOOR_NIGHT = MappingProxyType({
    "weather_sunny": "窗外是晴朗的夜空，室内是灯光",
    "weather_rainy": "窗外夜里在下雨，雨滴在窗玻璃外侧；室内的它和座位保持干燥",
    "weather_cloudy": "窗外夜里多云，室内是灯光",
    "weather_snowy": "窗外夜里在下雪，室内的它和座位保持干燥温暖",
})
WEATHER_TOKENS = frozenset(WEATHER_LIGHT)

IMPERFECTION = "随手拍的质感：轻微手抖、画面不完全水平、少量运动模糊与噪点"

# 物理接触：生图模型最容易在这里露馅——杯子悬空、爪子穿过桌面、坐着却没有承重。
CONTACT_RULE = "统一的透视与接触阴影：身体自然承重，爪子、器物与台面互不穿透"
# 表情只要一种。同时要求"惊讶又镇定"会得到一张两边都不像的脸。
SINGLE_EXPRESSION_RULE = "只用一种表情，不要同时要求多个矛盾表情"

# --- 身份锁 ---
IDENTITY_RULE = (
    "必须和参考图是同一只{animal}：脸型、口鼻长度、耳形、鼻色、眼色、毛色花纹与身体比例一致，"
    "不要换成同品种的另一只。参考图只定长相，不抄姿势和背景；完整重绘，不是拼贴"
)
# 脸可能不入镜时，不能声称脸型一致——那会让模型硬把脸塞进特写里。
IDENTITY_RULE_NO_FACE = (
    "画面里出现的部分必须和参考图是同一只{animal}：毛色、花纹、爪形与身体比例一致。"
    "参考图只定长相，不抄姿势和背景；完整重绘，不是拼贴"
)
ANATOMY_RULE = "保持真实动物结构，拿东西用爪子和嘴，不要画成人手或人形"
# 参考照没拍到的部位，不许自己发明醒目标记——那会让主人觉得"这不是我的那只"。
UNSEEN_MARKS_RULE = "参考图没拍到的部位保持普通，不添加新花纹或配饰"

# --- 负面提示词。与正向分开发送。---
NEGATIVE = (
    "卡通, 插画, 3D渲染, 动漫, 拟人化的人脸, 人手, 人类手指, 人的身体, "
    "多余的肢体, 缺少肢体, 扭曲变形的脸, 融化的五官, 多只眼睛, "
    "拼贴, 抠图, 贴纸, 水印, 文字, 字幕, 商标, 品牌标志, 可读的招牌, "
    "截图黑边, 关闭按钮, 页码角标, 平台账号, 界面控件, "
    "纯色背景, 白色影棚背景, 证件照, 完全糊掉的背景, "
    "受伤, 流血, 恐怖, 惊吓"
)

# --- DNA -> 画面表现。DNA 只改动作、姿态和取景，绝不改身份或地点。---
HABIT_TEXT = MappingProxyType({
    "head_tilt": "习惯微微歪头",
    "curl_up": "习惯把身体蜷起来",
    "look_out_window": "喜欢往窗外看",
    "sniff_objects": "习惯先凑近闻一闻",
})
PREFERENCE_FRAMING = MappingProxyType({
    "quiet_corner": "放在画面靠边、安静的位置",
    "wide_view": "多留一些环境纵深",
    "close_camera": "脸再凑近镜头一些",
})
PERSONALITY_POSE = MappingProxyType({
    "curious": "姿态往前探",
    "reserved": "姿态收着、安静",
    "playful": "姿态活跃",
    "calm": "姿态沉稳",
})
# 镜头模式已经决定了视线落在哪，和它直接冲突的习惯不再作为 DNA 子句发出。
# **不是说自拍里不能有窗外**——landmark / aurora 的自拍就把景色放在身后；
# 是同一句提示里不能既要求看镜头、又要求看别处，那样模型只能二选一。
CAMERA_CONFLICTING_HABITS = MappingProxyType({
    "front_selfie": frozenset({"look_out_window"}),
})
# 表情文案已经表达过的习惯，不再作为 DNA 子句重复
EXPRESSION_COVERS = MappingProxyType({
    "head_tilt": frozenset({"head_tilt"}),
    "curious": frozenset(),
    "relaxed": frozenset(),
    "focused": frozenset(),
    "pleased": frozenset(),
    "startled_playful": frozenset(),
})
# 构图文案里已经点名的物件，不必在事实清单里再说一遍（提示词越短越守得住）
COMPOSITION_IMPLIES = MappingProxyType({
    "window_journey": frozenset({"train_seat", "train_window"}),
    "mirror_full": frozenset({"gym_mirror"}),
    "bench_seated": frozenset({"gym_mirror", "gym_bench"}),
    "landmark_behind": frozenset({"landmark_in_view"}),
    "garden_bed": frozenset(),
    "deck_wide": frozenset(),
    "snow_open": frozenset(),
    "night_sky": frozenset(),
    "work_side": frozenset(),
    "table_corner": frozenset(),
    "home_low": frozenset(),
    "cockpit_wide": frozenset(),
    "close_object": frozenset(),
})


def daypart_for(hour: int) -> str:
    """当地墙上小时 -> 时段。超出白天区间的一律按夜晚处理。"""
    for start, end, name in DAYPARTS:
        if start <= hour < end:
            return name
    return "night"
