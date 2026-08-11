"""Counsel: turn table, trace, evidence + session crisis/memory fields

Revision ID: f1a2c3d4e5f6
Revises: 6b1e9d4f2a70
Create Date: 2026-08-11 00:00:00.000000

기존 counsel_sessions 를 확장하고, 대화 턴/트레이스/근거 테이블을 추가한다.
- counsel_sessions: is_crisis, memory_*, last_active_at, title 추가
- counsel_turns: 대화 한 줄(ConversationStore 의 저장 대상)
- counsel_turn_traces: 어시스턴트 턴 1:1 트레이스(안전 감사·사후 리뷰)
- counsel_evidences: 답변별 참조 일기(H-02, 이력 조회 붙을 때 채워짐)

PostgreSQL 전용이다. JSONB·BIGSERIAL·now() 는 PG 문법이고, 이 프로젝트의
운영 DB(database/conn/db.py)도 PG다. env.py 의 SQLite 폴백으로는 돌릴 수 없다
(선행 리비전 9a77b00fc3d1 이 이미 PG 전용 ALTER 를 쓴다).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6b1e9d4f2a70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- counsel_sessions 확장 ---
    op.add_column(
        "counsel_sessions",
        sa.Column("title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "counsel_sessions",
        sa.Column(
            "is_crisis",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "counsel_sessions",
        sa.Column(
            "memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "counsel_sessions",
        sa.Column(
            "memory_period_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )
    op.add_column(
        "counsel_sessions",
        sa.Column(
            "memory_max_items",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    op.add_column(
        "counsel_sessions",
        sa.Column(
            "last_active_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_counsel_sessions_user_active",
        "counsel_sessions",
        ["user_id", "last_active_at"],
        unique=False,
    )

    # --- counsel_turns ---
    op.create_table(
        "counsel_turns",
        sa.Column("turn_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("counsel_id", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["counsel_id"], ["counsel_sessions.counsel_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("turn_id"),
    )
    op.create_index(
        "ix_counsel_turns_counsel_turn",
        "counsel_turns",
        ["counsel_id", "turn_id"],
        unique=False,
    )

    # --- counsel_turn_traces (어시스턴트 턴 1:1) ---
    op.create_table(
        "counsel_turn_traces",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("turn_id", sa.BigInteger(), nullable=False),
        sa.Column("trace_id", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("result_code", sa.String(length=30), nullable=False),
        sa.Column("safety_level", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=True),
        sa.Column("emotion", sa.String(length=30), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "knowledge_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "ontology_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "event_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("guardrail_hits", postgresql.JSONB(), nullable=True),
        sa.Column("stage_ms", postgresql.JSONB(), nullable=True),
        sa.Column("error_detail", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["counsel_turns.turn_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", name="uq_counsel_trace_turn"),
    )
    op.create_index(
        "ix_counsel_traces_trace_id", "counsel_turn_traces", ["trace_id"], unique=False
    )
    op.create_index(
        "ix_counsel_traces_result_safety",
        "counsel_turn_traces",
        ["result_code", "safety_level"],
        unique=False,
    )

    # --- counsel_evidences (H-02, 이력 조회 붙을 때 사용) ---
    op.create_table(
        "counsel_evidences",
        sa.Column("evidence_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("turn_id", sa.BigInteger(), nullable=False),
        sa.Column("diary_session_id", sa.String(length=50), nullable=True),
        sa.Column("diary_date", sa.Date(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["counsel_turns.turn_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["diary_session_id"],
            ["diary_sessions.session_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index(
        "ix_counsel_evidences_turn", "counsel_evidences", ["turn_id"], unique=False
    )

    # 기존 세션의 safety_level 기본값을 'safe' → 'normal' 로 맞춘다.
    # SafetyLevel enum 은 normal/caution/crisis 이고, 저장소가 crisis 를 쓸 때
    # 'safe' 가 남아 있으면 롤업 등급이 뒤섞인다.
    op.execute(
        "UPDATE counsel_sessions SET safety_level = 'normal' WHERE safety_level = 'safe'"
    )
    op.alter_column(
        "counsel_sessions",
        "safety_level",
        existing_type=sa.String(length=20),
        server_default="normal",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "counsel_sessions",
        "safety_level",
        existing_type=sa.String(length=20),
        server_default="safe",
        existing_nullable=False,
    )
    op.execute(
        "UPDATE counsel_sessions SET safety_level = 'safe' WHERE safety_level = 'normal'"
    )

    op.drop_index("ix_counsel_evidences_turn", table_name="counsel_evidences")
    op.drop_table("counsel_evidences")

    op.drop_index(
        "ix_counsel_traces_result_safety", table_name="counsel_turn_traces"
    )
    op.drop_index("ix_counsel_traces_trace_id", table_name="counsel_turn_traces")
    op.drop_table("counsel_turn_traces")

    op.drop_index("ix_counsel_turns_counsel_turn", table_name="counsel_turns")
    op.drop_table("counsel_turns")

    op.drop_index(
        "ix_counsel_sessions_user_active", table_name="counsel_sessions"
    )
    op.drop_column("counsel_sessions", "last_active_at")
    op.drop_column("counsel_sessions", "memory_max_items")
    op.drop_column("counsel_sessions", "memory_period_days")
    op.drop_column("counsel_sessions", "memory_enabled")
    op.drop_column("counsel_sessions", "is_crisis")
    op.drop_column("counsel_sessions", "title")
