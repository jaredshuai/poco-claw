"""add agent_run_lifecycle_events table

Revision ID: a7b8c9d0e1f2
Revises: 62c30d49d2b9
Create Date: 2026-05-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "62c30d49d2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_run_lifecycle_events",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_source", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("claimed_by", sa.String(128), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lifecycle_events_run_id",
        "agent_run_lifecycle_events",
        ["run_id"],
    )
    op.create_index(
        "ix_lifecycle_events_session_id",
        "agent_run_lifecycle_events",
        ["session_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_lifecycle_events_session_id", table_name="agent_run_lifecycle_events"
    )
    op.drop_index("ix_lifecycle_events_run_id", table_name="agent_run_lifecycle_events")
    op.drop_table("agent_run_lifecycle_events")
