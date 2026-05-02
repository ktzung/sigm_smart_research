"""SSH Server management API router."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.lab import LabMember
from app.services.ssh_server_service import ssh_server_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/ssh-servers", tags=["ssh-servers"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SSHServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    host: str
    username: str
    key_path: str
    passphrase: str = ""
    gpu_type: str
    scheduler_type: str = "standalone"


class SSHServerResponse(BaseModel):
    id: int
    name: str
    host: str
    username: str
    gpu_type: str
    scheduler_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Role guard ────────────────────────────────────────────────────────────────

def _require_remote_exec_role(user: User, db: Session) -> None:
    """Block undergraduate_student from SSH server management."""
    # Check any lab membership — if any lab has them as undergrad, block
    memberships = db.query(LabMember).filter_by(user_id=user.id).all()
    for m in memberships:
        if m.role == "undergraduate_student":
            raise HTTPException(
                403,
                detail="Remote execution is not available for undergraduate students.",
            )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=SSHServerResponse, status_code=201)
def register_server(
    body: SSHServerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_remote_exec_role(current_user, db)
    server = ssh_server_service.register(
        user_id=current_user.id,
        name=body.name,
        host=body.host,
        username=body.username,
        key_path=body.key_path,
        passphrase=body.passphrase,
        gpu_type=body.gpu_type,
        scheduler_type=body.scheduler_type,
        db=db,
    )
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=None,
        topic_id=None,
        event_type="ssh_server_change",
        event_data={"action": "register", "server_name": server.name, "server_id": server.id},
        status="success",
        db=db,
    )
    return server


@router.get("", response_model=list[SSHServerResponse])
def list_servers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_remote_exec_role(current_user, db)
    return ssh_server_service.list_servers(current_user.id, db)


@router.delete("/{server_id}", status_code=204)
def delete_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_remote_exec_role(current_user, db)
    ssh_server_service.delete(server_id, current_user.id, db)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=None,
        topic_id=None,
        event_type="ssh_server_change",
        event_data={"action": "delete", "server_id": server_id},
        status="success",
        db=db,
    )


@router.get("/{server_id}/health-check")
def health_check(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_remote_exec_role(current_user, db)
    commands = ssh_server_service.health_check_commands(server_id, current_user.id, db)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=None,
        topic_id=None,
        event_type="ssh_server_health_check",
        event_data={"server_id": server_id},
        status="success",
        db=db,
    )
    return commands
