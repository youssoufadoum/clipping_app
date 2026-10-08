from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import Unauthorized
from app.core.security import hash_password, verify_access_token, verify_password
from tests.conftest import register


def test_register_login_and_me(client: TestClient) -> None:
    headers = register(client, "Creator@Example.com")
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "creator@example.com"
    assert me.json()["plan_code"] == "free"

    login = client.post(
        "/api/v1/auth/local/login",
        json={"email": "creator@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    bad = client.post(
        "/api/v1/auth/local/login",
        json={"email": "creator@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_duplicate_registration_rejected(client: TestClient) -> None:
    register(client, "dup@example.com")
    resp = client.post(
        "/api/v1/auth/local/register",
        json={"email": "dup@example.com", "password": "another-password"},
    )
    assert resp.status_code == 409


def test_short_password_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/local/register", json={"email": "x@example.com", "password": "short"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer not-a-jwt"])
def test_protected_routes_require_valid_token(client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    resp = client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_and_forged_tokens_rejected(client: TestClient) -> None:
    from app.core.config import get_settings

    secret = get_settings().secret_key
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": "virello-local-dev",
            "exp": int(time.time()) - 10,
        },
        secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"

    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iss": "virello-local-dev",
            "exp": int(time.time()) + 60,
        },
        "attacker-secret-attacker-secret-1234",
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    )


def test_session_verify(client: TestClient, auth: dict[str, str]) -> None:
    resp = client.post("/api/v1/auth/session/verify", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["provider"] == "local"


def test_supabase_hs256_verification() -> None:
    settings = Settings(
        auth_mode="supabase",
        supabase_url="https://proj.supabase.co",
        supabase_jwt_secret="super-secret-jwt-token-with-at-least-32-chars",
    )
    uid = uuid.uuid4()
    claims = {
        "sub": str(uid),
        "email": "A@B.io",
        "aud": "authenticated",
        "iss": "https://proj.supabase.co/auth/v1",
        "exp": int(time.time()) + 60,
    }
    token = jwt.encode(claims, settings.supabase_jwt_secret, algorithm="HS256")
    identity = verify_access_token(token, settings)
    assert identity.user_id == uid and identity.email == "a@b.io"

    wrong_aud = jwt.encode(
        {**claims, "aud": "anon"}, settings.supabase_jwt_secret, algorithm="HS256"
    )
    with pytest.raises(Unauthorized):
        verify_access_token(wrong_aud, settings)
    wrong_iss = jwt.encode(
        {**claims, "iss": "https://evil.example/auth/v1"},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(Unauthorized):
        verify_access_token(wrong_iss, settings)
    none_alg = jwt.encode(claims, None, algorithm="none")
    with pytest.raises(Unauthorized):
        verify_access_token(none_alg, settings)


def test_local_auth_forbidden_in_production() -> None:
    with pytest.raises(ValueError):
        Settings(app_env="production", auth_mode="local", api_secret_key="x" * 40)
    with pytest.raises(ValueError):
        Settings(app_env="production", auth_mode="supabase", api_secret_key="short")


def test_local_auth_endpoints_disabled_in_supabase_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "auth_mode", "supabase")
    resp = client.post(
        "/api/v1/auth/local/login", json={"email": "a@example.com", "password": "whatever-123"}
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "LOCAL_AUTH_DISABLED"


def test_password_hashing() -> None:
    stored = hash_password("s3cret-password")
    assert stored.startswith("scrypt$") and "s3cret" not in stored
    assert verify_password("s3cret-password", stored)
    assert not verify_password("other", stored)
    assert not verify_password("x", "garbage")


def test_login_rate_limited(client: TestClient) -> None:
    for _ in range(20):
        client.post(
            "/api/v1/auth/local/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        )
    resp = client.post(
        "/api/v1/auth/local/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


def test_admin_flag_from_server_config(client: TestClient) -> None:
    headers = register(client, "admin@example.com")
    assert client.get("/api/v1/me", headers=headers).json()["is_admin"] is True
    # Clients cannot grant themselves admin.
    resp = client.patch(
        "/api/v1/me", json={"is_admin": False, "display_name": "Ada"}, headers=register(client)
    )
    assert resp.status_code == 200 and resp.json()["is_admin"] is False
