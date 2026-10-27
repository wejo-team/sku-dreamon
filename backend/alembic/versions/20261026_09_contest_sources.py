"""공고 수집 출처와 확인 상태를 구분한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_09"
down_revision: str | Sequence[str] | None = "20261025_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHITESPACE = (
    r"\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020"
    r"\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007"
    r"\2008\2009\200A\2028\2029\202F\205F\3000"
)


def _required(columns: tuple[str, ...]) -> str:
    return " AND ".join(
        f"btrim({column}, U&'{_WHITESPACE}') <> ''" for column in columns
    )


def upgrade() -> None:
    op.add_column("contests", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "contests",
        sa.Column(
            "source_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("contests", "official_url", existing_type=sa.Text(), nullable=True)
    op.alter_column(
        "contests",
        "verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.drop_constraint("ck_contests_required_text", "contests", type_="check")
    op.create_check_constraint(
        "ck_contests_required_text",
        "contests",
        _required(("title", "organizer_name", "eligibility_text")),
    )
    op.create_check_constraint(
        "ck_contests_source_urls",
        "contests",
        "(official_url IS NOT NULL OR source_url IS NOT NULL) AND "
        + " AND ".join(
            f"({column} IS NULL OR btrim({column}, U&'{_WHITESPACE}') <> '')"
            for column in ("official_url", "source_url")
        ),
    )
    op.create_check_constraint(
        "ck_contests_source_metadata",
        "contests",
        "jsonb_typeof(source_metadata) = 'object'",
    )


def downgrade() -> None:
    # 확인되지 않은 값을 만들어 이전 NOT NULL 계약을 만족시키지 않는다.
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM contests "
            "WHERE official_url IS NULL OR verified_at IS NULL)"
        )
    ):
        raise RuntimeError("Unverified contests must be resolved before downgrade")
    op.drop_constraint("ck_contests_source_metadata", "contests", type_="check")
    op.drop_constraint("ck_contests_source_urls", "contests", type_="check")
    op.drop_constraint("ck_contests_required_text", "contests", type_="check")
    op.create_check_constraint(
        "ck_contests_required_text",
        "contests",
        _required(("title", "organizer_name", "eligibility_text", "official_url")),
    )
    op.alter_column("contests", "official_url", existing_type=sa.Text(), nullable=False)
    op.alter_column(
        "contests",
        "verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("contests", "source_metadata")
    op.drop_column("contests", "source_url")
