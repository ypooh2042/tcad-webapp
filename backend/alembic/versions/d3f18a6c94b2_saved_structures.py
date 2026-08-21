"""saved structures

Revision ID: d3f18a6c94b2
Revises: c7b41d9e2f08

소자 해석에 쓸 수 있는 `.str` 을 오래 보관한다.

잡 산출물은 유휴·쿼터 스윕에 지워진다. 공정을 돌린 다음 날 소자 해석을 하려면
그때마다 공정을 다시 돌려야 한다는 뜻이라, 전극이 있는 것만 골라 따로 둔다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3f18a6c94b2"
down_revision: Union[str, Sequence[str], None] = "c7b41d9e2f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_structures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_saved_structures_owner_id",
            ondelete="CASCADE",
        ),
        # 잡이 지워져도 구조는 남아야 한다. 그것이 이 표의 존재 이유다.
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_saved_structures_job_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_saved_structures"),
        sa.UniqueConstraint(
            "owner_id", "source_path", "filename", name="uq_saved_structures_name"
        ),
    )
    op.create_index("ix_saved_structures_owner_id", "saved_structures", ["owner_id"])
    op.create_index("ix_saved_structures_job_id", "saved_structures", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_structures_job_id", table_name="saved_structures")
    op.drop_index("ix_saved_structures_owner_id", table_name="saved_structures")
    op.drop_table("saved_structures")
