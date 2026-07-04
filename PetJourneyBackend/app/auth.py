from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .config import Settings

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
SESSION_TOKEN_ISSUER = "petsoul-backend"
SESSION_TOKEN_TTL_SECONDS = 180 * 24 * 3600
MOCK_TOKEN_PREFIX = "mock-apple-sub:"


class AuthError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AppleIdentity:
    apple_sub: str
    email: str | None


class AuthService:
    """Sign in with Apple 验证 + 自有会话 JWT 签发。

    apple_auth_mode == "mock" 时接受 "mock-apple-sub:<sub>" 形式的令牌，
    供单测与本地 Mock 联调使用，线上必须保持 live。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._jwk_client: PyJWKClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.auth_secret)

    @property
    def bundle_id(self) -> str:
        return (
            self.settings.apple_bundle_id
            or self.settings.apns_bundle_id
            or "com.petsoul.petjourney"
        )

    def verify_apple_identity_token(self, identity_token: str) -> AppleIdentity:
        token = (identity_token or "").strip()
        if not token:
            raise AuthError("identity token is empty")

        if self.settings.apple_auth_mode == "mock":
            if token.startswith(MOCK_TOKEN_PREFIX):
                sub = token[len(MOCK_TOKEN_PREFIX):].strip()
                if sub:
                    return AppleIdentity(apple_sub=sub, email=f"{sub}@mock.local")
            raise AuthError("invalid mock identity token")

        try:
            if self._jwk_client is None:
                self._jwk_client = PyJWKClient(APPLE_JWKS_URL, cache_keys=True)
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.bundle_id,
                issuer=APPLE_ISSUER,
            )
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError("apple identity token verification failed") from exc

        sub = payload.get("sub")
        if not sub:
            raise AuthError("apple identity token missing sub")
        return AppleIdentity(apple_sub=str(sub), email=payload.get("email"))

    def issue_session_token(self, user_id: str) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "sub": user_id,
                "iss": SESSION_TOKEN_ISSUER,
                "iat": now,
                "exp": now + SESSION_TOKEN_TTL_SECONDS,
            },
            self._secret(),
            algorithm="HS256",
        )

    def decode_session_token(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._secret(),
                algorithms=["HS256"],
                issuer=SESSION_TOKEN_ISSUER,
            )
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError("invalid session token") from exc
        sub = payload.get("sub")
        if not sub:
            raise AuthError("session token missing sub")
        return str(sub)

    def _secret(self) -> str:
        if not self.settings.auth_secret:
            raise AuthError("auth secret is not configured")
        return self.settings.auth_secret


def build_auth_service(settings: Settings) -> AuthService:
    return AuthService(settings)
