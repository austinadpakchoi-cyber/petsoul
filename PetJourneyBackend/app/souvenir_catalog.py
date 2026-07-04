from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .schemas import SouvenirItemType, TravelQuest, TravelQuestStop, TravelQuestType


@dataclass(frozen=True)
class SouvenirTemplate:
    item_type: SouvenirItemType
    title: str
    subtitle: str
    story_template: str
    pet_voice: str
    rarity: str = "common"
    template_id: str | None = None

    def render(self, *, quest: TravelQuest, stop: TravelQuestStop, bag_hint: str) -> tuple[str, SouvenirItemType, str, str, str, str, str]:
        values = {
            "bag_hint": bag_hint,
            "city": stop.city or quest.destination,
            "destination": quest.destination,
            "place": stop.name,
        }
        title = self.title.format(**values)
        subtitle = self.subtitle.format(**values)
        story = self.story_template.format(**values)
        pet_voice = self.pet_voice.format(**values)
        template_id = self.template_id or _stable_template_id(self.item_type, title)
        return (template_id, self.item_type, title, subtitle, story, pet_voice, self.rarity)


@dataclass(frozen=True)
class SouvenirPreset:
    keywords: tuple[str, ...]
    templates: tuple[SouvenirTemplate, ...]


def build_souvenir_templates(
    *,
    quest: TravelQuest,
    stop: TravelQuestStop,
    bag_hint: str,
    bag_tags: list[str],
) -> list[tuple[str, SouvenirItemType, str, str, str, str, str]]:
    if quest.quest_type == TravelQuestType.worldcup:
        return _render(WORLDCUP_TEMPLATES, quest=quest, stop=stop, bag_hint=bag_hint)

    primary_context = _primary_context_text(quest=quest, stop=stop, bag_tags=bag_tags)
    context = _context_text(quest=quest, stop=stop, bag_tags=bag_tags)
    selected: list[SouvenirTemplate] = []
    for preset in CITY_PRESETS:
        if _matches(primary_context, preset.keywords):
            selected.extend(preset.templates)
            break

    for preset in BAG_PRESETS:
        if _matches(primary_context, preset.keywords):
            selected.extend(preset.templates)

    for preset in PLACE_PRESETS:
        if _matches(context, preset.keywords):
            selected.extend(preset.templates)

    selected.extend(GLOBAL_TEMPLATES)
    return _render(_dedupe(selected)[:3], quest=quest, stop=stop, bag_hint=bag_hint)


def _primary_context_text(*, quest: TravelQuest, stop: TravelQuestStop, bag_tags: list[str]) -> str:
    return " ".join(
        [
            quest.destination,
            quest.owner_message,
            stop.city,
            stop.name,
            stop.role,
            " ".join(stop.source_notes),
            " ".join(bag_tags),
        ]
    ).lower()


def _context_text(*, quest: TravelQuest, stop: TravelQuestStop, bag_tags: list[str]) -> str:
    stop_text = " ".join(
        f"{guide_stop.city} {guide_stop.name} {guide_stop.role} {' '.join(guide_stop.source_notes)}"
        for guide_stop in (quest.guide.stops if quest.guide else [])
    )
    return " ".join(
        [
            quest.destination,
            quest.owner_message,
            stop.city,
            stop.name,
            stop.role,
            " ".join(stop.source_notes),
            stop_text,
            " ".join(bag_tags),
        ]
    ).lower()


def _matches(context: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in context for keyword in keywords)


def _render(
    templates: list[SouvenirTemplate] | tuple[SouvenirTemplate, ...],
    *,
    quest: TravelQuest,
    stop: TravelQuestStop,
    bag_hint: str,
) -> list[tuple[str, SouvenirItemType, str, str, str, str, str]]:
    return [template.render(quest=quest, stop=stop, bag_hint=bag_hint) for template in templates]


def _dedupe(templates: list[SouvenirTemplate]) -> list[SouvenirTemplate]:
    seen: set[str] = set()
    result: list[SouvenirTemplate] = []
    for template in templates:
        if template.title in seen:
            continue
        seen.add(template.title)
        result.append(template)
    return result


def _stable_template_id(item_type: SouvenirItemType, title: str) -> str:
    digest = hashlib.sha1(f"{item_type.value}|{title}".encode("utf-8")).hexdigest()[:12]
    return f"tpl_{digest}"


WORLDCUP_TEMPLATES = (
    SouvenirTemplate(
        SouvenirItemType.ticket_stub,
        "球场灯光票根",
        "一小张被灯光照过的纸片",
        "TA 在赛场外把这张路线票根夹进小包里。{bag_hint}",
        "我把灯光和欢呼声折小一点，带回来给你。",
        "rare",
    ),
    SouvenirTemplate(
        SouvenirItemType.cultural_creative,
        "城市小围巾挂件",
        "没有官方标志，只留下队伍颜色的氛围",
        "路边摊位上挂着很多颜色，TA 选了最不吵的一条小挂件。",
        "它很轻，走路时会轻轻晃，好像还带着球场的风。",
        "uncommon",
    ),
    SouvenirTemplate(
        SouvenirItemType.photo_print,
        "看台边的拍立得",
        "一张像被路人帮忙拍下来的小照片",
        "比赛散场后，TA 在不拥挤的角落停了一会儿，把这一刻留下。",
        "我没有挤到最前面，但我看见了很亮的夜晚。",
    ),
)


CITY_PRESETS = (
    SouvenirPreset(
        ("厦门", "鼓浪屿", "福建"),
        (
            SouvenirTemplate(
                SouvenirItemType.ticket_stub,
                "鼓浪屿渡船票角",
                "边缘带着海风的小票角",
                "TA 从渡口出来时，把这张票角夹进小包里，像把一小段海路收好。{bag_hint}",
                "它闻起来有一点点咸，我一看到就想起船慢慢靠岸的声音。",
                "uncommon",
            ),
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "海风小船贴纸",
                "贴在手机角落也不会吵的小贴纸",
                "靠近 {place} 的小店里有一排安静的小船图案，TA 挑了颜色最轻的那一枚。",
                "我想把海边的小窗贴给你，等你想我的时候就看一眼。",
            ),
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "凤凰花瓣纸签",
                "像傍晚路边掉下来的红色书签",
                "TA 在街角等风停的时候捡到一片压扁的花瓣，把它夹进纸签里。",
                "它很轻，可是颜色很认真，像今天在认真想你。",
            ),
        ),
    ),
    SouvenirPreset(
        ("京都", "kyoto", "鴨川", "鸭川", "祇园", "gion"),
        (
            SouvenirTemplate(
                SouvenirItemType.charm,
                "和纸小书签",
                "摸起来有一点木香和纸香",
                "TA 在 {city} 的窄路边停下，挑了一枚不亮眼的和纸书签。{bag_hint}",
                "它不会发出声音，只会安静地提醒我慢慢走。",
                "uncommon",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "抹茶糖纸",
                "被折得很平的小糖纸",
                "午后的光落在店门口，TA 把糖纸仔细抹平，像收好一小口苦甜。",
                "我没有吃太多，只把味道最轻的那一点带回来。",
            ),
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "鸭川小石子",
                "一颗被水磨得圆圆的小石子",
                "TA 沿着水边走了一会儿，选了一颗不会硌到包里的小石子。",
                "它比玩具还安静，但拿在爪边很踏实。",
            ),
        ),
    ),
    SouvenirPreset(
        ("雷克雅未克", "reykjavik", "冰岛", "iceland", "极光"),
        (
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "火山黑沙小瓶",
                "装着一点深色海岸线的小瓶子",
                "TA 在冷风里低头看了很久，把一点黑沙收进透明小瓶。{bag_hint}",
                "它不像宝石，可是里面有很远很远的路。",
                "uncommon",
            ),
            SouvenirTemplate(
                SouvenirItemType.charm,
                "羊毛线结",
                "像从暖屋门口掉下来的一小截线",
                "外面很冷，TA 在暖灯旁边发现一个松松的线结，把它当成回家的暗号。",
                "我把暖的那一头留给你，冷的那一头我自己拿着。",
            ),
            SouvenirTemplate(
                SouvenirItemType.photo_print,
                "极光色小卡",
                "一张没有文字的渐变色小卡",
                "夜色很长的时候，TA 把天边的颜色记成一张小卡。",
                "我看见天空慢慢亮了一下，就像你在很远处叫我。",
                "rare",
            ),
        ),
    ),
    SouvenirPreset(
        ("巴黎", "paris", "塞纳", "seine"),
        (
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "咖啡杯垫角",
                "压着一点晨光的纸杯垫",
                "TA 在街角咖啡店坐了一会儿，带走杯垫上最干净的一角。{bag_hint}",
                "这个角落闻起来像早上的桌子，也像你慢慢醒来。",
            ),
            SouvenirTemplate(
                SouvenirItemType.charm,
                "旧书页书签",
                "从旧书摊边买来的薄薄书签",
                "风翻动摊位上的旧书，TA 选了一张没有字的小书签。",
                "我看不懂那些字，可我知道这张纸适合想念。",
                "uncommon",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "面包袋封口贴",
                "带着一点黄油气味的小贴纸",
                "路过面包店时，TA 把纸袋上的小贴纸收好。",
                "香味已经很淡了，可是我还是想带回来给你闻一下。",
            ),
        ),
    ),
    SouvenirPreset(
        ("里斯本", "lisbon", "葡萄牙", "电车", "tram"),
        (
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "蓝白瓷砖贴纸",
                "像墙面上掉下来的一小格颜色",
                "TA 在坡道边看了很久蓝白色的墙面，最后选了一张小小的瓷砖贴纸。{bag_hint}",
                "它有一点海的颜色，也有一点晒过太阳的白。",
                "uncommon",
            ),
            SouvenirTemplate(
                SouvenirItemType.ticket_stub,
                "海风电车票角",
                "被坡道和风吹弯的小票角",
                "电车慢慢经过时，TA 把票角折成很小的一片放进口袋。",
                "它轻得快飞走了，所以我一直按着它。",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "蛋挞纸托边",
                "一圈甜甜的纸边",
                "TA 没有把甜味带得太满，只收了纸托边缘的一小圈。",
                "甜的地方我留在路上了，轻的地方带回来给你。",
            ),
        ),
    ),
    SouvenirPreset(
        ("东京", "tokyo", "日本", "电车", "便利店"),
        (
            SouvenirTemplate(
                SouvenirItemType.ticket_stub,
                "电车票色小卡",
                "像站台灯箱一样干净的小卡",
                "TA 在站台边等车时，把一张颜色很安静的小卡收进包里。{bag_hint}",
                "车来的时候风很快，但我把这一小片颜色抓住了。",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "便利店饭团贴纸",
                "一枚被认真揭下来的包装贴",
                "夜里路过便利店，TA 挑了一个不太吵的角落，把包装贴抹平。",
                "它很小，可是很像深夜有人还在亮着灯。",
            ),
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "小食堂食券边",
                "一小条温热机器吐出来的纸边",
                "TA 在小食堂门口听见机器轻轻响了一声，就把食券边留作记号。",
                "我没有点很多，只记住那一下很小的咔哒声。",
            ),
        ),
    ),
    SouvenirPreset(
        ("首尔", "seoul", "弘大", "汉江"),
        (
            SouvenirTemplate(
                SouvenirItemType.charm,
                "旧书店书签",
                "纸边有一点旧木架的味道",
                "TA 在书店门口躲了一会儿风，带回一张安静的书签。{bag_hint}",
                "这里有很多声音，但这一张纸很会安静。",
            ),
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "小店纸袋封口贴",
                "贴过一次又被温柔揭下来的贴纸",
                "街边小店的纸袋封口贴很漂亮，TA 把它贴在小包内侧。",
                "我没有买很多东西，只买下了这一点灯光。",
            ),
            SouvenirTemplate(
                SouvenirItemType.photo_print,
                "夜灯拍立得",
                "一张边缘微微发亮的小照片",
                "天色暗下来以后，TA 把路灯和招牌都拍得很轻。",
                "我站得远远的，也能看见整条街在发光。",
                "uncommon",
            ),
        ),
    ),
    SouvenirPreset(
        ("上海", "shanghai", "外滩", "弄堂"),
        (
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "梧桐叶书签",
                "一枚压得很平的路边叶子",
                "TA 在树影下面慢慢走，把一片完整的叶子夹进小包。{bag_hint}",
                "它像一把很小的伞，我想替你留住这一点阴影。",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "弄堂点心纸袋",
                "边角带着一点热气的小纸袋",
                "路过小店时，TA 把纸袋边折得很整齐。",
                "香味会跑掉，所以我先把纸袋收起来。",
            ),
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "江边灯色小卡",
                "一张像傍晚水面的小色卡",
                "TA 在江边没有站太久，只把灯光记成一张小卡。",
                "水面一直在动，可这一小片颜色终于安静下来了。",
                "uncommon",
            ),
        ),
    ),
    SouvenirPreset(
        ("北京", "beijing", "胡同", "故宫"),
        (
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "胡同门牌小贴纸",
                "一枚方方正正的红色小贴纸",
                "TA 在窄巷里看见旧门牌的颜色，选了一枚小贴纸带走。{bag_hint}",
                "它不大，但看起来很会记路。",
            ),
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "糖葫芦纸套边",
                "带着一点亮晶晶甜味的纸边",
                "路边的红色很亮，TA 只收起纸套上最轻的一角。",
                "甜味太热闹了，我带回来一点点就好。",
            ),
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "秋叶小书签",
                "风一吹就会想家的小叶片",
                "TA 把一片干净的叶子压进纸里，像收住这一天的风。",
                "它脆脆的，所以我一路都走得很轻。",
            ),
        ),
    ),
)


BAG_PRESETS = (
    SouvenirPreset(
        ("sea", "beach", "ocean", "海", "海边", "souvenir"),
        (
            SouvenirTemplate(
                SouvenirItemType.charm,
                "给主人看的海边小结",
                "一截被系成小结的蓝白细绳",
                "因为小包里留着主人的提醒，TA 在海风里挑了一截不扎手的小绳结。{bag_hint}",
                "我把风系住一点点，回去的时候就不会全都散掉。",
            ),
        ),
    ),
    SouvenirPreset(
        ("comfort", "slow_travel", "return_home", "lucky", "rare_photo", "comfort_item", "慢", "护身"),
        (
            SouvenirTemplate(
                SouvenirItemType.charm,
                "回家线结",
                "摸到它就会想起熟悉地方的小线结",
                "TA 把这枚线结放在包里最内侧，像给返程留了一盏很小的灯。{bag_hint}",
                "我会去看远方，也会记得哪里能让我好好睡觉。",
                "uncommon",
            ),
        ),
    ),
    SouvenirPreset(
        ("snack", "food", "小食", "零食", "吃"),
        (
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "给路上的小食封口贴",
                "一枚带着香味边缘的小贴纸",
                "TA 没有把小食全带回来，只把封口贴抹平，夹在小包侧袋。{bag_hint}",
                "香味会变淡，但我记得它刚打开时很温柔。",
            ),
        ),
    ),
)


PLACE_PRESETS = (
    SouvenirPreset(
        ("海边", "沙滩", "码头", "渡口", "港", "ferry", "beach", "pier", "harbor"),
        (
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "海风小贝壳",
                "一枚只会轻轻响的小贝壳",
                "TA 在 {place} 附近低头找了很久，挑到一枚不会划手的小贝壳。{bag_hint}",
                "它响得很小，像我走路时悄悄叫你的名字。",
            ),
        ),
    ),
    SouvenirPreset(
        ("咖啡", "cafe", "coffee", "面包", "bakery"),
        (
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "暖灯杯垫角",
                "被杯底压出圆形痕迹的小角",
                "TA 在 {place} 坐到灯变暖，带回杯垫上最安静的一角。{bag_hint}",
                "我没有打扰别人，只把桌上的一点点暖带回来。",
            ),
        ),
    ),
    SouvenirPreset(
        ("花店", "公园", "garden", "park", "flower", "树", "林"),
        (
            SouvenirTemplate(
                SouvenirItemType.found_object,
                "压平的小叶子",
                "一片像路上停顿号的小叶子",
                "TA 在 {place} 停下来闻了闻，把一片完整的小叶子夹进纸里。{bag_hint}",
                "它不会一直绿下去，可今天它很像我的心情。",
            ),
        ),
    ),
    SouvenirPreset(
        ("市场", "夜市", "小食", "market", "snack", "food"),
        (
            SouvenirTemplate(
                SouvenirItemType.snack_pack,
                "小食摊糖纸",
                "被折成四方形的亮色糖纸",
                "TA 从热闹边缘经过，没有挤进去，只把一张糖纸折得很整齐。{bag_hint}",
                "人很多，可这张纸在我包里一点都不吵。",
            ),
        ),
    ),
    SouvenirPreset(
        ("网吧", "游戏", "电竞", "netcafe", "game", "arcade"),
        (
            SouvenirTemplate(
                SouvenirItemType.cultural_creative,
                "屏幕光贴纸",
                "像键盘旁边漏出来的一小块蓝光",
                "TA 在 {place} 的角落坐了一会儿，带回一枚不发声的小贴纸。{bag_hint}",
                "它像很小的屏幕光，可以陪你等我上线。",
                "uncommon",
            ),
        ),
    ),
)


GLOBAL_TEMPLATES = (
    SouvenirTemplate(
        SouvenirItemType.cultural_creative,
        "{destination} 生活街贴纸",
        "一枚记录这座城市日常颜色的小贴纸",
        "TA 在 {destination} 的生活街区停了一会儿，挑了一个不浮夸的小纪念物。{bag_hint}",
        "我想把这座城市最小的一片颜色带回来。",
    ),
    SouvenirTemplate(
        SouvenirItemType.found_object,
        "路边小卡片",
        "夹着一点当地光线的纸片",
        "TA 在安静的角落发现一张好看的小卡片，像是这一天留下的页脚。",
        "它没有很贵重，但我看见它的时候想到了你。",
    ),
    SouvenirTemplate(
        SouvenirItemType.toy,
        "软软小玩具",
        "旅途中遇到的小伙伴",
        "TA 在路过的店里看见一个很软的小玩具，决定把它带回来。",
        "它可以陪我睡一小会儿，也可以陪你等我的下一张照片。",
        "uncommon",
    ),
)
