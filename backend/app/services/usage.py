"""Usage ledger and quota enforcement.

Policy (also shown to users):
* Source minutes are charged once per project when its video is successfully
  inspected. Failed or rejected uploads are not charged.
* Render minutes are charged once per successful render, by output duration.
  Failed and cancelled renders are not charged.
* Queued and running renders count as reserved against the remaining allowance
  so a burst of requests cannot exceed the plan.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.plans import Plan, get_plan
from app.models import Clip, JobStatus, JobType, ProcessingJob, Profile, Project, UsageLedger

SOURCE_MINUTES = "source_minutes"
RENDER_MINUTES = "render_minutes"
AI_MINUTES = "ai_minutes"


def period_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def minutes(seconds: float) -> float:
    """Usage is metered in tenths of a minute, rounded up."""
    return math.ceil(seconds / 6) / 10


def used(db: Session, user_id: uuid.UUID, unit: str) -> float:
    start, end = period_bounds()
    total = db.scalar(
        select(func.coalesce(func.sum(UsageLedger.quantity), 0.0)).where(
            UsageLedger.user_id == user_id,
            UsageLedger.unit == unit,
            UsageLedger.created_at >= start,
            UsageLedger.created_at < end,
        )
    )
    return float(total or 0.0)


def reserved_render_minutes(db: Session, user_id: uuid.UUID) -> float:
    rows = db.execute(
        select(Clip.duration_seconds)
        .join(ProcessingJob, ProcessingJob.clip_id == Clip.id)
        .join(Project, Project.id == Clip.project_id)
        .where(
            Project.owner_id == user_id,
            ProcessingJob.job_type == JobType.render_clip,
            ProcessingJob.status.in_((JobStatus.queued, JobStatus.running)),
        )
    ).all()
    return sum(minutes(r[0]) for r in rows)


@dataclass
class UsageSummary:
    plan: Plan
    period_start: datetime
    period_end: datetime
    source_minutes_used: float
    render_minutes_used: float
    render_minutes_reserved: float
    ai_minutes_used: float = 0.0

    @property
    def source_minutes_remaining(self) -> float:
        return max(0.0, self.plan.monthly_source_minutes - self.source_minutes_used)

    @property
    def ai_minutes_remaining(self) -> float:
        return max(0.0, self.plan.monthly_ai_minutes - self.ai_minutes_used)

    @property
    def render_minutes_remaining(self) -> float:
        return max(
            0.0,
            self.plan.monthly_render_minutes
            - self.render_minutes_used
            - self.render_minutes_reserved,
        )


def summary(db: Session, user: Profile) -> UsageSummary:
    start, end = period_bounds()
    return UsageSummary(
        plan=get_plan(user.plan_code),
        period_start=start,
        period_end=end,
        source_minutes_used=used(db, user.id, SOURCE_MINUTES),
        render_minutes_used=used(db, user.id, RENDER_MINUTES),
        render_minutes_reserved=reserved_render_minutes(db, user.id),
        ai_minutes_used=used(db, user.id, AI_MINUTES),
    )


def charge_once(
    db: Session,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    event_type: str,
    quantity: float,
    unit: str,
    idempotency_key: str,
    project_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    metadata: dict[str, object] | None = None,
) -> bool:
    """Insert a ledger row exactly once per idempotency key. Returns True if inserted."""
    result = db.execute(
        insert(UsageLedger)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            workspace_id=workspace_id,
            event_type=event_type,
            quantity=quantity,
            unit=unit,
            idempotency_key=idempotency_key,
            project_id=project_id,
            job_id=job_id,
            metadata=metadata or {},
        )
        .on_conflict_do_nothing(index_elements=[UsageLedger.idempotency_key])
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
