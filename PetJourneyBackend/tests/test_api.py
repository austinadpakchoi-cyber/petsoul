from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.amap_services import AMapWebServiceClient
from app.communicator.reply_policy import CommunicatorReplyPolicyEngine
from app.communicator.schemas import CommunicatorIntent, CommunicatorWorldSnapshot
from app.config import Settings
from app.credential_prompt_builder import PetCredentialPromptBuilder
from app.google_maps_services import GoogleMapsServiceClient
from app.image_provider import ImageReference, OpenAICompatibleImageProvider
from app.illustrated_guide_styles import (
    ACTIVE_STYLE_IDS,
    ILLUSTRATED_GUIDE_STYLES,
    STYLE_PACK_VERSION,
    select_illustrated_guide_style,
)
from app.main import create_app
from app.pet_guide_engine import PetGuideEngine
from app.pet_life_engine import PetLifeSimulationEngine
from app.place_interactions import PlaceInteractionEngine
from app.photo_mission_brain import PhotoMissionContext, PhotoMissionDraft
from app.photo_prompt_builder import PetPhotoPromptBuilder
from app.providers import JourneyCity
from app.schemas import (
    AcquisitionSource,
    ItineraryStop,
    IllustratedGuideStop,
    JourneyPlan,
    JourneyStatus,
    PetCredentialKind,
    PetDNA,
    PetType,
    PhotoPerspective,
    PlaceSignal,
    RouteSegment,
    SouvenirItem,
    SouvenirItemType,
    TransportDecision,
    TravelMode,
    TravelQuestType,
    WorldActivity,
    WorldSimulationSnapshot,
)
from app.storage import PetRecord
from app.transport_reality import MockTransportRealityProvider
from app.transport_schedule import (
    OpenAIWebSearchTransportScheduleProvider,
    TransportScheduleCandidate,
    TransportScheduleProvider,
    TransportScheduleRequest,
)
from app.travel_research import DoubaoArkClient, GuideResearchDraft, TravelGuideResearchEngine
from app.weather_provider import AMapWeatherProvider, GoogleWeatherProvider
from app.world_simulation import WorldSimulationEngine


class PetJourneyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        settings = Settings(
            database_path=root / "petjourney.sqlite3",
            upload_dir=root / "uploads",
            public_base_url="http://testserver",
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_pet_and_fetch_status(self) -> None:
        pet_id = self.create_pet()

        status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertEqual(payload["pet_id"], pet_id)
        self.assertEqual(payload["name"], "小星")
        self.assertIn(payload["status"], {"resting", "staying", "walking", "traveling", "flying"})
        self.assertGreaterEqual(len(payload["agent_state"]["thoughts"]), 1)
        latest_thought = payload["agent_state"]["latest_thought"]
        self.assertIn("汪", latest_thought["text"])
        self.assertTrue(latest_thought["translation_available"])
        self.assertIsNone(latest_thought["translation"])

        translation = self.client.get(
            f"/api/v1/thoughts/{latest_thought['id']}/translation",
            params={"pet_id": pet_id},
        )
        self.assertEqual(translation.status_code, 200)
        self.assertIn("translation", translation.json())
        self.assertGreater(len(translation.json()["translation"]), 4)

        position = self.client.get(f"/api/v1/pets/{pet_id}/city_position")
        self.assertEqual(position.status_code, 200)
        self.assertEqual(position.json()["city"], "厦门")

        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["notification_provider"], "mock-notification-provider")
        self.assertEqual(health.json()["memory_provider"], "sqlite-memory-store")
        self.assertEqual(health.json()["pet_life_engine"], "petsoul-life-simulation-engine")
        self.assertEqual(health.json()["scheduler"], "background-agent-scheduler")
        self.assertEqual(health.json()["photo_mission_brain"], "mock-photo-mission-brain")

    def test_day_plan_route_plan_and_feedback(self) -> None:
        pet_id = self.create_pet()

        day_plan = self.client.get(f"/api/v1/day_plan/{pet_id}")
        self.assertEqual(day_plan.status_code, 200)
        self.assertEqual(day_plan.json()["view_mode"], "agent_timeline")
        self.assertGreaterEqual(len(day_plan.json()["day_plan"]), 4)
        self.assertGreaterEqual(len(day_plan.json()["scheduled_transport"]), 1)

        route_plan = self.client.get(f"/api/v1/pets/{pet_id}/route_plan")
        self.assertEqual(route_plan.status_code, 200)
        self.assertEqual(route_plan.json()["provider"], "mock-multimodal-route-planner")
        self.assertGreaterEqual(len(route_plan.json()["places"]), 5)
        self.assertGreaterEqual(len(route_plan.json()["steps"]), 5)

        journey_plan = self.client.get(f"/api/v1/pets/{pet_id}/journey_plan")
        self.assertEqual(journey_plan.status_code, 200)
        journey_payload = journey_plan.json()
        self.assertEqual(journey_payload["provider"], "mock-multimodal-route-planner")
        self.assertEqual(journey_payload["transport_decision"]["selected_mode"], "walk")
        self.assertGreaterEqual(len(journey_payload["route_segments"]), 4)
        self.assertGreaterEqual(len(journey_payload["scheduled_transport"]), 1)
        self.assertTrue(any(item["mode"] == "drive" for item in journey_payload["scheduled_transport"]))
        self.assertTrue(any(item["photo_candidate"] for item in journey_payload["stops"]))

        pet_guide = self.client.get(f"/api/v1/pets/{pet_id}/pet_guide")
        self.assertEqual(pet_guide.status_code, 200)
        guide_payload = pet_guide.json()
        self.assertEqual(guide_payload["pet_id"], pet_id)
        self.assertEqual(guide_payload["city"], "厦门")
        self.assertIn("汪", guide_payload["animal_text"])
        self.assertIn("厦门", guide_payload["translation"])
        self.assertGreaterEqual(len(guide_payload["guide_stops"]), 3)
        self.assertEqual(guide_payload["language_style"], "dog_vocalization_with_hidden_translation")
        guide_names = " ".join(stop["name"] for stop in guide_payload["guide_stops"])
        self.assertNotIn("肯德基", guide_names)
        self.assertNotIn("KFC", guide_names)
        self.assertLessEqual(len(guide_payload["guide_stops"]), 6)
        self.assertGreaterEqual(guide_payload["quality_score"], 0.68)
        self.assertTrue(guide_payload["is_replicable_route"])
        self.assertGreaterEqual(
            sum(1 for token in ("狐尾山", "八市", "沙坡尾", "环岛路", "白城", "白鹭洲", "筼筜湖") if token in guide_names),
            2,
        )

        illustrated_guide = self.client.get(f"/api/v1/pets/{pet_id}/illustrated_guide")
        self.assertEqual(illustrated_guide.status_code, 200)
        illustrated_payload = illustrated_guide.json()
        self.assertEqual(illustrated_payload["pet_id"], pet_id)
        self.assertEqual(illustrated_payload["status"], "prompt_ready")
        self.assertEqual(illustrated_payload["city"], "厦门")
        self.assertGreaterEqual(len(illustrated_payload["stops"]), 3)
        self.assertLessEqual(len(illustrated_payload["stops"]), 5)
        self.assertIn("Use exactly these stops", illustrated_payload["image_prompt"])
        self.assertNotIn("provider", illustrated_payload["theme"].lower())

        world_snapshot = self.client.get(f"/api/v1/pets/{pet_id}/world_snapshot")
        self.assertEqual(world_snapshot.status_code, 200)
        world_payload = world_snapshot.json()
        self.assertEqual(world_payload["pet_id"], pet_id)
        self.assertEqual(world_payload["city"], "厦门")
        self.assertEqual(world_payload["provider"], "world-simulation-engine")
        self.assertIn(world_payload["status"], {"resting", "staying", "walking", "traveling", "flying"})
        self.assertIn(world_payload["current_activity"]["kind"], {"rest", "stop", "movement", "transport"})
        self.assertGreaterEqual(len(world_payload["timeline"]), 5)
        self.assertTrue(any(item["kind"] == "transport" for item in world_payload["timeline"]))
        self.assertTrue(any("真实世界原则" in rule for rule in world_payload["rules"]))
        self.assertIsNotNone(world_payload["life_tick"])
        self.assertEqual(world_payload["life_tick"]["provider"], "petsoul-life-simulation-engine")
        self.assertTrue(world_payload["life_tick"]["owner_visible_summary"])
        self.assertIn(
            world_payload["life_tick"]["animation_hint"],
            {
                "coffee_drink",
                "gaming",
                "camera",
                "walking",
                "transport_car",
                "transport_flight",
                "transport_train",
                "transport_ferry",
                "snack",
                "sleep",
                "observe",
                "sightseeing_sea",
            },
        )
        self.assertIn("allowed", world_payload["life_tick"]["decision"])

        status_after_world = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status_after_world.status_code, 200)
        status_payload = status_after_world.json()
        self.assertEqual(status_payload["status"], world_payload["status"])
        self.assertEqual(status_payload["agent_state"]["status_note"], world_payload["status_note"])
        current_place = world_payload["current_activity"].get("place_name")
        if current_place:
            self.assertIn(current_place, " ".join(status_payload["daily_logs"]))

        life_tick = self.client.get(f"/api/v1/pets/{pet_id}/life_tick")
        self.assertEqual(life_tick.status_code, 200)
        self.assertEqual(life_tick.json()["pet_id"], pet_id)
        self.assertGreaterEqual(len(life_tick.json()["retrieved_memories"]), 1)

        street_rank = self.client.get(f"/api/v1/pets/{pet_id}/street_rank", params={"theme": "coffee"})
        self.assertEqual(street_rank.status_code, 200)
        rank_payload = street_rank.json()
        self.assertEqual(rank_payload["pet_id"], pet_id)
        self.assertEqual(rank_payload["city"], "厦门")
        self.assertEqual(rank_payload["theme"], "coffee")
        self.assertGreaterEqual(len(rank_payload["items"]), 1)
        self.assertIn("扫街榜 API", rank_payload["source_notes"][0])

        feedback = self.client.post(
            "/api/v1/feedback",
            data={"pet_id": pet_id, "city": "厦门", "liked": "true"},
        )
        self.assertEqual(feedback.status_code, 200)
        self.assertTrue(feedback.json()["success"])
        self.assertIn("不会被打断", feedback.json()["message"])
        self.assertEqual(feedback.json()["updated_status"]["pet_id"], pet_id)

    def test_illustrated_guide_style_pack_enables_all_daily_styles(self) -> None:
        stops = [
            IllustratedGuideStop(
                index=1,
                time="08:20",
                name="狐尾山公园",
                label="慢慢散步",
                short_note="先去高一点的地方醒来",
                category="park",
            ),
            IllustratedGuideStop(
                index=2,
                time="10:10",
                name="八市",
                label="老城烟火",
                short_note="闻一闻早市的热气",
                category="market",
            ),
            IllustratedGuideStop(
                index=3,
                time="17:30",
                name="环岛路",
                label="海边的风",
                short_note="傍晚去海边慢慢走",
                category="coastal",
            ),
        ]

        self.assertEqual(len(ILLUSTRATED_GUIDE_STYLES), 14)
        self.assertEqual(ACTIVE_STYLE_IDS, {style.id for style in ILLUSTRATED_GUIDE_STYLES})
        self.assertIn("all14", STYLE_PACK_VERSION)

        seen = {
            select_illustrated_guide_style(
                seed=f"PJ-TEST:厦门:2026-07-{day:02d}",
                city="厦门",
                theme="从山上的风，到老城的烟火，再到傍晚的水边",
                stops=stops,
            ).id
            for day in range(1, 366)
        }
        self.assertEqual(seen, ACTIVE_STYLE_IDS)

    def test_status_polling_does_not_create_new_agent_turns(self) -> None:
        pet_id = self.create_pet()

        first = self.client.get(f"/api/v1/agent_status/{pet_id}")
        second = self.client.get(f"/api/v1/agent_status/{pet_id}")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            len(first.json()["agent_state"]["thoughts"]),
            len(second.json()["agent_state"]["thoughts"]),
        )

    def test_missing_pet_returns_404(self) -> None:
        response = self.client.get("/api/v1/agent_status/PJ-NOPE")
        self.assertEqual(response.status_code, 404)

    def test_demo_frenchie_seed_includes_photo_postcard(self) -> None:
        response = self.client.post("/api/v1/demo/frenchie")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["name"], "小黑")
        self.assertTrue(payload["photo_url"].endswith("/media/demo/frenchie-profile.png"))

        status = self.client.get(f"/api/v1/agent_status/{payload['pet_id']}")
        self.assertEqual(status.status_code, 200)
        postcards = status.json()["postcards"]
        self.assertGreaterEqual(len(postcards), 1)
        self.assertTrue(postcards[0]["image_url"].endswith("/media/demo/frenchie-netcafe-postcard.png"))

        media = self.client.get("/media/demo/frenchie-netcafe-postcard.png")
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.headers["content-type"], "image/png")

    def test_agent_brain_config_exposes_model_defaults(self) -> None:
        response = self.client.get("/api/v1/agent_brain/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["agent_model"], "gpt-5.5")
        self.assertEqual(payload["agent_deep_model"], "gpt-5.5")
        self.assertEqual(payload["translation_model"], "gpt-5.4-mini")
        self.assertEqual(payload["turn_interval_seconds"], 900.0)
        self.assertFalse(payload["remote_configured"])
        self.assertFalse(payload["remote_call_active"])
        self.assertFalse(payload["remote_call_enabled"])

        image_response = self.client.get("/api/v1/image_provider/config")
        self.assertEqual(image_response.status_code, 200)
        image_payload = image_response.json()
        self.assertEqual(image_payload["provider"], "mock-image-provider")
        self.assertEqual(image_payload["image_model"], "gpt-image-2")
        self.assertFalse(image_payload["remote_configured"])
        self.assertFalse(image_payload["remote_call_active"])
        self.assertFalse(image_payload["remote_call_enabled"])
        self.assertFalse(image_payload["reference_image_supported"])

        mission_brain_response = self.client.get("/api/v1/photo_mission_brain/config")
        self.assertEqual(mission_brain_response.status_code, 200)
        mission_brain_payload = mission_brain_response.json()
        self.assertEqual(mission_brain_payload["provider"], "mock-photo-mission-brain")
        self.assertEqual(mission_brain_payload["photo_mission_model"], "gpt-5.5")
        self.assertFalse(mission_brain_payload["remote_configured"])
        self.assertFalse(mission_brain_payload["remote_call_active"])
        self.assertFalse(mission_brain_payload["remote_call_enabled"])

        memory_response = self.client.get("/api/v1/memory/config")
        self.assertEqual(memory_response.status_code, 200)
        self.assertEqual(memory_response.json()["provider"], "sqlite-memory-store")

        notification_response = self.client.get("/api/v1/notifications/config")
        self.assertEqual(notification_response.status_code, 200)
        self.assertEqual(notification_response.json()["provider"], "mock-notification-provider")

        scheduler_response = self.client.get("/api/v1/scheduler/config")
        self.assertEqual(scheduler_response.status_code, 200)
        self.assertEqual(scheduler_response.json()["provider"], "background-agent-scheduler")

    def test_openai_skeleton_reports_configured_but_inactive(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "openai.sqlite3",
            upload_dir=Path(self.tempdir.name) / "openai-uploads",
            public_base_url="http://testserver",
            llm_provider="openai",
            openai_api_key="test-key",
            openai_base_url="https://api.austinsapi.com/v1",
        )
        client = TestClient(create_app(settings))
        response = client.get("/api/v1/agent_brain/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "openai-compatible-pet-agent")
        self.assertTrue(payload["remote_configured"])
        self.assertTrue(payload["remote_call_active"])
        self.assertTrue(payload["remote_call_enabled"])
        self.assertEqual(payload["base_url"], "https://api.austinsapi.com/v1")

        mission_brain = client.get("/api/v1/photo_mission_brain/config")
        self.assertEqual(mission_brain.status_code, 200)
        mission_payload = mission_brain.json()
        self.assertEqual(mission_payload["provider"], "openai-compatible-photo-mission-brain")
        self.assertTrue(mission_payload["remote_configured"])
        self.assertEqual(mission_payload["photo_mission_model"], "gpt-5.5")

    def test_image_provider_supports_pet_and_place_references(self) -> None:
        class FakeImageProvider(OpenAICompatibleImageProvider):
            def __init__(self, settings: Settings):
                super().__init__(settings)
                self.captured_files: list[ImageReference] = []
                self.captured_path = ""

            def _post_multipart(
                self,
                path: str,
                *,
                fields: dict[str, str],
                files: list[ImageReference],
            ) -> dict[str, object]:
                self.captured_path = path
                self.captured_files = files
                return {
                    "model": self.settings.image_model,
                    "data": [
                        {
                            "b64_json": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                                "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                            )
                        }
                    ],
                }

        provider = FakeImageProvider(Settings(image_api_key="image-key"))
        image = provider.generate_image_with_references(
            "Generate a photo with pet identity and place environment references.",
            references=[
                ImageReference(
                    image_bytes=b"pet-bytes",
                    mime_type="image/png",
                    filename="pet.png",
                    role="pet_identity",
                ),
                ImageReference(
                    image_bytes=b"place-bytes",
                    mime_type="image/jpeg",
                    filename="place.jpg",
                    role="place_environment",
                ),
            ],
        )

        self.assertEqual(provider.captured_path, "/images/edits")
        self.assertEqual([item.role for item in provider.captured_files], ["pet_identity", "place_environment"])
        self.assertEqual(image.provider, "openai-compatible-image-provider")
        self.assertEqual(image.mime_type, "image/png")

    def test_memory_endpoints_persist_identity_and_search_notes(self) -> None:
        pet_id = self.create_pet()

        initial = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(initial.status_code, 200)
        self.assertTrue(any(item["kind"] == "identity" for item in initial.json()))

        added = self.client.post(
            f"/api/v1/pets/{pet_id}/memories",
            json={
                "kind": "owner_note",
                "title": "喜欢阳台",
                "content": "小星以前很喜欢在阳台晒太阳，听到风声会安静下来。",
                "salience": 0.9,
                "source": "test",
                "metadata": {"anchor": "balcony"},
            },
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["kind"], "owner_note")
        memory_id = added.json()["id"]

        updated = self.client.patch(
            f"/api/v1/pets/{pet_id}/memories/{memory_id}",
            json={
                "title": "喜欢安静阳台",
                "content": "小星以前很喜欢在安静阳台晒太阳，也喜欢听柔和的风声。",
                "importance": 0.96,
                "memory_type": "preference",
                "emotional_valence": 0.45,
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "喜欢安静阳台")
        self.assertEqual(updated.json()["memory_type"], "preference")
        self.assertEqual(updated.json()["importance"], 0.96)

        search = self.client.post(
            f"/api/v1/pets/{pet_id}/memories/search",
            json={"query": "阳台 晒太阳", "limit": 5},
        )
        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertEqual(payload["provider"], "sqlite-memory-store")
        self.assertTrue(any(item["title"] == "喜欢安静阳台" for item in payload["items"]))

        deleted = self.client.delete(f"/api/v1/pets/{pet_id}/memories/{memory_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["success"])
        remaining = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(remaining.status_code, 200)
        self.assertFalse(any(item["id"] == memory_id for item in remaining.json()))

    def test_pet_dna_can_be_updated_and_written_to_memory(self) -> None:
        pet_id = self.create_pet()

        updated = self.client.patch(
            f"/api/v1/pet_dna/{pet_id}",
            json={
                "owner_title": "宝宝",
                "personality": "爱玩，也爱撒娇",
                "favorite_places": ["草地", "窗边"],
                "hobby": ["散步", "晒太阳"],
                "catchphrase": "我在路上，也在想你",
                "emoji_pref": "soft",
                "voice_style": "轻轻的、像寄信",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["owner_title"], "宝宝")

        fetched = self.client.get(f"/api/v1/pet_dna/{pet_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["personality"], "爱玩，也爱撒娇")

        memories = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(memories.status_code, 200)
        self.assertTrue(any(item["kind"] == "dna_update" for item in memories.json()))

    def test_scheduler_tick_registers_push_and_records_notification(self) -> None:
        pet_id = self.create_pet()

        registration = self.client.post(
            "/api/v1/push/register",
            json={
                "pet_id": pet_id,
                "device_token": "test-device-token",
                "platform": "ios",
                "environment": "sandbox",
            },
        )
        self.assertEqual(registration.status_code, 200)
        self.assertEqual(registration.json()["provider"], "mock-notification-provider")

        tick = self.client.post("/api/v1/scheduler/tick")
        self.assertEqual(tick.status_code, 200)
        tick_payload = tick.json()
        self.assertEqual(tick_payload["provider"], "background-agent-scheduler")
        self.assertEqual(tick_payload["pets_seen"], 1)
        self.assertGreaterEqual(tick_payload["agent_turns"], 1)
        self.assertGreaterEqual(tick_payload["notifications_sent"], 1)
        self.assertEqual(tick_payload["errors"], [])

        deliveries = self.client.get(f"/api/v1/pets/{pet_id}/notifications")
        self.assertEqual(deliveries.status_code, 200)
        self.assertGreaterEqual(len(deliveries.json()), 1)
        self.assertEqual(deliveries.json()[0]["status"], "mock_sent")

    def test_generate_selfie_creates_postcard_and_memory(self) -> None:
        response = self.client.post("/api/v1/demo/frenchie")
        self.assertEqual(response.status_code, 200)
        pet_id = response.json()["pet_id"]

        mission = self.client.get(f"/api/v1/pets/{pet_id}/photo_mission")
        self.assertEqual(mission.status_code, 200)
        mission_payload = mission.json()
        self.assertEqual(mission_payload["pet_id"], pet_id)
        self.assertTrue(mission_payload["scene_anchor"])
        self.assertIn("preserve the exact pet identity", mission_payload["image_prompt"])
        self.assertIn(mission_payload["camera_perspective"], {"first_person_selfie", "passerby_third_person", "communicator_view"})

        selfie = self.client.post(f"/api/v1/pets/{pet_id}/generate_selfie")
        self.assertEqual(selfie.status_code, 200)
        payload = selfie.json()
        self.assertIn("厦门", payload["location"])
        self.assertTrue(payload["text"])

        status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status.status_code, 200)
        postcard_count = len(status.json()["postcards"])
        self.assertGreaterEqual(postcard_count, 1)

        repeated_selfie = self.client.post(f"/api/v1/pets/{pet_id}/generate_selfie")
        self.assertEqual(repeated_selfie.status_code, 200)
        self.assertEqual(repeated_selfie.json()["id"], payload["id"])

        repeated_status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(repeated_status.status_code, 200)
        self.assertEqual(len(repeated_status.json()["postcards"]), postcard_count)

        memories = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(memories.status_code, 200)

    def test_owner_message_creates_autonomous_pet_reply_and_memory(self) -> None:
        pet_id = self.create_pet()
        response = self.client.post(
            f"/api/v1/pets/{pet_id}/messages",
            json={"message": "我想看看海边的小咖啡店，可以的话你自己决定要不要去。"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn(payload["decision"], {"accepted", "declined", "remembered", "comfort"})
        self.assertIn("自己", payload["message"])
        self.assertEqual(payload["thought"]["tone"], f"owner_message_{payload['decision']}")
        self.assertIn("汪", payload["thought"]["text"])
        self.assertEqual(payload["updated_status"]["pet_id"], pet_id)

        memories = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(memories.status_code, 200)
        self.assertTrue(any(item["kind"] == "owner_message" for item in memories.json()))

        communicator_messages = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages")
        self.assertEqual(communicator_messages.status_code, 200)
        senders = {item["sender"] for item in communicator_messages.json()}
        self.assertIn("owner", senders)
        self.assertIn("pet", senders)

    def test_communicator_visual_request_cooldown_moments_and_reactions(self) -> None:
        pet_id = self.create_pet()

        visual = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "你现在干嘛？"},
        )
        self.assertEqual(visual.status_code, 200)
        visual_payload = visual.json()
        self.assertEqual(visual_payload["intent"], "CURRENT_STATUS_VISUAL_REQUEST")
        self.assertIn(
            visual_payload["reply_policy"]["mode"],
            {"immediate", "delayed", "queued_until_photoable_scene", "queued_until_landed", "queued_until_morning"},
        )
        self.assertTrue(visual_payload["owner_message"]["scene_hash"])
        for message in visual_payload["messages"]:
            for attachment in message["attachments"]:
                # 位置卡只在 location_check 时出现；与正文同文的附件卡不再生成
                self.assertNotEqual(attachment["type"], "location_card")
                self.assertNotEqual(
                    "".join(attachment["text"].split()),
                    "".join(message["text"].split()),
                )
        if visual_payload["reply_policy"]["mode"] == "immediate":
            attachment_types = {
                attachment["type"]
                for message in visual_payload["messages"]
                for attachment in message["attachments"]
            }
            self.assertTrue(attachment_types & {"photo_placeholder", "photo_status_card"})

        ack = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "好滴 我看看"},
        )
        self.assertEqual(ack.status_code, 200)
        ack_payload = ack.json()
        self.assertEqual(ack_payload["intent"], "CONFIRM_PENDING_PHOTO")
        ack_attachment_types = {
            attachment["type"]
            for message in ack_payload["messages"]
            for attachment in message["attachments"]
        }
        self.assertFalse(ack_attachment_types & {"pending_photo_request"})
        ack_text = " ".join(message["text"] for message in ack_payload["messages"])
        self.assertNotIn("我听见你说", ack_text)
        self.assertNotIn("放进通讯器", ack_text)
        self.assertNotIn("自己的节奏", ack_text)

        repeated = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "再拍一张"},
        )
        self.assertEqual(repeated.status_code, 200)
        repeated_payload = repeated.json()
        self.assertEqual(repeated_payload["intent"], "PHOTO_REQUEST")
        self.assertEqual(repeated_payload["reply_policy"]["mode"], "no_reply_needed")
        self.assertTrue(repeated_payload["reply_policy"]["cooldown_applied"])
        # 正文已经说明"刚刚才拍过"，不再挂同义附件卡
        self.assertIn("拍过", repeated_payload["messages"][0]["text"])
        self.assertEqual(repeated_payload["messages"][0]["attachments"], [])

        messages = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages")
        self.assertEqual(messages.status_code, 200)
        senders = {item["sender"] for item in messages.json()}
        self.assertIn("owner", senders)
        self.assertTrue({"pet", "system"} & senders)

        moments = self.client.get(f"/api/v1/pets/{pet_id}/communicator/moments")
        self.assertEqual(moments.status_code, 200)
        moment_payload = moments.json()
        self.assertGreaterEqual(len(moment_payload), 2)
        self.assertTrue(all(item["pet_id"] == pet_id for item in moment_payload))
        self.assertTrue(any(item["attachments"] for item in moment_payload))
        self.assertTrue(any(item["social_reactors"] for item in moment_payload))
        moment_attachment_types = {
            attachment["type"]
            for item in moment_payload
            for attachment in item["attachments"]
        }
        self.assertNotIn("photo_placeholder", moment_attachment_types)
        self.assertNotIn("pending_photo_request", moment_attachment_types)
        self.assertFalse(any("你说想看看我" in item["text"] or "旅途圈" in item["text"] for item in moment_payload))
        first_social_moment = next(item for item in moment_payload if item["social_reactors"])
        self.assertGreaterEqual(first_social_moment["reactions"]["like"] + first_social_moment["reactions"]["hug"], 1)

        moment_id = moment_payload[0]["id"]
        reaction = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/moments/{moment_id}/reaction",
            json={"reaction": "paw"},
        )
        self.assertEqual(reaction.status_code, 200)
        self.assertEqual(reaction.json()["reaction"], "paw")
        self.assertIn("摸", reaction.json()["message"])

        updated_moments = self.client.get(f"/api/v1/pets/{pet_id}/communicator/moments")
        self.assertEqual(updated_moments.status_code, 200)
        updated = next(item for item in updated_moments.json() if item["id"] == moment_id)
        self.assertEqual(updated["owner_reaction"], "paw")
        self.assertEqual(updated["reactions"]["paw"], 1)

        memories = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(memories.status_code, 200)
        self.assertTrue(any(item["kind"] == "moment_reaction" for item in memories.json()))

    def test_communicator_reply_policy_handles_sleeping_flight_and_distress_priority(self) -> None:
        policy = CommunicatorReplyPolicyEngine()
        now = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)
        world = CommunicatorWorldSnapshot(
            pet_id="PJ-TEST",
            city="厦门",
            place_name="海边栈道",
            scene_anchor="厦门_海边栈道_walk",
            scene_hash="xiamen_coast_16",
            journey_status=JourneyStatus.staying,
            travel_mode=TravelMode.walk,
            activity_type="stop",
            can_generate_photo=True,
            animation_hint="observe",
            energy=80,
            happiness=80,
            curiosity=70,
            weather="晴天",
            local_hour=16,
            is_sleeping=False,
            is_in_transit=False,
            is_flying=False,
        )

        distress = policy.resolve(
            intent=CommunicatorIntent.emotional_distress,
            world=world.model_copy(update={"is_flying": True, "is_in_transit": True}),
            now=now,
        )
        self.assertEqual(distress.mode.value, "immediate")
        self.assertEqual(distress.reason_code, "owner_emotional_distress")

        flying = policy.resolve(
            intent=CommunicatorIntent.current_status_visual_request,
            world=world.model_copy(update={"is_flying": True, "is_in_transit": True, "can_generate_photo": False}),
            now=now,
        )
        self.assertEqual(flying.mode.value, "queued_until_landed")

        sleeping = policy.resolve(
            intent=CommunicatorIntent.current_status_visual_request,
            world=world.model_copy(update={"is_sleeping": True, "can_generate_photo": False, "animation_hint": "sleep"}),
            now=now,
        )
        self.assertEqual(sleeping.mode.value, "queued_until_morning")

    def test_communicator_owner_photo_share_persists_photo_and_memory(self) -> None:
        pet_id = self.create_pet()

        response = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages/photo",
            data={"text": "给你看一下今天的光"},
            files={"image": ("owner-photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "OWNER_PHOTO_SHARE")
        self.assertEqual(payload["owner_message"]["sender"], "owner")
        self.assertEqual(payload["owner_message"]["attachments"][0]["type"], "owner_photo")
        self.assertIn("/media/communicator_photos/", payload["owner_message"]["attachments"][0]["photo_url"])
        reply_text = " ".join(message["text"] for message in payload["messages"])
        self.assertIn("我看到啦", reply_text)

        memories = self.client.get(f"/api/v1/pets/{pet_id}/memories")
        self.assertEqual(memories.status_code, 200)
        self.assertTrue(any(item["kind"] == "owner_photo_share" for item in memories.json()))

    def test_communicator_send_replays_response_for_duplicate_client_message_id(self) -> None:
        pet_id = self.create_pet()
        body = {"text": "今天风大吗？", "client_message_id": "cli-dup-001"}
        first = self.client.post(f"/api/v1/pets/{pet_id}/communicator/messages", json=body)
        self.assertEqual(first.status_code, 200)
        before = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages").json()

        second = self.client.post(f"/api/v1/pets/{pet_id}/communicator/messages", json=body)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(second_payload["owner_message"]["id"], first_payload["owner_message"]["id"])
        self.assertEqual(
            [item["id"] for item in second_payload["messages"]],
            [item["id"] for item in first_payload["messages"]],
        )
        after = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages").json()
        self.assertEqual(len(after), len(before))

        third = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "今天风大吗？", "client_message_id": "cli-dup-002"},
        )
        self.assertEqual(third.status_code, 200)
        self.assertNotEqual(third.json()["owner_message"]["id"], first_payload["owner_message"]["id"])

    def test_communicator_photo_send_replays_for_duplicate_client_message_id(self) -> None:
        pet_id = self.create_pet()

        def post_photo():
            return self.client.post(
                f"/api/v1/pets/{pet_id}/communicator/messages/photo",
                data={"text": "给你看一下今天的光", "client_message_id": "cli-photo-001"},
                files={"image": ("owner-photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
            )

        first = post_photo()
        self.assertEqual(first.status_code, 200)
        second = post_photo()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["owner_message"]["id"], first.json()["owner_message"]["id"])

        messages = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages").json()
        owner_photo_messages = [
            item for item in messages if item["sender"] == "owner" and item["intent"] == "OWNER_PHOTO_SHARE"
        ]
        self.assertEqual(len(owner_photo_messages), 1)

    def test_communicator_location_card_only_for_location_check(self) -> None:
        pet_id = self.create_pet()
        location = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "你在哪？"},
        )
        self.assertEqual(location.status_code, 200)
        location_payload = location.json()
        self.assertEqual(location_payload["intent"], "LOCATION_CHECK")
        location_types = {
            attachment["type"]
            for message in location_payload["messages"]
            for attachment in message["attachments"]
        }
        self.assertIn("location_card", location_types)

        chat = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "拍给我看看现在的样子"},
        )
        self.assertEqual(chat.status_code, 200)
        chat_types = {
            attachment["type"]
            for message in chat.json()["messages"]
            for attachment in message["attachments"]
        }
        self.assertNotIn("location_card", chat_types)

    def test_non_dog_cat_pet_uses_species_signal_and_photo_subject(self) -> None:
        dna = {
            "owner_title": "姐姐",
            "personality": "会学人说话，很爱观察窗外",
            "favorite_places": ["窗边", "有光的小店"],
            "hobby": ["看人来人往"],
            "catchphrase": "啾啾，我看到啦",
            "emoji_pref": "soft",
            "voice_style": "像一只小鹦鹉发来的短句和啾啾声",
        }
        response = self.client.post(
            "/api/v1/create_pet",
            data={
                "pet_name": "小青",
                "pet_type": "parrot",
                "dna": json.dumps(dna, ensure_ascii=False),
            },
        )
        self.assertEqual(response.status_code, 200)
        pet_id = response.json()["pet_id"]

        status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status.status_code, 200)
        latest = status.json()["agent_state"]["latest_thought"]
        self.assertEqual(latest["language_style"], "parrot_chirp_with_hidden_translation")
        self.assertIn("啾", latest["text"])

        mission = self.client.get(f"/api/v1/pets/{pet_id}/photo_mission")
        self.assertEqual(mission.status_code, 200)
        self.assertIn("beloved parrot", mission.json()["image_prompt"])

    def test_place_interaction_engine_builds_landmark_and_worldcup_photo_missions(self) -> None:
        engine = PlaceInteractionEngine()
        pet = PetRecord(
            pet_id="PJ-TEST",
            name="小黑",
            pet_type=PetType.dog,
            dna=PetDNA(personality="好奇、黏人、喜欢看热闹"),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path=None,
        )
        gulangyu = PlaceSignal(
            id="gulangyu",
            name="鼓浪屿日光岩",
            category="sight",
            city="厦门",
            lat=24.445,
            lng=118.065,
            activity_hint="在海风里停下来",
            detail_hint="鼓浪屿标志性地点",
            source="test",
        )
        activity = WorldActivity(
            id="activity-gulangyu",
            kind="stop",
            status=JourneyStatus.staying,
            title="在鼓浪屿停留",
            detail="TA 正在海边慢慢观察。",
            city="厦门",
            place_name="鼓浪屿日光岩",
            lat=24.445,
            lng=118.065,
            icon_hint="mappin",
            source="test",
        )
        mission = engine.build_photo_mission(
            pet=pet,
            activity=activity,
            places=[gulangyu],
            weather="多云，海风很轻",
            now=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(mission.camera_perspective, "first_person_selfie")
        self.assertTrue(any("鼓浪屿" in hint for hint in mission.landmark_hints))
        self.assertIn("first-person pet selfie", mission.image_prompt)
        self.assertIn("The real place must be visible behind TA", mission.image_prompt)
        self.assertIn("No cutout", mission.image_prompt)

        stadium = PlaceSignal(
            id="worldcup-stadium",
            name="世界杯赛场外广场",
            category="stadium",
            city="洛杉矶",
            lat=34.0141,
            lng=-118.2879,
            activity_hint="在赛场外听见很远的欢呼声",
            detail_hint="比赛日前的赛场周边",
            source="test",
        )
        stadium_activity = activity.model_copy(
            update={
                "id": "activity-stadium",
                "city": "洛杉矶",
                "place_name": stadium.name,
                "lat": stadium.lat,
                "lng": stadium.lng,
            }
        )
        worldcup_mission = engine.build_photo_mission(
            pet=pet,
            activity=stadium_activity,
            places=[stadium],
            weather="晴，24°C",
            now=datetime(2026, 7, 3, 18, 0, tzinfo=timezone.utc),
            worldcup_event=True,
        )
        self.assertEqual(worldcup_mission.camera_perspective, "first_person_selfie")
        self.assertTrue(any("black-red-gold" in hint for hint in worldcup_mission.crowd_hints))
        self.assertIn("generic Germany supporters", worldcup_mission.image_prompt)
        self.assertIn("without official logos", worldcup_mission.image_prompt)

    def test_place_interaction_engine_prefers_photo_mission_brain_draft(self) -> None:
        class FakePhotoMissionBrain:
            provider_name = "fake-photo-mission-brain"

            def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
                return PhotoMissionDraft(
                    interaction_type="vinyl_shop_listening_stop",
                    title=f"在 {context.place.name} 旁边听见很轻的鼓点",
                    detail="模型根据当前地点临场生成的停留，而不是预设地点模板。",
                    pet_action="走进店里，在不挡路的小角落听了一会儿黑胶唱片里的鼓点",
                    emotional_tone="好奇、安静、有一点被音乐陪着的感觉",
                    dwell_minutes=42,
                    camera_perspective=PhotoPerspective.first_person_selfie,
                    scene_anchor=f"{context.place.city} · {context.place.name} · record sleeves",
                    landmark_hints=["record sleeves", "warm storefront glass"],
                    local_detail_hints=["turntable", "wood shelves", "late afternoon reflection"],
                    crowd_hints=[],
                    image_prompt="A warm phone photo of the pet near a vinyl shop.",
                    postcard_text="我在店里听见一点鼓点，好像这个城市也会轻轻摇尾巴。",
                    safety_notes=["Generated by fake model"],
                    model="fake-gpt",
                    provider=self.provider_name,
                )

            def config_snapshot(self) -> dict[str, str | bool | float]:
                return {"provider": self.provider_name}

        engine = PlaceInteractionEngine(FakePhotoMissionBrain())
        pet = PetRecord(
            pet_id="PJ-BRAIN",
            name="小星",
            pet_type=PetType.dog,
            dna=PetDNA(personality="喜欢声音、会自己找安静的地方"),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path=None,
        )
        place = PlaceSignal(
            id="vinyl-shop",
            name="暮色黑胶店",
            category="shop",
            city="厦门",
            lat=24.48,
            lng=118.08,
            activity_hint="门口有音乐声",
            detail_hint="一间地图服务返回的普通小店",
            source="test-map-provider",
        )

        mission = engine.build_photo_mission(
            pet=pet,
            activity=None,
            places=[place],
            weather="傍晚有一点海风",
            now=datetime(2026, 7, 3, 17, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(mission.provider, "fake-photo-mission-brain")
        self.assertEqual(mission.interaction.interaction_type, "vinyl_shop_listening_stop")
        self.assertEqual(mission.camera_perspective, "first_person_selfie")
        self.assertIn("黑胶唱片", mission.interaction.pet_action)
        self.assertIn("preserve the exact pet identity", mission.image_prompt)
        self.assertTrue(any("Model-generated photo mission" in note for note in mission.safety_notes))

    def test_pet_photo_prompt_builder_formats_reference_contract_and_quality_check(self) -> None:
        builder = PetPhotoPromptBuilder()
        pet = PetRecord(
            pet_id="PJ-PROMPT",
            name="小福",
            pet_type=PetType.cat,
            dna=PetDNA(personality="胆子小但很爱观察窗外的光"),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path="pet-reference.png",
        )
        place = PlaceSignal(
            id="place-cafe",
            name="默迹咖啡馆",
            category="cafe",
            city="厦门",
            lat=24.48,
            lng=118.08,
            activity_hint="窗边有咖啡香和柔和灯光",
            detail_hint="街边小咖啡馆的玻璃窗和小桌",
            source="test-map-provider",
            photo_url="https://example.com/place.jpg",
        )

        prompt = builder.build_prompt(
            pet=pet,
            place=place,
            perspective=PhotoPerspective.first_person_selfie,
            weather="多云，29°C",
            time_of_day="morning",
            landmark_hints=["街边小咖啡馆的玻璃窗"],
            local_detail_hints=["咖啡杯", "窗边小桌"],
            has_pet_reference=True,
            has_place_reference=True,
        )

        self.assertIn("pet_identity reference", prompt)
        self.assertIn("place_environment reference", prompt)
        self.assertIn("first-person pet selfie", prompt)
        self.assertIn("No cutout", prompt)
        self.assertIn("No watermark", prompt)
        report = builder.quality_check(
            prompt,
            expected_roles={"pet_identity", "place_environment"},
            place=place,
        )
        self.assertTrue(report.passed, report.summary)

        appended = builder.append_reference_contract("base prompt", roles={"pet_identity", "place_environment"})
        self.assertIn("preserve the exact pet identity", appended)
        self.assertIn("location layout", appended)

    def test_credential_prompt_builder_formats_pet_specific_documents(self) -> None:
        builder = PetCredentialPromptBuilder()
        pet = PetRecord(
            pet_id="PJ-CAT-42",
            name="奶糖",
            pet_type=PetType.cat,
            dna=PetDNA(owner_title="姐姐", personality="安静、爱趴窗台、会认真观察人"),
            created_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
            photo_path="pet-reference.png",
        )

        prompts = builder.build_wallet_prompts(
            pet=pet,
            issue_date=datetime(2026, 7, 4, tzinfo=timezone.utc).date(),
            current_location="厦门",
            has_pet_reference=True,
        )

        self.assertEqual(
            [prompt.kind for prompt in prompts],
            [
                PetCredentialKind.identity,
                PetCredentialKind.passport,
                PetCredentialKind.health_record,
                PetCredentialKind.driver_license,
                PetCredentialKind.boarding_pass,
                PetCredentialKind.hotel_key,
            ],
        )
        identity = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.identity)
        driver = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.driver_license)
        health = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.health_record)
        self.assertIn("奶糖", identity.image_prompt)
        self.assertIn("beloved cat", identity.image_prompt)
        self.assertIn("pet_identity reference", identity.image_prompt)
        self.assertIn("do not copy or imitate any real government", identity.image_prompt.lower())
        self.assertIn("All other document memories", identity.image_prompt)
        self.assertIn("Do not synchronize", identity.image_prompt)
        self.assertNotIn("Current location context: 厦门", identity.image_prompt)
        self.assertIn("姐姐", identity.fields["守护人 / Guardian"])
        self.assertIn("PAW DRIVER LICENSE", driver.title)
        self.assertIn("Cloud Cart", driver.image_prompt)
        self.assertIn("Fictional keepsake only", driver.fields["状态 / Status"])
        self.assertIn("fictional PetSoul care stamp", health.fields["疫苗记录 / Vaccine"])

    def test_credentials_prompt_endpoint_returns_pet_wallet_documents(self) -> None:
        pet_id = self.create_pet(pet_type="rabbit")

        response = self.client.get(f"/api/v1/pets/{pet_id}/credentials/prompts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["kind"] for item in payload],
            ["identity", "passport", "health_record", "driver_license", "boarding_pass", "hotel_key"],
        )
        self.assertTrue(all(item["image_prompt"] for item in payload))
        self.assertTrue(any("beloved rabbit" in item["image_prompt"] for item in payload))
        self.assertTrue(all("Do not synchronize" in item["image_prompt"] for item in payload))
        self.assertTrue(all("Fictional PetSoul document only" in item["safety_notes"][0] for item in payload))

    def test_place_interaction_engine_uses_signature_menu_for_food_and_cafe(self) -> None:
        engine = PlaceInteractionEngine()
        pet = PetRecord(
            pet_id="PJ-MENU",
            name="小福",
            pet_type=PetType.dog,
            dna=PetDNA(personality="会认真研究菜单，也喜欢看店里的人来人往"),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path=None,
        )
        cafe = PlaceSignal(
            id="cafe-menu",
            name="默迹咖啡馆",
            category="cafe",
            city="厦门",
            lat=24.48,
            lng=118.08,
            activity_hint="店里有手冲咖啡和靠窗小桌",
            detail_hint="本地咖啡店，适合慢慢坐一会儿",
            guide_reason="评价里常提到手冲和店内安静氛围",
            source="test-map-provider",
            raw={"tag": "精品咖啡;手冲"},
        )
        cafe_mission = engine.build_photo_mission(
            pet=pet,
            activity=None,
            places=[cafe],
            weather="多云，29°C",
            now=datetime(2026, 7, 3, 9, 20, tzinfo=timezone.utc),
        )

        self.assertIn("菜单", cafe_mission.interaction.pet_action)
        self.assertIn("手冲咖啡", cafe_mission.interaction.pet_action)
        self.assertNotIn("安全", cafe_mission.interaction.pet_action)
        self.assertNotIn("小份", cafe_mission.interaction.pet_action)
        self.assertIn("signature coffee", cafe_mission.image_prompt)

        food = PlaceSignal(
            id="shacha-menu",
            name="四里沙茶面",
            category="food",
            city="厦门",
            lat=24.47,
            lng=118.09,
            activity_hint="店里有本地沙茶面和热气",
            detail_hint="厦门本地餐馆，午饭时间有人排队",
            guide_reason="攻略里常提到沙茶面汤头和本地午餐氛围",
            source="test-map-provider",
            raw={"tag": "沙茶面;本地小吃"},
        )
        food_mission = engine.build_photo_mission(
            pet=pet,
            activity=None,
            places=[food],
            weather="晴，31°C",
            now=datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc),
        )

        self.assertIn("沙茶面", food_mission.interaction.pet_action)
        self.assertIn("旁边桌", food_mission.interaction.pet_action)
        self.assertNotIn("安全", food_mission.interaction.pet_action)
        self.assertNotIn("小份", food_mission.interaction.pet_action)
        self.assertIn("signature local dish", food_mission.image_prompt)

    def test_pet_life_engine_can_pause_guide_for_real_nearby_needs(self) -> None:
        class EmptyMemoryStore:
            provider_name = "empty-memory-store"

            def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list:
                return []

        pet = PetRecord(
            pet_id="PJ-NEED",
            name="小福",
            pet_type=PetType.dog,
            dna=PetDNA(personality="温柔、会自己找舒服的地方", favorite_places=["咖啡店", "公园"]),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path=None,
        )
        current = PlaceSignal(
            id="hot-street",
            name="湖滨北路街角",
            category="street",
            city="厦门",
            lat=24.4800,
            lng=118.0880,
            activity_hint="中午路上有点晒",
            detail_hint="人流和车流都比较满",
            source="test-map-provider",
        )
        cafe = PlaceSignal(
            id="quiet-cafe",
            name="默迹咖啡馆",
            category="cafe",
            city="厦门",
            lat=24.4806,
            lng=118.0890,
            activity_hint="窗边有饮料和安静座位",
            detail_hint="适合休息补水的本地咖啡店",
            source="test-map-provider",
            guide_score=4.7,
            distance_meters=130,
        )
        park = PlaceSignal(
            id="quiet-park",
            name="狐尾山公园",
            category="park",
            city="厦门",
            lat=24.4810,
            lng=118.0870,
            activity_hint="树荫和风更明显",
            detail_hint="适合慢慢恢复体力",
            source="test-map-provider",
            guide_score=4.6,
            distance_meters=180,
        )
        plan = JourneyPlan(
            pet_id=pet.pet_id,
            city="厦门",
            generated_at=datetime(2026, 7, 4, 4, 20, tzinfo=timezone.utc),
            provider="test-planner",
            horizon_hours=24,
            summary="今天慢慢走，累了就停。",
            current_activity=current.activity_hint,
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="短距离步行。",
                rejected_modes=[TravelMode.flight],
                autonomy_note="TA 自己决定节奏。",
            ),
            route_segments=[
                RouteSegment(
                    id="street-to-cafe",
                    mode=TravelMode.walk,
                    title="沿真实道路慢慢走",
                    detail="中午会注意补水。",
                    from_place=current.name,
                    to_place=cafe.name,
                    distance_meters=130,
                    duration_seconds=240,
                    provider="test-planner",
                )
            ],
            stops=[
                ItineraryStop(
                    id=current.id,
                    name=current.name,
                    category=current.category,
                    city=current.city,
                    lat=current.lat,
                    lng=current.lng,
                    title="中午路过街角",
                    detail="这里比较热，需要自己判断要不要停。",
                    planned_time="12:20",
                    dwell_minutes=12,
                )
            ],
            places=[current, cafe, park],
        )
        activity = WorldActivity(
            id="activity-hot-walk",
            kind="movement",
            status=JourneyStatus.walking,
            title="在太阳下面慢慢走",
            detail="中午有点热，人群很多，已经走了一段路。",
            city="厦门",
            place_name=current.name,
            lat=current.lat,
            lng=current.lng,
            mode=TravelMode.walk,
            progress=0.35,
            next_place_name=cafe.name,
            icon_hint="figure.walk",
            source="test-world",
        )
        snapshot = WorldSimulationSnapshot(
            pet_id=pet.pet_id,
            city="厦门",
            generated_at=datetime(2026, 7, 4, 4, 20, tzinfo=timezone.utc),
            provider="test-world",
            elapsed_seconds=12_000,
            travel_day=1,
            weather="多云，31°C，有点热，湿度78%",
            status=JourneyStatus.walking,
            status_note="正在路上",
            energy=32,
            happiness=74,
            curiosity=68,
            current_activity=activity,
            timeline=[],
            rules=["真实世界原则"],
        )

        result = PetLifeSimulationEngine(Settings(), EmptyMemoryStore()).tick(
            pet=pet,
            city=JourneyCity(
                name="厦门",
                lat=24.4798,
                lng=118.0894,
                weather="多云，31°C，有点热，湿度78%",
                phrases=("慢一点",),
                thoughts=("汪",),
            ),
            plan=plan,
            snapshot=snapshot,
            now=datetime(2026, 7, 4, 4, 20, tzinfo=timezone.utc),
        )

        self.assertEqual(result.need_state.primary_need, "rest")
        self.assertEqual(result.intent.kind, "rest_nearby")
        self.assertEqual(result.action.place_name, cafe.name)
        self.assertEqual(result.animation_hint, "sleep")
        self.assertNotIn("计划优先级", result.intent.reason)
        self.assertNotIn("攻略型", result.owner_visible_summary)

    def test_world_simulation_anchors_stops_without_location_drift(self) -> None:
        local_tz = timezone(timedelta(hours=8))
        pet = self.sample_pet(created_at=datetime(2026, 7, 4, 0, 0, tzinfo=local_tz))
        first_stop = ItineraryStop(
            id="morning-park",
            name="狐尾山公园",
            category="park",
            city="厦门",
            lat=24.4928,
            lng=118.0823,
            title="在公园慢慢醒来",
            detail="我先在这里听风。",
            planned_time="08:10",
            dwell_minutes=60,
        )
        last_stop = ItineraryStop(
            id="evening-cafe",
            name="默迹咖啡馆",
            category="cafe",
            city="厦门",
            lat=24.4708,
            lng=118.1011,
            title="傍晚坐下喝点东西",
            detail="我会在这里慢慢停留。",
            planned_time="18:40",
            dwell_minutes=50,
        )
        plan = JourneyPlan(
            pet_id=pet.pet_id,
            city="厦门",
            generated_at=datetime(2026, 7, 4, 0, 0, tzinfo=local_tz),
            provider="test-planner",
            horizon_hours=24,
            summary="今天慢慢生活。",
            current_activity=first_stop.detail,
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="短路段慢慢走。",
                rejected_modes=[],
                autonomy_note="TA 自己决定节奏。",
            ),
            route_segments=[
                RouteSegment(
                    id="park-to-cafe",
                    mode=TravelMode.walk,
                    title="沿真实道路慢慢走",
                    detail="沿路慢慢靠近下一站。",
                    from_place=first_stop.name,
                    to_place=last_stop.name,
                    distance_meters=2_400,
                    duration_seconds=1_800,
                    provider="test-planner",
                )
            ],
            stops=[first_stop, last_stop],
            places=[
                PlaceSignal(
                    id=first_stop.id,
                    name=first_stop.name,
                    category=first_stop.category,
                    city=first_stop.city,
                    lat=first_stop.lat,
                    lng=first_stop.lng,
                    activity_hint=first_stop.detail,
                    detail_hint="第一站",
                    source="test",
                ),
                PlaceSignal(
                    id=last_stop.id,
                    name=last_stop.name,
                    category=last_stop.category,
                    city=last_stop.city,
                    lat=last_stop.lat,
                    lng=last_stop.lng,
                    activity_hint=last_stop.detail,
                    detail_hint="最后一站",
                    source="test",
                ),
            ],
        )
        city = JourneyCity(
            name="厦门",
            lat=24.4798,
            lng=118.0894,
            weather="多云，29°C",
            phrases=("慢慢走",),
            thoughts=("汪",),
        )
        engine = WorldSimulationEngine(Settings())

        before_start = engine.snapshot(
            pet=pet,
            city=city,
            plan=plan,
            now=datetime(2026, 7, 4, 1, 0, tzinfo=local_tz),
        )
        self.assertEqual(before_start.current_activity.place_name, first_stop.name)
        self.assertAlmostEqual(before_start.current_activity.lat, first_stop.lat)
        self.assertAlmostEqual(before_start.current_activity.lng, first_stop.lng)

        first_refresh = engine.snapshot(
            pet=pet,
            city=city,
            plan=plan,
            now=datetime(2026, 7, 4, 8, 20, tzinfo=local_tz),
        )
        second_refresh = engine.snapshot(
            pet=pet,
            city=city,
            plan=plan,
            now=datetime(2026, 7, 4, 8, 45, tzinfo=local_tz),
        )

        self.assertEqual(first_refresh.current_activity.place_name, first_stop.name)
        self.assertEqual(second_refresh.current_activity.place_name, first_stop.name)
        self.assertAlmostEqual(first_refresh.current_activity.lat, first_stop.lat)
        self.assertAlmostEqual(second_refresh.current_activity.lat, first_stop.lat)
        self.assertAlmostEqual(first_refresh.current_activity.lng, first_stop.lng)
        self.assertAlmostEqual(second_refresh.current_activity.lng, first_stop.lng)

    def test_amap_provider_is_selected_when_configured(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "amap.sqlite3",
            upload_dir=Path(self.tempdir.name) / "amap-uploads",
            public_base_url="http://testserver",
            map_provider="amap",
            amap_api_key="test-amap-key",
        )
        client = TestClient(create_app(settings))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["map_provider_mode"], "amap")
        self.assertEqual(payload["map_provider"], "amap-web-map-provider")
        self.assertEqual(payload["world_simulation_engine"], "world-simulation-engine")
        self.assertEqual(payload["weather_provider"], "amap-weather-provider")
        self.assertEqual(payload["amap_web_service"], "amap-web-service-client")
        self.assertEqual(payload["street_rank_engine"], "petsoul-street-rank-engine")

    def test_google_provider_is_selected_when_configured(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "google.sqlite3",
            upload_dir=Path(self.tempdir.name) / "google-uploads",
            public_base_url="http://testserver",
            map_provider="google",
            google_maps_api_key="test-google-key",
        )
        client = TestClient(create_app(settings))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["map_provider"], "google-maps-map-provider")
        self.assertEqual(payload["google_maps_service"], "google-maps-service-client")
        self.assertEqual(payload["weather_provider"], "google-weather-provider")

        config = client.get("/api/v1/google/config")
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.json()["routes_api"])

    def test_google_maps_service_parses_places_routes_and_regeo(self) -> None:
        class FakeGoogleMapsServiceClient(GoogleMapsServiceClient):
            def _post_json(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
                if "places:searchNearby" in url:
                    return {
                        "places": [
                            {
                                "id": "places/test-cafe",
                                "displayName": {"text": "星巴克京都二年坂茶屋店"},
                                "formattedAddress": "Kyoto",
                                "location": {"latitude": 35.0001, "longitude": 135.7801},
                                "rating": 4.4,
                                "userRatingCount": 1200,
                                "primaryType": "cafe",
                                "types": ["cafe", "food", "point_of_interest"],
                                "photos": [{"name": "places/test/photos/1"}],
                            }
                        ]
                    }
                if "directions/v2:computeRoutes" in url:
                    return {
                        "routes": [
                            {
                                "distanceMeters": 872,
                                "duration": "740s",
                                "polyline": {"encodedPolyline": "encoded-polyline"},
                            }
                        ]
                    }
                return {}

            def _get_json(self, url: str) -> dict[str, object]:
                return {
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "488 Kamihonnōjimaechō, Nakagyo Ward, Kyoto, 604-8571日本",
                            "address_components": [
                                {"long_name": "Kyoto", "types": ["locality", "political"]},
                                {"long_name": "Kyoto Prefecture", "types": ["administrative_area_level_1", "political"]},
                                {"long_name": "Kamihonnōjimaechō", "types": ["route"]},
                            ],
                        }
                    ],
                }

        client = FakeGoogleMapsServiceClient(Settings(google_maps_api_key="test-google-key"))
        places = client.places_nearby(city_name="京都", lat=35.0116, lng=135.7681, theme="coffee", limit=3)
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].category, "cafe")
        self.assertEqual(places[0].source, "google-maps-service-client")
        self.assertEqual(places[0].rating, 4.4)

        route = client.route_between(
            mode=TravelMode.walk,
            origin_lng=135.7681,
            origin_lat=35.0116,
            destination_lng=135.7717,
            destination_lat=35.0159,
        )
        self.assertIsNotNone(route)
        self.assertEqual(route.distance_meters, 872)
        self.assertEqual(route.duration_seconds, 740)
        self.assertEqual(route.polyline, "encoded-polyline")

        regeo = client.reverse_geocode(lat=35.0116, lng=135.7681)
        self.assertIsNotNone(regeo)
        self.assertEqual(regeo.city, "Kyoto")
        self.assertEqual(regeo.source, "google-maps-service-client")

    def test_amap_web_service_parses_route_tips_and_regeo(self) -> None:
        class FakeAMapWebServiceClient(AMapWebServiceClient):
            def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
                if path == "/v3/direction/walking":
                    return {
                        "status": "1",
                        "route": {
                            "paths": [
                                {
                                    "distance": "1234",
                                    "duration": "900",
                                    "steps": [
                                        {"polyline": "118.1,24.4;118.2,24.5"},
                                        {"polyline": "118.2,24.5;118.3,24.6"},
                                    ],
                                }
                            ]
                        },
                    }
                if path == "/v3/assistant/inputtips":
                    return {
                        "status": "1",
                        "tips": [
                            {
                                "id": "B0TEST",
                                "name": "默迹咖啡馆",
                                "district": "福建省厦门市思明区",
                                "adcode": "350203",
                                "address": "测试路",
                                "typecode": "050500",
                                "location": "118.082,24.474",
                            }
                        ],
                    }
                if path == "/v3/geocode/regeo":
                    return {
                        "status": "1",
                        "regeocode": {
                            "formatted_address": "福建省厦门市思明区测试路",
                            "addressComponent": {
                                "province": "福建省",
                                "city": "厦门市",
                                "district": "思明区",
                                "township": "测试街道",
                                "adcode": "350203",
                                "streetNumber": {"street": "测试路", "number": "1号"},
                            },
                        },
                    }
                return {"status": "1"}

        client = FakeAMapWebServiceClient(Settings(amap_api_key="test-amap-key"))

        route = client.route_between(
            mode=TravelMode.walk,
            origin_lng=118.1,
            origin_lat=24.4,
            destination_lng=118.3,
            destination_lat=24.6,
        )
        self.assertIsNotNone(route)
        self.assertEqual(route.distance_meters, 1234)
        self.assertEqual(route.duration_seconds, 900)
        self.assertEqual(route.polyline, "118.1,24.4;118.2,24.5;118.3,24.6")

        tips = client.input_tips(keywords="咖啡", city="厦门")
        self.assertEqual(tips[0].name, "默迹咖啡馆")
        self.assertEqual(tips[0].lat, 24.474)
        self.assertEqual(tips[0].lng, 118.082)

        regeo = client.reverse_geocode(lat=24.474, lng=118.082)
        self.assertIsNotNone(regeo)
        self.assertEqual(regeo.formatted_address, "福建省厦门市思明区测试路")
        self.assertEqual(regeo.adcode, "350203")

    def test_amap_weather_provider_formats_and_caches_live_weather(self) -> None:
        class FakeAMapWeatherProvider(AMapWeatherProvider):
            calls = 0

            def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
                self.calls += 1
                self.assert_weather_path = path
                return {
                    "status": "1",
                    "lives": [
                        {
                            "weather": "多云",
                            "temperature": "29",
                            "winddirection": "东南",
                            "windpower": "3",
                            "humidity": "78",
                        }
                    ],
                }

        settings = Settings(amap_api_key="test-amap-key", map_provider="amap")
        provider = FakeAMapWeatherProvider(settings)
        city = JourneyCity(
            name="厦门",
            lat=24.4798,
            lng=118.0894,
            weather="海风很轻",
            phrases=("慢慢走",),
            thoughts=("汪",),
        )
        now = datetime(2026, 7, 3, 4, 0, tzinfo=timezone.utc)

        first = provider.city_with_weather(city, now=now)
        second = provider.city_with_weather(city, now=now + timedelta(seconds=30))

        self.assertEqual(first.weather, "多云，29°C，东南风3级，湿度78%")
        self.assertEqual(second.weather, first.weather)
        self.assertEqual(provider.calls, 1)

    def test_google_weather_provider_formats_and_caches_live_weather(self) -> None:
        class FakeGoogleWeatherProvider(GoogleWeatherProvider):
            calls = 0
            last_url = ""
            last_params: dict[str, str] = {}

            def _get_json(self, url: str, params: dict[str, str]) -> dict[str, object]:
                self.calls += 1
                self.last_url = url
                self.last_params = params
                return {
                    "weatherCondition": {
                        "description": {"text": "Sunny", "languageCode": "en"},
                        "type": "CLEAR",
                    },
                    "temperature": {"unit": "CELSIUS", "degrees": 23.8},
                    "feelsLikeTemperature": {"unit": "CELSIUS", "degrees": 25.2},
                    "relativeHumidity": 52,
                    "wind": {
                        "direction": {"degrees": 250, "cardinal": "WEST_SOUTHWEST"},
                        "speed": {"unit": "KILOMETERS_PER_HOUR", "value": 11.2},
                    },
                    "uvIndex": 7,
                }

        settings = Settings(google_maps_api_key="test-google-key", map_provider="google")
        provider = FakeGoogleWeatherProvider(settings)
        city = JourneyCity(
            name="洛杉矶",
            lat=34.0522,
            lng=-118.2437,
            weather="阳光很亮",
            phrases=("慢慢走",),
            thoughts=("汪",),
        )
        now = datetime(2026, 7, 3, 4, 0, tzinfo=timezone.utc)

        first = provider.city_with_weather(city, now=now)
        second = provider.city_with_weather(city, now=now + timedelta(seconds=30))

        self.assertEqual(first.weather, "Sunny，24°C，体感25°C，湿度52%，西南偏西风11km/h，UV 7")
        self.assertEqual(second.weather, first.weather)
        self.assertEqual(provider.calls, 1)
        self.assertIn("currentConditions:lookup", provider.last_url)
        self.assertEqual(provider.last_params["unitsSystem"], "METRIC")

    def test_image_provider_reports_relay_configuration(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "image.sqlite3",
            upload_dir=Path(self.tempdir.name) / "image-uploads",
            public_base_url="http://testserver",
            image_api_key="test-image-key",
            image_base_url="https://api.austinsapi.com/v1",
            image_model="gpt-image-2",
        )
        client = TestClient(create_app(settings))
        response = client.get("/api/v1/image_provider/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "openai-compatible-image-provider")
        self.assertEqual(payload["image_model"], "gpt-image-2")
        self.assertEqual(payload["base_url"], "https://api.austinsapi.com/v1")
        self.assertTrue(payload["remote_configured"])
        self.assertTrue(payload["remote_call_active"])
        self.assertTrue(payload["remote_call_enabled"])
        self.assertTrue(payload["reference_image_supported"])

    def test_worldcup_journey_plan_uses_multimodal_transport(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "worldcup.sqlite3",
            upload_dir=Path(self.tempdir.name) / "worldcup-uploads",
            public_base_url="http://testserver",
            worldcup_demo_enabled=True,
        )
        client = TestClient(create_app(settings))
        pet_id = self.create_pet(client=client)

        response = client.get(f"/api/v1/pets/{pet_id}/journey_plan")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["worldcup_event"])
        self.assertEqual(payload["transport_decision"]["selected_mode"], "flight")
        self.assertTrue(any(item["mode"] == "flight" for item in payload["route_segments"]))
        self.assertTrue(any(item["mode"] == "flight" for item in payload["scheduled_transport"]))
        flight_leg = next(item for item in payload["scheduled_transport"] if item["mode"] == "flight")
        self.assertEqual(flight_leg["service_number"], "FLIGHT-DEMO")
        self.assertIn(flight_leg["status"], {"scheduled", "waiting", "boarding", "in_transit", "arrived"})
        self.assertTrue(any(item["category"] == "stadium" for item in payload["places"]))

        snapshot = client.get(f"/api/v1/pets/{pet_id}/world_snapshot")
        self.assertEqual(snapshot.status_code, 200)
        snapshot_payload = snapshot.json()
        self.assertTrue(any(item["mode"] == "flight" for item in snapshot_payload["timeline"]))
        self.assertTrue(snapshot_payload["rules"])

    def test_travel_quest_worldcup_wish_builds_guide_before_departure(self) -> None:
        pet_id = self.create_pet()

        response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={
                "message": "小福，我想让你明天去世界杯看德国队比赛，先自己做一份攻略。",
                "preferred_start_date": "2026-07-05",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pet_id"], pet_id)
        self.assertEqual(payload["quest_type"], "worldcup")
        self.assertEqual(payload["status"], "guide_ready")
        self.assertTrue(payload["worldcup_event"])
        self.assertIsNone(payload["journey_plan"])
        self.assertEqual(payload["trip_type"], "round_trip")
        self.assertEqual(payload["return_policy"], "ask_after_event")
        self.assertEqual(payload["current_phase"], "guide_ready")
        self.assertEqual(payload["origin_anchor"]["city"], "厦门")
        self.assertIn("世界杯", payload["guide"]["title"])
        self.assertEqual(payload["guide"]["research"]["provider"], "openai_web_search")
        self.assertIn("Web Search", payload["guide"]["research"]["strategy"])
        self.assertTrue(any("赛场" in item["name"] for item in payload["guide"]["stops"]))
        self.assertTrue(any(item["mode"] == "flight" for item in payload["guide"]["transport_outline"]))
        self.assertIn("先", payload["autonomy_decision"])

        quests = self.client.get(f"/api/v1/pets/{pet_id}/travel_quests")
        self.assertEqual(quests.status_code, 200)
        self.assertEqual(len(quests.json()), 1)

        prepare = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{payload['id']}/prepare_departure")
        self.assertEqual(prepare.status_code, 200)
        prepared = prepare.json()
        self.assertEqual(prepared["status"], "preparing")
        self.assertIsNotNone(prepared["journey_plan"])
        self.assertTrue(prepared["journey_plan"]["worldcup_event"])
        self.assertTrue(any(item["photo_candidate"] for item in prepared["journey_plan"]["stops"]))

        options = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{payload['id']}/post_event_options")
        self.assertEqual(options.status_code, 200)
        options_payload = options.json()
        self.assertEqual(options_payload["status"], "return_planning")
        self.assertGreaterEqual(len(options_payload["post_event_options"]), 3)
        self.assertTrue(any(item["decision_type"] == "return_to_origin" for item in options_payload["post_event_options"]))

        select = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests/{payload['id']}/select_next_step",
            json={"option_id": "return-home-anchor", "owner_message": "看完比赛慢慢回家吧"},
        )
        self.assertEqual(select.status_code, 200)
        selected = select.json()
        self.assertEqual(selected["status"], "return_traveling")
        self.assertEqual(selected["selected_next_option_id"], "return-home-anchor")
        self.assertEqual(selected["journey_plan"]["city"], "厦门")

    def test_travel_quest_china_destination_prefers_doubao_social_research_placeholder(self) -> None:
        pet_id = self.create_pet()

        response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={
                "message": "小福，我想让你去鼓浪屿先做一份怎么玩的攻略。",
                "destination": "鼓浪屿",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["quest_type"], "city_trip")
        self.assertEqual(payload["guide"]["research"]["provider"], "doubao_social")
        self.assertIn("中国社媒", payload["guide"]["research"]["strategy"])
        self.assertIn("高德 POI/榜单", payload["guide"]["research"]["recommended_sources"])

    def test_doubao_ark_payload_matches_responses_multimodal_shape(self) -> None:
        settings = Settings(doubao_api_key="test-ark-key")
        client = DoubaoArkClient(settings)
        payload = client.build_vision_probe_payload(
            image_url="https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png",
            text="你看见了什么？",
        )

        self.assertEqual(payload["model"], "doubao-seed-2-1-pro-260628")
        content = payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_image")
        self.assertEqual(content[1]["type"], "input_text")

    def test_travel_research_uses_doubao_ark_when_configured(self) -> None:
        class FakeDoubaoClient:
            provider_name = "fake-doubao-ark"
            configured = True

            def guide_research(self, **_: object) -> GuideResearchDraft:
                return GuideResearchDraft(
                    strategy="先看近期真实游记，再让 TA 选能停留和拍照的生活路线。",
                    findings=[
                        "鼓浪屿适合按渡口、街巷、小店和海边慢慢串起来。",
                        "早上先看船班和天气，中午避开最晒的坡道。",
                        "咖啡店、小食铺和海边邮局都适合生成给主人看的照片或明信片。",
                    ],
                    recommended_sources=["高德 POI/榜单", "小红书公开攻略", "抖音公开内容"],
                    raw_text="{}",
                )

        engine = TravelGuideResearchEngine(
            Settings(doubao_api_key="test-ark-key", travel_guide_research_provider="doubao"),
            doubao_client=FakeDoubaoClient(),
        )
        research = engine.research(
            owner_message="小福先替我去鼓浪屿走一遍攻略",
            destination="鼓浪屿",
            quest_type=TravelQuestType.city_trip,
            current_city=JourneyCity(
                name="厦门",
                lat=24.4798,
                lng=118.0894,
                weather="多云",
                phrases=("慢慢走",),
                thoughts=("先替你看看。",),
            ),
            event_name=None,
            now=datetime.now(timezone.utc),
        )

        self.assertEqual(research.provider_name, "fake-doubao-ark")
        self.assertIn("真实游记", research.strategy)
        self.assertTrue(any("明信片" in finding for finding in research.findings))
        self.assertEqual(research.destination_region, "china")
        self.assertEqual(research.fact_provider_priority[:2], ["amap", "doubao_social"])
        self.assertGreaterEqual(len(research.social_findings), 1)
        self.assertGreaterEqual(len(research.evidence_packets), 1)
        self.assertTrue(all(packet.needs_verification for packet in research.evidence_packets))
        self.assertFalse(research.can_inform_replicable_route)
        self.assertTrue(any("高德" in note or "Google" in note for note in research.quality_gate_notes))
        self.assertTrue(any("高德 / Google Map" in role for role in research.orchestration_roles))
        self.assertTrue(any("Doubao" in role for role in research.orchestration_roles))
        self.assertTrue(any("GPT" in role for role in research.orchestration_roles))
        self.assertTrue(any("规则引擎" in role for role in research.orchestration_roles))
        self.assertTrue(any("Doubao Voice" in step for step in research.pipeline_steps))
        self.assertTrue(any("连锁快餐" in rule for rule in research.quality_gate_rules))
        self.assertEqual(research.voice_writer, "doubao_pet_voice")
        self.assertTrue(research.deep_critic_required)
        self.assertEqual(research.missing_capabilities, [])

    def test_travel_research_structures_social_evidence_without_model(self) -> None:
        engine = TravelGuideResearchEngine(Settings(travel_guide_research_provider="auto"))
        research = engine.research(
            owner_message="小福先替我看看厦门一天怎么玩",
            destination="厦门",
            quest_type=TravelQuestType.city_trip,
            current_city=JourneyCity(
                name="厦门",
                lat=24.4798,
                lng=118.0894,
                weather="多云",
                phrases=("慢慢走",),
                thoughts=("先替你看看。",),
            ),
            event_name=None,
            now=datetime.now(timezone.utc),
        )

        self.assertEqual(research.provider.value, "doubao_social")
        self.assertEqual(research.research_brief["city"], "厦门")
        self.assertIn("amap", research.fact_provider_priority)
        self.assertGreaterEqual(len(research.social_findings), 3)
        packet_names = " ".join(packet.name for packet in research.evidence_packets)
        self.assertIn("八市", packet_names)
        self.assertIn("沙坡尾", packet_names)
        self.assertTrue(all(packet.verification_status == "social_only_needs_map_verification" for packet in research.evidence_packets))
        self.assertTrue(any("社媒线索只作为软证据" in note for note in research.quality_gate_notes))
        self.assertTrue(any("高德召回国内" in step for step in research.pipeline_steps))
        self.assertIn("local_pet_voice_template", research.voice_writer)

    def test_travel_bag_and_souvenirs_attach_to_travel_quest(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={
                "message": "小福，我想让你去鼓浪屿慢慢玩，回来带一点小东西。",
                "destination": "鼓浪屿",
            },
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]

        empty_bag = self.client.get(f"/api/v1/pets/{pet_id}/travel_bag", params={"quest_id": quest_id})
        self.assertEqual(empty_bag.status_code, 200)
        self.assertEqual(empty_bag.json()["items"], [])
        self.assertIn("小包", empty_bag.json()["pet_visible_note"])

        packed = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_bag",
            json={
                "quest_id": quest_id,
                "owner_message": "慢慢玩，看到喜欢的小东西就带回来。",
                "items": [
                    {
                        "item_type": "snack",
                        "title": "路上小零食",
                        "note": "累的时候闻一闻就好",
                        "influence_tags": ["comfort", "slow_travel"],
                    },
                    {
                        "item_type": "lucky_charm",
                        "title": "小小护身符",
                        "note": "不要赶路",
                        "influence_tags": ["return_home", "rare_photo"],
                    },
                    {
                        "item_type": "guide_hint",
                        "title": "想看海边小店",
                        "note": "如果路过就看一眼",
                        "influence_tags": ["sea", "souvenir"],
                    },
                ],
            },
        )
        self.assertEqual(packed.status_code, 200)
        bag_payload = packed.json()
        self.assertEqual(bag_payload["quest_id"], quest_id)
        self.assertEqual(len(bag_payload["items"]), 3)
        self.assertIn("不会替我决定路线", bag_payload["pet_visible_note"])

        quest_with_bag = self.client.get(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}")
        self.assertEqual(quest_with_bag.status_code, 200)
        self.assertEqual(quest_with_bag.json()["travel_bag"]["items"][0]["title"], "路上小零食")

        souvenirs = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs")
        self.assertEqual(souvenirs.status_code, 200)
        souvenir_payload = souvenirs.json()
        self.assertGreaterEqual(len(souvenir_payload), 3)
        self.assertTrue(any(item["item_type"] in {"toy", "cultural_creative"} for item in souvenir_payload))
        self.assertTrue(all(item["quest_id"] == quest_id for item in souvenir_payload))
        self.assertTrue(all(item["image_prompt"] for item in souvenir_payload))
        self.assertIn("鼓浪屿", souvenir_payload[0]["city"])
        souvenir_titles = {item["title"] for item in souvenir_payload}
        self.assertIn("鼓浪屿渡船票角", souvenir_titles)
        self.assertIn("海风小船贴纸", souvenir_titles)
        self.assertTrue(any("小包" in item["story"] for item in souvenir_payload))

        repeated = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(
            [item["id"] for item in repeated.json()],
            [item["id"] for item in souvenir_payload],
        )

        collection = self.client.get(f"/api/v1/pets/{pet_id}/souvenirs")
        self.assertEqual(collection.status_code, 200)
        self.assertEqual(len(collection.json()), len(souvenir_payload))

    def test_souvenir_catalog_uses_destination_specific_collectibles(self) -> None:
        pet_id = self.create_pet()
        cases = [
            ("京都", ["和纸小书签", "抹茶糖纸", "鸭川小石子"]),
            ("雷克雅未克", ["火山黑沙小瓶", "羊毛线结", "极光色小卡"]),
        ]

        for destination, expected_titles in cases:
            quest_response = self.client.post(
                f"/api/v1/pets/{pet_id}/travel_quests",
                json={
                    "message": f"小福，替我去{destination}慢慢走一走，看看会带回什么小东西。",
                    "destination": destination,
                },
            )
            self.assertEqual(quest_response.status_code, 200)
            quest_id = quest_response.json()["id"]

            souvenirs = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs")
            self.assertEqual(souvenirs.status_code, 200)
            payload = souvenirs.json()
            titles = {item["title"] for item in payload}
            for title in expected_titles:
                self.assertIn(title, titles)
            self.assertNotIn(f"{destination} 小冰箱贴", titles)
            self.assertTrue(all(item["city"] == destination for item in payload))

    def test_economy_collect_is_idempotent_and_sell_uses_item_version(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={
                "message": "小星，去鼓浪屿慢慢玩，回来带一点小东西。",
                "destination": "鼓浪屿",
            },
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]

        first_collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(first_collect.status_code, 200)
        first_payload = first_collect.json()
        first_ids = [item["id"] for item in first_payload["items"]]
        first_tx_ids = [tx["tx_id"] for tx in first_payload["transactions"]]
        self.assertGreaterEqual(len(first_ids), 3)
        self.assertEqual(first_payload["snapshot"]["owned_item_count"], len(first_ids))
        self.assertTrue(all(item["template_id"] for item in first_payload["items"]))
        self.assertTrue(all(item["value_breakdown"]["final_market_value"] == item["market_value"] for item in first_payload["items"]))

        for _ in range(9):
            repeated = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
            self.assertEqual(repeated.status_code, 200)
            repeated_payload = repeated.json()
            self.assertEqual([item["id"] for item in repeated_payload["items"]], first_ids)
            self.assertEqual([tx["tx_id"] for tx in repeated_payload["transactions"]], first_tx_ids)

        economy = self.client.get(f"/api/v1/pets/{pet_id}/economy")
        self.assertEqual(economy.status_code, 200)
        self.assertEqual(len(economy.json()["recent_transactions"]), 1)
        self.assertEqual(economy.json()["recent_transactions"][0]["type"], "item_acquired")

        sellable = next(item for item in first_payload["items"] if item["trade_policy"] == "tradable")
        sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-once", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(sell.status_code, 200)
        sell_payload = sell.json()
        self.assertEqual(sell_payload["item"]["status"], "sold")
        self.assertEqual(sell_payload["item"]["version"], sellable["version"] + 1)
        self.assertEqual(sell_payload["wallet"]["travel_coin"], sellable["market_value"] // 2)

        repeated_sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-once", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(repeated_sell.status_code, 200)
        self.assertEqual(repeated_sell.json()["transaction"]["tx_id"], sell_payload["transaction"]["tx_id"])

        stale_sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-again", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(stale_sell.status_code, 409)

    def test_economy_derived_state_can_be_rebuilt_from_transactions(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={"message": "小星，去泉州走走，回来带一点小收藏。", "destination": "泉州"},
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]
        collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(collect.status_code, 200)
        sellable = next(item for item in collect.json()["items"] if item["trade_policy"] == "tradable")
        sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "replay-sell", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(sell.status_code, 200)

        expected = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        storage = self.client.app.state.storage
        storage.clear_economy_derived_state(pet_id)
        self.assertIsNone(storage.get_wallet(pet_id))
        self.assertIsNone(storage.get_economy_snapshot(pet_id))

        rebuilt = self.client.app.state.economy_engine.rebuild_derived_state(pet_id).model_dump(mode="json", by_alias=True)
        self.assertEqual(rebuilt["wallet"]["travel_coin"], expected["wallet"]["travel_coin"])
        self.assertEqual(rebuilt["wallet"]["star_dust"], expected["wallet"]["star_dust"])
        self.assertEqual(rebuilt["wallet"]["merit"], expected["wallet"]["merit"])
        for key in (
            "total_display_value",
            "sellable_value",
            "collection_value",
            "honor_value",
            "owned_item_count",
            "sellable_item_count",
            "archived_item_count",
            "sold_item_count",
        ):
            self.assertEqual(rebuilt["snapshot"][key], expected["snapshot"][key])
        self.assertEqual([tx["type"] for tx in rebuilt["recent_transactions"]], ["item_sold", "item_acquired"])

    def test_economy_read_endpoints_do_not_create_rewards_or_transactions(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={"message": "小星，去京都看看会带回什么。", "destination": "京都"},
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]
        collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(collect.status_code, 200)

        before_economy = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        before_inventory = self.client.get(f"/api/v1/pets/{pet_id}/inventory", params={"status": "all"}).json()
        before_tx_ids = [tx["tx_id"] for tx in before_economy["recent_transactions"]]
        before_item_ids = [item["id"] for item in before_inventory["items"]]

        for path in (
            f"/api/v1/pets/{pet_id}/economy",
            f"/api/v1/pets/{pet_id}/inventory?status=all",
            f"/api/v1/pets/{pet_id}/city_position",
            f"/api/v1/pets/{pet_id}/world_snapshot",
            f"/api/v1/pets/{pet_id}/life_tick",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)

        after_economy = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        after_inventory = self.client.get(f"/api/v1/pets/{pet_id}/inventory", params={"status": "all"}).json()
        self.assertEqual([tx["tx_id"] for tx in after_economy["recent_transactions"]], before_tx_ids)
        self.assertEqual([item["id"] for item in after_inventory["items"]], before_item_ids)
        self.assertEqual(after_economy["wallet"], before_economy["wallet"])

    def test_owner_fund_grant_requires_dev_admin_and_is_idempotent(self) -> None:
        pet_id = self.create_pet()
        disabled = self.client.post(
            f"/api/v1/pets/{pet_id}/owner_fund/grant",
            json={"grant_id": "grant-1", "star_dust": 1000, "reason": "test"},
        )
        self.assertEqual(disabled.status_code, 403)

        root = Path(self.tempdir.name) / "grant-app"
        settings = Settings(
            database_path=root / "petjourney.sqlite3",
            upload_dir=root / "uploads",
            public_base_url="http://testserver",
            economy_dev_grants_enabled=True,
            economy_admin_token="secret-token",
        )
        client = TestClient(create_app(settings))
        grant_pet_id = self.create_pet(client=client)

        wrong = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "wrong"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(wrong.status_code, 403)

        ok = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "secret-token"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertEqual(payload["wallet"]["star_dust"], 1000)
        self.assertEqual(payload["owner_fund"]["star_dust"], 1000)
        self.assertEqual(payload["owner_fund"]["project_budget"], 700)
        self.assertEqual(payload["recent_transactions"][0]["type"], "owner_fund_granted")

        repeated = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "secret-token"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["wallet"]["star_dust"], 1000)
        self.assertEqual(len(repeated.json()["recent_transactions"]), 1)

    def test_economy_value_breakdown_is_stable_and_rarity_monotonic(self) -> None:
        engine = self.client.app.state.economy_engine
        pet = self.sample_pet()
        base_item = SouvenirItem(
            id="SV-TEST",
            pet_id=pet.pet_id,
            quest_id="TQ-TEST",
            template_id="tpl_test_shell",
            item_type=SouvenirItemType.found_object,
            title="测试贝壳",
            subtitle="一枚用于测试的贝壳",
            city="青岛",
            place_name="第一海水浴场",
            story="退潮时发现，像一颗小星星。",
            pet_voice="我想把它带回来。",
            image_prompt="test",
            rarity="common",
            obtained_at=datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc),
            source="test",
        )

        first = engine._value_for_item(
            pet=pet,
            item=base_item,
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )
        second = engine._value_for_item(
            pet=pet,
            item=base_item,
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )
        rare = engine._value_for_item(
            pet=pet,
            item=base_item.model_copy(update={"rarity": "rare"}),
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )

        self.assertEqual(first.value_breakdown, second.value_breakdown)
        self.assertGreater(rare.market_value, first.market_value)

    def test_web_search_transport_schedule_parses_reference_only_candidate(self) -> None:
        class FakeWebSearchTransportScheduleProvider(OpenAIWebSearchTransportScheduleProvider):
            captured_payload: dict[str, object] | None = None

            def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
                self.captured_payload = payload
                return {
                    "output_text": json.dumps(
                        {
                            "found": True,
                            "mode": "flight",
                            "carrier": "Qatar Airways",
                            "service_number": "QR881",
                            "origin_name": "Xiamen Gaoqi International Airport",
                            "destination_name": "Doha Hamad International Airport",
                            "scheduled_departure": "18:40 CST",
                            "scheduled_arrival": "22:30 +03",
                            "terminal_or_platform": "T3",
                            "source_urls": ["https://example.com/flight/qr881"],
                            "confidence": "medium",
                            "notes": "Reference schedule only; no booking data.",
                        }
                    )
                }

        settings = Settings(
            openai_api_key="test-key",
            transport_schedule_provider="openai",
            transport_web_search_enabled=True,
        )
        provider = FakeWebSearchTransportScheduleProvider(settings)
        pet = self.sample_pet()
        request = TransportScheduleRequest(
            pet=pet,
            mode=TravelMode.flight,
            origin=self.place("xiamen", "厦门", "厦门", 24.544, 118.127, "city"),
            destination=self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport"),
            depart_after=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
            context="World Cup travel reference only.",
        )

        candidate = provider.best_candidate(request)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.service_number, "QR881")
        self.assertEqual(candidate.mode, TravelMode.flight)
        self.assertAlmostEqual(
            (candidate.scheduled_arrival - candidate.scheduled_departure).total_seconds() / 3600,
            8.83,
            places=1,
        )
        self.assertEqual(candidate.source_urls, ("https://example.com/flight/qr881",))
        self.assertEqual(candidate.reality_level, "web_reference_schedule")
        self.assertTrue(candidate.is_simulated)
        self.assertIsNotNone(provider.captured_payload)
        assert provider.captured_payload is not None
        self.assertEqual(provider.captured_payload["tools"], [{"type": "web_search_preview"}])
        prompt = provider.captured_payload["input"][0]["content"]
        self.assertIn("Do not collect", prompt)
        self.assertIn("prices", prompt)
        self.assertIn("seat availability", prompt)
        self.assertIn("booking", prompt)
        self.assertIn("ticketing websites", prompt)

    def test_web_search_transport_schedule_parses_connecting_itinerary(self) -> None:
        class FakeConnectingWebSearchProvider(OpenAIWebSearchTransportScheduleProvider):
            def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
                return {
                    "output_text": json.dumps(
                        {
                            "found": True,
                            "mode": "flight",
                            "itinerary_summary": "厦门经香港中转前往多哈。",
                            "confidence": "medium",
                            "notes": "公开时刻表参考，不含票价或余票。",
                            "segments": [
                                {
                                    "mode": "flight",
                                    "carrier": "Cathay Pacific",
                                    "service_number": "CX973",
                                    "origin_name": "厦门高崎国际机场",
                                    "origin_city": "厦门",
                                    "destination_name": "香港国际机场",
                                    "destination_city": "香港",
                                    "scheduled_departure": "12:20",
                                    "scheduled_arrival": "13:55",
                                    "terminal_or_platform": None,
                                    "source_urls": ["https://example.com/cx973"],
                                    "confidence": "medium",
                                    "notes": "第一段中转航班。",
                                },
                                {
                                    "mode": "flight",
                                    "carrier": "Qatar Airways",
                                    "service_number": "QR817",
                                    "origin_name": "香港国际机场",
                                    "origin_city": "香港",
                                    "destination_name": "多哈哈马德国际机场",
                                    "destination_city": "多哈",
                                    "scheduled_departure": "19:10 HKT",
                                    "scheduled_arrival": "23:05 +03",
                                    "terminal_or_platform": None,
                                    "source_urls": ["https://example.com/qr817"],
                                    "confidence": "medium",
                                    "notes": "第二段中转航班。",
                                },
                            ],
                        }
                    )
                }

        settings = Settings(
            openai_api_key="test-key",
            transport_schedule_provider="openai",
            transport_web_search_enabled=True,
        )
        provider = FakeConnectingWebSearchProvider(settings)
        pet = self.sample_pet()
        request = TransportScheduleRequest(
            pet=pet,
            mode=TravelMode.flight,
            origin=self.place("xiamen", "厦门", "厦门", 24.544, 118.127, "city"),
            destination=self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport"),
            depart_after=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
            context="World Cup connecting flight reference only.",
        )

        itinerary = provider.best_itinerary(request)

        self.assertEqual([item.service_number for item in itinerary], ["CX973", "QR817"])
        self.assertEqual(itinerary[0].destination_name, "香港国际机场")
        self.assertEqual(itinerary[1].origin_name, "香港国际机场")
        self.assertGreater(itinerary[1].scheduled_departure, itinerary[0].scheduled_arrival)
        self.assertTrue(all(item.source_urls for item in itinerary))

    def test_transport_reality_uses_reference_schedule_when_available(self) -> None:
        class FakeScheduleProvider:
            provider_name = "fake-web-reference-schedule-provider"

            def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
                return TransportScheduleCandidate(
                    mode=TravelMode.flight,
                    carrier="Qatar Airways",
                    service_number="QR881",
                    origin_name="Xiamen Gaoqi International Airport",
                    destination_name="Doha Hamad International Airport",
                    scheduled_departure=datetime(2026, 6, 15, 0, 5, tzinfo=timezone.utc),
                    scheduled_arrival=datetime(2026, 6, 15, 9, 15, tzinfo=timezone.utc),
                    terminal_or_platform="T3",
                    source_urls=("https://example.com/flight/qr881",),
                    confidence="high",
                    search_query="xiamen doha flight schedule number departure arrival",
                    notes="公开网页只作为时间线参考。",
                )

        pet = self.sample_pet(created_at=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc))
        provider = MockTransportRealityProvider(schedule_provider=FakeScheduleProvider())
        origin = self.place("xiamen", "厦门街角", "厦门", 24.4798, 118.0894, "street")
        airport = self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport")
        cafe = self.place("cafe", "赛场附近咖啡店", "多哈", 25.265, 51.505, "cafe")
        stadium = self.place("stadium", "世界杯赛场", "多哈", 25.263, 51.485, "stadium")

        legs = provider.worldcup_legs(
            pet=pet,
            origin=origin,
            airport=airport,
            cafe=cafe,
            stadium=stadium,
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
        )

        flight_leg = next(item for item in legs if item.mode == TravelMode.flight)
        self.assertEqual(flight_leg.service_number, "QR881")
        self.assertEqual(flight_leg.carrier, "Qatar Airways")
        self.assertEqual(flight_leg.provider, "fake-web-reference-schedule-provider")
        self.assertEqual(flight_leg.reality_level, "web_reference_schedule")
        self.assertEqual(flight_leg.source_urls, ["https://example.com/flight/qr881"])
        self.assertEqual(flight_leg.confidence, "high")
        self.assertIn("QR881", flight_leg.timeline_note or "")
        drive_leg = next(item for item in legs if item.mode == TravelMode.drive)
        self.assertGreater(drive_leg.scheduled_departure, flight_leg.scheduled_arrival)

    def test_transport_reality_expands_connecting_schedule(self) -> None:
        class FakeConnectingScheduleProvider:
            provider_name = "fake-connecting-schedule-provider"

            def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
                return [
                    TransportScheduleCandidate(
                        mode=TravelMode.flight,
                        carrier="Cathay Pacific",
                        service_number="CX973",
                        origin_name="厦门高崎国际机场",
                        destination_name="香港国际机场",
                        scheduled_departure=datetime(2026, 6, 15, 4, 20, tzinfo=timezone.utc),
                        scheduled_arrival=datetime(2026, 6, 15, 5, 55, tzinfo=timezone.utc),
                        source_urls=("https://example.com/cx973",),
                        confidence="medium",
                        notes="中转第一段。",
                    ),
                    TransportScheduleCandidate(
                        mode=TravelMode.flight,
                        carrier="Qatar Airways",
                        service_number="QR817",
                        origin_name="香港国际机场",
                        destination_name="多哈哈马德国际机场",
                        scheduled_departure=datetime(2026, 6, 15, 11, 10, tzinfo=timezone.utc),
                        scheduled_arrival=datetime(2026, 6, 15, 20, 5, tzinfo=timezone.utc),
                        source_urls=("https://example.com/qr817",),
                        confidence="medium",
                        notes="中转第二段。",
                    ),
                ]

            def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
                itinerary = self.best_itinerary(search)
                return itinerary[0] if itinerary else None

        pet = self.sample_pet(created_at=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc))
        provider = MockTransportRealityProvider(schedule_provider=FakeConnectingScheduleProvider())
        origin = self.place("xiamen", "厦门街角", "厦门", 24.4798, 118.0894, "street")
        airport = self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport")
        cafe = self.place("cafe", "赛场附近咖啡店", "多哈", 25.265, 51.505, "cafe")
        stadium = self.place("stadium", "世界杯赛场", "多哈", 25.263, 51.485, "stadium")

        legs = provider.worldcup_legs(
            pet=pet,
            origin=origin,
            airport=airport,
            cafe=cafe,
            stadium=stadium,
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
        )

        flight_legs = [item for item in legs if item.mode == TravelMode.flight]
        self.assertEqual([item.service_number for item in flight_legs], ["CX973", "QR817"])
        self.assertIn("中转第 1/2 段", flight_legs[0].timeline_note or "")
        self.assertIn("中转第 2/2 段", flight_legs[1].timeline_note or "")
        drive_leg = next(item for item in legs if item.mode == TravelMode.drive)
        self.assertGreater(drive_leg.scheduled_departure, flight_legs[-1].scheduled_arrival)

    def test_runtime_trace_owner_intent_and_memory_v2(self) -> None:
        pet_id = self.create_pet()

        status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status.status_code, 200)
        message = self.client.post(
            f"/api/v1/pets/{pet_id}/messages",
            json={"message": "你现在马上去海边给我拍照", "intent_hint": "photo"},
        )
        self.assertEqual(message.status_code, 200)
        message_payload = message.json()
        self.assertEqual(message_payload["owner_intent"]["intent"], "photo_request")
        self.assertFalse(message_payload["owner_intent"]["should_affect_route"])

        memory = self.client.post(
            f"/api/v1/pets/{pet_id}/memories",
            json={
                "kind": "owner_preference",
                "title": "喜欢安静海边",
                "content": "主人希望小星靠近安静、有海风的地方，但路线不能被强制。",
                "salience": 0.7,
                "memory_type": "preference",
                "importance": 0.92,
                "emotional_valence": 0.4,
                "confidence": 0.88,
                "structured_payload": {"place_affinity": "seaside", "soft_influence_only": True},
            },
        )
        self.assertEqual(memory.status_code, 200)
        self.assertEqual(memory.json()["memory_type"], "preference")
        self.assertEqual(memory.json()["importance"], 0.92)

        search = self.client.post(
            f"/api/v1/pets/{pet_id}/memories/search",
            json={"query": "安静海边 想你", "limit": 5},
        )
        self.assertEqual(search.status_code, 200)
        self.assertGreaterEqual(len(search.json()["items"]), 1)
        self.assertIn(search.json()["items"][0]["memory_type"], {"relationship", "preference", "recent_episodic", "episodic"})

        consolidation = self.client.post(f"/api/v1/pets/{pet_id}/memories/consolidate")
        self.assertEqual(consolidation.status_code, 200)
        self.assertIn("relationship_summary", consolidation.json())
        self.assertGreaterEqual(consolidation.json()["source_memory_count"], 1)

        traces = self.client.get(f"/api/v1/pets/{pet_id}/traces")
        self.assertEqual(traces.status_code, 200)
        trace_payload = traces.json()
        operations = {item["operation"] for item in trace_payload}
        self.assertIn("status", operations)
        self.assertIn("owner_message", operations)
        owner_trace = next(item for item in trace_payload if item["operation"] == "owner_message")
        self.assertIn("owner_intent", {step["name"] for step in owner_trace["steps"]})

        trace_detail = self.client.get(f"/api/v1/pets/{pet_id}/traces/{owner_trace['id']}")
        self.assertEqual(trace_detail.status_code, 200)
        self.assertEqual(trace_detail.json()["id"], owner_trace["id"])

    def test_guide_and_photo_pipeline_v2_fields(self) -> None:
        pet_id = self.create_pet()

        guide = self.client.get(f"/api/v1/pets/{pet_id}/pet_guide")
        self.assertEqual(guide.status_code, 200)
        guide_payload = guide.json()
        self.assertIn("guide_theme", guide_payload)
        self.assertGreaterEqual(len(guide_payload["selected_places"]), 1)
        first_place = guide_payload["selected_places"][0]
        self.assertIn("pet_dna_fit", first_place["score"])
        self.assertIn("city_signature", first_place["score"])
        self.assertIn("chain_store_penalty", first_place["score"])
        provided_place_ids = {stop["place_id"] for stop in guide_payload["guide_stops"]}
        self.assertIn(first_place["place_id"], provided_place_ids)

        mission = self.client.get(f"/api/v1/pets/{pet_id}/photo_mission")
        self.assertEqual(mission.status_code, 200)
        mission_payload = mission.json()
        self.assertEqual(mission_payload["camera_perspective"], "first_person_selfie")
        self.assertIn("pet_identity", mission_payload["prompt_blocks"])
        self.assertIn("place_environment", mission_payload["prompt_blocks"])
        self.assertIsNotNone(mission_payload["quality_report"])
        self.assertIn("pet_identity_score", mission_payload["quality_report"])

    def test_pet_guide_quality_gate_filters_low_value_core_stops(self) -> None:
        now = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)
        pet = PetRecord(
            pet_id="PJ-QUALITY",
            name="小福",
            pet_type=PetType.dog,
            dna=PetDNA(
                owner_title="妈妈",
                personality="温柔、喜欢慢慢走",
                favorite_places=["海边", "老街"],
                hobby=["晒太阳"],
                catchphrase="慢慢走",
                voice_style="像寄一封小信",
            ),
            created_at=now,
            photo_path=None,
        )

        def place(place_id: str, name: str, category: str, lat: float, lng: float, hint: str, score: float = 90) -> PlaceSignal:
            return PlaceSignal(
                id=place_id,
                name=name,
                category=category,
                city="厦门",
                lat=lat,
                lng=lng,
                activity_hint=hint,
                detail_hint=hint,
                source="test",
                guide_score=score,
                guide_reason=hint,
            )

        places = [
            place("kfc", "肯德基（滨北店）", "food", 24.48, 118.09, "普通连锁快餐，只适合作为临时补给", 92),
            place("convenience", "全家便利店", "shop", 24.481, 118.091, "临时补给点，不应该成为主线", 91),
            place("huweishan", "狐尾山 / 山海健康步道", "park", 24.4874, 118.0847, "高处、绿意和城市边界都很清楚", 96),
            place("bashi", "八市 / 开禾路老街", "food", 24.4579, 118.0739, "老城市场和本地小吃让路线有厦门记忆点", 98),
            place("shapowei", "沙坡尾 / 大学路", "place", 24.4386, 118.093, "老港、巷子、小店和海风都有画面感", 97),
            place("baicheng", "环岛路 / 白城沙滩", "beach", 24.4319, 118.1036, "海边和环岛路是厦门很强的城市标签", 97),
            place("bailuzhou", "白鹭洲 / 筼筜湖", "park", 24.4772, 118.0961, "傍晚湖面和城市灯适合写明信片", 95),
        ]
        stops = [
            ItineraryStop(id=f"stop-{item.id}", name=item.name, category=item.category, city=item.city, lat=item.lat, lng=item.lng, title=item.name, detail=item.activity_hint, planned_time=time, dwell_minutes=dwell, source=item.source)
            for item, time, dwell in [
                (places[0], "07:40", 110),
                (places[1], "08:20", 60),
                (places[2], "09:00", 45),
                (places[3], "10:30", 140),
                (places[4], "12:20", 100),
                (places[5], "15:00", 85),
                (places[6], "17:30", 50),
            ]
        ]
        plan = JourneyPlan(
            pet_id=pet.pet_id,
            city="厦门",
            generated_at=now,
            provider="test",
            horizon_hours=24,
            summary="小福今天想在厦门慢慢走。",
            current_activity="醒来",
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="近处慢慢走，远一点搭车。",
                rejected_modes=[],
                autonomy_note="TA 自己选择。",
            ),
            route_segments=[],
            stops=stops,
            places=places,
            next_postcard_hint="傍晚从白鹭洲寄回一封小信。",
        )

        guide = PetGuideEngine(Settings()).build_pet_guide(pet, plan, now)
        names = [stop.name for stop in guide.guide_stops]
        self.assertNotIn("肯德基（滨北店）", names)
        self.assertNotIn("全家便利店", names)
        self.assertLessEqual(len(guide.guide_stops), 6)
        self.assertTrue(all(stop.is_user_visible for stop in guide.guide_stops))
        self.assertTrue(guide.is_replicable_route)
        self.assertGreaterEqual(guide.quality_score, 0.68)
        bashi_stop = next(stop for stop in guide.guide_stops if "八市" in stop.name)
        self.assertEqual(bashi_stop.role, "food_anchor")
        self.assertLessEqual(bashi_stop.dwell_minutes, 75)
        self.assertTrue(any("规则引擎" in role for role in guide.orchestration_roles))
        self.assertTrue(any("城市代表性" in rule for rule in guide.quality_gate_rules))
        self.assertIn(guide.voice_provider, {"local_pet_voice_template", "doubao_pet_voice"})
        self.assertIn("amap", guide.fact_provider_priority)

    def test_doubao_voice_writer_cannot_change_pet_guide_route(self) -> None:
        class FakeDoubaoVoiceGuideEngine(PetGuideEngine):
            def _post_doubao_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
                self.last_payload = payload
                return {
                    "output_text": json.dumps(
                        {
                            "title": "小福在厦门慢慢走",
                            "translation": "汪汪，妈妈，我今天先在山上海风里醒一醒，再去老城闻热闹的味道。下午我会去海边，把光写进通讯器。",
                            "route_theme": "山上的风、老城的味道和海边的光",
                            "mood": "安静又认真",
                            "pet_first_person_guide": "我会先替你走一遍，把你以后也可以来的地方记下来。",
                            "stop_voices": [
                                {
                                    "place_id": "huweishan",
                                    "pet_reason": "我先来这里醒一醒，听风从高处吹过来。",
                                    "owner_tip": "如果你也来，可以把这里当作慢慢开始的一站。",
                                },
                                {
                                    "place_id": "bashi",
                                    "pet_reason": "我会在老街里看菜单，选一点厦门的本地味道。",
                                    "owner_tip": "这里适合感受老城和早午间的烟火气。",
                                },
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        now = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)
        pet = PetRecord(
            pet_id="PJ-VOICE",
            name="小福",
            pet_type=PetType.dog,
            dna=PetDNA(
                owner_title="妈妈",
                personality="温柔、喜欢慢慢走",
                favorite_places=["海边", "老街"],
                hobby=["晒太阳"],
                catchphrase="慢慢走",
                voice_style="像寄一封小信",
            ),
            created_at=now,
            photo_path=None,
        )
        places = [
            PlaceSignal(
                id="huweishan",
                name="狐尾山 / 山海健康步道",
                category="park",
                city="厦门",
                lat=24.4874,
                lng=118.0847,
                activity_hint="高处、绿意和城市边界都很清楚",
                detail_hint="高处、绿意和城市边界都很清楚",
                source="test",
                guide_score=96,
                guide_reason="高处、绿意和城市边界都很清楚",
            ),
            PlaceSignal(
                id="bashi",
                name="八市 / 开禾路老街",
                category="food",
                city="厦门",
                lat=24.4579,
                lng=118.0739,
                activity_hint="老城市场和本地小吃让路线有厦门记忆点",
                detail_hint="老城市场和本地小吃让路线有厦门记忆点",
                source="test",
                guide_score=98,
                guide_reason="老城市场和本地小吃让路线有厦门记忆点",
            ),
            PlaceSignal(
                id="baicheng",
                name="环岛路 / 白城沙滩",
                category="beach",
                city="厦门",
                lat=24.4319,
                lng=118.1036,
                activity_hint="海边和环岛路是厦门很强的城市标签",
                detail_hint="海边和环岛路是厦门很强的城市标签",
                source="test",
                guide_score=97,
                guide_reason="海边和环岛路是厦门很强的城市标签",
            ),
        ]
        stops = [
            ItineraryStop(
                id=f"stop-{item.id}",
                name=item.name,
                category=item.category,
                city=item.city,
                lat=item.lat,
                lng=item.lng,
                title=item.name,
                detail=item.activity_hint,
                planned_time=time,
                dwell_minutes=dwell,
                source=item.source,
            )
            for item, time, dwell in [
                (places[0], "08:30", 45),
                (places[1], "10:00", 60),
                (places[2], "15:00", 70),
            ]
        ]
        plan = JourneyPlan(
            pet_id=pet.pet_id,
            city="厦门",
            generated_at=now,
            provider="test",
            horizon_hours=24,
            summary="小福今天想在厦门慢慢走。",
            current_activity="醒来",
            transport_decision=TransportDecision(
                selected_mode=TravelMode.walk,
                reason="近处慢慢走，远一点搭车。",
                rejected_modes=[],
                autonomy_note="TA 自己选择。",
            ),
            route_segments=[],
            stops=stops,
            places=places,
            next_postcard_hint="傍晚从海边寄回一封小信。",
        )

        guide = FakeDoubaoVoiceGuideEngine(Settings(doubao_api_key="fake-key")).build_pet_guide(pet, plan, now)

        self.assertEqual([stop.place_id for stop in guide.guide_stops], ["huweishan", "bashi", "baicheng"])
        self.assertIn("doubao-pet-voice", guide.provider)
        self.assertEqual(guide.voice_provider, "doubao_pet_voice")
        self.assertIn("妈妈", guide.translation)
        self.assertNotIn("宝宝", guide.translation)
        self.assertFalse(any("内部字段" in stop.pet_reason for stop in guide.guide_stops))

    def test_eval_fixtures_load(self) -> None:
        eval_dir = Path(__file__).parent / "evals"
        expected = {
            "agent_brain_cases.json",
            "photo_mission_cases.json",
            "guide_engine_cases.json",
            "route_integrity_cases.json",
            "owner_intent_cases.json",
            "memory_retrieval_cases.json",
        }
        self.assertEqual({path.name for path in eval_dir.glob("*.json")}, expected)
        for path in eval_dir.glob("*.json"):
            cases = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(cases, list)
            self.assertGreaterEqual(len(cases), 1)
            self.assertIn("assertions", cases[0])

    def create_pet(self, client: TestClient | None = None, pet_type: str = "dog") -> str:
        client = client or self.client
        dna = {
            "owner_title": "妈妈",
            "personality": "黏人、温柔、喜欢慢慢走",
            "favorite_places": ["海边", "阳台"],
            "hobby": ["晒太阳"],
            "catchphrase": "慢慢走，我在",
            "emoji_pref": "soft",
            "voice_style": "像寄一封小信",
        }
        response = client.post(
            "/api/v1/create_pet",
            data={
                "pet_name": "小星",
                "pet_type": pet_type,
                "dna": json.dumps(dna, ensure_ascii=False),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        return payload["pet_id"]

    def sample_pet(self, created_at: datetime | None = None) -> PetRecord:
        return PetRecord(
            pet_id="PJ-TEST",
            name="小星",
            pet_type=PetType.dog,
            dna=PetDNA(
                owner_title="妈妈",
                personality="温柔、好奇",
                favorite_places=["海边"],
                hobby=["散步"],
                catchphrase="我在路上",
            ),
            created_at=created_at or datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
            photo_path=None,
        )

    def place(
        self,
        id: str,
        name: str,
        city: str,
        lat: float,
        lng: float,
        category: str,
    ) -> PlaceSignal:
        return PlaceSignal(
            id=id,
            name=name,
            category=category,
            city=city,
            lat=lat,
            lng=lng,
            activity_hint="安静地观察周围",
            detail_hint="测试地点",
            source="test",
        )


if __name__ == "__main__":
    unittest.main()
