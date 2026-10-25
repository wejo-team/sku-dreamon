"""기존 소속을 보존하는 증가형 학사 항목과 부모 연결을 정의한다."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class AcademicUnit(Base):
    __tablename__ = "academic_units"
    __table_args__ = (
        CheckConstraint("academic_unit_id > 0", name="ck_academic_units_id"),
        CheckConstraint("btrim(name) <> ''", name="ck_academic_units_name"),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> academic_unit_id",
            name="ck_academic_units_self_parent",
        ),
        Index("ix_academic_units_parent", "parent_id", "academic_unit_id"),
    )

    academic_unit_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "academic_units.academic_unit_id",
            name="fk_academic_units_parent",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    is_selectable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
