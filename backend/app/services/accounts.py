from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Identity
from app.models import Profile, Workspace, WorkspaceMember


def ensure_account(db: Session, identity: Identity) -> Profile:
    """Create the profile and personal workspace on first sight of a verified identity."""
    profile = db.get(Profile, identity.user_id)
    is_admin = bool(identity.email and identity.email in get_settings().admin_email_set)
    if profile is None:
        db.execute(
            insert(Profile)
            .values(id=identity.user_id, email=identity.email, is_admin=is_admin)
            .on_conflict_do_nothing(index_elements=[Profile.id])
        )
        db.flush()
        profile = db.get(Profile, identity.user_id)
        assert profile is not None
    else:
        changed = False
        if identity.email and profile.email != identity.email:
            profile.email = identity.email
            changed = True
        if profile.is_admin != is_admin:
            profile.is_admin = is_admin
            changed = True
        if not changed:
            personal = db.scalar(
                select(Workspace.id).where(
                    Workspace.owner_id == profile.id, Workspace.is_personal.is_(True)
                )
            )
            if personal is not None:
                return profile

    personal_ws = db.scalar(
        select(Workspace).where(Workspace.owner_id == profile.id, Workspace.is_personal.is_(True))
    )
    if personal_ws is None:
        personal_ws = Workspace(name="Personal", owner_id=profile.id, is_personal=True)
        db.add(personal_ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=personal_ws.id, user_id=profile.id, role="owner"))
    db.commit()
    return profile


def personal_workspace(db: Session, user_id: object) -> Workspace:
    ws = db.scalar(
        select(Workspace).where(Workspace.owner_id == user_id, Workspace.is_personal.is_(True))
    )
    assert ws is not None, "ensure_account must run first"
    return ws
