from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.ratelimit import get_rate_limiter
from app.core.security import verify_access_token
from app.db.session import get_db
from app.models import Profile
from app.services.accounts import ensure_account


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized()
    return token.strip()


def current_user(request: Request, db: Session = Depends(get_db)) -> Profile:
    identity = verify_access_token(_bearer(request))
    user = ensure_account(db, identity)
    request.state.user_id = str(user.id)
    return user


def admin_user(user: Profile = Depends(current_user)) -> Profile:
    if not user.is_admin:
        raise Forbidden("Administrator access is required.")
    return user


def client_ip(request: Request) -> str:
    # Behind a trusted proxy, configure uvicorn --proxy-headers so client.host is correct.
    return request.client.host if request.client else "unknown"


def rate_limit(
    scope: str, limit: int, window_seconds: int, *, per: str = "user"
) -> Callable[..., None]:
    def _dep(request: Request) -> None:
        if per == "ip":
            ident = client_ip(request)
        else:
            ident = getattr(request.state, "user_id", None) or client_ip(request)
        get_rate_limiter().hit(f"{scope}:{ident}", limit, window_seconds)

    return _dep
