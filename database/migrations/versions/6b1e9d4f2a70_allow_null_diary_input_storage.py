"""allow diary inputs without persisted media URLs

Revision ID: 6b1e9d4f2a70
Revises: 4d8f3b2a1c90
Create Date: 2026-08-11

Photo and audio originals are intentionally transient until final avatar video
storage is connected. Text inputs never have a storage URL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b1e9d4f2a70"
down_revision: Union[str, Sequence[str], None] = "4d8f3b2a1c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "diary_inputs",
        "storage_url",
        existing_type=sa.String(length=512),
        nullable=True,
    )


def downgrade() -> None:
    # Text and transient media inputs legitimately contain NULL, so provide a
    # reversible placeholder before restoring the legacy NOT NULL constraint.
    op.execute(
        "UPDATE diary_inputs SET storage_url = '' WHERE storage_url IS NULL"
    )
    op.alter_column(
        "diary_inputs",
        "storage_url",
        existing_type=sa.String(length=512),
        nullable=False,
    )
