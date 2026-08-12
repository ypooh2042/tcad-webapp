"""job runs a workspace file

Revision ID: 3e9efa5db5d7
Revises: 999772efcca9
Create Date: 2026-08-12 19:21:33.677211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e9efa5db5d7'
down_revision: Union[str, Sequence[str], None] = '999772efcca9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """잡이 작업공간 파일을 직접 가리키게 한다.

    소스를 스냅샷으로 함께 들고 있어야 한다. 경로만 두면 제출 뒤 사용자가
    파일을 고쳤을 때 결과와 입력이 어긋난다.
    """
    op.add_column(
        'jobs', sa.Column('source_path', sa.String(length=1024), nullable=True)
    )
    op.add_column('jobs', sa.Column('source', sa.Text(), nullable=True))
    op.alter_column(
        'jobs', 'source_revision_id', existing_type=sa.INTEGER(), nullable=True
    )


def downgrade() -> None:
    """되돌린다.

    파일 기반 잡은 리비전이 없어 예전 스키마로 표현할 수 없다. **지우지 않으면
    NOT NULL 복원이 실패해 롤백 자체가 막힌다.** 산출물은 캐시라 함께 사라져도
    소스만 있으면 다시 만들 수 있다.
    """
    op.execute("DELETE FROM jobs WHERE source_revision_id IS NULL")
    op.alter_column(
        'jobs', 'source_revision_id', existing_type=sa.INTEGER(), nullable=False
    )
    op.drop_column('jobs', 'source')
    op.drop_column('jobs', 'source_path')
