"""宠物核心端点：创建、状态、行程、图文攻略、快照等。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..agent_engine import PetNotFoundError
from ..dependencies import (
    get_credential_prompt_builder,
    get_engine,
    get_illustrated_guide_engine,
    get_route_planner,
    get_settings,
    get_storage,
)
from ..http_utils import public_media_url, public_photo_url, save_upload
from ..pet_guide_engine.preview_plan import lightweight_illustrated_guide_plan
from ..seeding import DEMO_FRENCHIE_POSTCARD_PHOTO, DEMO_FRENCHIE_PROFILE_PHOTO
from .helpers import parse_dna, with_not_found
from ..schemas import (
    AgentStatus,
    CityPosition,
    CreatePetResponse,
    DayPlan,
    FeedbackResponse,
    IllustratedGuide,
    JourneyEngineTrace,
    JourneyPlan,
    JourneyRoutePlan,
    LifeTickResult,
    PetAuthoredGuide,
    PetCredentialPrompt,
    PetDNA,
    PetType,
    PhotoMission,
    Postcard,
    StaticMapAsset,
    StreetRankResponse,
    ThoughtTranslation,
    WorldSimulationSnapshot,
)

router = APIRouter()


@router.post("/api/v1/create_pet", response_model=CreatePetResponse)
async def create_pet(
    pet_name: str = Form(...),
    pet_type: PetType = Form(...),
    dna: str = Form(...),
    pet_photo: UploadFile | None = File(default=None),
    settings=Depends(get_settings),
    storage=Depends(get_storage),
    engine=Depends(get_engine),
) -> CreatePetResponse:
    parsed_dna = parse_dna(dna)
    photo_path = await save_upload(settings.upload_dir, pet_photo)
    pet = storage.create_pet(
        name=pet_name.strip(),
        pet_type=pet_type,
        dna=parsed_dna,
        photo_path=photo_path,
    )
    engine.create_initial_journey(pet)

    city = engine.city_position(pet.pet_id).city
    return CreatePetResponse(
        success=True,
        pet_id=pet.pet_id,
        name=pet.name,
        location=city,
        photo_url=public_photo_url(settings, photo_path),
        message=f"{pet.name} 已经在 {city} 开始旅程了",
    )


@router.post("/api/v1/demo/frenchie", response_model=CreatePetResponse)
def create_demo_frenchie(
    settings=Depends(get_settings),
    storage=Depends(get_storage),
    engine=Depends(get_engine),
) -> CreatePetResponse:
    dna = PetDNA(
        owner_title="妈妈",
        personality="黏人、好奇、很会观察人的情绪，到了新地方会先看一圈再靠近。",
        favorite_places=["有地毯的小店", "安静网吧", "能晒太阳的街角"],
        hobby=["盯着屏幕看", "戴耳机陪人打游戏", "坐在咖啡店和小吃店里观察人来人往"],
        catchphrase="我在这里玩一会儿，也在想你。",
        emoji_pref="soft",
        voice_style="像发来一张随手拍照片，语气轻轻的但很认真。",
    )
    pet = storage.create_pet(
        name="小黑",
        pet_type=PetType.dog,
        dna=dna,
        photo_path=DEMO_FRENCHIE_PROFILE_PHOTO,
    )
    engine.create_initial_journey(pet)

    city = engine.city_position(pet.pet_id).city
    postcard_url = public_media_url(settings, DEMO_FRENCHIE_POSTCARD_PHOTO)
    storage.add_postcard(
        pet.pet_id,
        location=f"{city} · 安静网吧",
        text="我找到一个很亮的屏幕，旁边的人都很专心。我戴着耳机坐了一会儿，像是在陪他们赢一局。",
        weather="室内有蓝色的灯，外面应该还是温暖的",
        happiness=88,
        image_url=postcard_url,
    )
    storage.append_thought(
        pet.pet_id,
        "汪呜汪，汪汪！呜汪。",
        tone="selfie",
        animal_text="汪呜汪，汪汪！呜汪。",
        translation="我刚刚拍了一张照片给你。这里有键盘声、饮料杯，还有一点点像冒险的光。",
        language_style="dog_vocalization_with_hidden_translation",
        model=settings.agent_model,
    )
    storage.append_event(
        pet.pet_id,
        "发回一张场景照",
        "TA 在一个网吧里短暂停留，照片已经作为第一张明信片保存。",
    )

    return CreatePetResponse(
        success=True,
        pet_id=pet.pet_id,
        name=pet.name,
        location=city,
        photo_url=public_media_url(settings, DEMO_FRENCHIE_PROFILE_PHOTO),
        message=f"{pet.name} 的演示旅程已经建立，并发回了第一张照片。",
    )


@router.get("/api/v1/agent_status/{pet_id}", response_model=AgentStatus)
def agent_status(pet_id: str, engine=Depends(get_engine)) -> AgentStatus:
    return with_not_found(lambda: engine.status(pet_id))


@router.get("/api/v1/day_plan/{pet_id}", response_model=DayPlan)
def day_plan(pet_id: str, engine=Depends(get_engine)) -> DayPlan:
    return with_not_found(lambda: engine.day_plan(pet_id))


@router.get("/api/v1/pet_dna/{pet_id}", response_model=PetDNA)
def pet_dna(pet_id: str, engine=Depends(get_engine)) -> PetDNA:
    return with_not_found(lambda: engine.pet_dna(pet_id))


@router.patch("/api/v1/pet_dna/{pet_id}", response_model=PetDNA)
def update_pet_dna(pet_id: str, dna: PetDNA, engine=Depends(get_engine)) -> PetDNA:
    return with_not_found(lambda: engine.update_pet_dna(pet_id, dna))


@router.get("/api/v1/pets/{pet_id}/credentials/prompts", response_model=list[PetCredentialPrompt])
def credential_prompts(
    pet_id: str,
    storage=Depends(get_storage),
    credential_prompt_builder=Depends(get_credential_prompt_builder),
) -> list[PetCredentialPrompt]:
    pet = storage.get_pet(pet_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Pet not found")
    return credential_prompt_builder.build_wallet_prompts(
        pet=pet,
        has_pet_reference=bool(pet.photo_path),
    )


@router.get("/api/v1/thoughts/{thought_id}/translation", response_model=ThoughtTranslation)
def thought_translation(thought_id: str, pet_id: str, engine=Depends(get_engine)) -> ThoughtTranslation:
    return with_not_found(lambda: engine.thought_translation(pet_id=pet_id, thought_id=thought_id))


@router.get("/api/v1/pets/{pet_id}/traces", response_model=list[JourneyEngineTrace])
def list_traces(pet_id: str, limit: int = 20, engine=Depends(get_engine)) -> list[JourneyEngineTrace]:
    return with_not_found(lambda: engine.list_traces(pet_id, limit=limit))


@router.get("/api/v1/pets/{pet_id}/traces/{trace_id}", response_model=JourneyEngineTrace)
def get_trace(pet_id: str, trace_id: str, engine=Depends(get_engine)) -> JourneyEngineTrace:
    return with_not_found(lambda: engine.get_trace(pet_id, trace_id))


@router.get("/api/v1/pets/{pet_id}/city_position", response_model=CityPosition)
def city_position(pet_id: str, engine=Depends(get_engine)) -> CityPosition:
    return with_not_found(lambda: engine.city_position(pet_id))


@router.get("/api/v1/pets/{pet_id}/route_plan", response_model=JourneyRoutePlan)
def route_plan(pet_id: str, engine=Depends(get_engine)) -> JourneyRoutePlan:
    return with_not_found(lambda: engine.route_plan(pet_id))


@router.get("/api/v1/pets/{pet_id}/journey_plan", response_model=JourneyPlan)
def journey_plan(pet_id: str, engine=Depends(get_engine)) -> JourneyPlan:
    return with_not_found(lambda: engine.journey_plan(pet_id))


@router.get("/api/v1/pets/{pet_id}/pet_guide", response_model=PetAuthoredGuide)
def pet_guide(pet_id: str, engine=Depends(get_engine)) -> PetAuthoredGuide:
    return with_not_found(lambda: engine.pet_guide(pet_id))


@router.get("/api/v1/pets/{pet_id}/illustrated_guide", response_model=IllustratedGuide)
def illustrated_guide(
    pet_id: str,
    style_id: str | None = None,
    storage=Depends(get_storage),
    engine=Depends(get_engine),
    route_planner=Depends(get_route_planner),
    illustrated_guide_engine=Depends(get_illustrated_guide_engine),
) -> IllustratedGuide:
    def build() -> IllustratedGuide:
        pet = storage.get_pet(pet_id)
        if not pet:
            raise PetNotFoundError(pet_id)
        plan = lightweight_illustrated_guide_plan(engine, route_planner, pet)
        return illustrated_guide_engine.build(
            pet=pet,
            plan=plan,
            now=plan.generated_at,
            style_id=style_id,
        )

    return with_not_found(build)


@router.post("/api/v1/pets/{pet_id}/illustrated_guide/generate", response_model=IllustratedGuide)
def generate_illustrated_guide(
    pet_id: str,
    style_id: str | None = None,
    force_new_style: bool = False,
    storage=Depends(get_storage),
    engine=Depends(get_engine),
    route_planner=Depends(get_route_planner),
    illustrated_guide_engine=Depends(get_illustrated_guide_engine),
) -> IllustratedGuide:
    def build() -> IllustratedGuide:
        pet = storage.get_pet(pet_id)
        if not pet:
            raise PetNotFoundError(pet_id)
        plan = lightweight_illustrated_guide_plan(engine, route_planner, pet)
        return illustrated_guide_engine.build(
            pet=pet,
            plan=plan,
            now=plan.generated_at,
            generate_image=True,
            style_id=style_id,
            force_new_style=force_new_style,
        )

    return with_not_found(build)


@router.get("/api/v1/pets/{pet_id}/world_snapshot", response_model=WorldSimulationSnapshot)
def world_snapshot(pet_id: str, engine=Depends(get_engine)) -> WorldSimulationSnapshot:
    return with_not_found(lambda: engine.world_snapshot(pet_id))


@router.get("/api/v1/pets/{pet_id}/life_tick", response_model=LifeTickResult)
def life_tick(pet_id: str, engine=Depends(get_engine)) -> LifeTickResult:
    return with_not_found(lambda: engine.life_tick(pet_id))


@router.get("/api/v1/pets/{pet_id}/street_rank", response_model=StreetRankResponse)
def street_rank(pet_id: str, theme: str = "street", engine=Depends(get_engine)) -> StreetRankResponse:
    return with_not_found(lambda: engine.street_rank(pet_id, theme))


@router.get("/api/v1/pets/{pet_id}/static_map", response_model=StaticMapAsset)
def static_map(pet_id: str, zoom: int = 14, engine=Depends(get_engine)) -> StaticMapAsset:
    return with_not_found(lambda: engine.static_map_for_pet(pet_id, zoom=zoom))


@router.get("/api/v1/pets/{pet_id}/photo_mission", response_model=PhotoMission)
def photo_mission(pet_id: str, engine=Depends(get_engine)) -> PhotoMission:
    return with_not_found(lambda: engine.photo_mission(pet_id))


@router.post("/api/v1/pets/{pet_id}/generate_selfie", response_model=Postcard)
def generate_selfie(pet_id: str, engine=Depends(get_engine)) -> Postcard:
    return with_not_found(lambda: engine.generate_selfie(pet_id))


@router.post("/api/v1/feedback", response_model=FeedbackResponse)
def feedback(
    pet_id: str = Form(...),
    city: str = Form(...),
    liked: bool = Form(...),
    engine=Depends(get_engine),
) -> FeedbackResponse:
    return with_not_found(lambda: engine.feedback(pet_id=pet_id, city=city, liked=liked))
