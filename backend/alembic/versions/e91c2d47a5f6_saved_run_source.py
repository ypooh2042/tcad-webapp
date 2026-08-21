"""saved run source

Revision ID: e91c2d47a5f6
Revises: d3f18a6c94b2

저장한 해석에 **어느 `.in` 에서 나왔는지**를 함께 남긴다. 구조 파일 이름만으로는
여러 흐름에서 같은 이름이 나올 수 있어, 비교 화면에서 출처를 가릴 수 없다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e91c2d47a5f6"
down_revision: Union[str, Sequence[str], None] = "d3f18a6c94b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devsim_results",
        sa.Column(
            "source_path", sa.String(length=1024), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("devsim_results", "source_path")
