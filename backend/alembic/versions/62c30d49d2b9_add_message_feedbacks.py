"""add message feedbacks

Revision ID: 62c30d49d2b9
Revises: f3a9c1d2e4b5
Create Date: 2026-04-04 17:43:52.256950

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62c30d49d2b9'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1d2e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "message_feedbacks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "vote",
            sa.String(length=16),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "vote IN ('like', 'dislike', 'none')",
            name="ck_message_feedback_vote",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["agent_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "message_id",
            name="uq_message_feedback_user_msg",
        ),
    )
    op.create_index(
        op.f("ix_message_feedbacks_message_id"),
        "message_feedbacks",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_user_id"),
        "message_feedbacks",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_message_feedbacks_user_id"), table_name="message_feedbacks")
    op.drop_index(
        op.f("ix_message_feedbacks_message_id"),
        table_name="message_feedbacks",
    )
    op.drop_table("message_feedbacks")
