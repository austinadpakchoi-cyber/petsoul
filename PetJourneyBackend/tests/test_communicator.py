from base import *


class CommunicatorApiTests(PetJourneyApiTestBase):

    def test_scheduler_tick_registers_push_and_records_notification(self) -> None:
        pet_id = self.create_pet()
        # 提醒只属于「有主人」的宠物：先认领，再验证调度器会推进并推送。
        from pathlib import Path
        from app.storage import JourneyStorage

        storage = JourneyStorage(Path(self.tempdir.name) / "petjourney.sqlite3")
        user, _ = storage.upsert_user_by_apple_sub("sub-notify-test", None, "测试主人")
        storage.claim_pet(pet_id, user.user_id)
        orphan_pet_id = self.create_pet()  # 无主宠物不应被推进

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
        # 只推进认领过的宠物（孤儿宠物不进调度器）
        self.assertEqual(tick_payload["pets_seen"], 1)
        self.assertGreaterEqual(tick_payload["agent_turns"], 1)
        self.assertGreaterEqual(tick_payload["notifications_sent"], 1)
        self.assertEqual(tick_payload["errors"], [])

        deliveries = self.client.get(f"/api/v1/pets/{pet_id}/notifications")
        self.assertEqual(deliveries.status_code, 200)
        self.assertGreaterEqual(len(deliveries.json()), 1)
        self.assertEqual(deliveries.json()[0]["status"], "mock_sent")

        orphan_deliveries = self.client.get(f"/api/v1/pets/{orphan_pet_id}/notifications")
        self.assertEqual(orphan_deliveries.status_code, 200)
        self.assertEqual(len(orphan_deliveries.json()), 0)

    def test_communicator_client_message_id_dedup_replays_first_response(self) -> None:
        pet_id = self.create_pet()

        first = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "你今天在哪呀", "client_message_id": "cmid-1"},
        )
        self.assertEqual(first.status_code, 200)
        first_owner_id = first.json()["owner_message"]["id"]

        replay = self.client.post(
            f"/api/v1/pets/{pet_id}/communicator/messages",
            json={"text": "你今天在哪呀", "client_message_id": "cmid-1"},
        )
        self.assertEqual(replay.status_code, 200)
        # 同一幂等键：回放首次的响应，不生成新消息
        self.assertEqual(replay.json()["owner_message"]["id"], first_owner_id)

        listed = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages")
        owner_messages = [
            item for item in listed.json() if item["sender"] == "owner" and item["text"] == "你今天在哪呀"
        ]
        self.assertEqual(len(owner_messages), 1, "重发不得产生重复的主人消息")

    def test_legacy_owner_message_dedup_does_not_duplicate(self) -> None:
        pet_id = self.create_pet()

        first = self.client.post(
            f"/api/v1/pets/{pet_id}/messages",
            json={"message": "想你了", "client_message_id": "legacy-cmid-1"},
        )
        self.assertEqual(first.status_code, 200)

        replay = self.client.post(
            f"/api/v1/pets/{pet_id}/messages",
            json={"message": "想你了", "client_message_id": "legacy-cmid-1"},
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["success"])

        listed = self.client.get(f"/api/v1/pets/{pet_id}/communicator/messages")
        owner_messages = [
            item for item in listed.json() if item["sender"] == "owner" and item["text"] == "想你了"
        ]
        self.assertEqual(len(owner_messages), 1, "弱网重试不得重复落库")

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
        attachment_types = {
            attachment["type"]
            for message in visual_payload["messages"]
            for attachment in message["attachments"]
        }
        self.assertTrue(
            attachment_types
            & {"photo_placeholder", "photo_status_card", "pending_photo_request", "location_card"}
        )

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
        self.assertEqual(repeated_payload["messages"][0]["attachments"][0]["type"], "photo_status_card")

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

