import XCTest
@testable import PetJourneyIOS

/// 契约解码护栏：用后端 schema 的真实 JSON 形状反序列化 iOS 模型，
/// 断言关键字段不被静默丢弃（Codable 对多余字段静默忽略，漂移只能靠这里变红）。
final class ContractDecodingTests: XCTestCase {
    private var decoder: JSONDecoder!

    override func setUp() {
        super.setUp()
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            try RemoteDateDecoding.decodeFlexibleISO8601Date(from: decoder)
        }
    }

    func testLifeTickResultDecodesObservationAndMemories() throws {
        let json = #"""
        {
            "pet_id": "pet-1",
            "generated_at": "2026-08-14T08:00:00Z",
            "provider": "petsoul-life-simulation-engine",
            "observation": {
                "pet_id": "pet-1",
                "city": "厦门",
                "weather": "晴",
                "local_time": "2026-08-14T08:00:00Z",
                "current_activity": {
                    "id": "act-1", "kind": "rest", "status": "resting",
                    "title": "休息", "detail": "安静待着", "city": "厦门",
                    "place_name": "海边", "lat": 24.4, "lng": 118.1,
                    "mode": "stay", "progress": 0.0,
                    "icon_hint": "moon", "can_generate_photo": false,
                    "can_send_postcard": false, "source": "world"
                },
                "nearby_places": [],
                "constraints": ["不瞬移"]
            },
            "retrieved_memories": [
                {
                    "id": "m1", "pet_id": "pet-1", "kind": "episodic",
                    "title": "海边的风", "content": "记得海风", "salience": 0.8,
                    "source": "memory", "created_at": "2026-08-14T07:00:00Z",
                    "last_seen_at": "2026-08-14T07:05:00Z",
                    "metadata": {}, "memory_type": "episodic",
                    "importance": 0.7, "emotional_valence": 0.3, "confidence": 1.0
                }
            ],
            "need_state": {"energy": 80, "hunger": 20, "social": 60, "curiosity": 70, "comfort": 90, "playfulness": 50},
            "intent": {"id": "i1", "kind": "observe_world", "title": "观察", "reason": "听声音", "confidence": 0.68},
            "action": {"id": "a1", "action_type": "observe_world", "title": "观察", "detail": "看", "mode": "stay", "lat": 24.4, "lng": 118.1, "duration_minutes": 22, "animation_hint": "observe"},
            "decision": {"allowed": true, "reason": "ok"},
            "owner_visible_summary": "TA 正在观察",
            "visible_thought": {"current_inner_voice": "嗯", "next_intention": "再看看", "reason": "好奇", "time_window": "几分钟", "confidence": 0.68},
            "animal_text_hint": "呜",
            "animation_hint": "observe",
            "should_notify_owner": false,
            "next_tick_after_seconds": 600
        }
        """#

        let result = try decoder.decode(LifeTickResult.self, from: Data(json.utf8))
        XCTAssertNotNil(result.observation, "observation 不应被丢弃")
        XCTAssertEqual(result.observation?.city, "厦门")
        XCTAssertEqual(result.observation?.constraints, ["不瞬移"])
        XCTAssertEqual(result.retrievedMemories?.count, 1)
        XCTAssertEqual(result.retrievedMemories?.first?.title, "海边的风")
    }

    func testPhotoMissionDecodesQualityReportFields() throws {
        let json = #"""
        {
            "id": "photo-1", "pet_id": "pet-1", "generated_at": "2026-08-14T08:00:00Z",
            "provider": "openai-compatible-photo-mission-brain", "city": "厦门",
            "place": {"id": "p1", "name": "海边", "category": "beach", "city": "厦门", "lat": 24.4, "lng": 118.1, "activity_hint": "看海", "detail_hint": "安静", "source": "map"},
            "interaction": {"id": "i1", "pet_id": "pet-1", "place": {"id": "p1", "name": "海边", "category": "beach", "city": "厦门", "lat": 24.4, "lng": 118.1, "activity_hint": "看海", "detail_hint": "安静", "source": "map"}, "interaction_type": "seaside_memory_walk", "title": "海边", "detail": "走", "pet_action": "看海", "emotional_tone": "温柔", "dwell_minutes": 30, "can_generate_photo": true, "source": "brain"},
            "camera_perspective": "first_person_selfie", "scene_anchor": "海边",
            "landmark_hints": ["海"], "local_detail_hints": ["浪"], "crowd_hints": [],
            "weather": "晴", "time_of_day": "morning",
            "image_prompt": "一张海边自拍", "postcard_text": "我把这一刻寄给你",
            "safety_notes": [],
            "prompt_blocks": {"pet": "identity", "place": "environment"},
            "quality_report": {
                "pet_identity_score": 0.9, "place_recognition_score": 0.8,
                "emotional_tone_score": 0.85, "policy_safety": true,
                "logo_brand_risk": 0.05, "uncanny_risk": 0.1,
                "retry_reason": null, "failure_category": null,
                "evaluator": "heuristic-photo-quality-evaluator"
            },
            "retry_count": 1, "failure_category": null
        }
        """#

        let mission = try decoder.decode(PhotoMission.self, from: Data(json.utf8))
        XCTAssertEqual(mission.promptBlocks?["pet"], "identity")
        XCTAssertEqual(mission.qualityReport?.petIdentityScore, 0.9)
        XCTAssertTrue(mission.qualityReport?.policySafety ?? false)
        XCTAssertEqual(mission.retryCount, 1)
    }

    func testOwnerMessageResponseDecodesOwnerIntent() throws {
        let json = #"""
        {
            "success": true, "decision": "remembered",
            "message": "我听见了。",
            "thought": {
                "id": "t1", "text": "我听见了。", "timestamp": "2026-08-14T08:00:00Z",
                "tone": "warm", "animal_text": "汪", "translation_available": true,
                "translation": "我听见了。", "language_style": "dog_vocalization_with_hidden_translation",
                "model": "deepseek-chat"
            },
            "updated_status": null,
            "owner_intent": {
                "intent": "comfort", "strength": 0.8, "entities": {"mood": "想念"},
                "should_affect_route": false, "should_write_memory": true,
                "response_policy": "gentle_acknowledgement", "decision": "remembered",
                "safety_notes": []
            }
        }
        """#

        let response = try decoder.decode(OwnerMessageResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.ownerIntent?.intent, "comfort")
        XCTAssertEqual(response.ownerIntent?.strength, 0.8)
    }

    func testSouvenirItemDecodesMemorySourceFields() throws {
        let json = #"""
        {
            "id": "sv-1", "pet_id": "pet-1", "quest_id": "q1",
            "item_type": "photo_print", "title": "海边纪念", "subtitle": "一点海风",
            "city": "厦门", "place_name": "海边", "story": "那天", "pet_voice": "我在这里",
            "image_prompt": "纪念品", "image_url": null, "rarity": "common",
            "obtained_at": "2026-08-14T08:00:00Z", "source": "souvenir-catalog",
            "memory_type": "souvenir", "source_photo_mission_id": "photo-1",
            "bag_influence_tags": ["海边", "明信片"]
        }
        """#

        let item = try decoder.decode(SouvenirItem.self, from: Data(json.utf8))
        XCTAssertEqual(item.memoryType, "souvenir")
        XCTAssertEqual(item.sourcePhotoMissionID, "photo-1")
        XCTAssertEqual(item.bagInfluenceTags, ["海边", "明信片"])
    }

    func testPetAuthoredGuideDecodesSelectedPlaces() throws {
        let json = #"""
        {
            "pet_id": "pet-1", "city": "厦门", "generated_at": "2026-08-14T08:00:00Z",
            "provider": "pet-guide-brain", "model": "deepseek-chat",
            "title": "慢慢走", "animal_text": "汪", "translation": "我想慢慢走",
            "language_style": "dog_vocalization_with_hidden_translation",
            "route_theme": "海边", "mood": "好奇",
            "guide_stops": [],
            "scheduled_transport": [],
            "source_places_count": 0, "autonomy_note": "我自己决定",
            "guide_theme": "safe local walk",
            "selected_places": [
                {
                    "place_id": "p1", "name": "海边", "category": "beach", "city": "厦门",
                    "score": {"total": 0.8, "photo_potential": 0.9},
                    "why_pet_likes_it": "喜欢海风", "why_owner_may_care": "适合散步",
                    "photo_potential": "光很好", "crowd_risk": "人不多"
                }
            ],
            "why_pet_likes_it": ["喜欢海风"], "why_owner_may_care": ["适合散步"],
            "photo_potential": ["光很好"], "crowd_risk": ["人不多"],
            "pet_first_person_guide": "我今天会慢慢走"
        }
        """#

        let guide = try decoder.decode(PetAuthoredGuide.self, from: Data(json.utf8))
        XCTAssertEqual(guide.guideTheme, "safe local walk")
        XCTAssertEqual(guide.selectedPlaces?.count, 1)
        XCTAssertEqual(guide.selectedPlaces?.first?.placeID, "p1")
        XCTAssertEqual(guide.petFirstPersonGuide, "我今天会慢慢走")
    }
}
