"""旅行任务、行囊与纪念品端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_engine
from ..http_utils import with_not_found
from ..schemas import (
    CollectSouvenirsResponse,
    SouvenirItem,
    TravelBag,
    TravelBagPackRequest,
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelWishRequest,
)

router = APIRouter()


@router.post("/api/v1/pets/{pet_id}/travel_quests", response_model=TravelQuest)
def create_travel_quest(pet_id: str, request: TravelWishRequest, engine=Depends(get_engine)) -> TravelQuest:
    return with_not_found(lambda: engine.create_travel_quest(pet_id, request))


@router.get("/api/v1/pets/{pet_id}/travel_quests", response_model=list[TravelQuest])
def list_travel_quests(pet_id: str, limit: int = 20, engine=Depends(get_engine)) -> list[TravelQuest]:
    return with_not_found(lambda: engine.list_travel_quests(pet_id, limit=limit))


@router.get("/api/v1/pets/{pet_id}/travel_quests/{quest_id}", response_model=TravelQuest)
def get_travel_quest(pet_id: str, quest_id: str, engine=Depends(get_engine)) -> TravelQuest:
    return with_not_found(lambda: engine.get_travel_quest(pet_id, quest_id))


@router.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/prepare_departure", response_model=TravelQuest)
def prepare_travel_quest(pet_id: str, quest_id: str, engine=Depends(get_engine)) -> TravelQuest:
    return with_not_found(lambda: engine.prepare_travel_quest(pet_id, quest_id))


@router.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/post_event_options", response_model=TravelQuest)
def travel_quest_post_event_options(pet_id: str, quest_id: str, engine=Depends(get_engine)) -> TravelQuest:
    return with_not_found(lambda: engine.travel_quest_post_event_options(pet_id, quest_id))


@router.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/select_next_step", response_model=TravelQuest)
def select_travel_quest_next_step(
    pet_id: str,
    quest_id: str,
    request: TravelQuestDecisionRequest,
    engine=Depends(get_engine),
) -> TravelQuest:
    return with_not_found(lambda: engine.select_travel_quest_next_step(pet_id, quest_id, request))


@router.get("/api/v1/pets/{pet_id}/travel_bag", response_model=TravelBag)
def get_travel_bag(pet_id: str, quest_id: str | None = None, engine=Depends(get_engine)) -> TravelBag:
    return with_not_found(lambda: engine.get_travel_bag(pet_id, quest_id=quest_id))


@router.post("/api/v1/pets/{pet_id}/travel_bag", response_model=TravelBag)
def pack_travel_bag(pet_id: str, request: TravelBagPackRequest, engine=Depends(get_engine)) -> TravelBag:
    return with_not_found(lambda: engine.pack_travel_bag(pet_id, request))


@router.get("/api/v1/pets/{pet_id}/souvenirs", response_model=list[SouvenirItem])
def list_souvenirs(pet_id: str, limit: int = 50, engine=Depends(get_engine)) -> list[SouvenirItem]:
    return with_not_found(lambda: engine.list_souvenirs(pet_id, limit=limit))


@router.post(
    "/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect",
    response_model=CollectSouvenirsResponse,
)
def collect_travel_quest_souvenirs_with_economy(
    pet_id: str,
    quest_id: str,
    engine=Depends(get_engine),
) -> CollectSouvenirsResponse:
    return with_not_found(lambda: engine.collect_travel_quest_souvenirs_response(pet_id, quest_id))


@router.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs", response_model=list[SouvenirItem])
def collect_travel_quest_souvenirs(pet_id: str, quest_id: str, engine=Depends(get_engine)) -> list[SouvenirItem]:
    return with_not_found(lambda: engine.collect_travel_quest_souvenirs(pet_id, quest_id))
