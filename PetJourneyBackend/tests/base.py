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


class PetJourneyApiTestBase(unittest.TestCase):

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

