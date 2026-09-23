"""旧存储 → HomeSnapshot 适配（R0 真实本地读取链路）。

只读：宠物记录、钱包（pet_wallets.travel_coin，唯一游戏币口径）。不调用 world_snapshot /
life_tick 等可能推进世界或触发供应商的方法。旧模型没有“在家/守护/菜园”概念，因此
presence=unknown、plots=[]，并在 missing_capabilities 如实列出，不伪造。
"""

from __future__ import annotations

from ..config import Settings
from ..http_utils import public_photo_url
from ..schemas.web.common import DataOrigin
from ..schemas.web.home import GuardBasis, GuardState, HomeSnapshot, WalletSummary
from ..schemas.web.pets import PetOrigin, PetPresence, PetPrivateSummary, PetSpecies
from ..storage import JourneyStorage, PetRecord
from ..utils import utcnow

LEGACY_MISSING_CAPABILITIES = (
    "home.presence",
    "home.guard",
    "farm.plots",
    "reception.home_welcome",
    "journey.map",
)


def legacy_home_id(pet_id: str) -> str:
    """首发一个家绑定一只主宠物；在家园表建立前用确定性 ID 过渡（home 模块迁移后替换）。"""
    return f"home-{pet_id}"


def pet_species(record: PetRecord) -> PetSpecies:
    try:
        return PetSpecies(record.pet_type.value)
    except ValueError:
        return PetSpecies.other


def build_legacy_home_snapshot(storage: JourneyStorage, settings: Settings, user_id: str) -> HomeSnapshot | None:
    pets = storage.list_pets_for_user(user_id)
    if not pets:
        return None
    pet = pets[0]
    wallet = storage.get_wallet(pet.pet_id)
    home_id = legacy_home_id(pet.pet_id)
    summary = PetPrivateSummary(
        pet_id=pet.pet_id,
        home_id=home_id,
        name=pet.name,
        species=pet_species(pet),
        photo_url=public_photo_url(settings, pet.photo_path),
        origin=PetOrigin.own_pet,
        owner_title=None,  # 旧 DNA 的 owner_title 未经接待确认，不当作主人确认的称呼
        presence=PetPresence.unknown,
    )
    return HomeSnapshot(
        home_id=home_id,
        server_time=utcnow(),
        version=1,
        pet=summary,
        presence=PetPresence.unknown,
        guard=GuardState(guarding=False, basis=GuardBasis.none),
        wallet=WalletSummary(
            currency="travel_coin",
            balance=wallet.travel_coin if wallet else 0,
            updated_at=wallet.updated_at if wallet else None,
        ),
        plots=[],
        journey=None,
        welcome=None,
        missing_capabilities=list(LEGACY_MISSING_CAPABILITIES),
        data_origin=DataOrigin.live,
    )
