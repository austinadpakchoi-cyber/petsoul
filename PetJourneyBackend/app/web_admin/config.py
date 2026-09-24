"""管理后台自己的配置段（只读环境变量）。

为什么不放进 `app/config.py`：那份配置正由别的窗口修改，本窗口不改它。管理端的设置项前缀统一
`PETSOUL_ADMIN_*`，与玩家端的 `PETJOURNEY_*` 分开，避免把玩家配置误当成员工配置。
凭据一律不在这里出现——员工口令只有哈希进库，供应商密钥后台永远读不到。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

LIVE_ENVIRONMENTS = ("staging", "production")


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class AdminSettings:
    session_ttl_seconds: int
    cookie_secure: bool
    require_mfa: bool
    login_max_failures: int
    login_window_seconds: int
    allowed_origins: tuple[str, ...]

    @property
    def cookie_name(self) -> str:
        # host-only cookie，名字与玩家端不同：员工会话不会被带到玩家站点，玩家会话也进不来后台。
        return "petsoul_admin_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "petsoul_admin_csrf"


def load_admin_settings(web_environment: str, cookie_secure_default: bool) -> AdminSettings:
    live = (web_environment or "dev").strip().lower() in LIVE_ENVIRONMENTS
    origins = tuple(o.strip() for o in os.getenv("PETSOUL_ADMIN_ORIGINS", "http://127.0.0.1:5299,http://127.0.0.1:4299").split(",") if o.strip())
    return AdminSettings(
        session_ttl_seconds=int(os.getenv("PETSOUL_ADMIN_SESSION_TTL_SECONDS", str(8 * 3600))),
        cookie_secure=_flag("PETSOUL_ADMIN_COOKIE_SECURE", cookie_secure_default),
        # 公网正式环境默认要求 MFA；本地开发默认不要求，但仍可显式打开来验证这条路径。
        require_mfa=_flag("PETSOUL_ADMIN_REQUIRE_MFA", live),
        login_max_failures=int(os.getenv("PETSOUL_ADMIN_LOGIN_MAX_FAILURES", "6")),
        login_window_seconds=int(os.getenv("PETSOUL_ADMIN_LOGIN_WINDOW_SECONDS", "300")),
        allowed_origins=origins,
    )
