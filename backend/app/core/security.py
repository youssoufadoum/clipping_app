"""Identity verification.

The browser authenticates with the auth provider and sends the resulting
access token as ``Authorization: Bearer <jwt>``. The backend verifies the
token's signature, expiry, audience and issuer on every protected request; a
user id supplied in a request body or query string is never trusted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt

from app.core.config import Settings, get_settings
from app.core.errors import Unauthorized

LOCAL_ISSUER = "virello-local-dev"
LOCAL_TOKEN_TTL_SECONDS = 60 * 60 * 12


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    email: str | None
    provider: str


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)


def _supabase_issuer(settings: Settings) -> str | None:
    if not settings.supabase_url:
        return None
    return settings.supabase_url.rstrip("/") + "/auth/v1"


def verify_supabase_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid access token.") from exc

    alg = header.get("alg")
    options: Any = {"require": ["exp", "sub"]}
    issuer = _supabase_issuer(settings)
    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise Unauthorized("Token algorithm is not accepted by this server.")
            key: Any = settings.supabase_jwt_secret
        elif alg in ("RS256", "ES256", "EdDSA"):
            jwks_url = settings.supabase_jwt_jwks_url or (
                f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
                if settings.supabase_url
                else ""
            )
            if not jwks_url:
                raise Unauthorized("Authentication is not configured on this server.")
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        else:
            raise Unauthorized("Token algorithm is not accepted by this server.")
        return jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized(
            "Your session has expired. Please sign in again.", code="TOKEN_EXPIRED"
        ) from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid access token.") from exc


def issue_local_token(user_id: uuid.UUID, email: str, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": LOCAL_ISSUER,
        "iat": now,
        "exp": now + LOCAL_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def verify_local_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience="authenticated",
            issuer=LOCAL_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized(
            "Your session has expired. Please sign in again.", code="TOKEN_EXPIRED"
        ) from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid access token.") from exc


def verify_access_token(token: str, settings: Settings | None = None) -> Identity:
    settings = settings or get_settings()
    if settings.auth_mode == "local":
        claims = verify_local_token(token, settings)
        provider = "local"
    else:
        claims = verify_supabase_token(token, settings)
        provider = "supabase"
    if provider == "supabase" and settings.require_email_verified:
        meta = claims.get("user_metadata") or {}
        if meta.get("email_verified") is False:
            raise Unauthorized(
                "Please verify your email address to continue.", code="EMAIL_NOT_VERIFIED"
            )
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Invalid access token.") from exc
    email = claims.get("email")
    return Identity(user_id=user_id, email=email.lower() if email else None, provider=provider)


# --- Password hashing for the local provider (stdlib scrypt) ---------------

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    actual = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return hmac.compare_digest(actual, expected)
