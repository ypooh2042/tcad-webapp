"""devsim state

Revision ID: f4a7b2c81d95
Revises: e91c2d47a5f6

소자 해석 조건을 사용자별로 맡아 둔다. 전극에 이름을 붙이고 계면을 붙이고
전압을 정하는 데는 손이 꽤 가는데, 새로고침 한 번에 전부 초기값으로 돌아갔다.

열쇠는 구조 id 가 아니라 `.in` 경로다. 같은 코드를 다시 돌리면 구조는 새로
생기고 옛것은 지워지므로, 구조에 매달면 코드를 고칠 때마다 조건이 사라진다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a7b2c81d95"
down_revision: Union[str, Sequence[str], None] = "e91c2d47a5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devsim_states",
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_devsim_states_owner_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("owner_id", "source_path", name="pk_devsim_states"),
    )


def downgrade() -> None:
    op.drop_table("devsim_states")
