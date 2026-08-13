from base import *


class TravelQuestApiTests(PetJourneyApiTestBase):

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
            pet_name="小福",
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
            pet_name="小福",
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

