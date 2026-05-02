"""LLM cost tracking endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.llm_usage import LLMUsageRecord

router = APIRouter(prefix="/cost", tags=["cost"])


@router.get("/summary")
def get_cost_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return cost summary for the current user: total, by provider, by stage."""
    records = db.query(LLMUsageRecord).filter_by(user_id=current_user.id).all()

    total_cost = sum(r.cost_usd for r in records)
    total_tokens = sum(r.total_tokens for r in records)
    total_calls = len(records)

    # By provider
    by_provider: dict[str, dict] = {}
    for r in records:
        p = r.provider
        if p not in by_provider:
            by_provider[p] = {"cost_usd": 0.0, "tokens": 0, "calls": 0}
        by_provider[p]["cost_usd"] += r.cost_usd
        by_provider[p]["tokens"] += r.total_tokens
        by_provider[p]["calls"] += 1

    # By stage
    by_stage: dict[str, dict] = {}
    for r in records:
        s = r.stage
        if s not in by_stage:
            by_stage[s] = {"cost_usd": 0.0, "tokens": 0, "calls": 0}
        by_stage[s]["cost_usd"] += r.cost_usd
        by_stage[s]["tokens"] += r.total_tokens
        by_stage[s]["calls"] += 1

    # By model
    by_model: dict[str, dict] = {}
    for r in records:
        key = f"{r.provider}/{r.model}"
        if key not in by_model:
            by_model[key] = {"cost_usd": 0.0, "tokens": 0, "calls": 0}
        by_model[key]["cost_usd"] += r.cost_usd
        by_model[key]["tokens"] += r.total_tokens
        by_model[key]["calls"] += 1

    # Sort by cost desc
    by_provider = dict(sorted(by_provider.items(), key=lambda x: x[1]["cost_usd"], reverse=True))
    by_stage    = dict(sorted(by_stage.items(),    key=lambda x: x[1]["cost_usd"], reverse=True))
    by_model    = dict(sorted(by_model.items(),    key=lambda x: x[1]["cost_usd"], reverse=True))

    return {
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "by_provider": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_provider.items()},
        "by_stage":    {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_stage.items()},
        "by_model":    {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_model.items()},
    }


@router.get("/topic/{topic_id}")
def get_topic_cost(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return cost breakdown for a specific topic."""
    records = db.query(LLMUsageRecord).filter_by(
        user_id=current_user.id, topic_id=topic_id
    ).order_by(LLMUsageRecord.created_at.desc()).all()

    total_cost = sum(r.cost_usd for r in records)

    by_stage: dict[str, dict] = {}
    for r in records:
        s = r.stage
        if s not in by_stage:
            by_stage[s] = {"cost_usd": 0.0, "tokens": 0, "calls": 0, "model": r.model}
        by_stage[s]["cost_usd"] += r.cost_usd
        by_stage[s]["tokens"] += r.total_tokens
        by_stage[s]["calls"] += 1

    return {
        "topic_id": topic_id,
        "total_cost_usd": round(total_cost, 6),
        "total_calls": len(records),
        "by_stage": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_stage.items()},
    }


@router.get("/recent")
def get_recent_calls(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return recent LLM calls with cost details."""
    records = (
        db.query(LLMUsageRecord)
        .filter_by(user_id=current_user.id)
        .order_by(LLMUsageRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "stage": r.stage,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "cost_usd": round(r.cost_usd, 6),
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]
