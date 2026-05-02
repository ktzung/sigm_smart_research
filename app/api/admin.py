from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.security import hash_password
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.topic import Topic
from app.models.paper import Paper
from app.models.pipeline import PipelineRun
from app.models.lab import Lab
from app.schemas.profile import ConfigGuiRead, ConfigSaveRequest
from app.services import config_service

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = "user"
    plan: str = "free"
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str | None = None
    plan: str | None = None
    is_active: bool | None = None

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "role": u.role,
        "plan": u.plan,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _validate_role(role: str):
    if role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role")


def _validate_plan(plan: str):
    if plan not in ["free", "paid"]:
        raise HTTPException(status_code=400, detail="Invalid plan. Use: free | paid")

@router.get("/stats")
def get_global_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Return global statistics for the admin dashboard."""
    user_count = db.query(User).count()
    topic_count = db.query(Topic).count()
    paper_count = db.query(Paper).count()
    run_count = db.query(PipelineRun).count()
    lab_count = db.query(Lab).count()
    
    # Active runs
    active_runs = db.query(PipelineRun).filter_by(status="running").count()
    
    # Paper types distribution
    paper_types: dict[str, int] = {}
    for topic in db.query(Topic).all():
        paper_type = getattr(topic, "paper_type", None) or getattr(topic, "target_paper_type", "survey")
        paper_types[paper_type] = paper_types.get(paper_type, 0) + 1
    
    return {
        "summary": {
            "users": user_count,
            "topics": topic_count,
            "papers": paper_count,
            "pipeline_runs": run_count,
            "labs": lab_count,
            "running_now": active_runs,
        },
        "paper_types": paper_types
    }

@router.get("/users")
def list_all_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
    return [_serialize_user(u) for u in users]


@router.get("/users/{user_id}")
def get_user_detail(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _validate_role(body.role)
    _validate_plan(body.plan)

    email = body.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        role=body.role,
        plan=body.plan,
        is_active=body.is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    db.refresh(user)
    return _serialize_user(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: AdminUserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        _validate_role(body.role)
        if user.id == admin.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="Cannot revoke your own admin role")
        user.role = body.role

    if body.plan is not None:
        _validate_plan(body.plan)
        user.plan = body.plan

    if body.email is not None:
        email = body.email.strip().lower()
        existing = db.query(User).filter_by(email=email).first()
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = email

    if body.display_name is not None:
        user.display_name = body.display_name.strip()

    if body.password is not None:
        user.password_hash = hash_password(body.password)

    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    db.delete(user)
    db.commit()

@router.patch("/users/{user_id}/role")
def update_user_role(user_id: int, role: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _validate_role(role)
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and role != "admin":
        raise HTTPException(status_code=400, detail="Cannot revoke your own admin role")
    user.role = role
    db.commit()
    return {"message": f"User {user.email} updated to {role}"}


@router.patch("/users/{user_id}/plan")
def update_user_plan(user_id: int, plan: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _validate_plan(plan)
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.plan = plan
    db.commit()
    return {"message": f"User {user.email} plan updated to {plan}"}

@router.get("/config")
def get_system_config(admin: User = Depends(require_admin)):
    """Return current sensitive configuration (LLM models, etc.)."""
    from app.core.config import settings
    from app.core.llm_router import STAGE_ROUTING
    return {
        "llm_provider": settings.llm_provider,
        "openai_model": settings.openai_model,
        "perplexity_model": settings.perplexity_model,
        "gemini_model": settings.gemini_model,
        "routing": STAGE_ROUTING,
    }


@router.get("/config/gui", response_model=ConfigGuiRead)
def get_config_gui(admin: User = Depends(require_admin)):
    """Return current LLM config with API keys masked as booleans."""
    return config_service.get_config_gui()


@router.post("/config/save")
def save_config(body: ConfigSaveRequest, admin: User = Depends(require_admin)):
    """Write non-empty config values to .env and reload settings."""
    try:
        config_service.save_config(body)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write configuration: {exc}")
    return {"ok": True}
