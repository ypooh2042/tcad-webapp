"""devsim jobs

Revision ID: c7b41d9e2f08
Revises: a1c4f7d02b13

소자 해석을 두 번째 잡 종류로 들인다.

`jobs` 표를 나누지 않는 이유: 큐·중단·타임아웃·로그·산출물·청소가 두 종류에서
완전히 같다. 다른 것은 워커가 무엇을 부르느냐뿐이라, 꼬리표 한 칸이면 된다.

`devsim_results` 는 따로 둔다. 산출물은 유휴·쿼터 스윕에 지워지는데
(`app/jobs/sweeper.py`), 비교 기능은 예전 해석을 다시 불러와야 하기 때문이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7b41d9e2f08"
down_revision: Union[str, Sequence[str], None] = "a1c4f7d02b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default 를 두는 것은 기존 행 때문이다. 이 마이그레이션 전에 만들어진
    # 잡은 전부 SUPREM 실행이다.
    op.add_column(
        "jobs",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="suprem",
        ),
    )
    op.create_check_constraint(
        "ck_jobs_kind", "jobs", "kind in ('suprem', 'devsim')"
    )

    op.create_table(
        "devsim_results",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("structure", sa.String(length=255), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_devsim_results_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_devsim_results_owner_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_devsim_results"),
    )
    op.create_index(
        "ix_devsim_results_owner_id", "devsim_results", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_devsim_results_owner_id", table_name="devsim_results")
    op.drop_table("devsim_results")
    op.drop_constraint("ck_jobs_kind", "jobs", type_="check")
    op.drop_column("jobs", "kind")
