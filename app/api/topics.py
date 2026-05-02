from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.topic import Topic
from app.schemas.topic import TopicCreate, TopicRead, TopicUpdate
from app.schemas.paper import PaperRead
from app.middleware.auth import get_current_user
from app.middleware.plan_enforcement import check_topic_limit, increment_usage
from app.models.auth import User
from app.models.lab import LabMember
from app.services.audit_service import audit_service

router = APIRouter()


def _get_topic_or_404(topic_id: int, user: User, db: Session) -> Topic:
    topic = db.query(Topic).filter_by(id=topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Ownership: owner OR lab member
    if topic.user_id != user.id:
        if not topic.lab_id:
            raise HTTPException(403, detail="Not authorized to access this topic")
        # Check lab membership
        member = db.query(LabMember).filter_by(lab_id=topic.lab_id, user_id=user.id).first()
        if not member:
            raise HTTPException(403, detail="Not authorized to access this topic")
    return topic


@router.post("", response_model=TopicRead, status_code=201)
def create_topic(
    payload: TopicCreate, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Plan enforcement
    check_topic_limit(current_user, db)
    
    topic_data = payload.model_dump()
    topic_data["target_paper_type"] = topic_data.pop("paper_type")
    topic_data["user_id"] = current_user.id
    
    topic = Topic(**topic_data)
    db.add(topic)
    db.commit()
    db.refresh(topic)

    increment_usage(current_user.id, "topics_created", db)

    audit_service.log_event(
        user_id=current_user.id,
        lab_id=topic.lab_id,
        topic_id=topic.id,
        event_type="topic_created",
        event_data={"title": topic.title, "paper_type": topic.target_paper_type},
        status="success",
        db=db,
    )

    return topic


@router.get("", response_model=list[TopicRead])
def list_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Return topics owned by user OR topics in labs the user is a member of
    lab_ids = db.query(LabMember.lab_id).filter_by(user_id=current_user.id).all()
    lab_ids = [l[0] for l in lab_ids]
    
    return db.query(Topic).filter(
        (Topic.user_id == current_user.id) | (Topic.lab_id.in_(lab_ids) if lab_ids else False)
    ).all()


@router.get("/{topic_id}", response_model=TopicRead)
def get_topic(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return _get_topic_or_404(topic_id, current_user, db)


@router.patch("/{topic_id}", response_model=TopicRead)
def update_topic(
    topic_id: int, 
    payload: TopicUpdate, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "authors_info" and value:
            # Convert AuthorInfo objects to dicts for JSON storage
            setattr(topic, field, [a if isinstance(a, dict) else a.model_dump() for a in value])
        else:
            setattr(topic, field, value)
    db.commit()
    db.refresh(topic)
    return topic


@router.put("/{topic_id}/paper-meta", response_model=TopicRead)
def update_paper_meta(
    topic_id: int,
    paper_abstract: str | None = None,
    paper_keywords: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update abstract and keywords for the paper."""
    topic = _get_topic_or_404(topic_id, current_user, db)
    if paper_abstract is not None:
        topic.paper_abstract = paper_abstract
    if paper_keywords is not None:
        topic.paper_keywords = paper_keywords
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    db.delete(topic)
    db.commit()


@router.get("/{topic_id}/papers", response_model=list[PaperRead])
def list_papers(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    return topic.papers


@router.put("/{topic_id}/authors", response_model=TopicRead)
def update_authors(
    topic_id: int, 
    authors: list, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save author list for the paper. Each author: {name, email, affiliation, orcid, is_corresponding}"""
    topic = _get_topic_or_404(topic_id, current_user, db)
    topic.authors_info = authors
    db.commit()
    db.refresh(topic)
    return topic
@router.get("/{topic_id}/pipeline_status")
def get_topic_pipeline_status(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.pipeline import PipelineRun
    _get_topic_or_404(topic_id, current_user, db)
    runs = db.query(PipelineRun).filter_by(topic_id=topic_id).order_by(PipelineRun.id.desc()).all()
    # Key by stage, take latest (newest) run — include status and error
    status_map = {}
    for r in runs:
        if r.stage not in status_map:
            status_map[r.stage] = r.status
            # Attach error detail so UI can display it on failed stages
            if r.error:
                status_map[f"{r.stage}_error"] = r.error[:300]
    return status_map


# ── Model routing override endpoints ─────────────────────────────────────────

from pydantic import BaseModel as _BaseModel

class ModelOverrideRequest(_BaseModel):
    """
    Set model overrides for a topic.
    Keys:
      "stage:<stage_id>"      → override a specific stage
      "category:<category>"   → override all stages in a task category
                                 (search | fast_screen | deep_analysis | writing | coding)
    Value: {"provider": "anthropic", "model": "claude-opus-4-5"}
    Pass null/empty dict to clear all overrides.
    """
    overrides: dict | None = None


@router.get("/{topic_id}/model-routing")
def get_model_routing(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current effective model routing for this topic (defaults + overrides)."""
    from app.core.llm_router import STAGE_ROUTING, MODEL_CATALOG, CATEGORY_DEFAULTS, resolve_model_for_stage

    topic = _get_topic_or_404(topic_id, current_user, db)
    overrides = topic.model_routing_overrides or {}

    effective = {}
    for stage, (_, _, temperature, max_tokens, category) in STAGE_ROUTING.items():
        provider, model, _, _ = resolve_model_for_stage(stage, overrides)
        effective[stage] = {
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "category": category,
            "is_overridden": (
                f"stage:{stage}" in overrides or
                f"category:{category}" in overrides
            ),
        }

    return {
        "topic_id": topic_id,
        "overrides": overrides,
        "effective_routing": effective,
        "available_models": MODEL_CATALOG,
        "category_defaults": {k: {"provider": v[0], "model": v[1]} for k, v in CATEGORY_DEFAULTS.items()},
    }


@router.patch("/{topic_id}/model-routing")
def update_model_routing(
    topic_id: int,
    payload: ModelOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update model routing overrides for a topic."""
    from app.core.llm_router import STAGE_ROUTING, MODEL_CATALOG, CATEGORY_DEFAULTS

    topic = _get_topic_or_404(topic_id, current_user, db)

    if payload.overrides is None:
        # Clear all overrides
        topic.model_routing_overrides = None
        db.commit()
        return {"topic_id": topic_id, "overrides": None, "message": "All overrides cleared"}

    # Validate keys and values
    valid_stages = set(STAGE_ROUTING.keys())
    valid_categories = set(CATEGORY_DEFAULTS.keys())
    all_model_ids = {m["id"] for models in MODEL_CATALOG.values() for m in models}
    valid_providers = set(MODEL_CATALOG.keys())

    validated: dict = {}
    for key, value in payload.overrides.items():
        if not isinstance(value, dict):
            raise HTTPException(400, detail=f"Override value for '{key}' must be an object")

        provider = value.get("provider")
        model = value.get("model")

        if not provider or not model:
            raise HTTPException(400, detail=f"Override '{key}' must have 'provider' and 'model'")
        if provider not in valid_providers:
            raise HTTPException(400, detail=f"Unknown provider '{provider}'. Valid: {sorted(valid_providers)}")

        if key.startswith("stage:"):
            stage = key[6:]
            if stage not in valid_stages:
                raise HTTPException(400, detail=f"Unknown stage '{stage}'")
        elif key.startswith("category:"):
            cat = key[9:]
            if cat not in valid_categories:
                raise HTTPException(400, detail=f"Unknown category '{cat}'. Valid: {sorted(valid_categories)}")
        else:
            raise HTTPException(400, detail=f"Key '{key}' must start with 'stage:' or 'category:'")

        validated[key] = {"provider": provider, "model": model}

    topic.model_routing_overrides = validated
    db.commit()
    return {"topic_id": topic_id, "overrides": validated, "message": f"{len(validated)} override(s) saved"}


@router.delete("/{topic_id}/model-routing/{override_key:path}")
def delete_model_routing_override(
    topic_id: int,
    override_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a single override key (e.g. 'stage:synthesize' or 'category:writing')."""
    topic = _get_topic_or_404(topic_id, current_user, db)
    overrides = dict(topic.model_routing_overrides or {})
    if override_key not in overrides:
        raise HTTPException(404, detail=f"Override '{override_key}' not found")
    del overrides[override_key]
    topic.model_routing_overrides = overrides or None
    db.commit()
    return {"topic_id": topic_id, "removed": override_key, "remaining": len(overrides)}
