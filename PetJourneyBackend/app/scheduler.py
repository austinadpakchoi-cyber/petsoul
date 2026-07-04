from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from .config import Settings
from .memory_store import MemoryStore
from .notifications import NotificationDispatcher
from .schemas import JourneyThought, Postcard, SchedulerConfig, SchedulerTickResult
from .storage import JourneyStorage, utcnow

if TYPE_CHECKING:
    from .agent_engine import JourneyEngine


class BackgroundAgentScheduler:
    provider_name = "background-agent-scheduler"

    def __init__(
        self,
        *,
        storage: JourneyStorage,
        engine: JourneyEngine,
        notification_dispatcher: NotificationDispatcher,
        memory_store: MemoryStore,
        settings: Settings,
    ):
        self.storage = storage
        self.engine = engine
        self.notification_dispatcher = notification_dispatcher
        self.memory_store = memory_store
        self.settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        if not self.settings.scheduler_enabled or self.running:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stopping.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            await asyncio.to_thread(self.tick)
            try:
                await asyncio.wait_for(
                    self._stopping.wait(),
                    timeout=max(5.0, self.settings.scheduler_interval_seconds),
                )
            except TimeoutError:
                continue

    def tick(self) -> SchedulerTickResult:
        started_at = utcnow()
        pets = self.storage.list_pets()
        agent_turns = 0
        notifications_sent = 0
        errors: list[str] = []

        for pet in pets:
            try:
                before_thought_id = self._latest_state_key(pet.pet_id, "thought")
                before_postcard_id = self._latest_state_key(pet.pet_id, "postcard")
                status = self.engine.advance_status(pet.pet_id)
                latest_thought = status.agent_state.latest_thought
                latest_postcard = status.postcards[0] if status.postcards else None

                if latest_postcard and latest_postcard.id != before_postcard_id:
                    agent_turns += 1
                    deliveries = self.notification_dispatcher.send_to_pet(
                        pet.pet_id,
                        title=f"{pet.name} 发来一张照片",
                        body=self._preview(latest_postcard.text),
                        category="postcard",
                        data={"postcard_id": latest_postcard.id, "location": latest_postcard.location},
                    )
                    notifications_sent += self._sent_count(deliveries)
                    self._remember_postcard(pet.pet_id, pet.name, latest_postcard)
                elif latest_thought and latest_thought.id != before_thought_id:
                    agent_turns += 1
                    deliveries = self.notification_dispatcher.send_to_pet(
                        pet.pet_id,
                        title=f"{pet.name} 有新的声音",
                        body=self._preview(latest_thought.animal_text or latest_thought.text),
                        category="thought",
                        data={"thought_id": latest_thought.id, "tone": latest_thought.tone},
                    )
                    notifications_sent += self._sent_count(deliveries)
                    self._remember_thought(pet.pet_id, pet.name, latest_thought)

                if latest_thought:
                    self._set_latest_state_key(pet.pet_id, "thought", latest_thought.id)
                if latest_postcard:
                    self._set_latest_state_key(pet.pet_id, "postcard", latest_postcard.id)
            except Exception as exc:
                errors.append(f"{pet.pet_id}: {exc}")

        finished_at = utcnow()
        self.storage.set_scheduler_state("last_tick_at", finished_at.isoformat())
        return SchedulerTickResult(
            provider=self.provider_name,
            started_at=started_at,
            finished_at=finished_at,
            pets_seen=len(pets),
            agent_turns=agent_turns,
            notifications_sent=notifications_sent,
            errors=errors,
        )

    def config(self) -> SchedulerConfig:
        return SchedulerConfig(
            enabled=self.settings.scheduler_enabled,
            interval_seconds=self.settings.scheduler_interval_seconds,
            provider=self.provider_name,
            running=self.running,
            notification_provider=str(self.notification_dispatcher.config_snapshot()["provider"]),
            memory_provider=str(self.memory_store.config_snapshot()["provider"]),
        )

    def _latest_state_key(self, pet_id: str, kind: str) -> str | None:
        return self.storage.get_scheduler_state(f"pet:{pet_id}:latest_{kind}_id")

    def _set_latest_state_key(self, pet_id: str, kind: str, value: str) -> None:
        self.storage.set_scheduler_state(f"pet:{pet_id}:latest_{kind}_id", value)

    def _sent_count(self, deliveries) -> int:
        return sum(1 for item in deliveries if item.status in {"sent", "mock_sent"})

    def _preview(self, text: str, limit: int = 72) -> str:
        compact = " ".join(text.strip().split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit - 1]}…"

    def _remember_postcard(self, pet_id: str, pet_name: str, postcard: Postcard) -> None:
        with suppress(Exception):
            self.memory_store.add_memory(
                pet_id=pet_id,
                kind="postcard",
                title=f"{pet_name} 发来的照片",
                content=f"{postcard.location}: {postcard.text}",
                salience=0.84,
                source="scheduler",
                metadata={"postcard_id": postcard.id, "image_url": postcard.image_url or ""},
            )

    def _remember_thought(self, pet_id: str, pet_name: str, thought: JourneyThought) -> None:
        with suppress(Exception):
            self.memory_store.add_memory(
                pet_id=pet_id,
                kind="agent_turn",
                title=f"{pet_name} 的一次主动来信",
                content=thought.translation or thought.animal_text or thought.text,
                salience=0.68,
                source="scheduler",
                metadata={"thought_id": thought.id, "tone": thought.tone},
            )
