from __future__ import annotations

from pydantic import Field

from .base import PetJourneyBaseModel, PetType


class AuthPetSummary(PetJourneyBaseModel):
    pet_id: str
    name: str
    pet_type: PetType
    photo_url: str | None = None


class AppleSignInRequest(PetJourneyBaseModel):
    identity_token: str
    display_name: str | None = None


class AuthSessionResponse(PetJourneyBaseModel):
    access_token: str
    user_id: str
    display_name: str | None = None
    is_new_user: bool
    pets: list[AuthPetSummary] = Field(default_factory=list)


class ClaimPetRequest(PetJourneyBaseModel):
    pet_id: str


class MeResponse(PetJourneyBaseModel):
    user_id: str
    display_name: str | None = None
    email: str | None = None
    pets: list[AuthPetSummary] = Field(default_factory=list)


__all__ = [
    "AuthPetSummary",
    "AppleSignInRequest",
    "AuthSessionResponse",
    "ClaimPetRequest",
    "MeResponse",
]
