"""宠物通信端点（消息、照片、朋友圈瞬间）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..communicator.schemas import (
    CommunicatorMessage,
    CommunicatorMoment,
    CommunicatorSendRequest,
    CommunicatorSendResponse,
    MomentReactionRequest,
    MomentReactionResponse,
)
from ..dependencies import get_communicator_engine, get_settings
from ..http_utils import public_media_url, save_upload, with_not_found
from ..schemas import OwnerMessageRequest, OwnerMessageResponse

router = APIRouter()


@router.post("/api/v1/pets/{pet_id}/messages", response_model=OwnerMessageResponse)
def owner_message(
    pet_id: str,
    request: OwnerMessageRequest,
    communicator_engine=Depends(get_communicator_engine),
) -> OwnerMessageResponse:
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    return with_not_found(
        lambda: communicator_engine.legacy_owner_message(
            pet_id=pet_id,
            message=request.message,
            intent_hint=request.intent_hint,
        )
    )


@router.post("/api/v1/pets/{pet_id}/communicator/messages", response_model=CommunicatorSendResponse)
def send_communicator_message(
    pet_id: str,
    request: CommunicatorSendRequest,
    communicator_engine=Depends(get_communicator_engine),
) -> CommunicatorSendResponse:
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    return with_not_found(lambda: communicator_engine.send_message(pet_id=pet_id, request=request))


@router.post("/api/v1/pets/{pet_id}/communicator/messages/photo", response_model=CommunicatorSendResponse)
async def send_communicator_photo(
    pet_id: str,
    text: str = Form(default=""),
    image: UploadFile = File(...),
    settings=Depends(get_settings),
    communicator_engine=Depends(get_communicator_engine),
) -> CommunicatorSendResponse:
    media_path = await save_upload(settings.upload_dir, image, subdir="communicator_photos")
    if not media_path:
        raise HTTPException(status_code=422, detail="image must not be empty")
    image_url = public_media_url(settings, media_path)
    if not image_url:
        raise HTTPException(status_code=500, detail="public media url is not configured")
    return with_not_found(
        lambda: communicator_engine.send_photo(
            pet_id=pet_id,
            image_url=image_url,
            media_path=media_path,
            caption=text,
        )
    )


@router.get("/api/v1/pets/{pet_id}/communicator/messages", response_model=list[CommunicatorMessage])
def list_communicator_messages(
    pet_id: str,
    limit: int = 80,
    communicator_engine=Depends(get_communicator_engine),
) -> list[CommunicatorMessage]:
    return with_not_found(lambda: communicator_engine.list_messages(pet_id=pet_id, limit=limit))


@router.get("/api/v1/pets/{pet_id}/communicator/moments", response_model=list[CommunicatorMoment])
def list_communicator_moments(
    pet_id: str,
    limit: int = 50,
    communicator_engine=Depends(get_communicator_engine),
) -> list[CommunicatorMoment]:
    return with_not_found(lambda: communicator_engine.list_moments(pet_id=pet_id, limit=limit))


@router.post(
    "/api/v1/pets/{pet_id}/communicator/moments/{moment_id}/reaction",
    response_model=MomentReactionResponse,
)
def react_to_communicator_moment(
    pet_id: str,
    moment_id: str,
    request: MomentReactionRequest,
    communicator_engine=Depends(get_communicator_engine),
) -> MomentReactionResponse:
    return with_not_found(
        lambda: communicator_engine.react_to_moment(pet_id=pet_id, moment_id=moment_id, request=request)
    )
