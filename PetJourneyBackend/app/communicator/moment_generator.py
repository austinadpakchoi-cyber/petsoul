from __future__ import annotations

from datetime import datetime, timedelta

from .moment_store import CommunicatorMomentStore, new_moment_id
from .npc_society import npc_reactors
from .schemas import (
    AttachmentState,
    AttachmentType,
    CommunicatorAttachment,
    CommunicatorMoment,
    CommunicatorWorldSnapshot,
    MomentReaction,
    MomentSocialReactor,
    MomentSourceType,
)

MOMENT_MIN_INTERVAL_SECONDS = 1800
SAME_SCENE_MOMENT_COOLDOWN_SECONDS = 3600
MAX_MOMENTS_PER_DAY = 6
MAX_PHOTO_MOMENTS_PER_DAY = 3


class CommunicatorMomentGenerator:
    provider_name = "rule-based-communicator-moment-generator"

    def __init__(self, store: CommunicatorMomentStore, *, public_base_url: str | None = None):
        self.store = store
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None

    def ensure_seed_moments(self, *, pet_id: str, pet_name: str, world: CommunicatorWorldSnapshot, now: datetime) -> list[CommunicatorMoment]:
        existing = self.store.list_moments(pet_id, limit=3)
        if existing:
            return self._enrich_existing_moments(existing=existing, world=world, now=now)
        # 飞行/长途途中不 seed“到达/停留”动态——TA 还没到，等落地后自然产生
        if world.is_flying:
            return []
        moments = [
            self._moment(
                pet_id=pet_id,
                source_type=MomentSourceType.arrival,
                text=f"到{world.city}啦。这里的风和声音都还在慢慢认出来。",
                world=world,
                now=now - timedelta(minutes=42),
                mood="curious",
            ),
            self._moment(
                pet_id=pet_id,
                source_type=MomentSourceType.resting,
                text=f"{pet_name}在一个安静地方停了一小会儿，像是在把今天的路收进爪心。",
                world=world,
                now=now - timedelta(minutes=18),
                mood="calm",
            ),
        ]
        for moment in moments:
            self.store.add_moment(moment, scene_hash=world.scene_hash)
        return self.store.list_moments(pet_id)

    def maybe_create_moment(
        self,
        *,
        pet_id: str,
        source_type: MomentSourceType,
        text: str,
        world: CommunicatorWorldSnapshot,
        now: datetime,
        attachments: list[CommunicatorAttachment] | None = None,
        force: bool = False,
    ) -> CommunicatorMoment | None:
        resolved_attachments = attachments if attachments is not None else []
        if self._wait_for_ready_photo(source_type=source_type, attachments=resolved_attachments):
            return None
        if not force and not self._can_create(pet_id=pet_id, world=world, now=now, attachments=resolved_attachments):
            return None
        moment = self._moment(
            pet_id=pet_id,
            source_type=source_type,
            text=text,
            world=world,
            now=now,
            attachments=resolved_attachments,
            mood=self._mood(world),
        )
        return self.store.add_moment(moment, scene_hash=world.scene_hash)

    def _wait_for_ready_photo(
        self,
        *,
        source_type: MomentSourceType,
        attachments: list[CommunicatorAttachment],
    ) -> bool:
        if source_type not in {MomentSourceType.current_status_photo, MomentSourceType.photo_request_fulfilled}:
            return False
        photo_attachments = [
            item for item in attachments
            if item.type in {AttachmentType.photo, AttachmentType.photo_placeholder, AttachmentType.pending_photo_request}
        ]
        if not photo_attachments:
            return True
        return not any(item.type == AttachmentType.photo and item.photo_url for item in photo_attachments)

    def _can_create(
        self,
        *,
        pet_id: str,
        world: CommunicatorWorldSnapshot,
        now: datetime,
        attachments: list[CommunicatorAttachment],
    ) -> bool:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.store.count_moments_since(pet_id, day_start) >= MAX_MOMENTS_PER_DAY:
            return False
        has_photo = any(item.type in {AttachmentType.photo, AttachmentType.photo_placeholder} for item in attachments)
        if has_photo and self.store.count_moments_since(pet_id, day_start, photo_only=True) >= MAX_PHOTO_MOMENTS_PER_DAY:
            return False
        latest = self.store.latest_moment_at(pet_id)
        if latest and (now - latest).total_seconds() < MOMENT_MIN_INTERVAL_SECONDS:
            return False
        latest_scene = self.store.latest_moment_at(pet_id, scene_hash=world.scene_hash)
        if latest_scene and (now - latest_scene).total_seconds() < SAME_SCENE_MOMENT_COOLDOWN_SECONDS:
            return False
        if world.is_flying or world.is_sleeping or world.energy < 30:
            return False
        return True

    def _moment(
        self,
        *,
        pet_id: str,
        source_type: MomentSourceType,
        text: str,
        world: CommunicatorWorldSnapshot,
        now: datetime,
        attachments: list[CommunicatorAttachment] | None = None,
        mood: str = "calm",
    ) -> CommunicatorMoment:
        moment_attachments = attachments if attachments is not None else self._default_attachments(
            source_type=source_type,
            world=world,
            now=now,
        )
        social_reactors = self._social_reactors(
            source_type=source_type,
            world=world,
            mood=mood,
            now=now,
        )
        return CommunicatorMoment(
            id=new_moment_id(source_type),
            pet_id=pet_id,
            source_type=source_type,
            text=text,
            location=world.location,
            mood=mood,
            attachments=moment_attachments,
            reactions=self._reaction_counts(social_reactors),
            social_reactors=social_reactors,
            is_read=False,
            created_at=now,
        )

    def _mood(self, world: CommunicatorWorldSnapshot) -> str:
        if world.energy < 40:
            return "tired"
        if world.happiness >= 75:
            return "soft_happy"
        if world.curiosity >= 75:
            return "curious"
        return "calm"

    def _enrich_existing_moments(
        self,
        *,
        existing: list[CommunicatorMoment],
        world: CommunicatorWorldSnapshot,
        now: datetime,
    ) -> list[CommunicatorMoment]:
        enriched: list[CommunicatorMoment] = []
        for index, moment in enumerate(existing):
            update: dict[str, object] = {}
            if not moment.attachments and index < 2:
                attachments = self._default_attachments(
                    source_type=moment.source_type,
                    world=world,
                    now=moment.created_at,
                )
                if attachments:
                    update["attachments"] = attachments
            if not moment.social_reactors:
                reactors = self._social_reactors(
                    source_type=moment.source_type,
                    world=world,
                    mood=moment.mood,
                    now=moment.created_at,
                )
                if reactors:
                    update["social_reactors"] = reactors
                    update["reactions"] = self._merge_reaction_counts(moment.reactions, reactors)
            if update:
                update["updated_at"] = now
                moment = self.store.add_moment(moment.model_copy(update=update), scene_hash=world.scene_hash)
            enriched.append(moment)
        return enriched

    def _default_attachments(
        self,
        *,
        source_type: MomentSourceType,
        world: CommunicatorWorldSnapshot,
        now: datetime,
    ) -> list[CommunicatorAttachment]:
        if source_type in {MomentSourceType.current_status_photo, MomentSourceType.photo_request_fulfilled}:
            return []
        if source_type == MomentSourceType.arrival:
            return [
                CommunicatorAttachment(
                    type=AttachmentType.location_card,
                    title="到达地点",
                    text=f"{world.city}{' · ' + world.place_name if world.place_name else ''}。TA 刚到这里，先向朋友圈报个平安。",
                    state=AttachmentState.ready,
                    location=world.location,
                    metadata={
                        "scene_hash": world.scene_hash,
                        "origin": "parallel_world_moment",
                    },
                )
            ]
        if source_type == MomentSourceType.postcard_candidate:
            return [
                CommunicatorAttachment(
                    type=AttachmentType.postcard_candidate,
                    title="明信片候选",
                    text=f"{world.city}{' · ' + world.place_name if world.place_name else ''}。这里适合慢慢写成一张明信片。",
                    state=AttachmentState.planned,
                    location=world.location,
                    metadata={"scene_hash": world.scene_hash, "origin": "parallel_world_moment"},
                )
            ]
        if source_type == MomentSourceType.resting:
            return [
                CommunicatorAttachment(
                    type=AttachmentType.location_card,
                    title="停留地点",
                    text=f"{world.city}{' · ' + world.place_name if world.place_name else ''}。TA 在这里慢慢待了一会儿。",
                    state=AttachmentState.ready,
                    location=world.location,
                    metadata={"scene_hash": world.scene_hash},
                )
            ]
        return []

    def _social_reactors(
        self,
        *,
        source_type: MomentSourceType,
        world: CommunicatorWorldSnapshot,
        mood: str,
        now: datetime,
    ) -> list[MomentSocialReactor]:
        return npc_reactors(
            city=world.city,
            scene_hash=world.scene_hash,
            source_type=source_type.value,
            mood=mood,
            now=now,
        )

    def _reaction_counts(self, reactors: list[MomentSocialReactor]) -> dict[str, int]:
        counts = {
            MomentReaction.like.value: 0,
            MomentReaction.paw.value: 0,
            MomentReaction.hug.value: 0,
        }
        for reactor in reactors:
            counts[reactor.reaction.value] = counts.get(reactor.reaction.value, 0) + 1
        return counts

    def _merge_reaction_counts(
        self,
        existing: dict[str, int],
        reactors: list[MomentSocialReactor],
    ) -> dict[str, int]:
        counts = {
            MomentReaction.like.value: existing.get(MomentReaction.like.value, 0),
            MomentReaction.paw.value: existing.get(MomentReaction.paw.value, 0),
            MomentReaction.hug.value: existing.get(MomentReaction.hug.value, 0),
        }
        for reactor in reactors:
            counts[reactor.reaction.value] = counts.get(reactor.reaction.value, 0) + 1
        return counts
