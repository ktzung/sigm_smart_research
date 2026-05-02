"""Lab homepage and news endpoints — public read, professor-only write."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.schemas.profile import NewsCreate, NewsUpdate, NewsRead, NewsDetailRead, LabHomepageRead, EventCreate, EventUpdate, EventRead
from app.services import lab_homepage_service

router = APIRouter(tags=["lab-homepage"])


@router.get("/{lab_id}/homepage", response_model=LabHomepageRead)
def get_lab_homepage(lab_id: int, db: Session = Depends(get_db)):
    """Public lab homepage — no auth required."""
    return lab_homepage_service.get_homepage(lab_id, db)


@router.get("/{lab_id}/news", response_model=list[NewsRead])
def list_lab_news(lab_id: int, db: Session = Depends(get_db)):
    """List news items (pinned first) — public."""
    lab_homepage_service._require_lab(lab_id, db)
    items = lab_homepage_service.list_news(lab_id, db)
    return [NewsRead.model_validate(n) for n in items]


@router.get("/{lab_id}/news/{news_id}", response_model=NewsDetailRead)
def get_lab_news_detail(lab_id: int, news_id: int, db: Session = Depends(get_db)):
    """Get full news detail including author name — public, no auth required."""
    return lab_homepage_service.get_news_detail(lab_id, news_id, db)


@router.post("/{lab_id}/news", response_model=NewsRead, status_code=201)
def create_lab_news(
    lab_id: int,
    data: NewsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create news announcement — professor only."""
    news = lab_homepage_service.create_news(lab_id, current_user.id, data, db)
    return NewsRead.model_validate(news)


@router.patch("/{lab_id}/news/{news_id}", response_model=NewsRead)
def update_lab_news(
    lab_id: int,
    news_id: int,
    data: NewsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update news — professor or original author only."""
    news = lab_homepage_service.update_news(lab_id, news_id, current_user.id, data, db)
    return NewsRead.model_validate(news)


@router.delete("/{lab_id}/news/{news_id}", status_code=204)
def delete_lab_news(
    lab_id: int,
    news_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete news — professor or original author only."""
    lab_homepage_service.delete_news(lab_id, news_id, current_user.id, db)


# ── Events ────────────────────────────────────────────────────────────────────

@router.get("/{lab_id}/events", response_model=list[EventRead])
def list_lab_events(lab_id: int, db: Session = Depends(get_db)):
    """List events — public."""
    lab_homepage_service._require_lab(lab_id, db)
    return [EventRead.model_validate(e) for e in lab_homepage_service.list_events(lab_id, db)]


@router.post("/{lab_id}/events", response_model=EventRead, status_code=201)
def create_lab_event(
    lab_id: int,
    data: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = lab_homepage_service.create_event(lab_id, current_user.id, data, db)
    return EventRead.model_validate(event)


@router.patch("/{lab_id}/events/{event_id}", response_model=EventRead)
def update_lab_event(
    lab_id: int,
    event_id: int,
    data: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = lab_homepage_service.update_event(lab_id, event_id, current_user.id, data, db)
    return EventRead.model_validate(event)


@router.delete("/{lab_id}/events/{event_id}", status_code=204)
def delete_lab_event(
    lab_id: int,
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lab_homepage_service.delete_event(lab_id, event_id, current_user.id, db)
