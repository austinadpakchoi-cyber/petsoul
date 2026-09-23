"""主人主动发起的拍照命令：判这一刻 TA 是不是**真的**在那个场景里。

为什么需要它：现有的拍照挂在**到访活动**上（`service.py` 里必须先有 `visit`）。
在家时既没有行程也没有到访，途中要到店之后才有到访——也就是说事件模型里**根本没有那个时刻**，
不是"有调用点没接上"。所以 `home` / `train` 只能由主人主动发起；
`flight_adventure` 则是主人明确选的**虚构主题**，按设计本来就不该由真实行程推导。

**cafe 不在这里**：到咖啡馆拍照仍走行程里的到访活动，那条路不变，两条并存、不互相替代。

这个模块**只判定、不写库**：读一条行程段是只读查询，其余都是纯函数。
真正的排队、预占与撤权复核全在 `illustrations.request_photo` 那条既有链路上，这里一概不另造。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..schemas.web.transport import TransportMode

# 算"在列车上"的承运方式。**只认封闭词表**：认不出的一律不算，宁可拒绝也不要把一次驾车说成坐火车。
# 取值来自 `app/schemas/web/transport.py` 的 TransportMode 枚举，不是自己编的字符串。
TRAIN_MODES = frozenset({TransportMode.train.value})

SCENE_HOME = "home"
SCENE_TRAIN = "train"
SCENE_FLIGHT = "flight_adventure"

# 各场景能断言的**已核验事实**。照片导演按这些事实挑配方，给不出就 hold，不回退旧模板。
#
# `train_window` / `train_seat` 是**承运方式蕴含的属性**——列车有窗有座是载体本身的性质，
# 被核验的是这一段的 `mode` 属于列车类，不是"看见了窗户"。这一点在响应与日志里都写明，
# 免得日后被误读成独立观测。
# **`audio_player` 不能这么给**：那是"它恰好带了什么设备"，属偶然事实，没核验就是没有。
# **`earned_medal` 任何场景都不给**：勋章要真的赢得过。
SCENE_FACTS: dict[str, tuple[str, ...]] = {
    SCENE_HOME: ("at_home",),
    SCENE_TRAIN: ("on_train", "train_window", "train_seat"),
    SCENE_FLIGHT: ("flight_adventure",),
}

FACT_BASIS: dict[str, str] = {
    "at_home": "此刻确实在家（presence=at_home）",
    "on_train": "当前行程段的 mode 属于列车类（封闭词表）",
    "train_window": "由已核验的 mode 蕴含：列车本身有窗，不是独立观测",
    "train_seat": "由已核验的 mode 蕴含：列车本身有座，不是独立观测",
    "flight_adventure": "主人在命令里明确选择的虚构飞行主题",
}


@dataclass(frozen=True)
class PhotoSetting:
    """这一刻的取景设定。`facts` 直接交给照片导演，`basis` 是每条事实的依据，用于诊断。"""

    place: str
    city: str
    facts: tuple[str, ...]
    fictional: bool

    @property
    def basis(self) -> dict[str, str]:
        return {fact: FACT_BASIS[fact] for fact in self.facts if fact in FACT_BASIS}


def active_leg(conn: sqlite3.Connection, journey_id: str, now: datetime) -> sqlite3.Row | None:
    """此刻正走在哪一段。只读，用调用方的连接；没有正在走的段就返回 None。"""
    return conn.execute(
        "SELECT * FROM web_journey_legs WHERE journey_id = ? AND starts_at <= ? AND ends_at > ? ORDER BY sequence LIMIT 1",
        (journey_id, now.isoformat(), now.isoformat()),
    ).fetchone()


def is_train_leg(leg: sqlite3.Row | None) -> bool:
    """这一段算不算"在列车上"。认不出的 mode 一律不算。"""
    return leg is not None and leg["mode"] in TRAIN_MODES


def setting_for(scene: str, *, city: str, place_label: str) -> PhotoSetting:
    """把场景变成取景设定。调用方要先确认状态真的成立（这里不再校验一次）。"""
    if scene == SCENE_HOME:
        return PhotoSetting(place=place_label, city=city, facts=SCENE_FACTS[SCENE_HOME], fictional=False)
    if scene == SCENE_TRAIN:
        return PhotoSetting(place="列车上", city=city, facts=SCENE_FACTS[SCENE_TRAIN], fictional=False)
    return PhotoSetting(place="云层之上（主人选的虚构主题）", city=city, facts=SCENE_FACTS[SCENE_FLIGHT], fictional=True)


# 给生图提示词用的动作描述（`scene` 参数，和 `scene_key` 不是一回事：后者是场景键，前者是「在做什么」）。
SCENE_ACTIONS: dict[str, str] = {
    SCENE_HOME: "在家里待着",
    SCENE_TRAIN: "坐在列车上看窗外",
    SCENE_FLIGHT: "在主人想象的飞行冒险里",
}


def source_key_of(user_id: str, pet_id: str, scene: str, idempotency_key: str) -> str:
    """这次请求的领域编号：由 **谁、给哪只宠物、什么场景、哪一个 Idempotency-Key** 稳定派生。

    **不含时间**。曾经按分钟取桶，那样有个要命的洞：任务已经排上队、幂等回执还没写完就退出，
    六分钟后拿同一个 key 接手时会算出**另一个**编号，于是又排一次、又占一次额度——
    主人只按了一次，钱花了两次。现在同一个 key 永远派生同一个编号，接手时命中
    `request_image` 既有的 `ON CONFLICT(dedupe_key) DO NOTHING`，拿回原来那个任务。

    带上 `pet_id`：同一位主人拿同一个 key 给另一只宠物拍，**绝不能把上一只的任务回给它**。
    编号里 key 只留摘要，避免把主人的原始 key 写进领域数据。
    """
    digest = hashlib.sha256(f"{user_id}|{pet_id}|{scene}|{idempotency_key}".encode()).hexdigest()[:16]
    return f"photo-request:{pet_id}:{scene}:{digest}"


def registrations(conn: sqlite3.Connection, pet_id: str, limit: int = 50) -> list[sqlite3.Row]:
    """这只宠物由主人主动发起的那些摄影请求，新的在前。**纯读**：不推进任何任务、不发起任何调用。

    只认这条命令登记的行（领域编号以 `photo-request:` 开头）——到访触发的照片走另一条路，不混进来。
    """
    return conn.execute(
        "SELECT i.illustration_id, i.task_id, i.status, i.rel_path, i.created_at, t.payload_json "
        "FROM web_illustrations i LEFT JOIN web_tasks t ON t.task_id = i.task_id "
        "WHERE i.pet_id = ? AND i.source_event_id LIKE 'photo-request:%' ORDER BY i.created_at DESC LIMIT ?",
        (pet_id, limit)).fetchall()


def registration_of(conn: sqlite3.Connection, pet_id: str, request_id: str) -> sqlite3.Row | None:
    """按稳定标识找一条，顺带把宠物对上——**不是这只宠物的就当没有**，不泄露存在与否。"""
    return conn.execute(
        "SELECT i.illustration_id, i.task_id, i.status, i.rel_path, i.created_at, t.payload_json "
        "FROM web_illustrations i LEFT JOIN web_tasks t ON t.task_id = i.task_id "
        "WHERE i.illustration_id = ? AND i.pet_id = ? AND i.source_event_id LIKE 'photo-request:%'",
        (request_id, pet_id)).fetchone()
