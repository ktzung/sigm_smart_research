"""Lab Homepage service: news, member grouping, statistics."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.lab import Lab, LabMember
from app.models.profile import LabNews, LabEvent, UserProfile, Publication, Project
from app.models.auth import User
from app.schemas.profile import (
    NewsCreate, NewsUpdate, NewsRead, NewsDetailRead,
    EventCreate, EventUpdate, EventRead,
    MemberDisplay, LabStats, LabHomepageRead,
)

logger = logging.getLogger(__name__)

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

# Role display order for homepage grouping
ROLE_DISPLAY_ORDER = ["professor", "phd_student", "master_student", "undergraduate_student"]
ROLE_LABELS = {
    "professor": "Professor",
    "phd_student": "PhD Student",
    "master_student": "Master Student",
    "undergraduate_student": "Undergraduate Student",
}


# ── News ──────────────────────────────────────────────────────────────────────

def list_news(lab_id: int, db: Session) -> list[LabNews]:
    """Return news items: pinned first, then by published_at desc."""
    return (
        db.query(LabNews)
        .filter_by(lab_id=lab_id)
        .order_by(LabNews.pinned.desc(), LabNews.published_at.desc())
        .all()
    )


def get_news_detail(lab_id: int, news_id: int, db: Session) -> NewsDetailRead:
    """Return full news detail including author display name — public."""
    result = (
        db.query(LabNews, User)
        .join(User, LabNews.author_id == User.id)
        .filter(LabNews.id == news_id, LabNews.lab_id == lab_id)
        .first()
    )
    if not result:
        raise HTTPException(404, detail="News item not found")
    news, author = result
    return NewsDetailRead(
        id=news.id,
        lab_id=news.lab_id,
        author_id=news.author_id,
        title=news.title,
        content=news.content,
        published_at=news.published_at,
        pinned=news.pinned,
        created_at=news.created_at,
        updated_at=news.updated_at,
        author_display_name=author.display_name,
    )


def create_news(lab_id: int, author_id: int, data: NewsCreate, db: Session) -> LabNews:
    _require_lab(lab_id, db)
    _require_professor(lab_id, author_id, db)
    news = LabNews(
        lab_id=lab_id,
        author_id=author_id,
        title=data.title,
        content=data.content,
        pinned=data.pinned,
        published_at=data.published_at or _utcnow(),
    )
    db.add(news)
    db.commit()
    db.refresh(news)
    logger.info("Lab news created: lab=%d title=%s", lab_id, news.title[:50])
    return news


def update_news(lab_id: int, news_id: int, requester_id: int, data: NewsUpdate, db: Session) -> LabNews:
    news = _get_news_or_404(news_id, lab_id, db)
    _require_professor_or_author(lab_id, requester_id, news.author_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(news, field, value)
    db.commit()
    db.refresh(news)
    return news


def delete_news(lab_id: int, news_id: int, requester_id: int, db: Session) -> None:
    news = _get_news_or_404(news_id, lab_id, db)
    _require_professor_or_author(lab_id, requester_id, news.author_id, db)
    db.delete(news)
    db.commit()


# ── Members grouped ───────────────────────────────────────────────────────────

def get_members_grouped(lab_id: int, db: Session) -> dict[str, list[MemberDisplay]]:
    """Return members grouped by role in display order."""
    members = (
        db.query(LabMember, User, UserProfile)
        .join(User, LabMember.user_id == User.id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(LabMember.lab_id == lab_id)
        .all()
    )

    # Count publications per user
    from app.models.profile import Publication
    pub_counts: dict[int, int] = {}
    for member, user, _ in members:
        pub_counts[user.id] = db.query(Publication).filter_by(user_id=user.id).count()

    grouped: dict[str, list[MemberDisplay]] = {role: [] for role in ROLE_DISPLAY_ORDER}

    for member, user, profile in members:
        display = MemberDisplay(
            user_id=user.id,
            display_name=user.display_name,
            avatar_url=profile.avatar_url if profile else None,
            title=profile.title if profile else None,
            bio=profile.bio if profile else None,
            role=member.role,
            profile_url=f"/api/v1/users/{user.id}/profile",
            orcid=profile.orcid if profile else None,
            google_scholar_url=profile.google_scholar_url if profile else None,
            website_url=profile.website_url if profile else None,
            publication_count=pub_counts.get(user.id, 0),
        )
        if member.role in grouped:
            grouped[member.role].append(display)
        else:
            grouped.setdefault(member.role, []).append(display)

    # Remove empty role groups
    return {k: v for k, v in grouped.items() if v}


# ── Statistics ────────────────────────────────────────────────────────────────

def compute_statistics(lab_id: int, db: Session) -> LabStats:
    """Aggregate publications, projects, members from current lab members only."""
    member_user_ids = [
        row[0] for row in
        db.query(LabMember.user_id).filter_by(lab_id=lab_id).all()
    ]

    if not member_user_ids:
        return LabStats(total_publications=0, total_projects=0, total_active_members=0)

    total_publications = (
        db.query(Publication)
        .filter(Publication.user_id.in_(member_user_ids))
        .count()
    )
    total_projects = (
        db.query(Project)
        .filter(Project.user_id.in_(member_user_ids))
        .count()
    )

    return LabStats(
        total_publications=total_publications,
        total_projects=total_projects,
        total_active_members=len(member_user_ids),
    )


# ── Full homepage ─────────────────────────────────────────────────────────────

def get_homepage(lab_id: int, db: Session) -> LabHomepageRead:
    """Assemble full lab homepage: news + events + members + stats."""
    lab = _require_lab(lab_id, db)
    news_items = list_news(lab_id, db)
    events = list_events(lab_id, db)
    members = get_members_grouped(lab_id, db)
    stats = compute_statistics(lab_id, db)

    return LabHomepageRead(
        lab_id=lab.id,
        lab_name=lab.name,
        lab_description=lab.description,
        news=[NewsRead.model_validate(n) for n in news_items],
        events=[EventRead.model_validate(e) for e in events],
        members=members,
        statistics=stats,
    )


# ── Events ────────────────────────────────────────────────────────────────────

def list_events(lab_id: int, db: Session) -> list[LabEvent]:
    """Return upcoming events first, then past events, max 20."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (
        db.query(LabEvent)
        .filter_by(lab_id=lab_id)
        .order_by(LabEvent.event_date.asc())
        .limit(20)
        .all()
    )


def create_event(lab_id: int, author_id: int, data: EventCreate, db: Session) -> LabEvent:
    _require_lab(lab_id, db)
    _require_professor(lab_id, author_id, db)
    event = LabEvent(
        lab_id=lab_id,
        author_id=author_id,
        title=data.title,
        description=data.description,
        event_date=data.event_date,
        location=data.location,
        event_type=data.event_type,
        url=data.url,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_event(lab_id: int, event_id: int, requester_id: int, data: EventUpdate, db: Session) -> LabEvent:
    event = _get_event_or_404(event_id, lab_id, db)
    _require_professor_or_author(lab_id, requester_id, event.author_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


def delete_event(lab_id: int, event_id: int, requester_id: int, db: Session) -> None:
    event = _get_event_or_404(event_id, lab_id, db)
    _require_professor_or_author(lab_id, requester_id, event.author_id, db)
    db.delete(event)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_lab(lab_id: int, db: Session) -> Lab:
    lab = db.query(Lab).filter_by(id=lab_id).first()
    if not lab:
        raise HTTPException(404, detail="Lab not found")
    return lab


def _get_news_or_404(news_id: int, lab_id: int, db: Session) -> LabNews:
    news = db.query(LabNews).filter_by(id=news_id, lab_id=lab_id).first()
    if not news:
        raise HTTPException(404, detail="News item not found")
    return news


def _require_professor_or_author(lab_id: int, requester_id: int, author_id: int, db: Session) -> None:
    """Allow if requester is professor in this lab OR is the news author."""
    if requester_id == author_id:
        return
    member = db.query(LabMember).filter_by(lab_id=lab_id, user_id=requester_id).first()
    if not member or member.role != "professor":
        raise HTTPException(403, detail="Required role: professor")


def _require_professor(lab_id: int, user_id: int, db: Session) -> None:
    member = db.query(LabMember).filter_by(lab_id=lab_id, user_id=user_id).first()
    if not member or member.role != "professor":
        raise HTTPException(403, detail="Required role: professor")


def _get_event_or_404(event_id: int, lab_id: int, db: Session) -> LabEvent:
    event = db.query(LabEvent).filter_by(id=event_id, lab_id=lab_id).first()
    if not event:
        raise HTTPException(404, detail="Event not found")
    return event
