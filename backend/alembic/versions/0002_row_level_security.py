"""Row Level Security.

RLS is enabled on every table so that, on Supabase, the ``anon`` and
``authenticated`` roles (used by PostgREST / supabase-js) can never read data
that does not belong to the signed-in user. All writes go through the API,
which connects as the table owner and enforces ownership in code; client
roles receive read-only policies scoped by ``auth.uid()``.

Policies referencing ``auth.uid()`` are only created when the ``auth`` schema
exists (i.e. on Supabase). On plain PostgreSQL, RLS stays enabled with no
policies, which denies access to every non-owner role.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "profiles",
    "local_auth_users",
    "workspaces",
    "workspace_members",
    "projects",
    "processing_jobs",
    "transcripts",
    "clips",
    "caption_segments",
    "media_assets",
    "usage_ledger",
    "subscriptions",
    "brand_templates",
    "social_accounts",
    "scheduled_posts",
    "webhook_events",
    "audit_events",
]

MEMBER_WS = "(SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid())"
MEMBER_PROJECTS = f"(SELECT id FROM projects WHERE workspace_id IN {MEMBER_WS})"

POLICIES = {
    "profiles": "id = auth.uid()",
    "workspace_members": "user_id = auth.uid()",
    "workspaces": f"id IN {MEMBER_WS}",
    "projects": f"workspace_id IN {MEMBER_WS}",
    "processing_jobs": f"project_id IN {MEMBER_PROJECTS}",
    "transcripts": f"project_id IN {MEMBER_PROJECTS}",
    "clips": f"project_id IN {MEMBER_PROJECTS}",
    "media_assets": f"project_id IN {MEMBER_PROJECTS}",
    "caption_segments": f"clip_id IN (SELECT id FROM clips WHERE project_id IN {MEMBER_PROJECTS})",
    "usage_ledger": "user_id = auth.uid()",
    "subscriptions": "user_id = auth.uid()",
    "brand_templates": f"workspace_id IN {MEMBER_WS}",
    "scheduled_posts": f"clip_id IN (SELECT id FROM clips WHERE project_id IN {MEMBER_PROJECTS})",
    # social_accounts, webhook_events, audit_events, local_auth_users: no client access.
}


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    statements = "\n".join(
        f"EXECUTE 'CREATE POLICY {table}_select_own ON {table} FOR SELECT TO authenticated "
        f"USING ({expr.replace(chr(39), chr(39) * 2)})';"
        for table, expr in POLICIES.items()
    )
    op.execute(f"""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth')
         AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        {statements}
      END IF;
    END $$;
    """)


def downgrade() -> None:
    for table in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON {table}")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
