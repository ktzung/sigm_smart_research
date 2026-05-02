"""
Revision stage: takes reviewer feedback and generates improved draft sections.
Implements the review → revise loop for Q1 quality.
"""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection, ReviewReport

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def revise_section(topic: Topic, section_name: str, db: Session) -> DraftSection:
    """Revise a single section based on reviewer feedback."""
    # Get latest draft
    draft = (
        db.query(DraftSection)
        .filter_by(topic_id=topic.id, section_name=section_name)
        .order_by(DraftSection.version.desc())
        .first()
    )
    if not draft:
        raise ValueError(f"No draft found for section '{section_name}'")

    # Get latest review
    review = (
        db.query(ReviewReport)
        .filter_by(topic_id=topic.id)
        .order_by(ReviewReport.created_at.desc())
        .first()
    )
    if not review:
        raise ValueError("No review report found. Run review stage first.")

    template = _jinja_env.get_template("revision.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        section_name=section_name,
        original_draft=draft.content,
        major_weaknesses=review.major_weaknesses or "",
        minor_issues=review.minor_issues or "",
        revision_priorities=review.revision_priorities or "",
    )

    router = get_router()
    revised_content = router.complete_for_stage(
        "revision",
        "You are an expert academic writer revising a survey paper based on peer review feedback.",
        user_prompt,
    )

    new_draft = DraftSection(
        topic_id=topic.id,
        section_name=section_name,
        content=revised_content,
        version=draft.version + 1,
        citation_map=draft.citation_map,
    )
    db.add(new_draft)
    db.commit()
    logger.info("Revised section '%s' v%d for topic %d", section_name, new_draft.version, topic.id)
    return new_draft


def revise_all_sections(topic: Topic, db: Session) -> list[DraftSection]:
    """Revise all sections based on reviewer feedback."""
    from app.services.writing import get_sections_for_topic
    revised = []
    for section in get_sections_for_topic(topic):
        try:
            draft = revise_section(topic, section, db)
            revised.append(draft)
        except Exception as e:
            logger.warning("Could not revise section '%s': %s", section, e)
    return revised
