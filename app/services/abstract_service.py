"""Abstract and Contributions generation service."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection, GapRecord

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def generate_abstract_and_contributions(topic: Topic, db: Session) -> dict:
    """Generate abstract and contributions list from existing draft sections."""
    # Get latest drafts
    all_drafts = db.query(DraftSection).filter_by(topic_id=topic.id).all()
    latest: dict[str, DraftSection] = {}
    for d in all_drafts:
        if d.section_name not in latest or d.version > latest[d.section_name].version:
            latest[d.section_name] = d

    if not latest:
        raise ValueError("No draft sections found. Run Draft stage first.")

    # Build sections summary (first 300 chars each)
    sections_summary = "\n\n".join(
        f"[{name.upper()}]\n{d.content[:300]}..."
        for name, d in latest.items()
        if d.content
    )

    # Gaps summary
    gaps = db.query(GapRecord).filter_by(topic_id=topic.id).all()
    gaps_summary = "\n".join(
        f"- [{g.priority}] {g.gap_type}: {g.description}"
        for g in gaps
    ) or "No gaps identified yet."

    template = _jinja_env.get_template("abstract_contributions.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        sections_summary=sections_summary[:6000],
        gaps_summary=gaps_summary[:2000],
    )

    router = get_router()
    raw = router.complete_for_stage(
        "draft",
        "You are an expert academic writer. Return only valid JSON.",
        user_prompt,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Abstract generation JSON parse failed: %s", raw[:200])
        data = {"abstract": raw, "contributions": ""}

    abstract = data.get("abstract", "")
    contributions = data.get("contributions", "")

    # Save abstract as a draft section
    _upsert_section(topic.id, "abstract", abstract, db)
    _upsert_section(topic.id, "contributions", contributions, db)

    # Also update topic.paper_abstract if the field exists
    if hasattr(topic, "paper_abstract"):
        topic.paper_abstract = abstract
        db.commit()

    logger.info("Abstract and contributions generated for topic %d", topic.id)
    return {"abstract": abstract, "contributions": contributions}


def _upsert_section(topic_id: int, section_name: str, content: str, db: Session) -> DraftSection:
    existing = (
        db.query(DraftSection)
        .filter_by(topic_id=topic_id, section_name=section_name)
        .order_by(DraftSection.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1
    draft = DraftSection(
        topic_id=topic_id,
        section_name=section_name,
        content=content,
        version=version,
    )
    db.add(draft)
    db.commit()
    return draft
