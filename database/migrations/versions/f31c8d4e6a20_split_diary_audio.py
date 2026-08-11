"""split diary audio from narration scripts

Revision ID: f31c8d4e6a20
Revises: c7f4a2b19d6e
Create Date: 2026-08-11

"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "f31c8d4e6a20"
down_revision: Union[str, Sequence[str], None] = "c7f4a2b19d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIO_COLUMNS = {
    "voice_id",
    "audio_url",
    "audio_hash",
    "audio_size",
    "audio_mime_type",
}


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    """Create diary_audios and reconcile a schema already changed in pgAdmin."""
    if context.is_offline_mode():
        op.create_table(
            "diary_audios",
            sa.Column("audio_id", sa.String(length=50), nullable=False),
            sa.Column("script_id", sa.String(length=50), nullable=False),
            sa.Column("voice_id", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=True),
            sa.Column("audio_url", sa.String(length=512), nullable=True),
            sa.Column("audio_hash", sa.String(length=64), nullable=True),
            sa.Column("audio_size", sa.Integer(), nullable=True),
            sa.Column("audio_mime_type", sa.String(length=100), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["script_id"], ["narration_scripts.script_id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("audio_id"),
        )
        op.create_index(
            "ix_diary_audios_script_status_created",
            "diary_audios",
            ["script_id", "status", "created_at"],
            unique=False,
        )
        op.execute(
            """
            INSERT INTO diary_audios (
                audio_id, script_id, voice_id, status, audio_url,
                audio_hash, audio_size, audio_mime_type, created_at, updated_at
            )
            SELECT
                'audio_' || SUBSTRING(MD5(script_id) FROM 1 FOR 24),
                script_id, voice_id,
                CASE WHEN audio_url IS NOT NULL THEN 'completed' ELSE 'pending' END,
                audio_url, audio_hash, audio_size, audio_mime_type,
                created_at, updated_at
            FROM narration_scripts
            WHERE voice_id IS NOT NULL
               OR audio_url IS NOT NULL
               OR audio_hash IS NOT NULL
               OR audio_size IS NOT NULL
               OR audio_mime_type IS NOT NULL
            ON CONFLICT (audio_id) DO NOTHING
            """
        )
        for column_name in sorted(_AUDIO_COLUMNS):
            op.drop_column("narration_scripts", column_name)
        return

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "diary_audios" not in tables:
        op.create_table(
            "diary_audios",
            sa.Column("audio_id", sa.String(length=50), nullable=False),
            sa.Column("script_id", sa.String(length=50), nullable=False),
            sa.Column("voice_id", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=True),
            sa.Column("audio_url", sa.String(length=512), nullable=True),
            sa.Column("audio_hash", sa.String(length=64), nullable=True),
            sa.Column("audio_size", sa.Integer(), nullable=True),
            sa.Column("audio_mime_type", sa.String(length=100), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["script_id"],
                ["narration_scripts.script_id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("audio_id"),
        )
        op.create_index(
            "ix_diary_audios_script_status_created",
            "diary_audios",
            ["script_id", "status", "created_at"],
            unique=False,
        )

    narration_columns = _columns("narration_scripts")
    if _AUDIO_COLUMNS.issubset(narration_columns):
        op.execute(
            """
            INSERT INTO diary_audios (
                audio_id, script_id, voice_id, status, audio_url,
                audio_hash, audio_size, audio_mime_type, created_at, updated_at
            )
            SELECT
                'audio_' || SUBSTRING(MD5(script_id) FROM 1 FOR 24),
                script_id,
                voice_id,
                CASE WHEN audio_url IS NOT NULL THEN 'completed' ELSE 'pending' END,
                audio_url,
                audio_hash,
                audio_size,
                audio_mime_type,
                created_at,
                updated_at
            FROM narration_scripts
            WHERE voice_id IS NOT NULL
               OR audio_url IS NOT NULL
               OR audio_hash IS NOT NULL
               OR audio_size IS NOT NULL
               OR audio_mime_type IS NOT NULL
            ON CONFLICT (audio_id) DO NOTHING
            """
        )

    for column_name in sorted(_AUDIO_COLUMNS & narration_columns):
        op.drop_column("narration_scripts", column_name)


def downgrade() -> None:
    """Move the latest audio metadata back to narration_scripts."""
    if context.is_offline_mode():
        op.add_column(
            "narration_scripts", sa.Column("voice_id", sa.String(length=50), nullable=True)
        )
        op.add_column(
            "narration_scripts", sa.Column("audio_url", sa.String(length=512), nullable=True)
        )
        op.add_column(
            "narration_scripts", sa.Column("audio_hash", sa.String(length=64), nullable=True)
        )
        op.add_column(
            "narration_scripts", sa.Column("audio_size", sa.Integer(), nullable=True)
        )
        op.add_column(
            "narration_scripts",
            sa.Column("audio_mime_type", sa.String(length=100), nullable=True),
        )
        op.execute(
            """
            UPDATE narration_scripts AS ns
            SET voice_id = da.voice_id,
                audio_url = da.audio_url,
                audio_hash = da.audio_hash,
                audio_size = da.audio_size,
                audio_mime_type = da.audio_mime_type
            FROM diary_audios AS da
            WHERE da.audio_id = (
                SELECT latest.audio_id
                FROM diary_audios AS latest
                WHERE latest.script_id = ns.script_id
                ORDER BY latest.created_at DESC
                LIMIT 1
            )
            """
        )
        op.drop_index(
            "ix_diary_audios_script_status_created", table_name="diary_audios"
        )
        op.drop_table("diary_audios")
        return

    narration_columns = _columns("narration_scripts")
    column_types = {
        "voice_id": sa.String(length=50),
        "audio_url": sa.String(length=512),
        "audio_hash": sa.String(length=64),
        "audio_size": sa.Integer(),
        "audio_mime_type": sa.String(length=100),
    }
    for column_name, column_type in column_types.items():
        if column_name not in narration_columns:
            op.add_column(
                "narration_scripts",
                sa.Column(column_name, column_type, nullable=True),
            )

    if "diary_audios" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.execute(
            """
            UPDATE narration_scripts AS ns
            SET voice_id = da.voice_id,
                audio_url = da.audio_url,
                audio_hash = da.audio_hash,
                audio_size = da.audio_size,
                audio_mime_type = da.audio_mime_type
            FROM diary_audios AS da
            WHERE da.audio_id = (
                SELECT latest.audio_id
                FROM diary_audios AS latest
                WHERE latest.script_id = ns.script_id
                ORDER BY latest.created_at DESC
                LIMIT 1
            )
            """
        )
        op.drop_index(
            "ix_diary_audios_script_status_created",
            table_name="diary_audios",
        )
        op.drop_table("diary_audios")
