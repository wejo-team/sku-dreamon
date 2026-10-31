"""학수번호로 통합한 과목 원장과 프로필의 선택 과목 관계를 저장한다."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("course_id > 0", name="ck_courses_id"),
        CheckConstraint(
            "btrim(code) <> '' AND btrim(name) <> ''", name="ck_courses_text"
        ),
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    departments: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )


class ProfileCourse(Base):
    __tablename__ = "profile_courses"
    __table_args__ = (Index("ix_profile_courses_course", "course_id", "account_id"),)

    account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "profiles.profile_id",
            name="fk_profile_courses_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "courses.course_id",
            name="fk_profile_courses_course",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
