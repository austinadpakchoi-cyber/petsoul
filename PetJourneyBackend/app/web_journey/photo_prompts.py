"""写实照片的提示词构造（从 illustrations.py 拆出来，见 COORD-A-ATOMIC：为给原子登记腾出定义数）。

这里只负责"把事实拼成一句提示词"，不碰数据库、不排队、不调供应商。
照片要写实，不把宠物卡通化——它是宠物，不是人（用户 2026-09-22）。
规则照片导演接进来之后，编译好的提示词会走同一批入口，这些构造器仍是没有导演时的兜底。
"""

from __future__ import annotations

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
SPECIES_EN = {"cat": "cat", "dog": "dog", "rabbit": "rabbit", "hamster": "hamster", "bird": "small bird", "parrot": "parrot", "other": "small animal"}


def build_prompt(*, species: str, name: str, personality: str | None, title: str, story: str, with_reference: bool) -> str:
    """冒险插画的英文写实提示词。

    - **名字不进提示词**（与自拍、证件照同一理由：名字最容易被画成招牌上的字；是不是同一只靠参考图）。`name` 仍收着，只是不用；
      冒险故事也由调用方用「这只{种类}」渲染（`illustrations._render`），名字不会从 story 混进来。
    - **招牌与文字用正面写法**：GPT 和方舟都不支持 negative_prompt，把 text、signs、logos 写出来反而可能招来。
      这句**未经出图验证**（P），是押注，不是已验证的修复。
    """
    who = f"a {SPECIES_EN.get(species, 'small animal')}"
    # 用户 2026-09-22：照片要写实，不把宠物卡通化——它是宠物，不是人。
    parts = [
        "Photorealistic photograph, natural light, real camera look, shallow depth of field.",
        f"Main subject: {who}, a real animal" + (f" (personality: {personality})" if personality else "") + ", with normal animal anatomy and posture.",
        f"Scene ({title}): {story} Show it as a believable real-life moment; small props or a tiny accessory are fine, but the pet stays a real animal.",
        "Not a cartoon, not an illustration, not anthropomorphic. No people, no human hands, no phones. "
        "Any signs or screens are blank or hidden behind foreground objects; object surfaces are plain. Single image, the pet clearly visible.",
    ]
    if with_reference:
        parts.insert(2, "It must be the same individual as in the reference photo (image 1): same fur colors, markings, eye color, face and body shape.")
    return " ".join(parts)


SPECIES_CN = {"cat": "猫", "dog": "狗", "rabbit": "兔子", "hamster": "仓鼠", "bird": "小鸟", "parrot": "鹦鹉", "other": "小动物"}


def build_selfie_prompt(*, species: str, name: str, place: str, city: str, scene: str, with_reference: bool) -> str:
    """明信片/合影用的写实“自拍”：像它自己对着镜头拍的，不画人手和手机。

    - **名字不进提示词**：街边背景有招牌可画，名字最容易被画成招牌上的字（P 在真图上吃过亏）；是不是同一只靠参考图。
      `name` 仍收着（签名不变），只是不用。
    - **只读 `scene`，不读 `place`、`city`**：地名同样会被画成招牌字。scene 全仓只有提示词一个读者，只放画面描述
      （到站自拍：「在高楼林立、街道干净的城市街区的新家附近，站在街边……」）；place、city 是给界面和照片导演的**真名**
      （B 全仓核过：place 有 4 个读者、city 有 6 个，含导演的 SceneFacts 与 `routers/web/pets.py` 的展示），这里不读，
      专名因此在模板这一层就进不来，不靠每个调用方自觉。`place`、`city` 仍收着（签名不变）。
    - **招牌与文字用正面写法**：GPT 和方舟都不支持 negative_prompt，把「招牌、文字」写出来反而可能招来。
      这句正面写法**未经出图验证**（P：否定写法下两次都出了伪文字；正面写法有没有用，还没有证据），是押注，不是已验证的修复。
    """
    animal = SPECIES_CN.get(species, "小动物")
    parts = [
        f"写实摄影照片：一只真实的{animal}，{scene}。",
        "镜头离它很近、略带广角，像它自己对着镜头拍的照片。自然光，浅景深，背景虚化，真实相机质感。",
        f"必须是参考图里的同一只{animal}：同样的毛色、花纹、眼睛颜色、脸型和体型。" if with_reference else None,
        "真实动物，正常的动物姿态，不是卡通，不是插画，不拟人。",
        "画面中不要出现人、人手或手机；背景里的牌子和显示屏保持空白，或被前景挡住，画面里物件的表面都是素面的。",
    ]
    return "".join(p for p in parts if p)


def build_portrait_prompt(*, species: str, name: str, personality: str | None) -> str:
    """没有照片的伙伴第一次被画时的“证件照”：之后所有照片都以它为参考，保证是同一只。

    **名字不进提示词**，理由比自拍更硬：这张是以后每一张的身份参考，名字要是被画成字，会跟着传进后面每一张（P）。
    `name` 仍收着（签名不变），只是不用。原来末尾的「画面中没有文字、没有人」删了：前面「干净的浅色背景」已经管住，
    否定写法反而可能招来（P）。以上**未经出图验证**。
    """
    animal = SPECIES_CN.get(species, "小动物")
    return (f"写实宠物照片：一只{animal}" + (f"（性格：{personality}）" if personality else "") +
            "，正面半身像，看向镜头，干净的浅色背景，柔和自然光，毛发细节清晰，真实相机质感。"
            "真实动物，不是卡通，不是插画，不拟人。")


def build_journal_prompt(*, species: str, name: str, title: str, lines: list[str], city: str, with_reference: bool) -> str:
    """攻略手账图：写实俯拍的一页手账，标题与站点名写在画面上（短文字，Seedream 4.5 能写对）。"""
    animal = SPECIES_CN.get(species, "小动物")
    listed = "、".join(f"“{i + 1}. {line[:8]}”" for i, line in enumerate(lines[:4]))
    parts = [
        f"写实摄影照片，俯拍：一本打开的旅行手账平铺在木桌上，纸面干净。手账左上角用黑色手写中文写着标题“{title[:10]}”，下面用手写中文列出几行：{listed}。",
        f"纸上贴着两张真实的小照片：一张是{city}的街景，一张是一只{animal}「{name}」。旁边放着一支钢笔。自然光，真实质感。",
        f"照片里的{animal}必须是参考图里的同一只：同样的毛色、花纹和脸型。" if with_reference else None,
        "除了上面这些中文，不要出现其他文字、票据或品牌标志；不要出现人或人手。",
    ]
    return "".join(p for p in parts if p)
