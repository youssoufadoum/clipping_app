"""Operator commands.

python -m app.cli set-plan <email> <plan>      # until Stripe billing ships
python -m app.cli recover-jobs                 # one-off stale job recovery sweep
python -m app.cli cleanup-work-dir [--hours N]  # remove old worker temp files
python -m app.cli export-openapi <path>        # write the OpenAPI spec
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import func, select

from app.core.plans import PLANS
from app.db.session import get_sessionmaker
from app.models import AuditEvent, Profile


def set_plan(email: str, plan: str) -> int:
    if plan not in PLANS:
        print(f"Unknown plan {plan!r}. Choose from: {', '.join(PLANS)}", file=sys.stderr)
        return 2
    with get_sessionmaker()() as db:
        profile = db.scalar(select(Profile).where(func.lower(Profile.email) == email.lower()))
        if profile is None:
            print(f"No user with email {email}", file=sys.stderr)
            return 1
        previous = profile.plan_code
        profile.plan_code = plan
        db.add(
            AuditEvent(
                actor_id=None,
                action="plan.changed_by_operator",
                target_type="profile",
                target_id=str(profile.id),
                metadata_={"from": previous, "to": plan},
            )
        )
        db.commit()
    print(f"{email}: {previous} -> {plan}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("set-plan")
    p.add_argument("email")
    p.add_argument("plan")
    sub.add_parser("recover-jobs")
    c = sub.add_parser("cleanup-work-dir")
    c.add_argument("--hours", type=int, default=6)
    o = sub.add_parser("export-openapi")
    o.add_argument("path")
    args = parser.parse_args(argv)

    if args.cmd == "set-plan":
        return set_plan(args.email, args.plan)
    if args.cmd == "recover-jobs":
        from app.worker.tasks import recover_stale_jobs_once

        print(recover_stale_jobs_once())
        return 0
    if args.cmd == "cleanup-work-dir":
        from app.worker.tasks import cleanup_work_dir

        cleanup_work_dir(args.hours)
        return 0
    if args.cmd == "export-openapi":
        from app.main import app

        with open(args.path, "w") as fh:
            json.dump(app.openapi(), fh, indent=2)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
