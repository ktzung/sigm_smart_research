"""Audit logging service — all writes are non-fatal."""
import logging
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from app.models.audit import AuditLog, UsageStat

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class AuditService:
    """Service for audit logging and usage tracking.

    All log write methods are wrapped in try/except — failures are logged
    but never propagated to the caller.
    """

    def log_event(
        self,
        user_id: int | None,
        lab_id: int | None,
        topic_id: int | None,
        event_type: str,
        event_data: dict | None,
        status: str,
        db: Session,
    ) -> None:
        """Generic audit log write. Never raises — failure is logged only."""
        try:
            entry = AuditLog(
                user_id=user_id,
                lab_id=lab_id,
                topic_id=topic_id,
                event_type=event_type,
                event_data=event_data,
                status=status,
                created_at=_utcnow(),
            )
            db.add(entry)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Audit log write failed (event=%s): %s", event_type, e)

    def log_pipeline_run(
        self,
        user_id: int | None,
        lab_id: int | None,
        topic_id: int | None,
        stage: str,
        status: str,
        started_at: datetime | None,
        finished_at: datetime | None,
        db: Session,
    ) -> None:
        """Log a pipeline run event. Never raises."""
        self.log_event(
            user_id=user_id,
            lab_id=lab_id,
            topic_id=topic_id,
            event_type="pipeline_run",
            event_data={
                "stage": stage,
                "started_at": str(started_at),
                "finished_at": str(finished_at),
            },
            status=status,
            db=db,
        )

    def log_github_event(
        self,
        user_id: int,
        repo_url: str,
        event_type: str,
        status: str,
        db: Session,
    ) -> None:
        """Log a GitHub-related event. Never raises."""
        self.log_event(
            user_id=user_id,
            lab_id=None,
            topic_id=None,
            event_type=event_type,
            event_data={"repo_url": repo_url},
            status=status,
            db=db,
        )

    def get_lab_audit_log(
        self,
        lab_id: int,
        page: int,
        page_size: int,
        db: Session,
    ) -> dict:
        """Return paginated audit log entries for a lab, sorted by created_at DESC."""
        total = db.query(AuditLog).filter(AuditLog.lab_id == lab_id).count()
        items = (
            db.query(AuditLog)
            .filter(AuditLog.lab_id == lab_id)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": e.id,
                    "user_id": e.user_id,
                    "event_type": e.event_type,
                    "event_data": e.event_data,
                    "status": e.status,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in items
            ],
        }

    def increment_usage(
        self,
        user_id: int,
        field: str,
        db: Session,
        amount: int = 1,
    ) -> None:
        """Upsert UsageStat for current month. Never raises.

        field: one of topics_created | pipeline_runs | papers_ingested
        """
        try:
            month = date.today().replace(day=1)
            stat = db.query(UsageStat).filter(
                UsageStat.user_id == user_id,
                UsageStat.month == month,
            ).first()
            if not stat:
                stat = UsageStat(user_id=user_id, month=month)
                db.add(stat)
                db.flush()
            current = getattr(stat, field, 0) or 0
            setattr(stat, field, current + amount)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                "Usage increment failed (user=%s field=%s): %s", user_id, field, e
            )


# Module-level singleton for convenience
audit_service = AuditService()
