from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class SynthesisResult(Base):
    __tablename__ = "synthesis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    comparison_table: Mapped[dict | None] = mapped_column(JSON)
    recurring_patterns: Mapped[str | None] = mapped_column(Text)
    contradictions: Mapped[str | None] = mapped_column(Text)
    method_clusters: Mapped[dict | None] = mapped_column(JSON)
    benchmark_coverage: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TaxonomyCandidate(Base):
    __tablename__ = "taxonomy_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    dimensions: Mapped[dict | None] = mapped_column(JSON)   # {dim_name: [categories]}
    paper_mapping: Mapped[dict | None] = mapped_column(JSON) # {paper_id: {dim: category}}
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GapRecord(Base):
    __tablename__ = "gap_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    gap_type: Mapped[str] = mapped_column(String(100))  # missing_setting | assumption | benchmark | theory | opportunity
    description: Mapped[str] = mapped_column(Text)
    evidence_paper_ids: Mapped[list | None] = mapped_column(JSON)  # list of paper ids
    evidence_quotes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(String(20))  # high | medium | low
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DraftSection(Base):
    __tablename__ = "draft_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    section_name: Mapped[str] = mapped_column(String(100))  # introduction | background | ...
    content: Mapped[str] = mapped_column(Text)
    citation_map: Mapped[dict | None] = mapped_column(JSON)  # {placeholder: paper_id}
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ReviewReport(Base):
    __tablename__ = "review_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    major_weaknesses: Mapped[str | None] = mapped_column(Text)
    minor_issues: Mapped[str | None] = mapped_column(Text)
    revision_priorities: Mapped[str | None] = mapped_column(Text)
    overall_score: Mapped[str | None] = mapped_column(String(20))
    raw_review: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    lab_id: Mapped[int | None] = mapped_column(ForeignKey("labs.id"))
    stage: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | done | failed
    result_summary: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    topic: Mapped["Topic"] = relationship(back_populates="pipeline_runs")  # type: ignore[name-defined]


class IdeaRecord(Base):
    """Research ideas proposed by the idea_generation stage (Claude Sonnet, Socratic brainstorming)."""
    __tablename__ = "idea_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    novelty_argument: Mapped[str] = mapped_column(Text, nullable=False)
    methodology_hint: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)   # easy | medium | hard
    expected_impact: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low | medium | high
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
