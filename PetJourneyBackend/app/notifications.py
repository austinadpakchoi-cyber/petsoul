from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol

from .config import Settings
from .schemas import NotificationDelivery
from .storage import JourneyStorage


@dataclass(frozen=True, slots=True)
class PushMessage:
    pet_id: str
    title: str
    body: str
    category: str
    data: dict[str, object]


class NotificationProvider(Protocol):
    provider_name: str

    def send(self, *, device_token: str, message: PushMessage, environment: str = "sandbox") -> tuple[str, str | None]:
        ...

    def config_snapshot(self) -> dict[str, str | bool]:
        ...


class MockNotificationProvider:
    provider_name = "mock-notification-provider"

    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, *, device_token: str, message: PushMessage, environment: str = "sandbox") -> tuple[str, str | None]:
        return "mock_sent", None

    def config_snapshot(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider_name,
            "remote_configured": self._apns_configured(),
            "remote_call_active": False,
            "environment": self.settings.apns_environment,
        }

    def _apns_configured(self) -> bool:
        return bool(
            self.settings.apns_team_id
            and self.settings.apns_key_id
            and self.settings.apns_bundle_id
            and self.settings.apns_private_key_path
        )


class APNsNotificationProvider:
    provider_name = "apns-notification-provider"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._jwt_token: str | None = None
        self._jwt_issued_at = 0.0

    def send(self, *, device_token: str, message: PushMessage, environment: str = "sandbox") -> tuple[str, str | None]:
        if not self._configured():
            return "skipped", "APNs credentials are not configured"
        try:
            import httpx  # type: ignore
            import jwt  # type: ignore
        except Exception as exc:
            return "skipped", f"APNs dependencies are missing: {exc}"

        token = self._auth_token(jwt)
        host = "api.push.apple.com" if environment == "production" else "api.sandbox.push.apple.com"
        url = f"https://{host}/3/device/{device_token}"
        payload = {
            "aps": {
                "alert": {
                    "title": message.title,
                    "body": message.body,
                },
                "sound": "default",
                "category": message.category,
            },
            "pet_id": message.pet_id,
            **message.data,
        }
        headers = {
            "authorization": f"bearer {token}",
            "apns-topic": self.settings.apns_bundle_id or "",
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        try:
            with httpx.Client(http2=True, timeout=8.0) as client:
                response = client.post(url, json=payload, headers=headers)
        except Exception as exc:
            return "failed", str(exc)
        if 200 <= response.status_code < 300:
            return "sent", None
        return "failed", f"{response.status_code} {response.text}"

    def config_snapshot(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider_name,
            "remote_configured": self._configured(),
            "remote_call_active": self._configured(),
            "environment": self.settings.apns_environment,
        }

    def _configured(self) -> bool:
        return bool(
            self.settings.apns_team_id
            and self.settings.apns_key_id
            and self.settings.apns_bundle_id
            and self.settings.apns_private_key_path
            and self.settings.apns_private_key_path.exists()
        )

    def _auth_token(self, jwt_module) -> str:
        now = time()
        if self._jwt_token and now - self._jwt_issued_at < 45 * 60:
            return self._jwt_token
        private_key = self.settings.apns_private_key_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
        self._jwt_token = jwt_module.encode(
            {"iss": self.settings.apns_team_id, "iat": int(now)},
            private_key,
            algorithm="ES256",
            headers={"kid": self.settings.apns_key_id},
        )
        self._jwt_issued_at = now
        return self._jwt_token


class NotificationDispatcher:
    provider_name = "notification-dispatcher"

    def __init__(self, storage: JourneyStorage, provider: NotificationProvider):
        self.storage = storage
        self.provider = provider

    def register_device(self, *, pet_id: str, device_token: str, platform: str, environment: str) -> dict[str, object]:
        return self.storage.upsert_device_token(
            pet_id=pet_id,
            device_token=device_token.strip(),
            platform=platform,
            environment=environment,
        )

    def unregister_device(self, *, device_token: str, platform: str = "ios") -> None:
        self.storage.remove_device_token(device_token.strip(), platform=platform)

    def send_to_pet(self, pet_id: str, title: str, body: str, category: str, data: dict[str, object] | None = None) -> list[NotificationDelivery]:
        tokens = self.storage.list_device_tokens(pet_id)
        message = PushMessage(pet_id=pet_id, title=title, body=body, category=category, data=data or {})
        deliveries: list[NotificationDelivery] = []
        if not tokens:
            item = self.storage.record_notification_delivery(
                pet_id=pet_id,
                device_token=None,
                title=title,
                body=body,
                category=category,
                provider=self.provider.provider_name,
                status="no_device",
            )
            return [NotificationDelivery.model_validate(item)]
        for token in tokens:
            status, error = self.provider.send(
                device_token=str(token["device_token"]),
                message=message,
                environment=str(token["environment"]),
            )
            item = self.storage.record_notification_delivery(
                pet_id=pet_id,
                device_token=str(token["device_token"]),
                title=title,
                body=body,
                category=category,
                provider=self.provider.provider_name,
                status=status,
                error=error,
            )
            deliveries.append(NotificationDelivery.model_validate(item))
        return deliveries

    def config_snapshot(self) -> dict[str, str | bool]:
        payload = self.provider.config_snapshot()
        payload["dispatcher"] = self.provider_name
        return payload


def build_notification_dispatcher(storage: JourneyStorage, settings: Settings) -> NotificationDispatcher:
    remote_configured = bool(
        settings.apns_team_id
        and settings.apns_key_id
        and settings.apns_bundle_id
        and settings.apns_private_key_path
    )
    provider: NotificationProvider
    if remote_configured:
        provider = APNsNotificationProvider(settings)
    else:
        provider = MockNotificationProvider(settings)
    return NotificationDispatcher(storage, provider)
