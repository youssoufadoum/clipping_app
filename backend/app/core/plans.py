"""Server-side plan configuration.

Prices are deliberately absent: the price of a paid plan is whatever the
configured Stripe price says. Quotas live here so they are enforced by the
server regardless of what the client displays.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

GB = 1024 * 1024 * 1024


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    description: str
    monthly_source_minutes: int
    monthly_render_minutes: int
    max_upload_bytes: int
    max_video_duration_seconds: int
    max_projects: int
    watermark: bool
    priority_processing: bool
    team_workspace: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


PLANS: dict[str, Plan] = {
    "free": Plan(
        code="free",
        name="Free",
        description="Try the full workflow on short videos. Exports carry a small watermark.",
        monthly_source_minutes=60,
        monthly_render_minutes=30,
        max_upload_bytes=2 * GB,
        max_video_duration_seconds=30 * 60,
        max_projects=10,
        watermark=True,
        priority_processing=False,
        team_workspace=False,
    ),
    "creator": Plan(
        code="creator",
        name="Creator",
        description="For individual creators publishing every week.",
        monthly_source_minutes=600,
        monthly_render_minutes=300,
        max_upload_bytes=5 * GB,
        max_video_duration_seconds=2 * 60 * 60,
        max_projects=200,
        watermark=False,
        priority_processing=False,
        team_workspace=False,
    ),
    "pro": Plan(
        code="pro",
        name="Pro",
        description="Higher limits and priority processing for heavy publishers.",
        monthly_source_minutes=1800,
        monthly_render_minutes=900,
        max_upload_bytes=10 * GB,
        max_video_duration_seconds=4 * 60 * 60,
        max_projects=1000,
        watermark=False,
        priority_processing=True,
        team_workspace=False,
    ),
    "team": Plan(
        code="team",
        name="Team",
        description="Shared workspace and centralized billing for teams and agencies.",
        monthly_source_minutes=6000,
        monthly_render_minutes=3000,
        max_upload_bytes=10 * GB,
        max_video_duration_seconds=4 * 60 * 60,
        max_projects=5000,
        watermark=False,
        priority_processing=True,
        team_workspace=True,
    ),
}


def get_plan(code: str | None) -> Plan:
    return PLANS.get(code or "free", PLANS["free"])
