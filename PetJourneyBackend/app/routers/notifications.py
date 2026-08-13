"""推送设备与通知投递端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_engine, get_notification_dispatcher, get_storage
from ..http_utils import with_not_found
from ..schemas import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    NotificationDelivery,
)

router = APIRouter()


@router.post("/api/v1/push/register", response_model=DeviceRegistrationResponse)
def register_push_device(
    request: DeviceRegistrationRequest,
    engine=Depends(get_engine),
    notification_dispatcher=Depends(get_notification_dispatcher),
) -> DeviceRegistrationResponse:
    with_not_found(lambda: engine.pet_dna(request.pet_id))
    item = notification_dispatcher.register_device(
        pet_id=request.pet_id,
        device_token=request.device_token,
        platform=request.platform,
        environment=request.environment,
    )
    return DeviceRegistrationResponse(
        success=True,
        device_id=str(item["id"]),
        provider=str(notification_dispatcher.config_snapshot()["provider"]),
        message="设备已经登记，TA 可以在 app 未打开时继续来信。",
    )


@router.post("/api/v1/push/unregister")
def unregister_push_device(
    request: DeviceRegistrationRequest,
    notification_dispatcher=Depends(get_notification_dispatcher),
) -> dict[str, bool]:
    notification_dispatcher.unregister_device(device_token=request.device_token, platform=request.platform)
    return {"success": True}


@router.get("/api/v1/pets/{pet_id}/notifications", response_model=list[NotificationDelivery])
def notification_deliveries(
    pet_id: str,
    limit: int = 20,
    engine=Depends(get_engine),
    storage=Depends(get_storage),
) -> list[NotificationDelivery]:
    with_not_found(lambda: engine.pet_dna(pet_id))
    return [
        NotificationDelivery.model_validate(item)
        for item in storage.list_notification_deliveries(pet_id, limit=max(1, min(100, limit)))
    ]
