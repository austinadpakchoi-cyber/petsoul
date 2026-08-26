"""后台调度器提醒门禁测试：只推进有主人的宠物 + 按类别节流。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from app.config import Settings
from app.scheduler import BackgroundAgentScheduler
from app.schemas import JourneyThought, NotificationDelivery, PetDNA, PetType
from app.storage import JourneyStorage


class FakeMemoryStore:
    provider_name = "fake-memory-store"

    def __init__(self) -> None:
        self.memories: list[dict] = []

    def add_memory(self, **kwargs) -> None:
        self.memories.append(kwargs)

    def config_snapshot(self) -> dict:
        return {"provider": self.provider_name}


class FakeDispatcher:
    def __init__(self) -> None:
        self.sends: list[dict] = []

    def send_to_pet(self, pet_id, title, body, category, data=None):
        self.sends.append(
            {"pet_id": pet_id, "title": title, "body": body, "category": category, "data": data}
        )
        return [
            NotificationDelivery(
                id=f"nd-{len(self.sends)}",
                pet_id=pet_id,
                device_token="token",
                title=title,
                body=body,
                category=category,
                provider="fake",
                status="mock_sent",
                timestamp=datetime.now(timezone.utc),
            )
        ]

    def config_snapshot(self) -> dict:
        return {"provider": "fake"}


class FakeStatus:
    def __init__(self, thought: JourneyThought | None):
        self.agent_state = type("AgentState", (), {"latest_thought": thought})()
        self.postcards: list = []


class FakeEngine:
    def __init__(self) -> None:
        self.advanced: list[str] = []
        self.thought_counter = 0

    def advance_status(self, pet_id: str):
        self.advanced.append(pet_id)
        self.thought_counter += 1
        thought = JourneyThought(
            id=f"thought-{self.thought_counter}",
            text="我在看海。",
            timestamp=datetime.now(timezone.utc),
            tone="moment",
        )
        return FakeStatus(thought)


class SchedulerNotificationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.storage = JourneyStorage(root / "petjourney.sqlite3")
        self.settings = Settings(scheduler_enabled=True, scheduler_interval_seconds=60)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _scheduler(self, engine: FakeEngine, dispatcher: FakeDispatcher) -> BackgroundAgentScheduler:
        return BackgroundAgentScheduler(
            storage=self.storage,
            engine=engine,
            notification_dispatcher=dispatcher,
            memory_store=FakeMemoryStore(),
            settings=self.settings,
        )

    def _create_pet(self, name: str, owned: bool) -> str:
        pet = self.storage.create_pet(
            name=name,
            pet_type=PetType.dog,
            dna=PetDNA(owner_title="妈妈", personality="温柔"),
            photo_path=None,
        )
        if owned:
            user, _ = self.storage.upsert_user_by_apple_sub(f"sub-{name}", None, "主人")
            self.storage.claim_pet(pet.pet_id, user.user_id)
        return pet.pet_id

    def test_tick_only_advances_owned_pets(self) -> None:
        owned_id = self._create_pet("有主人的宠物", owned=True)
        orphan_id = self._create_pet("孤儿宠物", owned=False)
        engine = FakeEngine()
        dispatcher = FakeDispatcher()
        scheduler = self._scheduler(engine, dispatcher)

        result = scheduler.tick()

        self.assertEqual(result.pets_seen, 1)
        self.assertEqual(engine.advanced, [owned_id])
        self.assertNotIn(orphan_id, engine.advanced)
        self.assertTrue(all(send["pet_id"] == owned_id for send in dispatcher.sends))

    def test_thought_notifications_are_throttled(self) -> None:
        owned_id = self._create_pet("有主人的宠物", owned=True)
        engine = FakeEngine()
        dispatcher = FakeDispatcher()
        scheduler = self._scheduler(engine, dispatcher)

        scheduler.tick()
        scheduler.tick()

        thought_sends = [s for s in dispatcher.sends if s["category"] == "thought"]
        # 两轮都产生了新想法，但节流窗口内只允许推送一次
        self.assertEqual(len(thought_sends), 1)
        self.assertEqual(thought_sends[0]["pet_id"], owned_id)

    def test_throttle_does_not_block_world_advance(self) -> None:
        owned_id = self._create_pet("有主人的宠物", owned=True)
        engine = FakeEngine()
        dispatcher = FakeDispatcher()
        scheduler = self._scheduler(engine, dispatcher)

        scheduler.tick()
        scheduler.tick()

        # 节流只拦推送，世界照常推进（两轮各推进一次）
        self.assertEqual(engine.advanced.count(owned_id), 2)


if __name__ == "__main__":
    unittest.main()
