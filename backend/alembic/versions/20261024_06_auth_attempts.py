"""인증 시도 제한의 프로세스 공유 저장소를 추가한다."""

import sqlalchemy as sa
from alembic import op

revision = "20261024_06"
down_revision = "20261024_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_auth_attempts_count"),
    )


def downgrade() -> None:
    op.drop_table("auth_attempts")
