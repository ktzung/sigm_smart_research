from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class GitHubRepo(Base):
    __tablename__ = "github_repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_token: Mapped[str | None] = mapped_column(Text)  # AES-256 encrypted GitHub token
    # pending | running | done | failed
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    analyses: Mapped[list["CodeAnalysis"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class CodeAnalysis(Base):
    __tablename__ = "code_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_repo_id: Mapped[int] = mapped_column(
        ForeignKey("github_repos.id", ondelete="CASCADE"), nullable=False
    )
    languages: Mapped[dict | None] = mapped_column(JSON)        # {"Python": 12500, "JS": 3200}
    directory_tree: Mapped[str | None] = mapped_column(Text)
    key_modules: Mapped[list | None] = mapped_column(JSON)      # [{name, path, description}]
    readme_summary: Mapped[str | None] = mapped_column(Text)
    dependencies: Mapped[list | None] = mapped_column(JSON)     # ["fastapi", "sqlalchemy"]
    quality_issues: Mapped[list | None] = mapped_column(JSON)   # [{type, file, line, message}]
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100))
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    repo: Mapped["GitHubRepo"] = relationship(back_populates="analyses")
