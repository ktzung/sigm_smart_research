from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    members: Mapped[list["LabMember"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )
    invitations: Mapped[list["LabInvitation"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )


class LabMember(Base):
    __tablename__ = "lab_members"
    __table_args__ = (UniqueConstraint("lab_id", "user_id", name="uq_lab_members_lab_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # professor | phd_student | master_student | undergraduate_student
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    lab: Mapped["Lab"] = relationship(back_populates="members")


class LabInvitation(Base):
    __tablename__ = "lab_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    lab: Mapped["Lab"] = relationship(back_populates="invitations")
