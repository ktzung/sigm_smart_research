"""Remote execution models: SSHServer and RemoteExecution."""
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

EXECUTION_STATUSES = ["generated", "deployed", "running", "harvested", "analyzed"]


class SSHServer(Base):
    __tablename__ = "ssh_servers"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_ssh_servers_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_key_path: Mapped[str] = mapped_column(Text, nullable=False)    # AES-256-GCM
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text)           # AES-256-GCM
    gpu_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scheduler_type: Mapped[str] = mapped_column(String(20), nullable=False, default="standalone")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    executions: Mapped[list["RemoteExecution"]] = relationship(
        back_populates="ssh_server", cascade="all, delete-orphan"
    )


class RemoteExecution(Base):
    __tablename__ = "remote_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    ssh_server_id: Mapped[int | None] = mapped_column(
        ForeignKey("ssh_servers.id", ondelete="SET NULL"), nullable=True
    )
    # generated | deployed | running | harvested | analyzed
    execution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="generated"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    ssh_server: Mapped["SSHServer | None"] = relationship(back_populates="executions")
