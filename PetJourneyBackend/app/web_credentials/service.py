"""证件卡包（对齐说明 §5）：把旧 iOS 的身份卡、护照、照护档案、驾驶证、登机牌、酒店房卡接回网页，并新增星球银行卡。

- 证件编号稳定、全局唯一（前缀-年份-随机 6 位，数据库唯一约束），不截取宠物 ID 尾部；
- 签发时间持久保存；同一签发事件（source_key）只签发一次，刷新、重启、重复请求都不会“今天重新签发”；
- 身份卡、银行卡、照护档案在入住时签发（签发时间就是入住时间）；护照在第一次出远门时签发，到达后盖纪念章；
  登机牌、船票车票按实际成立的交通段签发，状态随行程时间变化（待出发 → 在途 → 已使用）；
- 驾驶证只能由驾考模块在考试通过后签发（见 app/web_driving）；
- 酒店房卡：当前旅程都是当天往返、没有过夜入住，暂不签发，保留条目与获得条件；
- 星球银行卡就是现有钱包账户的展示入口：余额与流水直接读统一账本，不另建余额；
- 照护档案属于私密资料，只给主人看，不进公开卡片。
这些都是 PetSoul 世界里的证件或纪念票据，不代表现实订票、预订或现实资格。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt

logger = logging.getLogger(__name__)
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混的 I、O、0、1


@dataclass(frozen=True)
class KindInfo:
    label: str
    condition: str
    prefix: str
    private: bool = False


CATALOG: dict[str, KindInfo] = {
    "identity_card": KindInfo("宠物 ID", "入住星球时签发", "PS-ID"),
    "bank_card": KindInfo("星球银行卡", "入住时开户；就是 TA 的钱包账户，工资和旅费都记在这里", "PSB"),
    "care_profile": KindInfo("照护档案", "入住时按注册、照片与接待资料建立；主人修改 DNA 后同步", "PS-CARE", private=True),
    "passport": KindInfo("护照", "第一次出远门（跨城或跨境）时签发；本地散步不需要", "PSP"),
    "driver_license": KindInfo("爪爪驾驶证", "在爪爪驾校通过四科考试后签发（科目一到科目四）", "PAW-DL"),
    "boarding_pass": KindInfo("登机牌", "坐飞机出行时，按实际成立的航段签发", "BP"),
    "transport_ticket": KindInfo("船票 / 车票", "坐船或火车出行时，按实际成立的行程段签发", "TK"),
    "hotel_key": KindInfo("酒店房卡", "在外过夜入住时发放；目前的旅程都是当天往返，暂未开放", "RK"),
}
FORMAL_TRIPS = {"macau_ferry": "澳门", "tokyo_flight": "东京"}  # 需要护照的出远门（跨境）
TICKET_KIND = {"flight": "boarding_pass", "ferry": "transport_ticket", "train": "transport_ticket"}


def new_number(prefix: str, year: int) -> str:
    return f"{prefix}-{year}-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


class CredentialService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        # 装配时注入
        self.home_of: Callable[[str], object | None] = lambda pet_id: None
        self.pet_brief: Callable[[str], dict | None] = lambda pet_id: None  # {name, species, photo_url, photo_generated}
        self.place_display_of: Callable[[str], str] = lambda home_id: ""
        self.care_notes_of: Callable[[str, str], list[str]] = lambda user_id, pet_id: []
        self.balance_of: Callable[[str], int] = lambda pet_id: 0
        self.ledger_of: Callable[[str], list[dict]] = lambda pet_id: []
        self.legs_of: Callable[[str], list] = lambda journey_id: []
        self.service_of: Callable[[str | None], tuple[str, str] | None] = lambda world_service_id: None  # (承运人, 班次)
        self.on_issued: Callable[[str, str, str, dict, bool], None] = lambda user_id, pet_id, kind, row, announce: None

    # ---- 签发（幂等）----
    def issue(self, *, user_id: str, pet_id: str, kind: str, source_key: str, issued_at: datetime, title: str | None = None,
              data: dict | None = None, links: list[dict] | None = None, announce: bool = True) -> tuple[dict, bool]:
        """同一 (宠物, 种类, 签发事件) 只签发一次；返回 (记录, 是否新签发)。签发提交后才发纪念消息。"""
        existing = self._by_source(pet_id, kind, source_key)
        if existing is not None:  # 常见情况：已经签发过，不必加写锁
            return existing, False
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row, created = self.insert(conn, user_id=user_id, pet_id=pet_id, kind=kind, source_key=source_key, issued_at=issued_at, title=title,
                                       data=data, links=links)
        if created:
            try:
                self.on_issued(user_id, pet_id, kind, row, announce)
            except Exception:  # noqa: BLE001 - 纪念消息发不出去不影响已经签发的证件
                logger.exception("credential announcement failed kind=%s pet=%s", kind, pet_id)
        return row, created

    def insert(self, conn: sqlite3.Connection, *, user_id: str, pet_id: str, kind: str, source_key: str, issued_at: datetime, title: str | None = None,
               data: dict | None = None, links: list[dict] | None = None) -> tuple[dict, bool]:
        """在调用方的事务里签发（例如驾考：考试通过与驾驶证签发同一次提交）；不发消息，消息由调用方在提交后安排。"""
        existing = self._by_source_in(conn, pet_id, kind, source_key)
        if existing is not None:
            return existing, False
        info = CATALOG[kind]
        for _ in range(8):  # 编号冲突（极少）时重抽；约束失败只撤销这一条语句，事务仍然有效
            number = new_number(info.prefix, issued_at.year)
            try:
                conn.execute(
                    "INSERT INTO web_credentials (credential_id, user_id, pet_id, kind, number, source_key, issued_at, title, data_json, links_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"cr-{uuid.uuid4().hex[:12]}", user_id, pet_id, kind, number, source_key, iso(issued_at), title,
                     json.dumps(data or {}, ensure_ascii=False), json.dumps(links or [], ensure_ascii=False, default=str), iso(issued_at)),
                )
            except sqlite3.IntegrityError:
                existing = self._by_source_in(conn, pet_id, kind, source_key)
                if existing is not None:  # 同一签发事件已经有了
                    return existing, False
                continue  # 编号撞了：重抽
            return self._by_source_in(conn, pet_id, kind, source_key), True
        raise RuntimeError("could not allocate a unique credential number")

    def _by_source(self, pet_id: str, kind: str, source_key: str) -> dict | None:
        with self.storage.connect() as conn:
            return self._by_source_in(conn, pet_id, kind, source_key)

    def _by_source_in(self, conn: sqlite3.Connection, pet_id: str, kind: str, source_key: str) -> dict | None:
        row = conn.execute("SELECT * FROM web_credentials WHERE pet_id = ? AND kind = ? AND source_key = ?", (pet_id, kind, source_key)).fetchone()
        return self._row(row) if row else None

    @staticmethod
    def _row(row) -> dict:
        return {"credential_id": row["credential_id"], "user_id": row["user_id"], "pet_id": row["pet_id"], "kind": row["kind"], "number": row["number"],
                "source_key": row["source_key"], "issued_at": parse_dt(row["issued_at"]), "title": row["title"],
                "data": json.loads(row["data_json"]), "links": json.loads(row["links_json"])}

    def ensure_basics(self, user_id: str, pet_id: str, *, announce: bool = False) -> None:
        """入住的身份卡、银行卡、照护档案：签发时间就是这只宠物住进来的时间（补签也不会写成今天；后加进家的宠物按它自己的入住时间）。"""
        home = self.home_of(pet_id)
        if home is None or getattr(home, "activated_at", None) is None:
            return
        activated_at = home.activated_at if isinstance(home.activated_at, datetime) else parse_dt(home.activated_at)
        link = [{"kind": "home", "ref_id": home.home_id, "title": "入住星球", "at": iso(activated_at)}]
        for kind in ("identity_card", "bank_card", "care_profile"):
            self.issue(user_id=user_id, pet_id=pet_id, kind=kind, source_key=f"home:{home.home_id}", issued_at=activated_at,
                       title=CATALOG[kind].label, links=link, announce=announce and kind == "identity_card")

    # ---- 旅行证件（世界事件 sink）----
    def on_world_event(self, event) -> None:
        journey = event.journey
        if event.kind == "departed":
            self._travel_documents(journey, event.occurred_at)
        elif event.kind == "leg_arrived" and journey.destination_key in FORMAL_TRIPS:
            self._stamp(journey, event)

    def _travel_documents(self, journey, departed_at: datetime) -> None:
        link = {"kind": "journey", "ref_id": journey.journey_id, "title": journey.title, "at": iso(departed_at)}
        if journey.destination_key in FORMAL_TRIPS:
            passport, _ = self.issue(user_id=journey.user_id, pet_id=journey.pet_id, kind="passport", source_key="passport", issued_at=departed_at,
                                     title="PetSoul 星球护照", links=[link])
            if not any(item.get("ref_id") == journey.journey_id for item in passport["links"]):
                self._append_link(passport["credential_id"], link)
        for leg in self.legs_of(journey.journey_id):
            kind = TICKET_KIND.get(leg.mode)
            if kind is None or leg.kind != "main":
                continue
            service = self.service_of(leg.world_service_id)
            carrier, code = service if service else ("动物世界交通", "")
            origin, destination = leg.origin.get("name", ""), leg.destination.get("name", "")
            title = f"{carrier} {code} {origin} → {destination}".replace("  ", " ").strip()
            digest = hashlib.sha1(leg.leg_id.encode("utf-8")).hexdigest()
            seat = f"{int(digest[:4], 16) % 30 + 1}{'ABCDEF'[int(digest[4:6], 16) % 6]}"
            self.issue(user_id=journey.user_id, pet_id=journey.pet_id, kind=kind, source_key=f"leg:{leg.leg_id}", issued_at=departed_at, title=title,
                       data={"carrier": carrier, "code": code, "origin": origin, "destination": destination, "mode": leg.mode, "seat": seat,
                             "departure": iso(leg.starts_at), "arrival": iso(leg.ends_at), "leg_id": leg.leg_id},
                       links=[link, {"kind": "leg", "ref_id": leg.leg_id, "title": title, "at": iso(leg.starts_at)}], announce=False)

    def _append_link(self, credential_id: str, link: dict) -> None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT links_json FROM web_credentials WHERE credential_id = ?", (credential_id,)).fetchone()
            links = json.loads(row["links_json"]) + [link]
            conn.execute("UPDATE web_credentials SET links_json = ? WHERE credential_id = ?", (json.dumps(links, ensure_ascii=False), credential_id))

    def _stamp(self, journey, event) -> None:
        city = FORMAL_TRIPS[journey.destination_key]
        with self.storage.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO web_passport_stamps (pet_id, journey_id, city, title, stamped_at) VALUES (?, ?, ?, ?, ?)",
                         (journey.pet_id, journey.journey_id, city, journey.title, iso(event.occurred_at)))

    # ---- 读取 ----
    @staticmethod
    def status_of(row: dict, now: datetime) -> str:
        if row["kind"] in ("boarding_pass", "transport_ticket"):
            departure, arrival = parse_dt(row["data"]["departure"]), parse_dt(row["data"]["arrival"])
            return "active" if now < departure else ("in_progress" if now < arrival else "used")
        return "active"

    def rows(self, user_id: str, pet_id: str) -> list[dict]:
        """这只宠物的证件（属于宠物本身，全家成员看到同一份；调用方已检查成员关系）。user_id 只为兼容旧调用。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_credentials WHERE pet_id = ? ORDER BY issued_at", (pet_id,)).fetchall()
        return [self._row(r) for r in rows]

    def get(self, user_id: str, credential_id: str) -> dict | None:
        """按证件号取；是否能看由调用方按这张证件所属宠物的成员关系判断。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_credentials WHERE credential_id = ?", (credential_id,)).fetchone()
        return self._row(row) if row else None

    def stamps(self, pet_id: str) -> list[dict]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_passport_stamps WHERE pet_id = ? ORDER BY stamped_at", (pet_id,)).fetchall()
        return [{"city": r["city"], "stamped_at": parse_dt(r["stamped_at"]), "journey_id": r["journey_id"], "title": r["title"]} for r in rows]

    def license_of(self, pet_id: str) -> dict | None:
        with self.storage.connect() as conn:
            return self.license_in(conn, pet_id)

    def license_in(self, conn: sqlite3.Connection, pet_id: str) -> dict | None:
        row = conn.execute("SELECT * FROM web_credentials WHERE pet_id = ? AND kind = 'driver_license' ORDER BY issued_at LIMIT 1", (pet_id,)).fetchone()
        return self._row(row) if row else None
