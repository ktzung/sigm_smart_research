"""Remote execution API router — Stages 16–22 and artefact download."""
import io
import tempfile
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.topic import Topic
from app.models.lab import LabMember
from app.models.pipeline import PipelineRun, DraftSection
from app.models.remote import RemoteExecution, SSHServer
from app.services.audit_service import audit_service
from app.services.hybrid_lab_service import hybrid_lab_service
from app.services.code_synthesis_service import code_synthesis_service
from app.services.env_architect_service import env_architect_service
from app.services.remote_deploy_service import remote_deploy_service
from app.services.execution_service import execution_service
from app.services.harvest_service import harvest_service
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/topics/{topic_id}/remote", tags=["remote-execution"])

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

REMOTE_EXEC_ROLES = {"professor", "phd_student"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_topic_or_404(topic_id: int, user: User, db: Session) -> Topic:
    topic = db.query(Topic).filter_by(id=topic_id).first()
    if not topic:
        raise HTTPException(404, detail="Topic not found")
    if topic.user_id != user.id:
        if not topic.lab_id:
            raise HTTPException(403, detail="Not authorized to access this topic")
        member = db.query(LabMember).filter_by(lab_id=topic.lab_id, user_id=user.id).first()
        if not member:
            raise HTTPException(403, detail="Not authorized to access this topic")
    return topic


def _require_remote_exec_role(user: User, topic: Topic, db: Session) -> None:
    """Block undergraduate_student from all remote execution endpoints."""
    if topic.lab_id:
        member = db.query(LabMember).filter_by(lab_id=topic.lab_id, user_id=user.id).first()
        if member and member.role not in REMOTE_EXEC_ROLES:
            raise HTTPException(
                403,
                detail="Remote execution is not available for undergraduate students.",
            )
    # Personal topics: owner has full access


def _create_run(topic: Topic, stage: str, db: Session) -> PipelineRun:
    run = PipelineRun(
        topic_id=topic.id,
        stage=stage,
        user_id=topic.user_id,
        lab_id=topic.lab_id,
        status="running",
        started_at=_utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _finish_run(run: PipelineRun, result: dict, db: Session) -> None:
    run.status = "done"
    run.result_summary = result
    run.finished_at = _utcnow()
    db.commit()


def _fail_run(run: PipelineRun, error: str, db: Session) -> None:
    run.status = "failed"
    run.error = error
    run.finished_at = _utcnow()
    db.commit()


def _resolve_server(topic_id: int, db: Session) -> SSHServer | None:
    rec = db.query(RemoteExecution).filter_by(topic_id=topic_id).first()
    if rec and rec.ssh_server_id:
        return db.query(SSHServer).filter_by(id=rec.ssh_server_id).first()
    return None


def _audit_stage(user: User, topic: Topic, stage: str, status: str, db: Session) -> None:
    try:
        audit_service.log_event(
            user_id=user.id,
            lab_id=topic.lab_id,
            topic_id=topic.id,
            event_type="remote_pipeline_run",
            event_data={"stage": stage},
            status=status,
            db=db,
        )
    except Exception:
        pass


# ── Stage 16 ──────────────────────────────────────────────────────────────────

@router.post("/stage16")
def run_stage16(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    run = _create_run(topic, "stage16", db)
    try:
        draft = hybrid_lab_service.generate_hybrid_design(topic, db)
        _finish_run(run, {"section_id": draft.id, "section_name": draft.section_name}, db)
        _audit_stage(current_user, topic, "stage16", "success", db)
        return {"run_id": run.id, "status": "done", "section_name": draft.section_name}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage16", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage16", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 17 ──────────────────────────────────────────────────────────────────

@router.post("/stage17")
def run_stage17(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    run = _create_run(topic, "stage17", db)
    try:
        drafts = code_synthesis_service.synthesize_code(topic, db)
        _finish_run(run, {"sections": [d.section_name for d in drafts]}, db)
        _audit_stage(current_user, topic, "stage17", "success", db)
        return {"run_id": run.id, "status": "done", "sections": [d.section_name for d in drafts]}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage17", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage17", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 18 ──────────────────────────────────────────────────────────────────

@router.post("/stage18")
def run_stage18(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    run = _create_run(topic, "stage18", db)
    try:
        drafts = env_architect_service.generate_env(topic, db)
        _finish_run(run, {"sections": [d.section_name for d in drafts]}, db)
        _audit_stage(current_user, topic, "stage18", "success", db)
        return {"run_id": run.id, "status": "done", "sections": [d.section_name for d in drafts]}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage18", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage18", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 19 ──────────────────────────────────────────────────────────────────

@router.post("/stage19")
def run_stage19(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    server = _resolve_server(topic_id, db)
    run = _create_run(topic, "stage19", db)
    try:
        draft = remote_deploy_service.generate_deploy_script(topic, server, db)
        _finish_run(run, {"section_id": draft.id, "section_name": draft.section_name}, db)
        _audit_stage(current_user, topic, "stage19", "success", db)
        return {"run_id": run.id, "status": "done", "section_name": draft.section_name}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage19", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage19", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 20 ──────────────────────────────────────────────────────────────────

@router.post("/stage20")
def run_stage20(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    server = _resolve_server(topic_id, db)
    run = _create_run(topic, "stage20", db)
    try:
        drafts = execution_service.generate_exec_script(topic, server, db)
        _finish_run(run, {"sections": [d.section_name for d in drafts]}, db)
        _audit_stage(current_user, topic, "stage20", "success", db)
        return {"run_id": run.id, "status": "done", "sections": [d.section_name for d in drafts]}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage20", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage20", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 21 ──────────────────────────────────────────────────────────────────

@router.post("/stage21")
def run_stage21(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    server = _resolve_server(topic_id, db)
    run = _create_run(topic, "stage21", db)
    try:
        draft = harvest_service.generate_harvest_script(topic, server, db)
        _finish_run(run, {"section_id": draft.id, "section_name": draft.section_name}, db)
        _audit_stage(current_user, topic, "stage21", "success", db)
        return {"run_id": run.id, "status": "done", "section_name": draft.section_name}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage21", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage21", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Stage 22 ──────────────────────────────────────────────────────────────────

@router.post("/stage22")
def run_stage22(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)
    run = _create_run(topic, "stage22", db)
    try:
        draft = analytics_service.generate_experiments_section(topic, db)
        _finish_run(run, {"section_id": draft.id, "section_name": draft.section_name}, db)
        _audit_stage(current_user, topic, "stage22", "success", db)
        return {"run_id": run.id, "status": "done", "section_name": draft.section_name}
    except HTTPException:
        _fail_run(run, "HTTPException", db)
        _audit_stage(current_user, topic, "stage22", "failed", db)
        raise
    except Exception as e:
        _fail_run(run, str(e), db)
        _audit_stage(current_user, topic, "stage22", "failed", db)
        raise HTTPException(500, detail=str(e))


# ── Server selection ──────────────────────────────────────────────────────────

class ServerSelectBody(BaseModel):
    ssh_server_id: int


@router.post("/server")
def select_server(
    topic_id: int,
    body: ServerSelectBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)

    # Verify server belongs to user
    server = db.query(SSHServer).filter_by(id=body.ssh_server_id, user_id=current_user.id).first()
    if not server:
        raise HTTPException(404, detail="SSH server not found.")

    rec = db.query(RemoteExecution).filter_by(topic_id=topic_id).first()
    if not rec:
        rec = RemoteExecution(topic_id=topic_id, execution_status="generated", ssh_server_id=server.id)
        db.add(rec)
    else:
        rec.ssh_server_id = server.id
    db.commit()
    return {"topic_id": topic_id, "ssh_server_id": server.id, "server_name": server.name}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)

    rec = db.query(RemoteExecution).filter_by(topic_id=topic_id).first()
    if not rec:
        return {"topic_id": topic_id, "execution_status": None, "ssh_server": None}

    server_info = None
    if rec.ssh_server:
        server_info = {
            "id": rec.ssh_server.id,
            "name": rec.ssh_server.name,
            "host": rec.ssh_server.host,
            "username": rec.ssh_server.username,
            "gpu_type": rec.ssh_server.gpu_type,
            "scheduler_type": rec.ssh_server.scheduler_type,
        }

    return {
        "topic_id": topic_id,
        "execution_status": rec.execution_status,
        "ssh_server": server_info,
    }


# ── Artefact download ─────────────────────────────────────────────────────────

@router.get("/artefacts/{section_name}")
def download_artefact(
    topic_id: int,
    section_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_remote_exec_role(current_user, topic, db)

    draft = (
        db.query(DraftSection)
        .filter_by(topic_id=topic_id, section_name=section_name)
        .order_by(DraftSection.version.desc())
        .first()
    )
    if not draft:
        raise HTTPException(404, detail="Stage has not been run yet for this topic.")

    try:
        audit_service.log_event(
            user_id=current_user.id,
            lab_id=topic.lab_id,
            topic_id=topic_id,
            event_type="artefact_download",
            event_data={"section_name": section_name},
            status="success",
            db=db,
        )
    except Exception:
        pass

    content = (draft.content or "").encode("utf-8")
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{section_name}"'},
    )
