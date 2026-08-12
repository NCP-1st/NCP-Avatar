"""Counsel trace: diary retrieval observability

Revision ID: b7c8d9e0f1a2
Revises: f1a2c3d4e5f6
Create Date: 2026-08-12 00:00:00.000000

counsel_turn_traces 에 일기 검색 관측 컬럼 3개를 추가한다.

CounselTrace 스키마는 이미 이 값들을 들고 있었지만 저장되지 않아, 임계값
(DIARY_MIN_SCORE / DIARY_MIN_MATCH_TOKENS / DIARY_STRONG_SCORE)을 실측으로
옮길 근거가 쌓이지 않았다.

- diary_count        : 프롬프트에 실제로 들어간 일기 수
- diary_top_score    : 그중 최상위 관련도 (0건이면 NULL)
- diary_top_candidate: 임계값에 걸러지기 **전** 후보 최고점

세 번째가 핵심이다. 참조에 성공한 턴은 counsel_evidences 로도 알 수 있지만,
기준을 낮출지 말지는 **떨어진 턴이 몇 점이었는지**가 정한다.

기존 행은 diary_count=0, 점수 컬럼 NULL 로 남는다. 되돌리기는 컬럼 삭제뿐이라
관측값은 사라진다 — 어차피 파생 데이터라 상담 이력에는 영향이 없다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "f1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "counsel_turn_traces",
        sa.Column(
            "diary_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "counsel_turn_traces",
        sa.Column("diary_top_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "counsel_turn_traces",
        sa.Column("diary_top_candidate", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("counsel_turn_traces", "diary_top_candidate")
    op.drop_column("counsel_turn_traces", "diary_top_score")
    op.drop_column("counsel_turn_traces", "diary_count")
