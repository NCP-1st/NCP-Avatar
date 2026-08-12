"""add avatar video object metadata

Revision ID: a2b3c4d5e6f7
Revises: f1a2c3d4e5f6
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_avatar_videos_version",
        "avatar_videos",
        ["version_id"],
    )
    op.add_column("avatar_videos", sa.Column("object_key", sa.String(512), nullable=True))
    op.add_column("avatar_videos", sa.Column("video_hash", sa.String(64), nullable=True))
    op.add_column("avatar_videos", sa.Column("video_size", sa.Integer(), nullable=True))
    op.add_column(
        "avatar_videos",
        sa.Column("video_mime_type", sa.String(100), nullable=True),
    )
    op.add_column("avatar_videos", sa.Column("error_code", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_constraint(
        "uq_avatar_videos_version",
        "avatar_videos",
        type_="unique",
    )
    op.drop_column("avatar_videos", "error_code")
    op.drop_column("avatar_videos", "video_mime_type")
    op.drop_column("avatar_videos", "video_size")
    op.drop_column("avatar_videos", "video_hash")
    op.drop_column("avatar_videos", "object_key")
