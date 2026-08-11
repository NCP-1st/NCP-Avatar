"""drop diary chats and retain only user inputs

Revision ID: 4d8f3b2a1c90
Revises: c7f4a2b19d6e
Create Date: 2026-08-11

Existing diary chat rows are intentionally removed. User text submitted after
this migration is stored as diary_inputs(type='text').
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d8f3b2a1c90"
down_revision: Union[str, Sequence[str], None] = "c7f4a2b19d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("diary_chats")


def downgrade() -> None:
    op.create_table(
        "diary_chats",
        sa.Column("chat_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("chat", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["diary_sessions.session_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chat_id"),
    )
