"""User profile, publications, and projects endpoints."""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.auth import User
from app.schemas.profile import (
    ProfileUpdate, ProfileRead,
    PublicationCreate, PublicationUpdate, PublicationRead,
    ProjectCreate, ProjectUpdate, ProjectRead,
    UserProfilePage,
)
from app.services import profile_service

router = APIRouter(tags=["profiles"])
public_router = APIRouter(tags=["profiles"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, detail="User not found")
    return user


# ── Public profile page ───────────────────────────────────────────────────────

@router.get("/{user_id}/profile", response_model=UserProfilePage)
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Public profile page — no auth required."""
    user = _get_user_or_404(user_id, db)
    profile = profile_service.get_or_create_profile(user_id, db)
    publications = profile_service.list_publications(user_id, db)
    projects = profile_service.list_projects(user_id, db)
    return UserProfilePage(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        profile=ProfileRead.model_validate(profile),
        publications=[PublicationRead.model_validate(p) for p in publications],
        projects=[ProjectRead.model_validate(p) for p in projects],
    )


from app.middleware.auth import get_current_user

# ── Own profile (requires auth) ───────────────────────────────────────────────

@router.patch("/me/profile", response_model=ProfileRead)
def update_my_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update own profile fields."""
    profile = profile_service.update_profile(current_user.id, data, db)
    return ProfileRead.model_validate(profile)


@router.post("/me/avatar", response_model=ProfileRead)
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and store an avatar image for the current user."""
    allowed_content_types = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if file.content_type not in allowed_content_types:
        raise HTTPException(400, detail="Avatar must be a PNG, JPG, WEBP, or GIF image")

    content = await file.read()
    if not content:
        raise HTTPException(400, detail="Uploaded file is empty")

    upload_dir = Path("storage") / "profile-avatars"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower() or allowed_content_types[file.content_type]
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = allowed_content_types[file.content_type]

    filename = f"user-{current_user.id}-{uuid4().hex}{suffix}"
    (upload_dir / filename).write_bytes(content)

    profile = profile_service.update_profile(
        current_user.id,
        ProfileUpdate(avatar_url=f"/storage/profile-avatars/{filename}"),
        db,
    )
    return ProfileRead.model_validate(profile)


# ── Publications ──────────────────────────────────────────────────────────────

@public_router.get("/publications/{publication_id}", response_model=PublicationRead)
def get_publication(publication_id: int, db: Session = Depends(get_db)):
    """Get a single publication by ID — public, no auth required."""
    from app.models.profile import Publication
    pub = db.query(Publication).filter_by(id=publication_id).first()
    if not pub:
        raise HTTPException(404, detail="Publication not found")
    return PublicationRead.model_validate(pub)


@router.get("/{user_id}/publications", response_model=list[PublicationRead])
def list_publications(user_id: int, db: Session = Depends(get_db)):
    """List publications for a user — public."""
    _get_user_or_404(user_id, db)
    return [PublicationRead.model_validate(p) for p in profile_service.list_publications(user_id, db)]


@router.post("/me/publications", response_model=PublicationRead, status_code=201)
def create_publication(
    data: PublicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pub = profile_service.create_publication(current_user.id, data, db)
    return PublicationRead.model_validate(pub)


@router.patch("/me/publications/{pub_id}", response_model=PublicationRead)
def update_publication(
    pub_id: int,
    data: PublicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pub = profile_service.update_publication(current_user.id, pub_id, data, db)
    return PublicationRead.model_validate(pub)


@router.delete("/me/publications/{pub_id}", status_code=204)
def delete_publication(
    pub_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile_service.delete_publication(current_user.id, pub_id, db)


# ── Projects ──────────────────────────────────────────────────────────────────

@public_router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    """Get a single project by ID — public, no auth required."""
    from app.models.profile import Project
    proj = db.query(Project).filter_by(id=project_id).first()
    if not proj:
        raise HTTPException(404, detail="Project not found")
    return ProjectRead.model_validate(proj)


@router.get("/{user_id}/projects", response_model=list[ProjectRead])
def list_projects(user_id: int, db: Session = Depends(get_db)):
    """List projects for a user — public."""
    _get_user_or_404(user_id, db)
    return [ProjectRead.model_validate(p) for p in profile_service.list_projects(user_id, db)]


@router.post("/me/projects", response_model=ProjectRead, status_code=201)
def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proj = profile_service.create_project(current_user.id, data, db)
    return ProjectRead.model_validate(proj)


@router.patch("/me/projects/{proj_id}", response_model=ProjectRead)
def update_project(
    proj_id: int,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proj = profile_service.update_project(current_user.id, proj_id, data, db)
    return ProjectRead.model_validate(proj)


@router.delete("/me/projects/{proj_id}", status_code=204)
def delete_project(
    proj_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile_service.delete_project(current_user.id, proj_id, db)
