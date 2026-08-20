"""editor state

Revision ID: a1c4f7d02b13
Revises: 3e9efa5db5d7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4f7d02b13"
down_revision: Union[str, Sequence[str], None] = "3e9efa5db5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "editor_states",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 제약에 이름을 준다. 이름이 없으면 downgrade 에서 지울 수 없다.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_editor_states_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_editor_states"),
    )


def downgrade() -> None:
    op.drop_table("editor_states")
