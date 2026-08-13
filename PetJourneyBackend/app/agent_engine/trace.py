"""引擎轨迹编排：trace 的读写与步骤/轨迹构造。

`_trace_step` / `_save_trace` 被 status、photo、owner_message 等场景复用，
集中在此避免散落。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from ..schemas import EngineStepTrace, JourneyEngineTrace
from ..storage import utcnow


class TraceMixin:
    def list_traces(self, pet_id: str, limit: int = 20) -> list[JourneyEngineTrace]:
        self._pet(pet_id)
        return self.storage.list_engine_traces(pet_id, limit=limit)

    def get_trace(self, pet_id: str, trace_id: str) -> JourneyEngineTrace:
        self._pet(pet_id)
        trace = self.storage.get_engine_trace(pet_id, trace_id)
        if not trace:
            raise KeyError(trace_id)
        return trace

    def _trace_step(
        self,
        name: str,
        *,
        started_at: datetime | None = None,
        status: str = "ok",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
        fallback: str | None = None,
    ) -> EngineStepTrace:
        started = started_at or utcnow()
        return EngineStepTrace(
            name=name,
            status=status,
            started_at=started,
            finished_at=utcnow(),
            inputs=inputs or {},
            outputs=outputs or {},
            error=error,
            fallback=fallback,
        )

    def _save_trace(
        self,
        *,
        pet_id: str,
        operation: str,
        started_at: datetime,
        steps: list[EngineStepTrace],
        state_before: dict[str, Any] | None = None,
        state_after: dict[str, Any] | None = None,
        error: Exception | str | None = None,
    ) -> None:
        error_text = str(error) if error else None
        fallbacks = [step.fallback for step in steps if step.fallback]
        errors = [step.error for step in steps if step.error]
        if error_text:
            errors.append(error_text)
        trace = JourneyEngineTrace(
            id=f"trace-{uuid.uuid4().hex[:16]}",
            pet_id=pet_id,
            operation=operation,
            status="error" if error_text else "ok",
            started_at=started_at,
            finished_at=utcnow(),
            steps=steps,
            state_before=state_before or {},
            state_after=state_after or {},
            errors=errors,
            fallbacks=fallbacks,
        )
        try:
            self.storage.save_engine_trace(trace)
        except Exception:
            return
