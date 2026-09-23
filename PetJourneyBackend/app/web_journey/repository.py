"""旅程持久化：web_journeys / web_journey_legs / web_visits / web_world_events。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow


@dataclass
class JourneyRecord:
    journey_id: str
    user_id: str
    pet_id: str
    home_id: str
    destination_key: str
    title: str
    city: str
    lifecycle: str
    itinerary_version: int
    fee: int
    departed_at: datetime
    completes_at: datetime
    completed_at: datetime | None


@dataclass
class LegRecord:
    leg_id: str
    journey_id: str
    sequence: int
    direction: str
    kind: str
    mode: str
    role: str
    world_service_id: str | None
    origin: dict
    destination: dict
    starts_at: datetime
    ends_at: datetime
    time_basis: str
    freshness: str
    position_basis: str
    route: list[dict] = field(default_factory=list)
    reference: dict | None = None  # 这段时间从哪来：参考班次 / 路线估算（供应商、取回时间、有效期）/ 世界规则 / 演示


@dataclass
class VisitRecord:
    visit_id: str
    journey_id: str
    pet_id: str
    user_id: str
    place: dict
    template: str
    starts_at: datetime
    ends_at: datetime
    recommendation_id: str | None
    activities: list[dict]
    version: int


def _journey(row: sqlite3.Row) -> JourneyRecord:
    return JourneyRecord(
        journey_id=row["journey_id"],
        user_id=row["user_id"],
        pet_id=row["pet_id"],
        home_id=row["home_id"],
        destination_key=row["destination_key"],
        title=row["title"],
        city=row["city"],
        lifecycle=row["lifecycle"],
        itinerary_version=row["itinerary_version"],
        fee=row["fee"],
        departed_at=parse_dt(row["departed_at"]),
        completes_at=parse_dt(row["completes_at"]),
        completed_at=parse_dt(row["completed_at"]) if row["completed_at"] else None,
    )


def _leg(row: sqlite3.Row) -> LegRecord:
    return LegRecord(
        leg_id=row["leg_id"],
        journey_id=row["journey_id"],
        sequence=row["sequence"],
        direction=row["direction"],
        kind=row["kind"],
        mode=row["mode"],
        role=row["role"],
        world_service_id=row["world_service_id"],
        origin=json.loads(row["origin_json"]),
        destination=json.loads(row["destination_json"]),
        starts_at=parse_dt(row["starts_at"]),
        ends_at=parse_dt(row["ends_at"]),
        time_basis=row["time_basis"],
        freshness=row["freshness"],
        position_basis=row["position_basis"],
        route=json.loads(row["route_json"]),
        reference=json.loads(row["reference_json"]) if "reference_json" in row.keys() and row["reference_json"] else None,
    )


def _visit(row: sqlite3.Row) -> VisitRecord:
    return VisitRecord(
        visit_id=row["visit_id"],
        journey_id=row["journey_id"],
        pet_id=row["pet_id"],
        user_id=row["user_id"],
        place=json.loads(row["place_json"]),
        template=row["template"],
        starts_at=parse_dt(row["starts_at"]),
        ends_at=parse_dt(row["ends_at"]),
        recommendation_id=row["recommendation_id"],
        activities=json.loads(row["activities_json"]),
        version=row["version"],
    )


class JourneyRepository:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def insert(self, conn: sqlite3.Connection, journey: JourneyRecord, legs: list[LegRecord], visit: VisitRecord, created_at: datetime) -> None:
        conn.execute(
            "INSERT INTO web_journeys (journey_id, user_id, pet_id, home_id, destination_key, title, city, lifecycle, itinerary_version, fee, "
            "departed_at, completes_at, completed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?, ?, NULL, ?)",
            (journey.journey_id, journey.user_id, journey.pet_id, journey.home_id, journey.destination_key, journey.title, journey.city,
             journey.fee, iso(journey.departed_at), iso(journey.completes_at), iso(created_at)),
        )
        for leg in legs:
            conn.execute(
                "INSERT INTO web_journey_legs (leg_id, journey_id, sequence, direction, kind, mode, role, world_service_id, origin_json, "
                "destination_json, starts_at, ends_at, time_basis, freshness, position_basis, route_json, reference_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (leg.leg_id, leg.journey_id, leg.sequence, leg.direction, leg.kind, leg.mode, leg.role, leg.world_service_id,
                 json.dumps(leg.origin, ensure_ascii=False), json.dumps(leg.destination, ensure_ascii=False), iso(leg.starts_at), iso(leg.ends_at),
                 leg.time_basis, leg.freshness, leg.position_basis, json.dumps(leg.route),
                 json.dumps(leg.reference, ensure_ascii=False) if leg.reference else None),
            )
        conn.execute(
            "INSERT INTO web_visits (visit_id, journey_id, pet_id, user_id, place_json, template, starts_at, ends_at, recommendation_id, "
            "activities_json, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)",
            (visit.visit_id, visit.journey_id, visit.pet_id, visit.user_id, json.dumps(visit.place, ensure_ascii=False), visit.template,
             iso(visit.starts_at), iso(visit.ends_at), json.dumps(visit.activities, ensure_ascii=False)),
        )

    def active_for_pet(self, pet_id: str, conn: sqlite3.Connection | None = None) -> JourneyRecord | None:
        """给了连接就在调用方的事务里读（最终提交前的领域条件复核要用同一个连接，见 CR-C1）。"""
        with self._using(conn) as conn:
            row = conn.execute("SELECT * FROM web_journeys WHERE pet_id = ? AND lifecycle = 'active'", (pet_id,)).fetchone()
        return None if row is None else _journey(row)

    def active_journeys(self, limit: int = 200, after: str | None = None) -> list[JourneyRecord]:
        """进行中的旅程，按 journey_id 排序分页。after：上一轮停在哪个编号（游标），用来轮着处理，避免后排的旅程一直排不上。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_journeys WHERE lifecycle = 'active' AND journey_id > ? ORDER BY journey_id LIMIT ?",
                                (after or "", limit)).fetchall()
        return [_journey(r) for r in rows]

    def active_count(self) -> int:
        with self.storage.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE lifecycle = 'active'").fetchone()["n"])

    def latest_for_pet(self, pet_id: str) -> JourneyRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_journeys WHERE pet_id = ? ORDER BY departed_at DESC LIMIT 1", (pet_id,)).fetchone()
        return None if row is None else _journey(row)

    def get(self, journey_id: str) -> JourneyRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_journeys WHERE journey_id = ?", (journey_id,)).fetchone()
        return None if row is None else _journey(row)

    def legs(self, journey_id: str) -> list[LegRecord]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_journey_legs WHERE journey_id = ? ORDER BY sequence", (journey_id,)).fetchall()
        return [_leg(row) for row in rows]

    def leg(self, leg_id: str) -> LegRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_journey_legs WHERE leg_id = ?", (leg_id,)).fetchone()
        return None if row is None else _leg(row)

    def visit_for_journey(self, journey_id: str) -> VisitRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_visits WHERE journey_id = ?", (journey_id,)).fetchone()
        return None if row is None else _visit(row)

    def visit(self, visit_id: str) -> VisitRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_visits WHERE visit_id = ?", (visit_id,)).fetchone()
        return None if row is None else _visit(row)

    def update_visit(self, visit: VisitRecord, expected_version: int, conn: sqlite3.Connection | None = None) -> bool:
        with self._using(conn) as conn:
            return conn.execute(
                "UPDATE web_visits SET place_json = ?, recommendation_id = ?, activities_json = ?, version = version + 1 WHERE visit_id = ? AND version = ?",
                (json.dumps(visit.place, ensure_ascii=False), visit.recommendation_id, json.dumps(visit.activities, ensure_ascii=False), visit.visit_id, expected_version),
            ).rowcount == 1

    def rechoose_venue(self, visit: VisitRecord, expected_itinerary: int) -> bool:
        """到店前改选：同一事务里更新到访地点、与之相接的两段交通端点（时间不变，不为餐厅缩短），并把行程版本 +1。"""
        place = visit.place
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            bumped = conn.execute(
                "UPDATE web_journeys SET itinerary_version = itinerary_version + 1 WHERE journey_id = ? AND itinerary_version = ?",
                (visit.journey_id, expected_itinerary),
            ).rowcount == 1
            if not bumped:
                conn.rollback()
                return False
            updated = conn.execute(
                "UPDATE web_visits SET place_json = ?, recommendation_id = ?, version = version + 1 WHERE visit_id = ? AND version = ?",
                (json.dumps(place, ensure_ascii=False), visit.recommendation_id, visit.visit_id, visit.version),
            ).rowcount == 1
            if not updated:
                conn.rollback()
                return False
            rows = conn.execute("SELECT * FROM web_journey_legs WHERE journey_id = ? ORDER BY sequence", (visit.journey_id,)).fetchall()
            outbound = [r for r in rows if r["direction"] == "outbound"]
            inbound = [r for r in rows if r["direction"] == "return"]
            endpoint = {"name": place["name"], "lat": place["lat"], "lng": place["lng"], "verified": False}
            if outbound:
                leg = outbound[-1]
                dest = {**json.loads(leg["destination_json"]), **endpoint}
                route = json.loads(leg["route_json"]) or []
                if route:
                    route[-1] = {"lat": place["lat"], "lng": place["lng"]}
                conn.execute("UPDATE web_journey_legs SET destination_json = ?, route_json = ? WHERE leg_id = ?",
                             (json.dumps(dest, ensure_ascii=False), json.dumps(route), leg["leg_id"]))
            if inbound:
                leg = inbound[0]
                origin = {**json.loads(leg["origin_json"]), **endpoint}
                route = json.loads(leg["route_json"]) or []
                if route:
                    route[0] = {"lat": place["lat"], "lng": place["lng"]}
                conn.execute("UPDATE web_journey_legs SET origin_json = ?, route_json = ? WHERE leg_id = ?",
                             (json.dumps(origin, ensure_ascii=False), json.dumps(route), leg["leg_id"]))
        return True

    def bump_itinerary(self, journey_id: str, expected_version: int) -> bool:
        with self.storage.connect() as conn:
            return conn.execute(
                "UPDATE web_journeys SET itinerary_version = itinerary_version + 1 WHERE journey_id = ? AND itinerary_version = ?",
                (journey_id, expected_version),
            ).rowcount == 1

    @contextmanager
    def _using(self, conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        """调用者给了连接（同一个 UnitOfWork）就用它，不提交也不关闭；没给就自己开一个短连接。"""
        if conn is not None:
            yield conn
            return
        with self.storage.connect() as own:
            yield own

    def applied_events(self, journey_id: str, conn: sqlite3.Connection | None = None) -> set[str]:
        with self._using(conn) as conn:
            return {row["event_key"] for row in conn.execute("SELECT event_key FROM web_world_events WHERE journey_id = ?", (journey_id,))}

    def record_event(self, journey_id: str, event_key: str, kind: str, occurred_at: datetime, applied_at: datetime,
                     conn: sqlite3.Connection | None = None) -> bool:
        with self._using(conn) as conn:
            return conn.execute(
                "INSERT OR IGNORE INTO web_world_events (journey_id, event_key, kind, occurred_at, applied_at) VALUES (?, ?, ?, ?, ?)",
                (journey_id, event_key, kind, iso(occurred_at), iso(applied_at)),
            ).rowcount == 1

    def complete(self, journey_id: str, completed_at: datetime, conn: sqlite3.Connection | None = None) -> None:
        with self._using(conn) as conn:
            conn.execute(
                "UPDATE web_journeys SET lifecycle = 'completed', completed_at = ? WHERE journey_id = ? AND lifecycle = 'active'",
                (iso(completed_at), journey_id),
            )

    def replace_plan(self, journey_id: str, legs: list[LegRecord], visit: VisitRecord, departed_at: datetime, completes_at: datetime, title: str) -> None:
        """出门前改签：换掉还没开始的交通段与到访，行程版本 +1（出门前没有世界事件、没有签发船票，不会留下半截记录）。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM web_journey_legs WHERE journey_id = ?", (journey_id,))
            conn.execute("DELETE FROM web_visits WHERE journey_id = ?", (journey_id,))
            for leg in legs:
                conn.execute(
                    "INSERT INTO web_journey_legs (leg_id, journey_id, sequence, direction, kind, mode, role, world_service_id, origin_json, "
                    "destination_json, starts_at, ends_at, time_basis, freshness, position_basis, route_json, reference_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (leg.leg_id, journey_id, leg.sequence, leg.direction, leg.kind, leg.mode, leg.role, leg.world_service_id,
                     json.dumps(leg.origin, ensure_ascii=False), json.dumps(leg.destination, ensure_ascii=False), iso(leg.starts_at), iso(leg.ends_at),
                     leg.time_basis, leg.freshness, leg.position_basis, json.dumps(leg.route), json.dumps(leg.reference, ensure_ascii=False) if leg.reference else None),
                )
            conn.execute(
                "INSERT INTO web_visits (visit_id, journey_id, pet_id, user_id, place_json, template, starts_at, ends_at, recommendation_id, "
                "activities_json, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)",
                (visit.visit_id, journey_id, visit.pet_id, visit.user_id, json.dumps(visit.place, ensure_ascii=False), visit.template,
                 iso(visit.starts_at), iso(visit.ends_at), json.dumps(visit.activities, ensure_ascii=False)),
            )
            conn.execute("UPDATE web_journeys SET departed_at = ?, completes_at = ?, title = ?, itinerary_version = itinerary_version + 1 WHERE journey_id = ?",
                         (iso(departed_at), iso(completes_at), title, journey_id))

    def cancel(self, journey_id: str) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_journeys SET lifecycle = 'cancelled', completed_at = ? WHERE journey_id = ?", (iso(utcnow()), journey_id))
