"""员工二次验证（RFC 6238 TOTP，SHA-1 / 6 位 / 30 秒）。只用标准库，不引入新依赖。

密钥只在两处出现：入册时返回给本人一次，以及库里的 `admin_staff.mfa_secret`。审计与日志都不记它。
校验允许前后各一个时间窗（±30 秒），用于时钟漂移；不做更宽的容忍。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
WINDOW = 1  # 前后各允许一个 30 秒窗口


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code_at(secret: str, counter: int) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def code_now(secret: str, now: float | None = None) -> str:
    return _code_at(secret, int((now if now is not None else time.time()) // PERIOD))


def verify(secret: str, code: str, now: float | None = None) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not secret or len(code) != DIGITS or not code.isdigit():
        return False
    counter = int((now if now is not None else time.time()) // PERIOD)
    return any(hmac.compare_digest(_code_at(secret, counter + drift), code) for drift in range(-WINDOW, WINDOW + 1))


def provisioning_uri(secret: str, username: str, issuer: str = "PetSoul Admin") -> str:
    label = quote(f"{issuer}:{username}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}&digits={DIGITS}&period={PERIOD}"
