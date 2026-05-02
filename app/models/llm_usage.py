"""LLM usage and cost tracking model."""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class LLMUsageRecord(Base):
    """Tracks every LLM API call with token counts and estimated cost."""
    __tablename__ = "llm_usage_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)   # estimated USD
    latency_ms: Mapped[int | None] = mapped_column(Integer)        # response time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
