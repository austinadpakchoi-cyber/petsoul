"""网页 R0 领域边界的关键不变量：MemoryPolicy、寻味上下文、交通时间线、影音锚点。

这些只证明边界/纯函数语义；接待保存、寻味算法、真实班次与同步播放均未实现、未验收。
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from app.companion_media import lease_allows, participation_counts, position_at, video_allowed
from app.food_discovery import (
    FoodContextError,
    public_preference_view,
    real_quality_evidence,
    recommendation_freshness,
    validate_request_context,
)
from app.reception import build_home_welcome, project_memory
from app.schemas.web.companion_media import ControlLease, MediaAnchor, MediaKind, MediaSessionState, ParticipationMode
from app.schemas.web.common import LatLng
from app.schemas.web.food import (
    DietaryRestriction,
    DietaryRestrictionKind,
    EvidenceCitation,
    EvidenceSourceKind,
    FoodMode,
    FoodPreference,
    FoodRecommendationRequest,
    OwnerDiningContext,
    PreferenceSource,
    PreferenceSubject,
    RecommendationFreshness,
    TasteVector,
)
from app.schemas.web.reception import (
    CandidateKind,
    CandidateSubject,
    CareNote,
    CareNoteSlot,
    MemoryGrant,
    MemoryPurpose,
    SaveTarget,
)
from app.schemas.web.transport import LegTimes, PetArrivalContext, TravellerRole
from app.transport_world import (
    derive_service_number,
    leg_progress,
    position_along,
    schedule_after_leg,
    world_service_key,
)

NOW = datetime(2026, 9, 22, 7, 35, tzinfo=timezone.utc)


def note(note_id: str, kind: CandidateKind, target: SaveTarget, purposes, *, slot=None, value=None, version=1, **kw) -> CareNote:
    return CareNote(
        note_id=note_id,
        pet_id="pet-1",
        kind=kind,
        subject=CandidateSubject.relationship,
        text=f"text-{note_id}",
        target=target,
        purposes=list(purposes),
        slot=slot,
        slot_value=value,
        version=version,
        confirmed_at=NOW,
        **kw,
    )


def grant(note_id: str, purpose: MemoryPurpose, version: int = 1, revoked=False) -> MemoryGrant:
    return MemoryGrant(
        grant_id=f"g-{note_id}-{purpose.value}",
        note_id=note_id,
        note_version=version,
        purpose=purpose,
        granted_at=NOW,
        revoked_at=NOW if revoked else None,
    )


class MemoryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        home = MemoryPurpose.home_interaction
        self.notes = [
            note("title", CandidateKind.habit, SaveTarget.give_to_pet, [home], slot=CareNoteSlot.owner_title, value="姐姐"),
            note("private", CandidateKind.owner_private, SaveTarget.give_to_pet, [home]),
            note("keep", CandidateKind.habit, SaveTarget.keep_here, [home]),
            note("guess", CandidateKind.inference, SaveTarget.give_to_pet, [home]),
            note("revoked", CandidateKind.habit, SaveTarget.give_to_pet, [home], revoked_at=NOW),
            note("travel-only", CandidateKind.habit, SaveTarget.give_to_pet, [MemoryPurpose.travel_preference]),
            note("old", CandidateKind.habit, SaveTarget.give_to_pet, [home], slot=CareNoteSlot.favorite_object, value="旧毯子"),
            note("new", CandidateKind.habit, SaveTarget.give_to_pet, [home], slot=CareNoteSlot.favorite_object, value="蓝色小毯子", supersedes_note_id="old"),
            note("stale-grant", CandidateKind.habit, SaveTarget.give_to_pet, [home], version=2),
        ]
        self.grants = [grant(n.note_id, p) for n in self.notes for p in n.purposes if n.note_id != "stale-grant"]
        self.grants.append(grant("stale-grant", home, version=1))

    def test_only_confirmed_granted_current_notes_are_projected(self) -> None:
        projection = project_memory(
            pet_id="pet-1", purpose=MemoryPurpose.home_interaction, notes=self.notes, grants=self.grants, now=NOW
        )
        self.assertEqual({item.note_id for item in projection.items}, {"title", "new"})

    def test_revoked_grant_stops_use(self) -> None:
        grants = [grant("title", MemoryPurpose.home_interaction, revoked=True)]
        projection = project_memory(
            pet_id="pet-1", purpose=MemoryPurpose.home_interaction, notes=self.notes[:1], grants=grants, now=NOW
        )
        self.assertEqual(projection.items, [])

    def test_other_pet_notes_never_leak(self) -> None:
        projection = project_memory(
            pet_id="pet-2", purpose=MemoryPurpose.home_interaction, notes=self.notes, grants=self.grants, now=NOW
        )
        self.assertEqual(projection.items, [])

    def test_home_welcome_uses_confirmed_title(self) -> None:
        projection = project_memory(
            pet_id="pet-1", purpose=MemoryPurpose.home_interaction, notes=self.notes, grants=self.grants, now=NOW
        )
        welcome = build_home_welcome(projection, projection_version=3)
        self.assertTrue(welcome.greeting.startswith("姐姐"))
        self.assertNotIn("text-private", welcome.model_dump_json())
        with self.assertRaises(ValueError):
            travel = project_memory(
                pet_id="pet-1", purpose=MemoryPurpose.travel_preference, notes=self.notes, grants=self.grants, now=NOW
            )
            build_home_welcome(travel, projection_version=1)


class FoodContextTests(unittest.TestCase):
    def pet_ctx(self, version: int = 1) -> PetArrivalContext:
        return PetArrivalContext(
            journey_id="j1",
            itinerary_version=version,
            leg_id="leg-2",
            city="香港",
            destination_timezone="Asia/Hong_Kong",
            feasible_arrival_utc=NOW,
            stay_window_start_utc=NOW + timedelta(minutes=10),
            stay_window_end_utc=NOW + timedelta(hours=2),
        )

    def test_modes_do_not_borrow_each_others_time(self) -> None:
        owner_ctx = OwnerDiningContext(plan_date=date(2026, 10, 1), meal_time_local="12:30", timezone="Asia/Hong_Kong", city="香港")
        validate_request_context(FoodRecommendationRequest(mode=FoodMode.pet_virtual_explore, pet_id="p", pet_context=self.pet_ctx()))
        validate_request_context(FoodRecommendationRequest(mode=FoodMode.owner_real_dining, pet_id="p", owner_context=owner_ctx))
        with self.assertRaises(FoodContextError):
            validate_request_context(FoodRecommendationRequest(mode=FoodMode.owner_real_dining, pet_id="p", pet_context=self.pet_ctx()))
        with self.assertRaises(FoodContextError):
            validate_request_context(FoodRecommendationRequest(mode=FoodMode.pet_virtual_explore, pet_id="p", owner_context=owner_ctx))

    def test_fixture_and_virtual_never_count_as_real_quality(self) -> None:
        cites = [
            EvidenceCitation(evidence_id="e1", source_kind=EvidenceSourceKind.fixture, source_label="演示", aspect="面", observation="x"),
            EvidenceCitation(evidence_id="e2", source_kind=EvidenceSourceKind.map_poi, source_label="地图", aspect="评分", observation="y"),
            EvidenceCitation(evidence_id="e3", source_kind=EvidenceSourceKind.owner_feedback, source_label="主人", aspect="咸度", observation="z"),
        ]
        self.assertEqual([c.evidence_id for c in real_quality_evidence(cites)], ["e3"])

    def test_private_restrictions_not_in_public_view(self) -> None:
        pref = FoodPreference(
            preference_id="fp1",
            subject=PreferenceSubject.owner,
            pet_id="p",
            version=1,
            label="清淡",
            taste=TasteVector(salty=-2),
            restrictions=[DietaryRestriction(kind=DietaryRestrictionKind.allergy, label="花生")],
            source=PreferenceSource.fixture,
            updated_at=NOW,
        )
        self.assertNotIn("花生", str(public_preference_view(pref)))

    def test_itinerary_change_marks_recommendation_for_recheck(self) -> None:
        from app.schemas.web.food import (
            Branch,
            EligibilityStatus,
            FoodDataStatus,
            FoodRecommendation,
            JudgementScores,
            RecommendationGroup,
            RecommendationProvenance,
        )
        from app.schemas.web.common import DataOrigin

        rec = FoodRecommendation(
            recommendation_id="r1",
            mode=FoodMode.pet_virtual_explore,
            branch=Branch(branch_id="fixture:b1", name="示例面馆"),
            scores=JudgementScores(),
            eligibility=EligibilityStatus.eligible,
            group=RecommendationGroup.primary,
            provenance=RecommendationProvenance(
                generated_at=NOW, fact_version="f1", preference_version=1, rule_version="r0",
                data_status=FoodDataStatus.fixture, coverage_note="演示",
            ),
            freshness=RecommendationFreshness.fresh,
            itinerary_version=1,
            data_origin=DataOrigin.fixture,
        )
        self.assertEqual(recommendation_freshness(rec, self.pet_ctx(1)), RecommendationFreshness.fresh)
        self.assertEqual(recommendation_freshness(rec, self.pet_ctx(2)), RecommendationFreshness.needs_recheck)


class TransportTimelineTests(unittest.TestCase):
    def times(self) -> LegTimes:
        return LegTimes(
            origin_timezone="Asia/Shanghai",
            destination_timezone="Asia/Shanghai",
            planned_departure_utc=datetime(2026, 9, 22, 6, 20, tzinfo=timezone.utc),
            planned_arrival_utc=datetime(2026, 9, 22, 8, 55, tzinfo=timezone.utc),
        )

    def test_progress_uses_server_time_not_page_open(self) -> None:
        # 14:20 → 16:55（UTC+8）共 2h35m；15:35 打开时剩 1h20m，而不是从打开时重新计时。
        progress = leg_progress(self.times(), NOW)
        self.assertAlmostEqual(progress, 75 / 155, places=4)

    def test_estimated_arrival_extends_instead_of_compressing(self) -> None:
        times = self.times().model_copy(update={"estimated_arrival_utc": datetime(2026, 9, 22, 9, 30, tzinfo=timezone.utc)})
        self.assertLess(leg_progress(times, NOW), leg_progress(self.times(), NOW))
        next_start = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
        shifted = schedule_after_leg(next_start, datetime(2026, 9, 22, 9, 30, tzinfo=timezone.utc), timedelta(minutes=20))
        self.assertEqual(shifted, datetime(2026, 9, 22, 9, 50, tzinfo=timezone.utc))

    def test_world_service_key_is_stable_and_instance_specific(self) -> None:
        a = world_service_key("fixture", "OP-1", date(2026, 9, 22), "PEK", "SHA", 1)
        b = world_service_key("fixture", "OP-1", date(2026, 9, 23), "PEK", "SHA", 1)
        self.assertNotEqual(a, b)
        self.assertEqual(derive_service_number(a), derive_service_number(a))

    def test_position_along_route(self) -> None:
        route = [LatLng(lat=0, lng=0), LatLng(lat=0, lng=2)]
        point, heading = position_along(route, 0.5)
        self.assertAlmostEqual(point.lng, 1.0, places=3)
        self.assertAlmostEqual(heading, 90.0, places=3)


class CompanionAnchorTests(unittest.TestCase):
    def test_position_follows_anchor_and_clamps(self) -> None:
        anchor = MediaAnchor(position_ms=10_000, server_time=NOW)
        self.assertEqual(position_at(anchor, MediaSessionState.playing, 60_000, NOW + timedelta(seconds=5)), 15_000)
        self.assertEqual(position_at(anchor, MediaSessionState.paused, 60_000, NOW + timedelta(seconds=5)), 10_000)
        self.assertEqual(position_at(anchor, MediaSessionState.playing, 12_000, NOW + timedelta(seconds=5)), 12_000)

    def test_driving_blocks_video_and_lease(self) -> None:
        self.assertFalse(video_allowed(TravellerRole.driver))
        self.assertTrue(video_allowed(TravellerRole.passenger))
        lease = ControlLease(holder_device_id="d1", lease_expires_at=NOW + timedelta(seconds=30))
        self.assertTrue(lease_allows(lease, "d1", NOW))
        self.assertFalse(lease_allows(lease, "d2", NOW))
        self.assertTrue(lease_allows(lease, "d2", NOW + timedelta(seconds=31)))

    def test_only_synced_fresh_heartbeat_counts(self) -> None:
        self.assertTrue(participation_counts(ParticipationMode.synced, MediaKind.audio, 800, 5))
        self.assertFalse(participation_counts(ParticipationMode.synced, MediaKind.audio, 1500, 5))
        self.assertFalse(participation_counts(ParticipationMode.solo, MediaKind.audio, 0, 5))
        self.assertFalse(participation_counts(ParticipationMode.synced, MediaKind.video, 0, 120))


if __name__ == "__main__":
    unittest.main()
