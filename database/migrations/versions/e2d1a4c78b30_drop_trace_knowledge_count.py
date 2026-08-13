"""Counsel trace: drop knowledge_count

Revision ID: e2d1a4c78b30
Revises: d4e5f6a7b8c9
Create Date: 2026-08-13 00:00:00.000000

counsel_turn_traces 에서 knowledge_count 컬럼을 지운다.

이 값은 "이번 턴에 상담 기법 조각을 몇 개 검색해 왔나"였다. 그 검색 갈래를
없애고 기법을 프롬프트 정적 블록으로 옮기면서(prompts.py의 "감정에 따라
달라지는 것" / "소재에 따라 달라지는 것") 셀 것이 사라졌고, 그 뒤로는 항상
0이 들어간다.

지우기 전에 남아 있던 값을 확인했다:

    값 0 : 102행  (2026-08-11 ~ 2026-08-13)
    값 1 :  25행  (2026-08-11 ~ 2026-08-12)

0이 아닌 25행은 검색 갈래가 살아 있던 이틀치다. 그런데 이 숫자만으로는
아무것도 되짚을 수 없다 — 어떤 조각이 걸렸는지는 애초에 저장한 적이 없고
(일기와 달리 근거 테이블이 없다), 조각 코퍼스 자체가 코드와 함께 지워졌다.
남은 것은 해석할 수 없는 카운터뿐이라 보존 가치가 없다고 판단했다.

되돌리면 컬럼은 돌아오지만 그 25행의 1은 돌아오지 않는다. 전부 0이 된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2d1a4c78b30"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("counsel_turn_traces", "knowledge_count")


def downgrade() -> None:
    """Downgrade schema."""
    # server_default 를 남긴다. 기존 행을 채우기 위해 필요하고, 지울 당시에도
    # 원본 마이그레이션(f1a2c3d4e5f6)이 같은 형태로 만들어 두었다.
    op.add_column(
        "counsel_turn_traces",
        sa.Column(
            "knowledge_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
