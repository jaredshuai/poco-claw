"""add user_accounts for profile and credits

Revision ID: f3a9c1d2e4b5
Revises: e1f2a3b4c5d6
Create Date: 2026-04-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a9c1d2e4b5"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=512), nullable=False),
        sa.Column("avatar_url", sa.String(length=2048), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("plan_name_key", sa.String(length=128), nullable=False),
        sa.Column("credits_total", sa.String(length=64), nullable=False),
        sa.Column("credits_free", sa.String(length=64), nullable=False),
        sa.Column("daily_refresh_current", sa.Integer(), nullable=False),
        sa.Column("daily_refresh_max", sa.Integer(), nullable=False),
        sa.Column("refresh_time", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_accounts")
