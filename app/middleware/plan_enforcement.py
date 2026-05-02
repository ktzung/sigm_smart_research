"""Plan enforcement: check monthly usage limits for Free/Paid plans."""
from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.auth import User
from app.models.audit import UsageStat

_UPGRADE_URL = "/plans"

FREE_LIMITS = {"topics": 5, "pipeline_runs": 3, "papers": 50}
PAID_LIMITS = {"topics": 50, "pipeline_runs": None, "papers": 500}  # None = unlimited


def _get_usage(user: User, db: Session) -> UsageStat:
    month = date.today().replace(day=1)
    stat = db.query(UsageStat).filter_by(user_id=user.id, month=month).first()
    if not stat:
        stat = UsageStat(user_id=user.id, month=month)
        db.add(stat)
        db.commit()
        db.refresh(stat)
    return stat


def _limit_exceeded(limit: int, resource: str) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "detail": f"Monthly {resource} limit ({limit}) reached. Upgrade to continue.",
            "upgrade_url": _UPGRADE_URL,
        },
    )


class PlanEnforcer:
    """Enforce per-plan monthly usage limits."""

    def check_topic_limit(self, user: User, db: Session) -> None:
        """Raise HTTP 429 if the user has reached their monthly topic creation limit."""
        limit = PAID_LIMITS["topics"] if user.plan == "paid" else FREE_LIMITS["topics"]
        if limit is None:
            return
        stat = _get_usage(user, db)
        if stat.topics_created >= limit:
            raise _limit_exceeded(limit, "topic")

    def check_pipeline_run_limit(self, user: User, db: Session) -> None:
        """Raise HTTP 429 if the user has reached their monthly pipeline run limit."""
        if user.plan == "paid":
            return  # unlimited for paid
        limit = FREE_LIMITS["pipeline_runs"]
        stat = _get_usage(user, db)
        if stat.pipeline_runs >= limit:
            raise _limit_exceeded(limit, "pipeline run")

    def check_paper_ingest_limit(self, user: User, db: Session) -> None:
        """Raise HTTP 429 if the user has reached their monthly paper ingest limit."""
        limit = PAID_LIMITS["papers"] if user.plan == "paid" else FREE_LIMITS["papers"]
        if limit is None:
            return
        stat = _get_usage(user, db)
        if stat.papers_ingested >= limit:
            raise _limit_exceeded(limit, "paper ingest")


# Module-level singleton for convenience
plan_enforcer = PlanEnforcer()


# Backward-compatible standalone functions (used by existing API routes)
def check_topic_limit(user: User, db: Session) -> None:
    plan_enforcer.check_topic_limit(user, db)


def check_pipeline_run_limit(user: User, db: Session) -> None:
    plan_enforcer.check_pipeline_run_limit(user, db)


def check_paper_ingest_limit(user: User, db: Session) -> None:
    plan_enforcer.check_paper_ingest_limit(user, db)


def increment_usage(user_id: int, field: str, db: Session, amount: int = 1) -> None:
    """Increment a usage counter atomically. field: topics_created | pipeline_runs | papers_ingested"""
    from sqlalchemy import update
    month = date.today().replace(day=1)
    stat = db.query(UsageStat).filter_by(user_id=user_id, month=month).first()
    if not stat:
        stat = UsageStat(user_id=user_id, month=month)
        db.add(stat)
        db.flush()
    # Atomic increment via SQL expression to avoid read-modify-write race condition
    db.execute(
        update(UsageStat)
        .where(UsageStat.user_id == user_id, UsageStat.month == month)
        .values({field: getattr(UsageStat, field) + amount})
    )
    db.commit()
