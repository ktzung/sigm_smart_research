from datetime import datetime, date, timezone
from sqlalchemy import String, Text, Boolean, DateTime, Date, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class UserProfile(Base):
    """Extended profile info — 1-to-1 with users."""
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(255))       # e.g. "Associate Professor"
    bio: Mapped[str | None] = mapped_column(Text)
    orcid: Mapped[str | None] = mapped_column(String(50))        # e.g. "0000-0002-1825-0097"
    google_scholar_url: Mapped[str | None] = mapped_column(String(500))
    researchgate_url: Mapped[str | None] = mapped_column(String(500))
    website_url: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Publication(Base):
    """Academic publication authored by a user."""
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, nullable=False)          # ["Nguyen Van A", "Tran Thi B"]
    venue: Mapped[str] = mapped_column(String(255), nullable=False)       # journal or conference name
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    doi: Mapped[str | None] = mapped_column(String(255))
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    abstract: Mapped[str | None] = mapped_column(Text)
    citation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # journal | conference | book_chapter | preprint
    pub_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Project(Base):
    """Research project or grant owned by a user."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)        # e.g. "Principal Investigator"
    funding_source: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)                   # NULL = ongoing
    # ongoing | completed | planned
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    collaborators: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LabNews(Base):
    """News/announcement posted on a Lab's homepage."""
    __tablename__ = "lab_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LabEvent(Base):
    """Upcoming or past lab event (seminar, defense, workshop, deadline…)."""
    __tablename__ = "lab_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))   # "Room B1-302" or "Online (Zoom)"
    event_type: Mapped[str] = mapped_column(String(50), default="seminar")
    # seminar | defense | workshop | deadline | conference | other
    url: Mapped[str | None] = mapped_column(String(500))        # registration / zoom link
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LabSlide(Base):
    """Hero slider image for a Lab's homepage."""
    __tablename__ = "lab_slides"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
