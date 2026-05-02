"""
PRISMA (Preferred Reporting Items for Systematic Reviews and Meta-Analyses)
documentation stage. Generates the PRISMA flow diagram data and checklist.
"""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def generate_prisma(topic: Topic, db: Session) -> dict:
    """Generate PRISMA flow data and methodology section."""
    papers = topic.papers
    included = [p for p in papers if p.decision and p.decision.label != "exclude"]
    excluded = [p for p in papers if p.decision and p.decision.label == "exclude"]

    label_counts: dict[str, int] = {}
    for p in included:
        if p.decision:
            label_counts[p.decision.label] = label_counts.get(p.decision.label, 0) + 1

    # PRISMA flow numbers
    query_plans = topic.query_plans
    total_bundles = sum(len(qp.bundles) for qp in query_plans) if query_plans else 0

    prisma_flow = {
        "identification": {
            "databases_searched": ["Semantic Scholar", "arXiv", "IEEE Xplore (pending)"],
            "search_queries": total_bundles,
            "records_identified": len(papers),
        },
        "screening": {
            "records_screened": len(papers),
            "records_excluded_rule_based": sum(
                1 for p in excluded if p.decision and p.decision.method == "rule"
            ),
            "records_excluded_llm": sum(
                1 for p in excluded if p.decision and p.decision.method == "llm"
            ),
        },
        "eligibility": {
            "full_text_assessed": len(included),
            "full_text_excluded": 0,
        },
        "included": {
            "studies_included": len(included),
            "direct": label_counts.get("direct", 0),
            "adjacent": label_counts.get("adjacent", 0),
            "foundational": label_counts.get("foundational", 0),
        },
    }

    # Generate methodology section text
    template = _jinja_env.get_template("prisma.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        prisma_flow=json.dumps(prisma_flow, indent=2),
        year_range="2015-2026",
        inclusion_criteria=[
            "Published in peer-reviewed venues or arXiv preprints",
            "Directly or adjacently related to the survey topic",
            "Published after 2015",
            "Abstract available",
        ],
        exclusion_criteria=[
            "Duplicate entries",
            "Non-English papers",
            "Papers without accessible abstract",
            "Papers published before 2015",
        ],
    )

    router = get_router()
    content = router.complete_for_stage(
        "prisma",
        "You are an expert academic writer specializing in systematic reviews.",
        user_prompt,
    )

    # Save as draft section
    existing = (
        db.query(DraftSection)
        .filter_by(topic_id=topic.id, section_name="methodology")
        .order_by(DraftSection.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1
    draft = DraftSection(
        topic_id=topic.id,
        section_name="methodology",
        content=content,
        version=version,
    )
    db.add(draft)
    db.commit()

    logger.info("PRISMA generated for topic %d: %s", topic.id, prisma_flow["included"])
    return {"prisma_flow": prisma_flow, "draft_id": draft.id}
