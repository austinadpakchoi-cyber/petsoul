from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class Settings:
    app_name: str = "PetJourney Backend"
    database_path: Path = BASE_DIR / "data" / "petjourney.sqlite3"
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    public_base_url: str | None = "http://127.0.0.1:8000"
    provider_mode: str = "mock"
    map_provider: str = "mock"
    cors_origins: tuple[str, ...] = ("*",)

    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.deepseek.com/v1"
    agent_model: str = "deepseek-chat"
    agent_deep_model: str = "deepseek-chat"
    agent_fast_model: str = "deepseek-chat"
    translation_model: str = "deepseek-chat"
    photo_mission_model: str = "deepseek-chat"
    agent_max_tokens: int = 512
    photo_mission_max_tokens: int = 900
    guide_max_tokens: int = 1600
    image_model: str = "gpt-image-2"
    image_base_url: str = "https://api.openai.com/v1"
    place_reference_images_enabled: bool = True
    place_reference_image_max_bytes: int = 8_000_000
    souvenir_images_enabled: bool = True
    souvenir_image_max_count: int = 2
    agent_reasoning_effort: str = "medium"
    agent_response_verbosity: str = "low"
    agent_timeout_seconds: float = 30.0
    image_timeout_seconds: float = 240.0
    map_timeout_seconds: float = 10.0
    agent_turn_interval_seconds: float = 1800.0

    amap_api_key: str | None = None
    google_maps_api_key: str | None = None
    doubao_api_key: str | None = None
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_timeout_seconds: float = 60.0
    doubao_reasoning_effort: str = "minimal"
    image_api_key: str | None = None
    worldcup_demo_enabled: bool = False

    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 60.0

    transport_schedule_provider: str = "mock"
    transport_web_search_enabled: bool = False
    transport_search_model: str = "deepseek-chat"
    transport_search_max_tokens: int = 1200
    transport_search_timeout_seconds: float = 30.0
    travel_guide_research_provider: str = "auto"
    travel_guide_search_model: str = "deepseek-chat"
    doubao_guide_model: str = "doubao-seed-2-1-pro-260628"

    apns_environment: str = "sandbox"
    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_bundle_id: str | None = None
    apns_private_key_path: Path | None = None

    auth_secret: str | None = None
    apple_auth_mode: str = "live"
    apple_bundle_id: str | None = None

    memory_provider: str = "sqlite"
    postgres_dsn: str | None = None
    memory_embedding_dimensions: int = 64
    economy_dev_grants_enabled: bool = False
    economy_admin_token: str | None = None
    economy_daily_coin_limit: int = 300


def load_settings() -> Settings:
    load_env_file(BASE_DIR / ".env")
    # 特性开关文件：.env 中已存在的键优先，此文件只补充缺省项
    load_env_file(BASE_DIR / ".env.features")
    cors_raw = os.getenv("PETJOURNEY_CORS_ORIGINS", "*")
    cors_origins = tuple(item.strip() for item in cors_raw.split(",") if item.strip()) or ("*",)

    return Settings(
        database_path=Path(os.getenv("PETJOURNEY_DB_PATH", str(BASE_DIR / "data" / "petjourney.sqlite3"))),
        upload_dir=Path(os.getenv("PETJOURNEY_UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))),
        public_base_url=os.getenv("PETJOURNEY_PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
        provider_mode=os.getenv("PETJOURNEY_PROVIDER_MODE", "mock"),
        map_provider=os.getenv("PETJOURNEY_MAP_PROVIDER", "mock"),
        cors_origins=cors_origins,
        llm_provider=os.getenv("PETJOURNEY_LLM_PROVIDER", "mock"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("PETJOURNEY_OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")),
        agent_model=os.getenv("PETJOURNEY_AGENT_MODEL", "deepseek-chat"),
        agent_deep_model=os.getenv("PETJOURNEY_AGENT_DEEP_MODEL", "deepseek-chat"),
        agent_fast_model=os.getenv("PETJOURNEY_AGENT_FAST_MODEL", "deepseek-chat"),
        translation_model=os.getenv("PETJOURNEY_TRANSLATION_MODEL", "deepseek-chat"),
        photo_mission_model=os.getenv(
            "PETJOURNEY_PHOTO_MISSION_MODEL",
            os.getenv("PETJOURNEY_AGENT_DEEP_MODEL", "deepseek-chat"),
        ),
        agent_max_tokens=int(os.getenv("PETJOURNEY_AGENT_MAX_TOKENS", "512")),
        photo_mission_max_tokens=int(os.getenv("PETJOURNEY_PHOTO_MISSION_MAX_TOKENS", "900")),
        guide_max_tokens=int(os.getenv("PETJOURNEY_GUIDE_MAX_TOKENS", "1600")),
        image_model=os.getenv("PETJOURNEY_IMAGE_MODEL", "gpt-image-2"),
        image_base_url=os.getenv(
            "PETJOURNEY_IMAGE_BASE_URL",
            os.getenv("PETJOURNEY_OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        ),
        place_reference_images_enabled=os.getenv("PETJOURNEY_PLACE_REFERENCE_IMAGES_ENABLED", "true").lower()
        in {"1", "true", "yes", "on"},
        place_reference_image_max_bytes=int(os.getenv("PETJOURNEY_PLACE_REFERENCE_IMAGE_MAX_BYTES", "8000000")),
        souvenir_images_enabled=os.getenv("PETJOURNEY_SOUVENIR_IMAGES_ENABLED", "true").lower()
        in {"1", "true", "yes", "on"},
        souvenir_image_max_count=int(os.getenv("PETJOURNEY_SOUVENIR_IMAGE_MAX_COUNT", "2")),
        agent_reasoning_effort=os.getenv("PETJOURNEY_AGENT_REASONING_EFFORT", "medium"),
        agent_response_verbosity=os.getenv("PETJOURNEY_AGENT_RESPONSE_VERBOSITY", "low"),
        agent_timeout_seconds=float(os.getenv("PETJOURNEY_AGENT_TIMEOUT_SECONDS", "30")),
        image_timeout_seconds=float(os.getenv("PETJOURNEY_IMAGE_TIMEOUT_SECONDS", "240")),
        map_timeout_seconds=float(os.getenv("PETJOURNEY_MAP_TIMEOUT_SECONDS", "10")),
        agent_turn_interval_seconds=float(os.getenv("PETJOURNEY_AGENT_TURN_INTERVAL_SECONDS", "1800")),
        amap_api_key=os.getenv("AMAP_API_KEY"),
        google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY"),
        doubao_api_key=os.getenv("DOUBAO_API_KEY"),
        doubao_base_url=os.getenv("PETJOURNEY_DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        doubao_timeout_seconds=float(os.getenv("PETJOURNEY_DOUBAO_TIMEOUT_SECONDS", "60")),
        doubao_reasoning_effort=os.getenv("PETJOURNEY_DOUBAO_REASONING_EFFORT", "minimal"),
        image_api_key=os.getenv("PETJOURNEY_IMAGE_API_KEY", os.getenv("IMAGE_API_KEY", os.getenv("OPENAI_IMAGE_API_KEY"))),
        worldcup_demo_enabled=os.getenv("PETJOURNEY_WORLDCUP_DEMO", "").lower() in {"1", "true", "yes", "on"},
        scheduler_enabled=os.getenv("PETJOURNEY_SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        scheduler_interval_seconds=float(os.getenv("PETJOURNEY_SCHEDULER_INTERVAL_SECONDS", "60")),
        transport_schedule_provider=os.getenv("PETJOURNEY_TRANSPORT_SCHEDULE_PROVIDER", "mock"),
        transport_web_search_enabled=os.getenv("PETJOURNEY_TRANSPORT_WEB_SEARCH_ENABLED", "").lower()
        in {"1", "true", "yes", "on"},
        transport_search_model=os.getenv(
            "PETJOURNEY_TRANSPORT_SEARCH_MODEL",
            os.getenv("PETJOURNEY_AGENT_FAST_MODEL", "deepseek-chat"),
        ),
        transport_search_max_tokens=int(os.getenv("PETJOURNEY_TRANSPORT_SEARCH_MAX_TOKENS", "1200")),
        transport_search_timeout_seconds=float(os.getenv("PETJOURNEY_TRANSPORT_SEARCH_TIMEOUT_SECONDS", "30")),
        travel_guide_research_provider=os.getenv("PETJOURNEY_TRAVEL_GUIDE_RESEARCH_PROVIDER", "auto"),
        travel_guide_search_model=os.getenv(
            "PETJOURNEY_TRAVEL_GUIDE_SEARCH_MODEL",
            os.getenv("PETJOURNEY_AGENT_FAST_MODEL", "deepseek-chat"),
        ),
        doubao_guide_model=os.getenv("PETJOURNEY_DOUBAO_GUIDE_MODEL", "doubao-seed-2-1-pro-260628"),
        apns_environment=os.getenv("PETJOURNEY_APNS_ENVIRONMENT", "sandbox"),
        apns_team_id=os.getenv("PETJOURNEY_APNS_TEAM_ID"),
        apns_key_id=os.getenv("PETJOURNEY_APNS_KEY_ID"),
        apns_bundle_id=os.getenv("PETJOURNEY_APNS_BUNDLE_ID"),
        apns_private_key_path=_optional_path(os.getenv("PETJOURNEY_APNS_PRIVATE_KEY_PATH")),
        auth_secret=os.getenv("PETJOURNEY_AUTH_SECRET"),
        apple_auth_mode=os.getenv("PETJOURNEY_APPLE_AUTH_MODE", "live"),
        apple_bundle_id=os.getenv("PETJOURNEY_APPLE_BUNDLE_ID"),
        memory_provider=os.getenv("PETJOURNEY_MEMORY_PROVIDER", "sqlite"),
        postgres_dsn=os.getenv("PETJOURNEY_POSTGRES_DSN"),
        memory_embedding_dimensions=int(os.getenv("PETJOURNEY_MEMORY_EMBEDDING_DIMENSIONS", "64")),
        economy_dev_grants_enabled=os.getenv("PETJOURNEY_ECONOMY_DEV_GRANTS_ENABLED", "").lower()
        in {"1", "true", "yes", "on"},
        economy_admin_token=os.getenv("PETJOURNEY_ADMIN_TOKEN"),
        economy_daily_coin_limit=int(os.getenv("PETJOURNEY_ECONOMY_DAILY_COIN_LIMIT", "300")),
    )


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    try:
        env_text = path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in env_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        cleaned = _clean_env_value(value)
        if not cleaned:
            # 空值视为未配置，不占位，让后续文件（如 .env.features）仍可补充
            continue
        os.environ[key] = cleaned


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)
