from base import *


class MemoryApiTests(PetJourneyApiTestBase):

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

