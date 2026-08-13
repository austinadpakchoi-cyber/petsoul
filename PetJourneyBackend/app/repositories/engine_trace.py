"""引擎追踪 Repository mixin：engine_traces 表读写。"""

from __future__ import annotations

import json

from ..schemas import JourneyEngineTrace
from ..utils import iso, parse_dt


class EngineTraceRepositoryMixin:
    def save_engine_trace(self, trace: JourneyEngineTrace) -> JourneyEngineTrace:
        payload = trace.model_dump(mode="json")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO engine_traces (
                    id, pet_id, operation, status, started_at, finished_at,
                    steps_json, state_before_json, state_after_json, errors_json, fallbacks_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.id,
                    trace.pet_id,
                    trace.operation,
                    trace.status,
                    iso(trace.started_at),
                    iso(trace.finished_at),
                    json.dumps(payload["steps"], ensure_ascii=False),
                    json.dumps(payload["state_before"], ensure_ascii=False),
                    json.dumps(payload["state_after"], ensure_ascii=False),
                    json.dumps(payload["errors"], ensure_ascii=False),
                    json.dumps(payload["fallbacks"], ensure_ascii=False),
                ),
            )
        return trace

    def list_engine_traces(self, pet_id: str, limit: int = 20) -> list[JourneyEngineTrace]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM engine_traces
                WHERE pet_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(200, limit))),
            ).fetchall()
        return [self._engine_trace_from_row(row) for row in rows]

    def get_engine_trace(self, pet_id: str, trace_id: str) -> JourneyEngineTrace | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM engine_traces
                WHERE pet_id = ? AND id = ?
                """,
                (pet_id, trace_id),
            ).fetchone()
        return self._engine_trace_from_row(row) if row else None

    def _engine_trace_from_row(self, row) -> JourneyEngineTrace:
        return JourneyEngineTrace.model_validate(
            {
                "id": row["id"],
                "pet_id": row["pet_id"],
                "operation": row["operation"],
                "status": row["status"],
                "started_at": parse_dt(row["started_at"]),
                "finished_at": parse_dt(row["finished_at"]),
                "steps": json.loads(row["steps_json"] or "[]"),
                "state_before": json.loads(row["state_before_json"] or "{}"),
                "state_after": json.loads(row["state_after_json"] or "{}"),
                "errors": json.loads(row["errors_json"] or "[]"),
                "fallbacks": json.loads(row["fallbacks_json"] or "[]"),
            }
        )
