from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.core.plans import PLANS, Plan
from app.db.session import get_db
from app.models import Profile, UsageLedger
from app.schemas import Page, PlanOut, UsageEventOut, UsageOut
from app.services import usage

router = APIRouter(tags=["usage & billing"])

USAGE_POLICY = [
    "Source minutes are counted once per project when its video is processed successfully.",
    "Render minutes are counted per successful export, based on the exported clip's length.",
    "Failed, cancelled and rejected jobs are never charged.",
    "Renders that are queued or in progress are reserved against your remaining minutes.",
    "Usage is metered in tenths of a minute, rounded up, and resets on the 1st of each month "
    "(UTC).",
]


def _checkout_available(plan: Plan) -> bool:
    return False  # Stripe checkout is implemented in phase 3.


def plan_out(plan: Plan) -> PlanOut:
    return PlanOut(**plan.to_dict(), checkout_available=_checkout_available(plan))


@router.get("/usage", response_model=UsageOut)
def get_usage(user: Profile = Depends(current_user), db: Session = Depends(get_db)) -> UsageOut:
    s = usage.summary(db, user)
    return UsageOut(
        plan=plan_out(s.plan),
        period_start=s.period_start,
        period_end=s.period_end,
        source_minutes_used=s.source_minutes_used,
        source_minutes_limit=s.plan.monthly_source_minutes,
        source_minutes_remaining=s.source_minutes_remaining,
        render_minutes_used=s.render_minutes_used,
        render_minutes_reserved=s.render_minutes_reserved,
        render_minutes_limit=s.plan.monthly_render_minutes,
        render_minutes_remaining=s.render_minutes_remaining,
        policy=USAGE_POLICY,
    )


@router.get("/usage/history", response_model=Page[UsageEventOut])
def usage_history(
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Page[UsageEventOut]:
    stmt = select(UsageLedger).where(UsageLedger.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(UsageLedger.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[UsageEventOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/billing/plans", response_model=list[PlanOut])
def list_plans() -> list[PlanOut]:
    return [plan_out(p) for p in PLANS.values()]


def _billing_unavailable() -> None:
    configured = bool(get_settings().stripe_secret_key)
    raise ServiceUnavailable(
        "Online billing is not available yet."
        + ("" if configured else " Stripe is not configured on this server."),
        code="BILLING_UNAVAILABLE",
    )


@router.post("/billing/checkout", responses={503: {"description": "Billing not available"}})
def checkout(user: Profile = Depends(current_user)) -> None:
    _billing_unavailable()


@router.post("/billing/portal", responses={503: {"description": "Billing not available"}})
def portal(user: Profile = Depends(current_user)) -> None:
    _billing_unavailable()
