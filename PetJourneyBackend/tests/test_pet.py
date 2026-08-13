from base import *


class PetLifecycleApiTests(PetJourneyApiTestBase):

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
        self.assertEqual(payload["agent_model"], "deepseek-chat")
        self.assertEqual(payload["agent_deep_model"], "deepseek-chat")
        self.assertEqual(payload["translation_model"], "deepseek-chat")
        self.assertEqual(payload["turn_interval_seconds"], 1800.0)
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
        self.assertEqual(mission_brain_payload["photo_mission_model"], "deepseek-chat")
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
        self.assertEqual(mission_payload["photo_mission_model"], "deepseek-chat")

