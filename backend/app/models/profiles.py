"""계정과 공유하는 현재 프로필 및 선택 항목·포트폴리오를 저장한다."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.mixins import CreatedAtMixin, UpdatedAtMixin


class Profile(CreatedAtMixin, UpdatedAtMixin, Base):
    """별도 UUID를 발급하지 않고 계정당 하나의 현재 프로필을 유지한다."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_profiles_version"),
        CheckConstraint("real_name <> ''", name="ck_profiles_real_name"),
        CheckConstraint(
            "(experience_state IN ('unspecified', 'none') AND experience_body IS NULL) "
            "OR (experience_state = 'provided' AND experience_body IS NOT NULL "
            "AND experience_body <> '')",
            name="ck_profiles_experience",
        ),
        Index("ix_profiles_academic_unit", "academic_unit_id"),
        Index(
            "ix_profiles_public_updated",
            text("updated_at DESC"),
            "profile_id",
            postgresql_where=text("is_public = true"),
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "accounts.account_id",
            name="fk_profiles_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    real_name: Mapped[str] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    profile_image_code: Mapped[str | None] = mapped_column(String(64))
    academic_status_code: Mapped[str | None] = mapped_column(String(64))
    grade_code: Mapped[str | None] = mapped_column(String(64))
    weekly_availability_code: Mapped[str | None] = mapped_column(String(64))
    academic_unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "academic_units.academic_unit_id",
            name="fk_profiles_academic_unit",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    experience_state: Mapped[str] = mapped_column(
        String(16), server_default=text("'unspecified'")
    )
    experience_body: Mapped[str | None] = mapped_column(Text)
    introduction: Mapped[str | None] = mapped_column(Text)


class ProfileInterest(Base):
    __tablename__ = "profile_interests"
    __table_args__ = (Index("ix_profile_interests_field", "field_code", "account_id"),)

    account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "profiles.profile_id",
            name="fk_profile_interests_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    field_code: Mapped[str] = mapped_column(String(64), primary_key=True)


class ProfileDesiredRole(Base):
    __tablename__ = "profile_desired_roles"
    __table_args__ = (
        Index("ix_profile_desired_roles_role", "role_code", "account_id"),
    )

    account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "profiles.profile_id",
            name="fk_profile_desired_roles_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    role_code: Mapped[str] = mapped_column(String(64), primary_key=True)


class ProfileSkill(Base):
    __tablename__ = "profile_skills"
    __table_args__ = (Index("ix_profile_skills_skill", "skill_code", "account_id"),)

    account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "profiles.profile_id",
            name="fk_profile_skills_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    skill_code: Mapped[str] = mapped_column(String(64), primary_key=True)


class PortfolioLink(Base):
    __tablename__ = "portfolio_links"
    __table_args__ = (CheckConstraint("url <> ''", name="ck_portfolio_links_url"),)

    portfolio_link_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "profiles.profile_id",
            name="fk_portfolio_links_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
