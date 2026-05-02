"""Shared prerequisite enforcement and RemoteExecution helpers."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.pipeline import PipelineRun
from app.models.remote import RemoteExecution

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


def require_stage_done(topic_id: int, stage_name: str, db: Session) -> None:
    """Raise HTTP 400 if the named stage has no successful PipelineRun for this topic."""
    run = (
        db.query(PipelineRun)
        .filter_by(topic_id=topic_id, stage=stage_name, status="done")
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=400,
            detail=f"Prerequisite stage '{stage_name}' has not completed successfully.",
        )


def get_or_create_remote_execution(topic_id: int, db: Session) -> RemoteExecution:
    """Upsert a RemoteExecution record for the given topic."""
    rec = db.query(RemoteExecution).filter_by(topic_id=topic_id).first()
    if not rec:
        rec = RemoteExecution(topic_id=topic_id, execution_status="generated")
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return rec


def update_execution_status(topic_id: int, status: str, db: Session) -> None:
    """Update RemoteExecution.execution_status for the given topic."""
    rec = db.query(RemoteExecution).filter_by(topic_id=topic_id).first()
    if rec:
        rec.execution_status = status
        db.commit()
    else:
        logger.warning("No RemoteExecution found for topic %d when updating status to '%s'", topic_id, status)
