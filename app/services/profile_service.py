"""Profile service: user profile, publications, projects."""
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.profile import UserProfile, Publication, Project
from app.schemas.profile import ProfileUpdate, PublicationCreate, PublicationUpdate, ProjectCreate, ProjectUpdate

logger = logging.getLogger(__name__)

VALID_PUB_TYPES = {"journal", "conference", "book_chapter", "preprint"}
VALID_PROJECT_STATUSES = {"ongoing", "completed", "planned"}


# ── Profile ───────────────────────────────────────────────────────────────────

def get_or_create_profile(user_id: int, db: Session) -> UserProfile:
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_profile(user_id: int, data: ProfileUpdate, db: Session) -> UserProfile:
    profile = get_or_create_profile(user_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


# ── Publications ──────────────────────────────────────────────────────────────

def list_publications(user_id: int, db: Session) -> list[Publication]:
    return (
        db.query(Publication)
        .filter_by(user_id=user_id)
        .order_by(Publication.year.desc(), Publication.created_at.desc())
        .all()
    )


def create_publication(user_id: int, data: PublicationCreate, db: Session) -> Publication:
    pub = Publication(user_id=user_id, **data.model_dump())
    db.add(pub)
    db.commit()
    db.refresh(pub)
    logger.info("Publication created: user=%d title=%s", user_id, pub.title[:50])
    return pub


def update_publication(user_id: int, pub_id: int, data: PublicationUpdate, db: Session) -> Publication:
    pub = db.query(Publication).filter_by(id=pub_id).first()
    if not pub:
        raise HTTPException(404, detail="Publication not found")
    if pub.user_id != user_id:
        raise HTTPException(403, detail="Access forbidden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(pub, field, value)
    db.commit()
    db.refresh(pub)
    return pub


def delete_publication(user_id: int, pub_id: int, db: Session) -> None:
    pub = db.query(Publication).filter_by(id=pub_id).first()
    if not pub:
        raise HTTPException(404, detail="Publication not found")
    if pub.user_id != user_id:
        raise HTTPException(403, detail="Access forbidden")
    db.delete(pub)
    db.commit()


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects(user_id: int, db: Session) -> list[Project]:
    return (
        db.query(Project)
        .filter_by(user_id=user_id)
        .order_by(Project.start_date.desc(), Project.created_at.desc())
        .all()
    )


def create_project(user_id: int, data: ProjectCreate, db: Session) -> Project:
    proj = Project(user_id=user_id, **data.model_dump())
    db.add(proj)
    db.commit()
    db.refresh(proj)
    logger.info("Project created: user=%d title=%s", user_id, proj.title[:50])
    return proj


def update_project(user_id: int, proj_id: int, data: ProjectUpdate, db: Session) -> Project:
    proj = db.query(Project).filter_by(id=proj_id).first()
    if not proj:
        raise HTTPException(404, detail="Project not found")
    if proj.user_id != user_id:
        raise HTTPException(403, detail="Access forbidden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(proj, field, value)
    db.commit()
    db.refresh(proj)
    return proj


def delete_project(user_id: int, proj_id: int, db: Session) -> None:
    proj = db.query(Project).filter_by(id=proj_id).first()
    if not proj:
        raise HTTPException(404, detail="Project not found")
    if proj.user_id != user_id:
        raise HTTPException(403, detail="Access forbidden")
    db.delete(proj)
    db.commit()
