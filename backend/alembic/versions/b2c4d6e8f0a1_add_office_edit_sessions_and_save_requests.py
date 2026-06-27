"""add office edit sessions and save requests

Revision ID: b2c4d6e8f0a1
Revises: a7b8c9d0e1f2
Create Date: 2026-06-24 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "office_edit_sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("manifest_key", sa.Text(), nullable=True),
        sa.Column("document_key", sa.String(length=255), nullable=False),
        sa.Column("callback_token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "discarded",
            sa.Boolean(),
            server_default=sa.text("false"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "callback_token", name="uq_office_edit_sessions_callback_token"
        ),
    )
    op.create_index(
        op.f("ix_office_edit_sessions_callback_token"),
        "office_edit_sessions",
        ["callback_token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_office_edit_sessions_document_key"),
        "office_edit_sessions",
        ["document_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_office_edit_sessions_session_id"),
        "office_edit_sessions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_office_edit_sessions_user_id"),
        "office_edit_sessions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "office_save_requests",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("edit_session_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("document_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staged_object_key", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["edit_session_id"],
            ["office_edit_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_office_save_requests_edit_session_id"),
        "office_save_requests",
        ["edit_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_office_save_requests_session_id"),
        "office_save_requests",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_office_save_requests_status"),
        "office_save_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_office_save_requests_user_id"),
        "office_save_requests",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_office_save_requests_user_id"),
        table_name="office_save_requests",
    )
    op.drop_index(
        op.f("ix_office_save_requests_status"),
        table_name="office_save_requests",
    )
    op.drop_index(
        op.f("ix_office_save_requests_session_id"),
        table_name="office_save_requests",
    )
    op.drop_index(
        op.f("ix_office_save_requests_edit_session_id"),
        table_name="office_save_requests",
    )
    op.drop_table("office_save_requests")
    op.drop_index(
        op.f("ix_office_edit_sessions_user_id"),
        table_name="office_edit_sessions",
    )
    op.drop_index(
        op.f("ix_office_edit_sessions_session_id"),
        table_name="office_edit_sessions",
    )
    op.drop_index(
        op.f("ix_office_edit_sessions_document_key"),
        table_name="office_edit_sessions",
    )
    op.drop_index(
        op.f("ix_office_edit_sessions_callback_token"),
        table_name="office_edit_sessions",
    )
    op.drop_table("office_edit_sessions")
