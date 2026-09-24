"""世界角色的提示词：按 P（ada5）《世界角色导演模式》编译——中性姿态按 2.2／2.4，其余五个姿态按 §6-5。

规范：`docs/coordination/WORLD-CHARACTER-DIRECTOR-SPEC-ada5.md`。**依据的是哪一版，以本窗口日志登记的指纹为准**；
代码里不抄指纹——抄了就会过期，这里上一版就停在一个 277 行的旧指纹上。

**这是临时自持的那一份**：等 P 把角色用途做进 `web_photo_director` 的编译器，
`service.py` 只需要把 `compile_prompt` 换成 P 的入口，本文件就可以退场。
调用点收在一处，就是为了到时候只改那一处。

身份锁 / 未见部位 / 解剖三句**逐字复用** P 的 `catalog` 常量（规范 2.2 第 72 行的要求）：
同一套词表出两种产物，将来 P 改一处，照片链路和角色链路一起跟着改，不会分叉。

### 两条不能做反的

  1. **提示词里一个字都不提"透明"**（规范 2.3）。模型没有 alpha 概念，会把"透明"当成一种
     **视觉图案**，把灰白棋盘格画进 RGB，得到一张完全不透明、却印着棋盘格的 PNG。
     透明是请求参数 `background` 的职责，不是这里的职责。
     钉着它的：`test_web_character_autostart.py::test_the_prompt_never_asks_for_transparency`（中性姿态），
     `test_web_character_pose_prompts.py` 的禁用字表（其余五个姿态，「透明」「棋盘」都在表里）。
     透明底现在**按调用请求**（`service._draw` 传 `background="transparent"`），棋盘格那一支因此可达，
     由 `validate` 的检测器判出 `checkerboard_drawn`——不再靠"不请求透明"让它到不了。
  2. **脚下不画地面、不画影子**（规范 2.3 末）。阴影画进角色图，它会跟着角色走进每一个场景，
     而且永远对不上那里的光。角色本体／地面阴影／场景前景是三层，阴影归渲染组件。

### 一处与 P 那边重复的措辞，靠一条跨包不变量守住

`_appearance_clause` 那句「参考图里已确认的特征：…」在 P 的 `compiler.py` 里是**私有**函数。
我没有跨包 import 私有名（P 改名就会断），而是重抄了这一句模板；
**词表本身（`APPEARANCE`）仍然只有 P 那一份**，分叉风险只落在这十几个字的连接句上。

P 的建议（我采纳）：与其把它提成公开符号，不如写一条**跨包不变量用例**逐字比两边的产物——
提成公开只防"改名"，**不防两边措辞各自漂移**，而那条用例两样都防，
且在**任何一边**改动时当场响。见 `test_web_character_publish.py::test_the_appearance_clause_matches_the_photo_directors`。

### `appearance_tags` 目前全链路为空，如实记下

`photo_director_bridge.py:148` 也传 `()`，**全仓没有任何地方在产出这个字段**。
P 规范 §6-2 那个 6 标签实例的标签来自手工写的 `test-pet-spec.json`，**不是运行时供给的**（P 已在规范里更正）。
这里留了 `CharacterService.appearance_tags_of(pet_id)` 钩子，默认空；数据源归属待指派。

### 批次二：五个姿态（§6-5）

`build_pose_prompt` 与中性姿态同构（六段、同一顺序、同一身份锁与未见部位句），**有三处固定文字不同**，理由在规范里：

  - 第 1 段不再写「头、耳、四肢与尾巴都在画面内」：蜷睡时四肢收在身下、鸟睡觉一只脚收进羽毛，这句会和姿态打架；
    防裁断改由各姿态的取景句（「不要触到画面边缘」）负责；
  - 解剖句换成**对爪子的正面描述**（`PAW`），紧跟在姿态句后面，第 5 段只留结构那半句——
    「拿东西用爪子和嘴」在吃东西里暗示爪里拿着食物，「人手」「人形」在回应抚摸里暗示一只人手；
  - 留空句去掉「托盘或底座」：「托盘」在吃东西时同样暗示器皿。

**状态名和道具名都不进提示词**（`POSE_FORBIDDEN`）：晒太阳不写阳光，吃东西不写碗，回应抚摸不写手——
写了模型就会画进精灵。光和道具归场景层，抚摸归交互层。30 条（5 姿态 × 6 物种）由用例逐条查。

**批次一的解剖句本批不改**：改了就是改正式中性姿态的产出。而真实测试里站姿用的正是旧句、五个姿态用的是 `{paw}`，
两句并存恰好是测过的那个组合（各 n=1）。统一措辞留到额外姿态的开关打开时一并定，届时单独出图验证（P 同意，已写进规范）。
"""

from __future__ import annotations

from ..web_photo_director.catalog import (
    ANATOMY_RULE,
    APPEARANCE,
    IDENTITY_RULE,
    SPECIES,
    SPECIES_CN,
    UNSEEN_MARKS_RULE,
)

# 首批：每个物种只做这一个中性姿态。猫狗兔鼠鸟的骨架不同，不硬套同一句（规范 2.4）。
POSES = {
    "cat": "四足自然站立，重心均匀，头部平视前方，尾巴自然下垂或微扬",
    "dog": "四足自然站立，重心均匀，头部平视前方，尾巴自然下垂或微扬",
    "rabbit": "四足着地伏踞，耳朵自然竖起，身体放松",
    "hamster": "四足站立，身体略微前倾，短尾自然",
    # 鸟类**不画栖木**：栖木是物件，属于场景层，画进角色图会跟着它进到每一个场景里。
    "bird": "双脚并立站定，翅膀收拢贴身，尾羽自然下垂",
    "parrot": "双脚并立站定，翅膀收拢贴身，尾羽自然下垂",
}
# 竖幅。**不要复用照片链路的 2048x2048**——`GPTIllustrator.render` 会把它映射成 1024x1024，
# 方画幅逼着模型裁身体或把主体缩小（规范 4.1）。1024x1536 在 GPT 白名单里，原样透传。
CANVAS = "1024x1536"
STYLE_VERSION = "character-v1"
# 第 4 段光照句：**每一个姿态都用这同一句，不因状态而放宽**（规范 §6-4 规则二）。
# 晒太阳最容易做错成把阳光画进精灵——那只猫到了晚上还在发光。光归场景层。
NEUTRAL_LIGHT = "均匀柔和的中性光，没有明显方向性投影，身体本身的明暗过渡自然，毛色在光下仍是参考图里的那个颜色"

# ---- 批次二（规范 §6-5）：下面的表格单元是**逐字使用的原文**，与规范逐字节比对过 ----
# 键名与契约 `schemas/web/character.py::CharacterPose` 是**同一个词**，不做映射。
EXTRA_POSES = ("sleeping", "sunbathing", "eating", "walking", "petted")
# 画幅跟着身体轮廓走：蜷着的是方的，舒展躺平与迈步是横的。三种都在 `GPTIllustrator.render` 的白名单里。
POSE_CANVAS = {
    "sleeping": "1024x1024",
    "sunbathing": "1536x1024",
    "eating": "1024x1024",
    "walking": "1536x1024",
    "petted": "1024x1536",
}
POSE_FRAMING = {
    "sleeping": "正面略偏的四分之三角，略高于身体的视角，方形构图；四周各留出约一成空白，身体不要触到画面边缘",
    "sunbathing": "侧前方视角，略高于身体，横幅构图；四周各留出约一成空白，舒展的四肢和尾巴都不要触到画面边缘",
    # 口鼻前方那块空白是给场景层放食盆的——这里只说"留一块空白"，不说"放食盆"
    "eating": "侧前方视角，平视偏高，方形构图；口鼻前方与下方留出一块空白，身体不要触到画面边缘",
    "walking": "纯侧面视角，平视高度，横幅构图；四周各留出约一成空白，抬起的脚和尾巴都不要触到画面边缘",
    "petted": "正面略偏的四分之三角，平视高度，竖幅构图；头顶上方多留一些空白，身体不要触到画面边缘",
}
_CAT_DOG = {
    "sleeping": "蜷成一团侧卧，下巴搭在前爪上，尾巴绕到身前，眼睛闭着，呼吸平稳",
    "sunbathing": "眼睛半眯，侧身平躺，头也侧着放平、不抬起，四肢自然向外舒展，肚子微微朝外，全身完全松弛",
    "eating": "四足站立，低头把口鼻凑到接近前爪的高度，脖子向前下方伸出，耳朵朝前，专注的神情",
    "walking": "朝画面右侧迈步，一侧前腿抬起，对侧后腿蹬地，重心略微偏前，尾巴自然扬起",
}
_BIRD = {
    "sleeping": "身体蓬起，头转向后方埋进背部羽毛，单脚站立，另一只脚收进腹部羽毛里",
    "sunbathing": "一侧翅膀向外半张开，羽毛蓬松，头微微偏向一侧，眼睛半闭",
    "eating": "身体前倾，头低下，喙朝向身前下方",
    "walking": "朝画面右侧迈步，一只脚抬起，身体前倾",
    "petted": "头低下并偏向一侧，颈后与头顶的羽毛蓬起，眼睛半闭",
}
# 「回应抚摸」猫与狗分开写：猫眯眼偏头，狗耳朵后贴、嘴微张。兔子「走动」写成跳——兔子不是走路。
POSE_TEXT = {
    "cat": {**_CAT_DOG, "petted": "坐着，头微微上仰并向一侧偏，眼睛满足地眯起，耳朵放松朝两侧，身体轻轻前倾"},
    "dog": {**_CAT_DOG, "petted": "坐着，头上仰，耳朵放平贴向脑后，嘴微微张开，尾巴扬起"},
    "rabbit": {
        "sleeping": "伏成圆圆的一团，四肢收在身下，耳朵放平贴在背上，眼睛闭着",
        "sunbathing": "侧身翻躺，后腿向后伸直，前爪放松，眼睛半眯",
        "eating": "伏在地上，头低下，嘴部朝向身前下方，耳朵自然竖起",
        "walking": "朝画面右侧，后腿蹬地、前爪刚离地，身体微微拉长，正要跳出去",
        "petted": "伏在地上，眼睛半闭，耳朵放松贴在背上，身体完全放松",
    },
    "hamster": {
        "sleeping": "蜷成一个小球，脸埋在身前，眼睛闭着",
        "sunbathing": "整个身体趴平，四肢向四周摊开，眼睛半眯",
        # 已知局限（规范 §6-5 第 3 件）：仓鼠吃东西本该两爪捧着食物，提示词不写食物，爪里就空着——
        # 要么渲染层在爪间叠一小块食物，要么换个表达。**不在这里写"食物"**，那会违反禁用字。
        "eating": "直立坐起，两只前爪合拢举在嘴前，脸颊微鼓",
        "walking": "朝画面右侧快步小跑，四只短腿交替迈开",
        "petted": "直立坐起，头微微上仰，前爪轻轻抬起",
    },
    "bird": _BIRD,
    "parrot": _BIRD,
}
# 对爪子的**正面**描述，紧跟在姿态句后面。不出现"手""人""拿"——那几个字在回应抚摸、吃东西里都会被连到别处。
PAW = {
    "cat": "前爪是猫的圆爪垫和短趾",
    "dog": "前爪是狗的圆爪垫和短趾",
    "rabbit": "爪子是兔子毛茸茸的圆爪",
    "hamster": "前爪是仓鼠细小的粉色小爪",
    "bird": "脚是鸟的细爪",
    "parrot": "脚是鹦鹉的细爪",
}
# 批次二的第 5 段：只留结构那半句（`ANATOMY_RULE` 里「拿东西用爪子和嘴，不要画成人手或人形」不要了）。
POSE_ANATOMY = "保持真实动物结构，四肢与尾巴同身体的连接清楚，没有多余肢体"
# 编译出的批次二提示词里**一个都不得出现**（规范 §6-5 的可执行不变量）。
POSE_FORBIDDEN = ("阳光", "太阳", "晒", "吃", "食", "碗", "盆", "床", "窝", "毯", "垫子", "手", "人", "摸", "抚", "光斑", "透明", "棋盘")


def supported(species: str) -> bool:
    """物种在封闭词表里、且首批给了姿态句，才编译得出来。`other` 一律 False —— **不猜**。"""
    return species in SPECIES and species in POSES


def _appearance_clause(tags: tuple[str, ...]) -> str:
    named = [APPEARANCE[tag] for tag in tags if tag in APPEARANCE]
    return "参考图里已确认的特征：" + "、".join(named) + "。" if named else ""


def build_character_prompt(species: str, appearance_tags: tuple[str, ...] = ()) -> str:
    """六段固定顺序：主体与姿态 → 身份锁 → 取景画幅 → 光照 → 解剖 → 留空（规范 2.1）。

    身份锁**紧跟主体**：角色图没有场景段占位，身份排到后段脸型会漂移（规范 2.1 第 50 行的实测结论）。
    """
    if not supported(species):
        raise ValueError(f"物种不在封闭词表里，不编译：{species!r}")
    animal = SPECIES_CN[species]
    return (
        f"写实摄影级的角色立绘：一只真实的{animal}，{POSES[species]}，"
        f"全身完整入画，头、耳、四肢与尾巴都在画面内。"
        f"{IDENTITY_RULE.format(animal=animal)}。"
        f"{_appearance_clause(appearance_tags)}{UNSEEN_MARKS_RULE}。"
        # 取景句**改过一次**（P 规范 §2.2，2026-09-23）：原句只写「头顶与脚底各留出约一成空白」，
        # 没要求左右——真实成图里尾巴尖横着伸出去，离右边 17px（1.66% < 2%），被判 `subject_cut_off`。
        # 看图身体并没被裁，是代理指标触发；**改的是因（提示词），不是测量（2% 阈值没动）**。
        # 改后同一参考重出，右边距 3.81%，校验通过（各 n=1）。
        f"正面略偏的四分之三角，平视高度，竖幅构图；四周各留出约一成空白，身体和尾巴都不要触到画面边缘。"
        f"{NEUTRAL_LIGHT}。"
        f"{ANATOMY_RULE}。四肢与尾巴同身体的连接清楚，没有多余肢体。"
        f"画面里只有这一只{animal}，脚下不画地面、不画影子、不画托盘或底座，主体之外整片留空。"
    )


def pose_supported(species: str, pose: str) -> bool:
    """批次二：物种在封闭词表里、且这个姿态给了该物种的姿态句。"""
    return supported(species) and pose in POSE_CANVAS and pose in POSE_TEXT.get(species, {})


def build_pose_prompt(species: str, pose: str, appearance_tags: tuple[str, ...] = ()) -> str:
    """批次二的五个姿态（规范 §6-5 模板）。与中性姿态同构，三处固定文字不同，见模块抬头。

    参考图是**同一套里已生效的中性姿态**（压在灰底上发），不是主人原照——那一层在 `poses.py`，不在这里。
    """
    if not pose_supported(species, pose):
        raise ValueError(f"姿态或物种不在词表里，不编译：{species!r} {pose!r}")
    animal = SPECIES_CN[species]
    return (
        f"写实摄影级的角色立绘：一只真实的{animal}，{POSE_TEXT[species][pose]}，{PAW[species]}，全身完整入画。"
        f"{IDENTITY_RULE.format(animal=animal)}。"
        f"{_appearance_clause(appearance_tags)}{UNSEEN_MARKS_RULE}。"
        f"{POSE_FRAMING[pose]}。"
        f"{NEUTRAL_LIGHT}。"
        f"{POSE_ANATOMY}。"
        f"画面里只有这一只{animal}，脚下不画地面、不画影子，主体之外整片留空。"
    )


# ---- 证件照（CR-6C2B-IDPHOTO，用户 2026-09-24 定：新宠物自动生成、默认开）----
# 按 P《宠物证件照导演规范》（`docs/coordination/ID-PHOTO-DIRECTOR-SPEC-ada5.md`）§二 逐字编译；依据的版本以本窗口日志登记为准。
# 三条不能做反的（规范 §一、§六）：
#   - **不写"证件""护照""照片"这类字，也不写宠物名字**：写了模型就会画出一张带边框、带字的证件卡（同角色那边"透明"会被画成棋盘格）；
#   - **推荐路线不写底色**：请求透明底，发布时合成到界面常量（模型画不准色值，颜色词还会染到毛色）；
#   - **取景写成几何位置**：下巴大约在画面高度一半，从上方裁 1024 正方形做头像时头是完整的。
ID_PHOTO_CANVAS = "1024x1536"
ID_PHOTO_STYLE_VERSION = "id-photo-p1"  # p1＝照 P 的规范第一版编译
ID_PHOTO_FACE = {
    "cat": "正脸朝向镜头，双眼平视镜头，嘴巴闭着，耳朵保持参考图里的样子，神情平静",
    "dog": "正脸朝向镜头，双眼平视镜头，嘴巴闭着，耳朵保持参考图里的样子，神情平静",
    "rabbit": "正脸朝向镜头，两只眼睛都看得见，嘴巴闭着，耳朵保持参考图里的样子，神情平静",
    "hamster": "正脸朝向镜头，双眼看向镜头，嘴巴闭着，神情平静",
    # 鸟改四分之三侧脸：眼睛长在头两侧，正脸反而看不清眼睛
    "bird": "头部四分之三侧向镜头，靠近镜头的那只眼睛清楚地看着镜头，喙合拢，羽毛整齐",
    "parrot": "头部四分之三侧向镜头，靠近镜头的那只眼睛清楚地看着镜头，喙合拢，羽毛整齐",
}
# 编译出的证件照提示词里**一个都不得出现**（规范 §六）
ID_PHOTO_FORBIDDEN = ("证件", "证", "护照", "驾照", "居民", "身份", "照片", "相片", "卡", "文字", "字母", "边框", "相框", "水印",
                      "印章", "条码", "二维码", "头像", "透明", "棋盘")


def build_id_photo_prompt(species: str, appearance_tags: tuple[str, ...] = (), *, opaque: bool = False) -> str:
    """规范 §二 的模板。`opaque=True` 是 §4.3 的备选路线（适配器不请求透明时）：**只换最后一句**，颜色词只出现这一次、放在最后。"""
    if not supported(species) or species not in ID_PHOTO_FACE:
        raise ValueError(f"物种不在封闭词表里，不编译：{species!r}")
    animal = SPECIES_CN[species]
    last = (f"画面里只有这一只{animal}的头部和上半身，身后是一整片均匀的浅灰蓝色，没有纹理、没有渐变。" if opaque
            else f"画面里只有这一只{animal}的头部和上半身，主体之外整片留空。")
    return (
        f"写实摄影级的近景：一只真实的{animal}，只拍头部和上半身，{ID_PHOTO_FACE[species]}。"
        f"{IDENTITY_RULE.format(animal=animal)}。"
        f"{_appearance_clause(appearance_tags)}{UNSEEN_MARKS_RULE}。"
        f"平视高度，竖幅构图；头部位于画面上半部、左右居中，耳尖或头顶上方留出少量空白，"
        f"下巴大约在画面高度的一半，胸口向下自然延伸到画面底边。"
        f"均匀柔和的正面光，脸上没有明显阴影，毛色在光下仍是参考图里的那个颜色，毛发细节清晰。"
        f"保持真实动物的脸部与身体结构。"
        f"{last}"
    )
