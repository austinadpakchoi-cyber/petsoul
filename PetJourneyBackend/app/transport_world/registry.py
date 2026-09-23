"""动物世界承运身份注册表：同一运营实例（唯一键）稳定映射到同一 WorldService，刷新/重启不换号。

展示编号 = 承运人前缀 + 由唯一键派生的三位数；与已有编号冲突时顺延，结果持久化后不再变化。
"""

from __future__ import annotations

import sqlite3
import uuid

from ..schemas.web.transport import TransportMode, WorldService
from ..storage import JourneyStorage
from ..utils import iso, utcnow
from .timeline import derive_service_number


class WorldServiceRegistry:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def get_or_create(self, service_key: str, carrier_name: str, code_prefix: str, mode: TransportMode, vehicle_style: str | None = None,
                      reference_id: str | None = None) -> WorldService:
        """reference_id：这个动物世界班次对应的现实参考班次（web_transport_reference_trips）；演示线路为空。"""
        existing = self.by_key(service_key)
        if existing:
            return existing
        base = int(derive_service_number(service_key))
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM web_world_services WHERE service_key = ?", (service_key,)).fetchone()
            if row is not None:
                return self._from_row(row)
            for offset in range(1000):
                code = f"{code_prefix}{(base + offset) % 1000:03d}"
                try:
                    conn.execute(
                        "INSERT INTO web_world_services (world_service_id, service_key, carrier_name, service_code, mode, vehicle_style, "
                        "reference_id, mapping_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                        (f"ws-{uuid.uuid4().hex[:12]}", service_key, carrier_name, code, mode.value, vehicle_style, reference_id, iso(utcnow())),
                    )
                    break
                except sqlite3.IntegrityError:
                    continue
            row = conn.execute("SELECT * FROM web_world_services WHERE service_key = ?", (service_key,)).fetchone()
        return self._from_row(row)

    def by_key(self, service_key: str) -> WorldService | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_world_services WHERE service_key = ?", (service_key,)).fetchone()
        return None if row is None else self._from_row(row)

    def by_id(self, world_service_id: str) -> WorldService | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_world_services WHERE world_service_id = ?", (world_service_id,)).fetchone()
        return None if row is None else self._from_row(row)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> WorldService:
        return WorldService(
            world_service_id=row["world_service_id"],
            carrier_name=row["carrier_name"],
            service_code=row["service_code"],
            mode=TransportMode(row["mode"]),
            vehicle_style=row["vehicle_style"],
            reference_id=row["reference_id"],
            mapping_version=row["mapping_version"],
        )
