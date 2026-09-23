"""Run as root on the approved HK host. Never prints credentials."""
from pathlib import Path
import os
import secrets

target = Path("/opt/petsoul/config/backend.env")
values = {
    "PETJOURNEY_AUTH_SECRET": secrets.token_urlsafe(48),
    "PETJOURNEY_PUBLIC_BASE_URL": "https://petsoul.games",
    "PETJOURNEY_CORS_ORIGINS": "https://petsoul.games",
    "PETJOURNEY_WEB_COOKIE_SECURE": "true",
    "PETJOURNEY_LEGACY_API_POLICY": "closed",
    "PETJOURNEY_APPLE_AUTH_MODE": "live",
    "PETJOURNEY_SCHEDULER_ENABLED": "false",
    "PETJOURNEY_WEB_PROVIDERS": "false",
    "PETJOURNEY_INTENT_LAYER_MODE": "off",
    "PETJOURNEY_PROVIDER_MODE": "mock",
    "PETJOURNEY_MAP_PROVIDER": "mock",
    "PETJOURNEY_LLM_PROVIDER": "mock",
    "PETJOURNEY_IMAGE_PROVIDER": "mock",
    "PETJOURNEY_TRANSPORT_SCHEDULE_PROVIDER": "mock",
    "PETJOURNEY_ECONOMY_DEV_GRANTS_ENABLED": "false",
}
if target.exists():
    raise SystemExit("Environment already exists; preserve it and review without printing secrets.")
fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("Production environment initialized; secure cookies, closed legacy API, providers disabled.")
