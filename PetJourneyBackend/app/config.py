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
    image_provider_type: str = "openai"
    volcengine_image_model: str = "doubao-seedream-4-0-250828"
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

    # 网页 R0（/api/v1/web）：只追加，不改变上面既有默认值
    legacy_api_policy: str = "open"
    web_cookie_secure: bool = True
    web_session_ttl_seconds: int = 30 * 24 * 3600
    web_private_media_dir: Path = BASE_DIR / "data" / "web-private-media"
    intent_layer_mode: str = "off"
    intent_layer_provider: str = "rule"
    # 网页真实供应商总开关（默认关闭：测试与其他窗口的本地运行不会产生付费调用）；只在服务端使用密钥
    web_providers_enabled: bool = False
    web_llm_daily_cap: int = 300
    web_image_daily_cap: int = 20
    # 每只宠物每天的生图额度（**单位**，不是张数：没有参考照时一次请求要先画证件照再画正图，占 2 个单位）。
    # 为什么要有这一条：`web_image_daily_cap` 是**全局**的，不分宠物也不分家庭——
    # 一只宠物（或一个主人反复点"重画"）可以把整个部署当天的额度吃光，别人一张都画不成。
    # 默认 6 ＝ 无参考照时约 3 张／天，有参考照时 6 张／天；它与全局那条**并列生效**，两条都不能超。
    # 设成 0 表示不限（只剩全局那条）——那正是现在的状态，不建议保持。
    web_image_per_pet_daily_cap: int = 6
    web_map_daily_cap: int = 500
    web_map_static_daily_cap: int = 200
    web_world_tick_seconds: float = 30.0
    web_image_model: str = "doubao-seedream-4-5-251128"
    web_llm_timeout_seconds: float = 15.0
    # 世界由谁推进：embedded＝API 进程内的后台线程（默认，本地开发）；worker＝独立任务进程（python -m app.web_worker），API 不跑；off＝都不跑
    # 心跳策略（web_runtime）接入方式：off 不跑；shadow 只评估并记录，不执行也不调模型（默认）
    web_heartbeat_mode: str = "shadow"
    # 自主决策（web_agent.decision）接入方式：off 不跑、一次模型都不调用（默认）；shadow 调用但只记录；live 复核后真的执行
    web_brain_mode: str = "off"
    # 每只宠物每个 UTC 记账日最多几次自主决策（只收紧已有供应商上限，不扩大付费范围）
    web_brain_daily_per_pet: int = 12
    web_world_runner: str = "embedded"
    # 运行环境标签（只用于状态报告与日志，不改变任何行为）：dev / demo / real-local / staging / production
    web_environment: str = "dev"
    # SQLite WAL（API 与独立任务进程同时读写时建议开启；会在数据库旁生成 -wal / -shm 文件，备份时一起带上）
    sqlite_wal: bool = False
    # 演示线路（海边咖啡馆 / 坐船去澳门 / 飞去东京的演示版与“示例”地点）：只在演示环境打开；正式与真实联调环境关闭
    web_demo_catalog: bool = False


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
        image_provider_type=os.getenv("PETJOURNEY_IMAGE_PROVIDER", "openai").strip().lower(),
        volcengine_image_model=os.getenv("PETJOURNEY_VOLCENGINE_IMAGE_MODEL", "doubao-seedream-4-0-250828"),
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
        legacy_api_policy=os.getenv("PETJOURNEY_LEGACY_API_POLICY", "open").strip().lower(),
        web_cookie_secure=os.getenv("PETJOURNEY_WEB_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"},
        web_session_ttl_seconds=int(os.getenv("PETJOURNEY_WEB_SESSION_TTL_SECONDS", str(30 * 24 * 3600))),
        web_private_media_dir=Path(os.getenv("PETJOURNEY_WEB_PRIVATE_MEDIA_DIR", str(BASE_DIR / "data" / "web-private-media"))),
        intent_layer_mode=os.getenv("PETJOURNEY_INTENT_LAYER_MODE", "off").strip().lower(),
        intent_layer_provider=os.getenv("PETJOURNEY_INTENT_LAYER_PROVIDER", "rule").strip().lower(),
        web_providers_enabled=os.getenv("PETJOURNEY_WEB_PROVIDERS", "").lower() in {"1", "true", "yes", "on"},
        web_llm_daily_cap=int(os.getenv("PETJOURNEY_WEB_LLM_DAILY_CAP", "300")),
        web_image_daily_cap=int(os.getenv("PETJOURNEY_WEB_IMAGE_DAILY_CAP", "20")),
        web_image_per_pet_daily_cap=int(os.getenv("PETJOURNEY_WEB_IMAGE_PER_PET_DAILY_CAP", "6")),
        web_map_daily_cap=int(os.getenv("PETJOURNEY_WEB_MAP_DAILY_CAP", "500")),
        web_map_static_daily_cap=int(os.getenv("PETJOURNEY_WEB_MAP_STATIC_DAILY_CAP", "200")),
        web_world_runner=os.getenv("PETJOURNEY_WEB_WORLD_RUNNER", "embedded").strip().lower(),
        web_environment=os.getenv("PETJOURNEY_WEB_ENVIRONMENT", "dev").strip().lower(),
        sqlite_wal=os.getenv("PETJOURNEY_SQLITE_WAL", "").lower() in {"1", "true", "yes", "on"},
        web_demo_catalog=os.getenv("PETJOURNEY_WEB_DEMO_CATALOG", "").lower() in {"1", "true", "yes", "on"},
        web_world_tick_seconds=float(os.getenv("PETJOURNEY_WEB_WORLD_TICK_SECONDS", "30")),
        web_image_model=os.getenv("PETJOURNEY_WEB_IMAGE_MODEL", "doubao-seedream-4-5-251128"),
        web_llm_timeout_seconds=float(os.getenv("PETJOURNEY_WEB_LLM_TIMEOUT_SECONDS", "15")),
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
