"""add diary embeddings

Revision ID: d4e5f6a7b8c9
Revises: c9d0e1f2a3b4
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diary_embeddings",
        sa.Column("version_id", sa.String(length=50), nullable=False),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], ["diary_versions.version_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("version_id"),
    )


def downgrade() -> None:
    op.drop_table("diary_embeddings")
