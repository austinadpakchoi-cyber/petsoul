"""把后台的处置真正落到玩家侧：**只在组合根装饰**，不改任何别的模块的源码。

三个执行点，都是"包住既有入口再放行"，不复制第二套判断：

1. `guard_session_check`：包住 `app.state.web_session_revocation_check`
   （`session.resolve_principal` 每个请求都会问它）。账号被冻结 → 手上的 cookie 立刻失效。
2. `guard_authenticate`：包住 `web.identity.authenticate`。冻结账号连**新会话都签发不出来**——
   只靠第 1 点会留一个"登录返回 200、之后每个请求 401"的缝。
3. `guard_provider_meter`：包住 `web.providers.meter.allow`。`ai_calls=paused` 时新的付费调用
   直接被拒，等同"到了每日上限"：本地额度按 not_sent 退回、不发 HTTP、不产生新费用。
   **在途的调用不受影响**，已经记下的用量与 unknown 一条都不动。

为什么是装饰而不是改源文件：会话、身份、供应商计量分别属于别的窗口。装饰在组合根发生（`main.py` 允许
import 一切），语义是"平台处置"这一层的，而不是那些模块的内在逻辑。长期更干净的做法是在
`WebIdentityService` 上加一个显式的 `account_status_check` 回调——已作为跨窗口请求记在窗口日志里。
"""

from __future__ import annotations

import logging
from typing import Callable

from ..storage import JourneyStorage
from .switches import AI_CALLS, SwitchStore

logger = logging.getLogger("petsoul.admin.enforcement")


class FrozenAccounts:
    """`admin_account_flags` 的只读视图，带 1 秒进程内缓存（每个请求都要问一次）。"""

    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self._cache: dict[str, tuple[float, bool]] = {}

    def is_frozen(self, user_id: str) -> bool:
        import time
        now = time.monotonic()
        hit = self._cache.get(user_id)
        if hit is not None and now - hit[0] < 1.0:
            return hit[1]
        try:
            with self.storage.connect() as conn:
                row = conn.execute("SELECT status FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()
            frozen = bool(row and row["status"] == "frozen")
        except Exception:  # noqa: BLE001 - 迁移未应用/库忙：不因后台表读不到就把玩家挡在门外
            logger.warning("account flag lookup failed user=%s", user_id)
            frozen = False
        self._cache[user_id] = (now, frozen)
        return frozen

    def invalidate(self, user_id: str) -> None:
        self._cache.pop(user_id, None)


def guard_session_check(previous: Callable[[str, str], bool], frozen: FrozenAccounts) -> Callable[[str, str], bool]:
    def check(user_id: str, session_id: str) -> bool:
        if frozen.is_frozen(user_id):
            return False  # → resolve_principal 抛 SESSION_EXPIRED
        return previous(user_id, session_id)

    return check


def guard_authenticate(previous: Callable[..., str], frozen: FrozenAccounts):
    """冻结账号：口令正确也不签发会话。用 InvalidCredentials 表达，不告诉对方"你被冻结了"。"""
    from ..web_identity import InvalidCredentials

    def authenticate(username: str, password: str, client_key: str) -> str:
        user_id = previous(username, password, client_key)
        if frozen.is_frozen(user_id):
            raise InvalidCredentials()
        return user_id

    return authenticate


def guard_provider_meter(meter, switches: SwitchStore) -> None:
    """就地替换实例上的 allow：暂停期间一律返回 False（＝到了上限），调用方按既有的 not_sent 路径处理。"""
    if meter is None:
        return
    previous = meter.allow

    def allow(provider: str) -> bool:
        if switches.state_cached(AI_CALLS) == "paused":
            logger.info("provider call blocked by admin switch provider=%s", provider)
            return False
        return previous(provider)

    meter.allow = allow  # type: ignore[method-assign]
