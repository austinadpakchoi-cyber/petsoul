from base import *


class GuideAndPlanApiTests(PetJourneyApiTestBase):

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

