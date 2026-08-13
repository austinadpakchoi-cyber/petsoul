"""Apple 登录与用户/宠物归属端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from ..auth import AuthError
from ..dependencies import get_auth_service, get_settings, get_storage
from ..http_utils import public_photo_url
from ..schemas import (
    AppleSignInRequest,
    AuthPetSummary,
    AuthSessionResponse,
    ClaimPetRequest,
    MeResponse,
)
from ..storage import PetOwnershipConflict, PetRecord

router = APIRouter()


def _auth_pet_summary(settings, pet: PetRecord) -> AuthPetSummary:
    return AuthPetSummary(
        pet_id=pet.pet_id,
        name=pet.name,
        pet_type=pet.pet_type,
        photo_url=public_photo_url(settings, pet.photo_path),
    )


def _require_user_id(auth_service, authorization: str | None) -> str:
    if not auth_service.configured:
        raise HTTPException(status_code=503, detail="auth is not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return auth_service.decode_session_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="invalid session token") from exc


def _me_response(storage, settings, user_id: str) -> MeResponse:
    user = storage.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    pets = [_auth_pet_summary(settings, pet) for pet in storage.list_pets_for_user(user_id)]
    return MeResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        email=user.email,
        pets=pets,
    )


@router.post("/api/v1/auth/apple", response_model=AuthSessionResponse)
def sign_in_with_apple(
    request: AppleSignInRequest,
    settings=Depends(get_settings),
    storage=Depends(get_storage),
    auth_service=Depends(get_auth_service),
) -> AuthSessionResponse:
    if not auth_service.configured:
        raise HTTPException(status_code=503, detail="auth is not configured")
    try:
        identity = auth_service.verify_apple_identity_token(request.identity_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user, is_new = storage.upsert_user_by_apple_sub(
        identity.apple_sub, identity.email, request.display_name
    )
    token = auth_service.issue_session_token(user.user_id)
    pets = [_auth_pet_summary(settings, pet) for pet in storage.list_pets_for_user(user.user_id)]
    return AuthSessionResponse(
        access_token=token,
        user_id=user.user_id,
        display_name=user.display_name,
        is_new_user=is_new,
        pets=pets,
    )


@router.get("/api/v1/me", response_model=MeResponse)
def current_user(
    authorization: str | None = Header(default=None),
    settings=Depends(get_settings),
    storage=Depends(get_storage),
    auth_service=Depends(get_auth_service),
) -> MeResponse:
    return _me_response(storage, settings, _require_user_id(auth_service, authorization))


@router.post("/api/v1/me/claim_pet", response_model=MeResponse)
def claim_pet_for_user(
    request: ClaimPetRequest,
    authorization: str | None = Header(default=None),
    settings=Depends(get_settings),
    storage=Depends(get_storage),
    auth_service=Depends(get_auth_service),
) -> MeResponse:
    user_id = _require_user_id(auth_service, authorization)
    try:
        storage.claim_pet(request.pet_id, user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pet not found") from exc
    except PetOwnershipConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _me_response(storage, settings, user_id)
