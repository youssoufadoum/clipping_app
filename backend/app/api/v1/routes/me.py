from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models import AuditEvent, LocalAuthUser, Profile, Project, Workspace
from app.schemas import AccountDeletion, ProfileOut, ProfileUpdate
from app.services.storage import get_storage, project_prefix

router = APIRouter(prefix="/me", tags=["account"])
log = logging.getLogger(__name__)


@router.get("", response_model=ProfileOut)
def get_me(user: Profile = Depends(current_user)) -> Profile:
    return user


@router.patch("", response_model=ProfileOut)
def update_me(
    body: ProfileUpdate, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> Profile:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: AccountDeletion, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    """Permanently delete the account, its projects, and all stored media."""
    settings = get_settings()
    storage = get_storage()
    projects = list(db.scalars(select(Project).where(Project.owner_id == user.id)))
    for project in projects:
        try:
            storage.delete_prefix(project_prefix(user.id, project.id))
        except Exception:  # noqa: BLE001
            log.exception("failed to delete project media", extra={"project_id": project.id})
            raise AppError(
                "Your media could not be deleted right now. Please try again.",
                code="DELETION_FAILED",
                status_code=503,
                retryable=True,
            ) from None

    if (
        settings.auth_mode == "supabase"
        and settings.supabase_url
        and settings.supabase_service_role_key
    ):
        key = settings.supabase_service_role_key
        headers = {"apikey": key}
        if not key.startswith("sb_"):
            # Legacy service_role JWTs also go in Authorization; new sb_secret_ keys must not.
            headers["Authorization"] = f"Bearer {key}"
        resp = httpx.delete(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user.id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code not in (200, 204, 404):
            log.error("supabase user deletion failed status=%s", resp.status_code)
            raise AppError(
                "Your sign-in account could not be deleted. Please contact support.",
                code="DELETION_FAILED",
                status_code=502,
            )
    db.add(
        AuditEvent(
            actor_id=None,
            action="account.deleted",
            target_type="profile",
            target_id=str(user.id),
            metadata_={"projects": len(projects)},
        )
    )
    db.execute(delete(Workspace).where(Workspace.owner_id == user.id))
    db.execute(delete(LocalAuthUser).where(LocalAuthUser.id == user.id))
    db.delete(user)
    db.commit()
