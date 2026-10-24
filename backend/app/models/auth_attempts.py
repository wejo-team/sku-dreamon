"""서버 프로세스가 공유하는 인증 시도 창을 저장한다."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    __table_args__ = (CheckConstraint("attempts >= 0", name="ck_auth_attempts_count"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(BigInteger)
