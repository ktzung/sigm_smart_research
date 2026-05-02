"""Lab management endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.auth import User
from app.models.lab import Lab, LabMember
from app.services.lab_service import lab_service
from app.services.audit_service import audit_service

router = APIRouter(tags=["labs"])


class LabCreate(BaseModel):
    name: str
    description: str | None = None


class InviteRequest(BaseModel):
    email: str
    role: str


class AcceptRequest(BaseModel):
    token: str


# ── Lab CRUD ──────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_lab(
    body: LabCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lab = lab_service.create_lab(body.name, body.description, current_user, db)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=lab.id,
        topic_id=None,
        event_type="lab_create",
        event_data={"name": lab.name},
        status="success",
        db=db,
    )
    return {"id": lab.id, "name": lab.name, "description": lab.description, "owner_id": lab.owner_id}


@router.get("")
def list_my_labs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = db.query(LabMember).filter_by(user_id=current_user.id).all()
    labs = []
    for m in memberships:
        lab = db.query(Lab).filter_by(id=m.lab_id).first()
        if lab:
            labs.append({"id": lab.id, "name": lab.name, "role": m.role})
    return labs


@router.get("/{lab_id}")
def get_lab(
    lab_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lab = db.query(Lab).filter_by(id=lab_id).first()
    if not lab:
        raise HTTPException(404, detail="Lab not found")
    return {"id": lab.id, "name": lab.name, "description": lab.description, "owner_id": lab.owner_id}


# ── Members ───────────────────────────────────────────────────────────────────

@router.get("/{lab_id}/members")
def list_members(
    lab_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    members = db.query(LabMember).filter_by(lab_id=lab_id).all()
    return [
        {"user_id": m.user_id, "role": m.role, "joined_at": m.joined_at.isoformat()}
        for m in members
    ]


@router.post("/{lab_id}/members/invite", status_code=201)
def invite_member(
    lab_id: int,
    body: InviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = lab_service.invite_member(lab_id, body.email, body.role, current_user, db)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=lab_id,
        topic_id=None,
        event_type="member_invite",
        event_data={"email": body.email, "role": body.role},
        status="success",
        db=db,
    )
    return {
        "invitation_id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "expires_at": inv.expires_at.isoformat(),
    }


@router.post("/{lab_id}/members/accept")
def accept_invitation(
    lab_id: int,
    body: AcceptRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Accept a lab invitation. Authentication is optional — token identifies the invite."""
    if current_user is None:
        raise HTTPException(401, detail="Token invalid or expired")
    member = lab_service.accept_invitation(body.token, current_user, db)
    return {"lab_id": member.lab_id, "user_id": member.user_id, "role": member.role}


@router.delete("/{lab_id}/members/{user_id}", status_code=204)
def remove_member(
    lab_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lab_service.remove_member(lab_id, user_id, current_user, db)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=lab_id,
        topic_id=None,
        event_type="member_remove",
        event_data={"removed_user_id": user_id},
        status="success",
        db=db,
    )


# ── Usage & Audit ─────────────────────────────────────────────────────────────

@router.get("/{lab_id}/usage")
def get_lab_usage(
    lab_id: int,
    month: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current-month usage statistics for all lab members. Professor only.

    Validates: Requirements 4.12
    """
    lab_service.require_min_role(lab_id, current_user.id, "professor", db)
    if month is None:
        from datetime import date as _date
        month = _date.today().replace(day=1)
    stats = lab_service.get_usage_stats(lab_id, month, db)
    return stats


@router.get("/{lab_id}/audit")
def get_lab_audit(
    lab_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return paginated audit log for a lab. Professor only.

    Validates: Requirements 5.3
    """
    lab_service.require_min_role(lab_id, current_user.id, "professor", db)
    return audit_service.get_lab_audit_log(lab_id, page, page_size, db)
