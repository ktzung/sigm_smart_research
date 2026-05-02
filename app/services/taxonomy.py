"""Taxonomy builder module."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import TaxonomyCandidate, SynthesisResult

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def build_taxonomy(topic: Topic, db: Session) -> TaxonomyCandidate:
    papers_data = []
    for paper in topic.papers:
        if not paper.extraction:
            continue
        ext = paper.extraction
        papers_data.append({
            "id": paper.id,
            "title": paper.title,
            "method_type": ext.method_type,
            "setting": ext.setting,
            "assumptions": ext.assumptions,
            "datasets": ext.datasets,
        })

    papers_json = json.dumps(papers_data, indent=2)[:8000]

    template = _jinja_env.get_template("taxonomy.j2")
    user_prompt = template.render(topic_title=topic.title, papers_json=papers_json)

    router = get_router()
    raw = router.complete_for_stage("taxonomy", "You are a research taxonomist. Return only valid JSON.", user_prompt)

    from app.utils.json_utils import extract_json
    data = extract_json(raw, dict)

    candidate = TaxonomyCandidate(
        topic_id=topic.id,
        dimensions=data.get("dimensions"),
        paper_mapping=data.get("paper_mapping"),
        explanation=data.get("explanation"),
    )
    db.add(candidate)
    db.commit()
    logger.info("Taxonomy built for topic %d", topic.id)
    return candidate
