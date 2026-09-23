"""把世界侧的出门事件映射成照片导演认得的场景键与已核验事实。

**纯映射**：不读库、不调用任何服务、不写任何东西。放在这里是因为组合根
（`web_agent_wiring.py`）已经顶在门禁上限，而这两件事本来也该能单独验。

两件事必须分开判，混在一起就会把"没权限 / 缺事实"悄悄降级成"这事不归导演管"：

- **是不是目标场景**（`scene_key_of`）：只看 `destination_key`。这个值一定有，
  不受运行时事实影响。不在目标集合 → 不传 `scene_key` → 继续走旧模板，这是**正常**的旧路。
- **够不够拍**（`verified_facts`）：看这次到访地点的**已核验**类目。
  目标场景缺事实**仍然是目标场景**——由 `readiness()` 判成 hold，**不回落旧模板**
  （COORD-B-INTERFACE 定的口径：目标被拒必须 hold，只有本来不在目标集合的才走旧路）。

类目取的是 `visit.place["category"]`，它可能来自真实地点供应商，也可能是星球内的地方或演示资料
（见 `web_journey/planning.py::visit_place`）。**只认封闭词表**：供应商给的类目字符串五花八门，
认不出就不断言 `at_cafe`，宁可 hold 也不要把一次普通到访说成"它在咖啡馆里"。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

# 落脚点是咖啡馆的那几种出门。**按拍照当刻的实际到访地判断，不按整趟的交通方式**
# （COORD-B-SCENE 的产品决定）：坐船去澳门、在街角咖啡馆坐下来拍的那张，就是一张咖啡馆照片；
# 不能因为 destination 写着"轮渡 / 飞行"就说这事不归导演管。
# 这四种在目录里的落脚点 `VenuePlan.category` 都是"咖啡馆"（`local:cafe` 走附近搜索，关键词"咖啡"）。
# 注意：进了目标集合**不等于**够拍——每一次仍要各自核已持久的事实，见 `verified_facts`。
CAFE_DESTINATIONS = frozenset({"local:cafe", "harbour_cafe", "macau_ferry", "tokyo_flight"})

# 能够断言"它确实在咖啡馆里"的类目封闭词表，**只收有实际证据的取值**：
#   - "咖啡馆"：目录里 VenuePlan 的类目（`web_journey/catalog.py`）；
#   - "cafe"  ：`LocalKind` 里 cafe 那一项的键；
#     曾经有一段时间 world 兜底给的是**家的栖息地**类目（真实环境实测落成"附近的公园"），
#     那是源头的缺陷。C 已修：`web_journey/local.py` 的 `WORLD_CATEGORY = {"cafe": "咖啡馆"}`
#     按出门种类取类目。**当时没有用扩词表去掩盖它**——公园就是公园，认不出就 hold，源头修好才是修好。
#   - "咖啡厅"：高德适配器把 `poi["type"]` 按 `;` 取末段的实际产物（`web_providers/geo.py:181`），仓内 fixture 里就有。
# 真实地点供应商返回的类目五花八门，所以这里做的是**有限归一化**（大小写、空白、全角）而不是模糊匹配：
# 认不出就不断言，由 readiness 判 hold 并给出原因——宁可先不画，也不要把一次普通到访说成"它在咖啡馆里"。
# **不为了能出图而放宽**。要加新取值，请先拿到该供应商的一条真实样本再加，不要照着文档猜。
CAFE_CATEGORIES = frozenset({"咖啡馆", "咖啡厅", "cafe"})

SCENE_CAFE = "cafe"


def scene_key_of(destination_key: str | None) -> str | None:
    """这次出门属不属于导演的目标场景。返回 None 表示**本来就不归导演管**，照旧走模板。

    只看目的地，不看有没有拿到事实、有没有授权——那些是 `readiness()` 的事。
    """
    if not destination_key:
        return None
    return SCENE_CAFE if destination_key in CAFE_DESTINATIONS else None


def fact_revision(place: Mapping | None) -> int | None:
    """照片所据事实的代数：**只由到访地点的身份与类目决定**。

    不能用 `visit.version`：`service.py` 在同一个事务里先登记照片（473 行）、再
    `_commit_activity → update_visit`（495 行）把 version +1，**登记完当场就比当前小 1**；
    之后主人选座、点饮品还会继续加。那个计数器把"事实被更正"和"后来正常生活"混在一个数里，
    结果是每一张照片立刻过期。

    这里只取照片真正依赖的四个字段：地点身份、名字、类目、时区——
    正常生活不动它们（照片不过期），地点或类目被更正时它必然变，
    而那恰好正是 `at_cafe`、地点名、当地小时会跟着变的时候。

    取值 0 ~ 2^32-1。它只用于**相等比较**（变了就 hold），不表示先后。
    截断到 32 位有极小的碰撞概率：碰撞的后果是"这次更正没被发现"，
    即一张按旧事实画的照片，不会多花钱、也不会画错人。
    """
    if not place:
        return None
    material = "|".join(str(place.get(key) or "") for key in ("place_id", "name", "category", "timezone"))
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16)


def canonical_category(category: object) -> str | None:
    """把地点类目归一化成词表里的写法。**有限归一化**：只做大小写、首尾空白与全角空格，不做模糊匹配。

    认不出就返回 None——调用方据此不断言事实，readiness 会 hold 并说明原因。
    """
    if not isinstance(category, str):
        return None
    cleaned = category.replace("　", " ").strip().casefold()
    return next((known for known in CAFE_CATEGORIES if known.casefold() == cleaned), None)


def verified_facts(scene_key: str | None, place: Mapping | None) -> tuple[str, ...]:
    """这次到访**已经核验**的事实 token。核验不了就不给，让 readiness 去 hold。

    只给"地点确实是这一类"这一条。点单（`coffee_cup`）、天气（`weather_*`）都有各自的
    真实来源，等那些来源接上了再各自补，这里不替它们编。
    """
    if scene_key != SCENE_CAFE or not place:
        return ()
    return ("at_cafe",) if canonical_category(place.get("category")) is not None else ()


def scene_facts(scene_key: str | None, place: Mapping | None, *, pet_id: str, household_id: str | None,
                event_id: str) -> list[dict]:
    """已核验事实，**按导演 `SceneFact` 的形状给**：六个键一个都不能少，消费端只认 `verified is True`。

    为什么不是 token 元组：导演要的是"谁、在哪个家庭、哪个事件里、核验过没有"，
    光给一个 token 它无从判断这条事实属于谁。给错形状的后果不是报错，是**正式链一直 hold** 而没人看得见。
    `event_id` 必须等于 `source_key`（跨重试不变，它进 context_key）。
    """
    if not household_id:
        return []  # 家庭编号缺失时不编：没有家庭就谈不上这条事实属于谁
    # fact_id 带上 event_id：`f-at_cafe` 对每一次到访都是同一个字符串，事后追不到具体哪一次。
    # 与主人主动发起那条命令的写法对齐（判定不看它，纯粹为可追溯）。
    return [{"fact_id": f"{event_id}:{token}", "token": token, "pet_id": pet_id, "household_id": household_id,
             "event_id": event_id, "verified": True}
            for token in verified_facts(scene_key, place)]


def fact_basis(scene_key: str | None, facts: tuple[str, ...]) -> dict[str, str]:
    """每条事实的**依据**，给任务诊断用，**不进提示词**。

    和 I 的拍照命令用同一套写法：说清这条事实是**独立观测**还是**由别的已核验事实蕴含**。
    分不清这两者，事后就说不出"当时凭什么断言它在咖啡馆里"。
    """
    if scene_key != SCENE_CAFE:
        return {}
    return {"at_cafe": "地点类目已核验属于咖啡馆（封闭词表；来源见 visit.place.category）"} if "at_cafe" in facts else {}


def missing_fact_reason(scene_key: str | None, place: Mapping | None) -> str | None:
    """断言不了事实时的原因，写进任务诊断，**不进提示词**。返回 None 表示事实齐了。

    为什么要单独给原因：目标场景缺事实要 hold，而 hold 在日志里长得和"没到时间"一样；
    运维要能一眼看出是"地点类目认不出"还是"根本没有地点"。
    """
    if scene_key != SCENE_CAFE:
        return None
    if not place:
        return "place_missing"
    category = place.get("category")
    if not isinstance(category, str) or not category.strip():
        return "category_missing"
    return None if canonical_category(category) is not None else f"category_not_recognised:{category.strip()[:32]}"


def place_timezone(place: Mapping | None) -> str | None:
    """拍照时刻要按**真实地点**换算，不是宿主机时区、也不是家的时区。

    `visit_place` 三条分支（真实地点 / 星球内的地方 / 演示资料）都带 `timezone`，取不到就是 None，
    由调用方决定是 hold 还是不传 `captured_at`——**不要**在这里回落到任何默认城市。
    """
    if not place:
        return None
    zone = place.get("timezone")
    return zone if isinstance(zone, str) and zone.strip() else None
