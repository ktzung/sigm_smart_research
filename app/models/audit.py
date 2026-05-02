from datetime import datetime, timezone, date
from sqlalchemy import String, Integer, DateTime, Date, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # Use Integer PK for cross-DB compatibility (SQLite requires INTEGER PRIMARY KEY for autoincrement behavior).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    lab_id: Mapped[int | None] = mapped_column(
        ForeignKey("labs.id", ondelete="SET NULL"), index=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL")
    )
    # pipeline_run | github_link | github_analysis | topic_create | member_invite | ...
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_data: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(20))  # success | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class UsageStat(Base):
    __tablename__ = "usage_stats"
    __table_args__ = (
        UniqueConstraint("user_id", "month", name="uq_usage_stats_user_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)  # first day of month e.g. 2025-01-01
    topics_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipeline_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    papers_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
