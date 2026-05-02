from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    # Core metadata
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list | None] = mapped_column(JSON)
    abstract: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String(500))
    citation_count: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200))  # S2 or arXiv id
    source_api: Mapped[str | None] = mapped_column(String(50))    # semantic_scholar | arxiv
    # Status flags
    pdf_downloaded: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Code repository (discovered via Papers With Code)
    code_repo_url: Mapped[str | None] = mapped_column(Text)
    code_repo_stars: Mapped[int | None] = mapped_column(Integer)
    code_framework: Mapped[str | None] = mapped_column(String(50))  # pytorch | tensorflow | jax | other
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    topic: Mapped["Topic"] = relationship(back_populates="papers")  # type: ignore[name-defined]
    sources: Mapped[list["PaperSource"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    decision: Mapped["PaperDecision | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    chunks: Mapped[list["PaperChunk"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    extraction: Mapped["ExtractionRecord | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")


class PaperSource(Base):
    """Tracks which query bundle discovered this paper."""
    __tablename__ = "paper_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    query_bundle_id: Mapped[int | None] = mapped_column(ForeignKey("query_bundles.id"))
    source_api: Mapped[str] = mapped_column(String(50))
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    paper: Mapped["Paper"] = relationship(back_populates="sources")


class PaperDecision(Base):
    __tablename__ = "paper_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), unique=True)
    label: Mapped[str] = mapped_column(String(50))       # direct | adjacent | foundational | exclude
    relevance_score: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(20), default="llm")  # rule | llm | manual
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    paper: Mapped["Paper"] = relationship(back_populates="decision")


class PaperChunk(Base):
    """Parsed text chunks from PDF."""
    __tablename__ = "paper_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    section: Mapped[str | None] = mapped_column(String(100))  # abstract | intro | method | ...
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)

    paper: Mapped["Paper"] = relationship(back_populates="chunks")


class ExtractionRecord(Base):
    """Structured knowledge extracted from a paper."""
    __tablename__ = "extraction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), unique=True)
    problem_formulation: Mapped[str | None] = mapped_column(Text)
    method_type: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[str | None] = mapped_column(Text)
    setting: Mapped[str | None] = mapped_column(Text)
    datasets: Mapped[list | None] = mapped_column(JSON)
    evaluation_protocol: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    relevance_to_topic: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    paper: Mapped["Paper"] = relationship(back_populates="extraction")
