"""split diary content and narration

Revision ID: c7f4a2b19d6e
Revises: 9a77b00fc3d1
Create Date: 2026-08-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7f4a2b19d6e"
down_revision: Union[str, Sequence[str], None] = "9a77b00fc3d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Keep the diary text formerly stored in script and add narration output."""
    op.drop_column("diary_versions", "content")
    op.alter_column(
        "diary_versions",
        "script",
        new_column_name="content",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    op.create_table(
        "narration_scripts",
        sa.Column("script_id", sa.String(length=50), nullable=False),
        sa.Column("diary_version_id", sa.String(length=50), nullable=False),
        sa.Column("narration_text", sa.Text(), nullable=True),
        sa.Column("emotion", sa.String(length=20), nullable=True),
        sa.Column(
            "tone",
            sa.String(length=50),
            server_default="따뜻한 회상",
            nullable=False,
        ),
        sa.Column(
            "target_duration_seconds",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("llm_model", sa.String(length=50), nullable=True),
        sa.Column("voice_id", sa.String(length=50), nullable=True),
        sa.Column("audio_url", sa.String(length=512), nullable=True),
        sa.Column("audio_hash", sa.String(length=64), nullable=True),
        sa.Column("audio_size", sa.Integer(), nullable=True),
        sa.Column("audio_mime_type", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["diary_version_id"],
            ["diary_versions.version_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("script_id"),
        sa.UniqueConstraint("diary_version_id"),
    )
    op.create_index(
        "ix_narration_scripts_version_status_created",
        "narration_scripts",
        ["diary_version_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the prior duplicate diary columns."""
    op.drop_index(
        "ix_narration_scripts_version_status_created",
        table_name="narration_scripts",
    )
    op.drop_table("narration_scripts")

    op.alter_column(
        "diary_versions",
        "content",
        new_column_name="script",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.add_column("diary_versions", sa.Column("content", sa.Text(), nullable=True))
    op.execute("UPDATE diary_versions SET content = script")
