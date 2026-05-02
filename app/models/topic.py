from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    lab_id: Mapped[int | None] = mapped_column(ForeignKey("labs.id"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    target_paper_type: Mapped[str] = mapped_column(String(50), default="survey")
    target_quality: Mapped[str] = mapped_column(String(20), default="Q1/Q2")
    literature_scarce: Mapped[bool] = mapped_column(Boolean, default=False)
    adjacent_fields: Mapped[list | None] = mapped_column(JSON)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    # Paper metadata for LaTeX export
    paper_abstract: Mapped[str | None] = mapped_column(Text)       # final abstract text
    paper_keywords: Mapped[str | None] = mapped_column(String(500)) # comma-separated
    authors_info: Mapped[list | None] = mapped_column(JSON)         # list of author dicts
    # Per-topic model routing overrides
    # Format: {"stage:synthesize": {"provider": "anthropic", "model": "claude-opus-4-5"},
    #          "category:writing": {"provider": "anthropic", "model": "claude-sonnet-4-5"}}
    model_routing_overrides: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    query_plans: Mapped[list["QueryPlan"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    papers: Mapped[list["Paper"]] = relationship(back_populates="topic", cascade="all, delete-orphan")  # type: ignore[name-defined]
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="topic", cascade="all, delete-orphan")  # type: ignore[name-defined]

    @property
    def paper_type(self) -> str:
        """Spec-aligned alias for backward compatibility with target_paper_type."""
        return self.target_paper_type

    @paper_type.setter
    def paper_type(self, value: str) -> None:
        self.target_paper_type = value


class QueryPlan(Base):
    __tablename__ = "query_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    topic: Mapped["Topic"] = relationship(back_populates="query_plans")
    bundles: Mapped[list["QueryBundle"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class QueryBundle(Base):
    __tablename__ = "query_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("query_plans.id"))
    label: Mapped[str] = mapped_column(String(50))   # direct | adjacent | foundational
    query_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50))  # semantic_scholar | arxiv | both

    plan: Mapped["QueryPlan"] = relationship(back_populates="bundles")
