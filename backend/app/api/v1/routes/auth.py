from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import _bearer, rate_limit
from app.core.config import get_settings
from app.core.errors import Conflict, ServiceUnavailable, Unauthorized
from app.core.security import (
    LOCAL_TOKEN_TTL_SECONDS,
    hash_password,
    issue_local_token,
    verify_access_token,
    verify_password,
)
from app.db.session import get_db
from app.models import LocalAuthUser
from app.schemas import LocalCredentials, SessionInfo, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session/verify", response_model=SessionInfo)
def verify_session(request: Request) -> SessionInfo:
    """Verify the bearer token and return the identity it represents."""
    identity = verify_access_token(_bearer(request))
    return SessionInfo(user_id=identity.user_id, email=identity.email, provider=identity.provider)


def _require_local_mode() -> None:
    settings = get_settings()
    if settings.auth_mode != "local" or settings.is_production:
        raise ServiceUnavailable(
            "Local development sign-in is disabled. Use the configured auth provider.",
            code="LOCAL_AUTH_DISABLED",
        )


@router.post(
    "/local/register",
    response_model=TokenResponse,
    dependencies=[
        Depends(_require_local_mode),
        Depends(rate_limit("local-register", 10, 3600, per="ip")),
    ],
    summary="Development-only email/password registration (AUTH_MODE=local)",
)
def local_register(body: LocalCredentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower()
    user = LocalAuthUser(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("An account with this email already exists.", code="EMAIL_TAKEN") from None
    token = issue_local_token(user.id, email, get_settings())
    return TokenResponse(
        access_token=token, expires_in=LOCAL_TOKEN_TTL_SECONDS, user_id=user.id, email=email
    )


@router.post(
    "/local/login",
    response_model=TokenResponse,
    dependencies=[
        Depends(_require_local_mode),
        Depends(rate_limit("local-login", 20, 900, per="ip")),
    ],
    summary="Development-only email/password sign-in (AUTH_MODE=local)",
)
def local_login(body: LocalCredentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower()
    user = db.scalar(select(LocalAuthUser).where(LocalAuthUser.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Incorrect email or password.", code="INVALID_CREDENTIALS")
    token = issue_local_token(user.id, email, get_settings())
    return TokenResponse(
        access_token=token, expires_in=LOCAL_TOKEN_TTL_SECONDS, user_id=user.id, email=email
    )
