"""TA 的攻略手账：进城或出远门时，TA 自己写一份一日小攻略——主人也能直接照着走（用户 2026-09-22 的方向）。

- 主人开启“模型回信”时由模型写：3–4 个站点，每站写名字、大概时段、为什么适合 TA、给主人的实用提示；
  只输出 JSON；不确定的信息写“以现场为准”，不编造价格与营业时间；
- 每个站点都用地图在这座城市里核对：查得到的换成真实名称与地址，并附来源；查不到的标“TA 听说的，未核实”，不给地址；
- 这次真实要去的地方一定是第一站；
- 主人开启“生成照片”时，再生成一页写实手账图（标题和站点名写在画面上）；文字另存为结构化数据，便于核对；
- 没开启模型时用模板，只写这次真实要去的地方。
散步、喝一杯和打工是日常，不写攻略。
"""

from __future__ import annotations

import json
import re
import uuid
from urllib import parse
from datetime import datetime
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.tasks import redraw_ticket
from ..web_platform.uow import execute_in, unit_of_work
from .photo_display import settled_photo
from .geo_plan import region_of
from .illustrations import SPECIES_CN

MAX_STOPS = 4
# 手账图已经结束、但没有图的两种状态：failed＝确定没画成；unknown＝可能已受理、结果没确认（与 schemas.web.social.PhotoStatus 一致）
UNRESOLVED_IMAGE = ("failed", "unknown")
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def with_links(stop: dict) -> dict:
    """核实过的站点：给出地图导航链接与可复制的名称地址；未核实的不给（避免照着去扑空）。"""
    if not stop.get("verified") or stop.get("lat") is None:
        return {**stop, "nav_url": None, "copy_text": None}
    query = parse.urlencode({"position": f"{stop['lng']},{stop['lat']}", "name": stop["name"], "coordinate": "wgs84", "src": "petsoul"})
    copy = f"{stop['name']}｜{stop['address']}" if stop.get("address") else stop["name"]
    return {**stop, "nav_url": f"https://uri.amap.com/marker?{query}", "copy_text": copy}


def copy_text(title: str, summary: str | None, city: str, stops: list[dict], tips: list[str]) -> str:
    """整份攻略的纯文本：只放核实过的站点（名称｜地址），没核实的写明“没有核实，不列出”，避免照着去扑空。"""
    lines = [f"{title}（{city}）"]
    if summary:
        lines.append(summary)
    verified = [s for s in stops if s.get("copy_text")]
    for index, stop in enumerate(verified, 1):
        lines.append(f"{index}. {stop['copy_text']}")
    skipped = len(stops) - len(verified)
    if skipped:
        lines.append(f"另有 {skipped} 个站点没有在地图上核实，没有列出。")
    lines += [f"· {tip}" for tip in tips]
    lines.append("现实出行的门票、交通和餐饮花费以现场为准；地点资料来自高德地图。")
    return "\n".join(lines)


def writes_guide(destination_key: str) -> bool:
    return not (destination_key.startswith("work:") or destination_key in ("local:stroll", "local:cafe"))


def _clip(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def guide_prompt(persona, city: str, destination: str) -> list[dict[str, str]]:
    likes = "、".join((persona.dna.favorite_places + persona.dna.hobbies) if persona and persona.dna else []) or "还在慢慢发现"
    animal = SPECIES_CN.get(getattr(persona, "species", "other"), "小动物")
    personality = (persona.dna.personality if persona and persona.dna and persona.dna.personality else None) or (persona.personality if persona else None) or "温和"
    name = persona.name if persona else "TA"
    system = "\n".join([
        f"你是「{name}」，一只{animal}，生活在 PetSoul 动物星球，性格：{personality}；喜欢：{likes}。",
        f"提示要符合{animal}的习性（例如仓鼠、小鸟不用牵引绳，狗才需要）。",
        f"你今天要去{city}的「{destination}」。请给自己写一份一日小攻略，主人也会照着走。",
        "要求：",
        f"1. 第一站必须是「{destination}」；总共 3 到 {MAX_STOPS} 站，都是{city}真实存在、叫得出名字的地方（景点、街区、公园、老店等）。",
        "2. 每站写：name（地点名）、time（大概时段，例如“上午”）、why（为什么适合你，结合性格和喜好，20 字内）、tip（给主人的实用提示，30 字内）。",
        "3. 不确定的信息写“以现场为准”；不要编造价格、营业时间、电话或优惠。",
        "4. 再写 title（攻略标题，10 字内）、summary（一句话，30 字内）、owner_tips（给主人的 1–3 条出行提醒）。",
        "只输出 JSON：{\"title\":..., \"summary\":..., \"stops\":[{\"name\":...,\"time\":...,\"why\":...,\"tip\":...}], \"owner_tips\":[...]}",
    ])
    return [{"role": "system", "content": system}, {"role": "user", "content": "请写这份攻略。"}]


def parse_guide(text: str) -> dict | None:
    match = _JSON.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    stops = [s for s in (data.get("stops") or []) if isinstance(s, dict) and _clip(s.get("name"), 30)]
    if not stops:
        return None
    return {
        "title": _clip(data.get("title"), 16) or "一日小攻略",
        "summary": _clip(data.get("summary"), 60),
        "stops": [{"name": _clip(s.get("name"), 30), "time": _clip(s.get("time"), 12), "why": _clip(s.get("why"), 40), "tip": _clip(s.get("tip"), 60)}
                  for s in stops[:MAX_STOPS]],
        "owner_tips": [_clip(t, 60) for t in (data.get("owner_tips") or []) if _clip(t, 60)][:3],
    }


class TravelGuideService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.chat = None
        self.geo = None
        self.model_enabled: Callable[[str], bool] = lambda user_id: False
        self.persona_of: Callable[[str, str], object | None] = lambda user_id, pet_id: None
        # 手账图（主人开启“生成照片”时）：返回生图任务号
        self.image_request: Callable[..., str | None] = lambda **kwargs: None
        # 同连接的终态口径（装配注入 `lambda conn, task_id: illustrations.outcome_of(task_id, conn)`）
        self.image_outcome_in: Callable[..., str | None] | None = None
        self.on_created: Callable[[object, str], None] = lambda journey, title: None
        self.journey_of: Callable[[str], object | None] = lambda journey_id: None
        self.visit_of: Callable[[str], object | None] = lambda journey_id: None

    # ---- 世界事件 sink：出发时写攻略 ----
    def on_world_event(self, event) -> None:
        if event.kind != "departed" or event.visit is None or not writes_guide(event.journey.destination_key):
            return
        self.create(event.journey, event.visit, event.occurred_at)

    def create(self, journey, visit, now: datetime) -> str | None:
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM web_travel_guides WHERE journey_id = ?", (journey.journey_id,)).fetchone():
                return None
        destination = visit.place["name"]
        draft, composed = None, "template"
        persona = self.persona_of(journey.user_id, journey.pet_id)
        if self.chat is not None and getattr(self.chat, "available", False) and self.model_enabled(journey.user_id):
            try:
                draft = parse_guide(self.chat.complete(guide_prompt(persona, journey.city, destination), max_tokens=700, temperature=0.7, json_mode=True).text)
                composed = "model" if draft else composed
            except Exception:  # noqa: BLE001 - 模型不可用：用模板
                draft = None
        if draft is None:
            draft = {"title": f"{journey.city}小攻略"[:16], "summary": f"今天去{destination}。", "owner_tips": ["出发前查一下天气和开放时间，以现场为准。"],
                     "stops": [{"name": destination, "time": "今天", "why": "这次就去这里。", "tip": "以现场为准。"}]}
        if draft["stops"][0]["name"] != destination:
            draft["stops"].insert(0, {"name": destination, "time": "第一站", "why": "这次真的要去的地方。", "tip": "以现场为准。"})
            draft["stops"] = draft["stops"][:MAX_STOPS]
        stops = [self._verify({**stop, "label": stop["name"]}, journey.city, visit.place.get("timezone") or "Asia/Hong_Kong", real=(index == 0), visit=visit)
                 for index, stop in enumerate(draft["stops"])]
        guide_id = f"gd-{uuid.uuid4().hex[:12]}"
        task_id = self.image_request(user_id=journey.user_id, pet_id=journey.pet_id, source_key=f"guide:{journey.journey_id}", title=draft["title"],
                                     lines=[s.get("label") or s["name"] for s in stops], city=journey.city)
        # 同收藏与通讯器：任务先入队、这里后插行，中间 worker 可能已经跑完。同一个写事务里先读一次终态。
        with unit_of_work(self.storage) as conn:
            settled = settled_photo(conn, task_id, self.image_outcome_in) if task_id else None
            status, url = settled if settled is not None else ("processing" if task_id else None, None)
            inserted = conn.execute(
                "INSERT OR IGNORE INTO web_travel_guides (guide_id, user_id, pet_id, journey_id, city, destination_title, title, summary, stops_json, owner_tips_json, "
                "composed_by, image_status, image_task_id, created_at, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (guide_id, journey.user_id, journey.pet_id, journey.journey_id, journey.city, journey.title, draft["title"], draft["summary"],
                 json.dumps(stops, ensure_ascii=False), json.dumps(draft["owner_tips"], ensure_ascii=False), composed,
                 status, task_id, iso(now), url),
            ).rowcount
        if inserted:
            self.on_created(journey, draft["title"])
            return guide_id
        return None

    def _verify(self, stop: dict, city: str, timezone: str, *, real: bool, visit) -> dict:
        found = None
        if real and visit.place.get("provider") not in (None, "fixture"):
            place = visit.place
            return {**stop, "name": place["name"], "verified": True, "address": place.get("address"), "lat": place.get("lat"), "lng": place.get("lng"),
                    "attribution": place.get("attribution")}
        if real:
            return {**stop, "verified": False, "address": None, "lat": None, "lng": None, "attribution": "演示地点：不对应真实商家"}
        if self.geo is not None:
            try:
                found = self.geo.place_in_city(region_of(timezone), stop["name"], city)
            except Exception:  # noqa: BLE001 - 核对失败按未核实处理
                found = None
        if found is None:
            return {**stop, "verified": False, "address": None, "lat": None, "lng": None, "attribution": "TA 听说的，未核实"}
        return {**stop, "name": found.name, "verified": True, "address": found.address, "lat": found.lat, "lng": found.lng, "attribution": found.attribution}

    # ---- 手账图回调 ----
    def image_ready(self, task_id: str, url: str, conn=None) -> None:
        execute_in(self.storage, conn, "UPDATE web_travel_guides SET image_url = ?, image_status = 'ready' WHERE image_task_id = ?", (url, task_id))

    def image_failed(self, task_id: str, conn=None, outcome: str = "failed") -> None:
        """outcome：`failed`＝确定没画成；`unknown`＝可能已经受理、结果没确认（手账上如实显示“还没确认”）。"""
        status = outcome if outcome in UNRESOLVED_IMAGE else "failed"
        execute_in(self.storage, conn, "UPDATE web_travel_guides SET image_status = ? WHERE image_task_id = ? AND image_status = 'processing'", (status, task_id))

    def image_retry_started(self, task_id: str, conn=None) -> None:
        """重画真的排上队了（由插画服务在重排事务里回调）：手账图回到“处理中”，与重排一起提交或一起作废。"""
        marks = ",".join("?" for _ in UNRESOLVED_IMAGE)
        execute_in(self.storage, conn, f"UPDATE web_travel_guides SET image_status = 'processing' WHERE image_task_id = ? AND image_status IN ({marks})",
                   (task_id, *UNRESOLVED_IMAGE))

    def image_retrying(self, pet_id: str, guide_id: str) -> str | None:
        """主人点攻略手账上的“重画”：只认这只宠物名下、已经结束又没出图的那一份；
        返回**重画凭据** `<任务号>#<当时看到的失败尝试次数>`，交给 `illustrations.retry`。

        攻略属于宠物本身、全家同一份，所以这里按 `pet_id` 归属判断（成员关系仍由调用方检查，两层都要有）。
        **只做归属与状态判断、不写库**：展示状态由 `illustrations.retry` 在重排的同一个事务里改（见 `image_retry_started`）。
        这道查询挡的是顺序连点；并发与迟到的重复请求由凭据里的失败版本 ＋ 重排事务里的条件更新挡。历史尝试的账本记录原样保留。
        """
        marks = ",".join("?" for _ in UNRESOLVED_IMAGE)
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT g.image_task_id, t.attempts FROM web_travel_guides g LEFT JOIN web_tasks t ON t.task_id = g.image_task_id "
                f"WHERE g.guide_id = ? AND g.pet_id = ? AND g.image_status IN ({marks})",
                (guide_id, pet_id, *UNRESOLVED_IMAGE)).fetchone()
        return redraw_ticket(row, "image_task_id")

    def image_state_for(self, pet_id: str, guide_id: str) -> str | None:
        """这只宠物名下那份手账的图现在是什么状态；不存在、不属于这只宠物、或根本没有图时返回 None。

        给路由分辨用：`None` 才是"找不到可重画的对象"（404）；`processing` / `ready` 说明对象在、只是这一刻不能重画。
        归属条件与 `image_retrying` 相同，不会因为走这条路绕过判断。
        """
        with self.storage.connect() as conn:
            row = conn.execute("SELECT image_status FROM web_travel_guides WHERE guide_id = ? AND pet_id = ? AND image_task_id IS NOT NULL",
                               (guide_id, pet_id)).fetchone()
        return row["image_status"] if row is not None else None

    # ---- 读取 ----
    def _row(self, row) -> dict:
        stops = [with_links(stop) for stop in json.loads(row["stops_json"])]
        journey = self.journey_of(row["journey_id"])
        status, visited, fee = None, [], None
        if journey is not None:
            fee = journey.fee
            status = "completed" if journey.lifecycle != "active" else "in_progress"
            visit = self.visit_of(row["journey_id"])
            if visit is not None and visit.starts_at <= utcnow():
                visited = [visit.place["name"]]  # 实际到过的地方（计划里其他站点没有自动算作到过）
        return {"guide_id": row["guide_id"], "journey_id": row["journey_id"], "city": row["city"], "destination_title": row["destination_title"],
                "title": row["title"], "summary": row["summary"], "stops": stops, "owner_tips": json.loads(row["owner_tips_json"]),
                "composed_by": row["composed_by"], "image_status": row["image_status"], "image_url": row["image_url"] if row["image_status"] == "ready" else None,
                "created_at": parse_dt(row["created_at"]), "status": status, "visited": visited, "coin_budget": fee,
                "real_budget_note": "现实出行的门票、交通和餐饮花费以现场为准；本攻略不提供价格，星币只用于 TA 在星球上的旅费。",
                "copy_text": copy_text(row["title"], row["summary"], row["city"], stops, json.loads(row["owner_tips_json"]))}

    def list(self, user_id: str, pet_id: str, limit: int = 20) -> list[dict]:
        """这只宠物写的攻略（属于宠物本身，全家同一份；调用方已检查成员关系）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_travel_guides WHERE pet_id = ? ORDER BY created_at DESC LIMIT ?", (pet_id, limit)).fetchall()
        return [self._row(r) for r in rows]

    def get(self, user_id: str, guide_id: str) -> dict | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_travel_guides WHERE guide_id = ?", (guide_id,)).fetchone()
        return self._row(row) if row else None
