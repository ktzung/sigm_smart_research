"""Research gap analysis module."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import GapRecord, SynthesisResult, TaxonomyCandidate

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def analyze_gaps(topic: Topic, db: Session) -> list[GapRecord]:
    # Get latest synthesis and taxonomy
    synthesis = (
        db.query(SynthesisResult)
        .filter_by(topic_id=topic.id)
        .order_by(SynthesisResult.created_at.desc())
        .first()
    )
    taxonomy = (
        db.query(TaxonomyCandidate)
        .filter_by(topic_id=topic.id)
        .order_by(TaxonomyCandidate.created_at.desc())
        .first()
    )

    synthesis_summary = ""
    if synthesis:
        synthesis_summary = json.dumps({
            "recurring_patterns": synthesis.recurring_patterns,
            "contradictions": synthesis.contradictions,
            "benchmark_coverage": synthesis.benchmark_coverage,
        })

    taxonomy_summary = ""
    if taxonomy:
        taxonomy_summary = json.dumps({
            "dimensions": taxonomy.dimensions,
            "explanation": taxonomy.explanation,
        })

    papers_data = []
    for paper in topic.papers:
        if not paper.extraction:
            continue
        ext = paper.extraction
        papers_data.append({
            "id": paper.id,
            "title": paper.title,
            "limitations": ext.limitations,
            "assumptions": ext.assumptions,
            "datasets": ext.datasets,
        })
    papers_json = json.dumps(papers_data, indent=2)[:6000]

    template = _jinja_env.get_template("gap_analysis.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        synthesis_summary=synthesis_summary,
        taxonomy_summary=taxonomy_summary,
        papers_json=papers_json,
    )

    router = get_router()
    raw = router.complete_for_stage("gaps", "You are a critical research analyst. Return only valid JSON.", user_prompt)

    from app.utils.json_utils import extract_json
    gaps_data = extract_json(raw, list)

    records: list[GapRecord] = []
    for item in gaps_data:
        rec = GapRecord(
            topic_id=topic.id,
            gap_type=item.get("gap_type", "future_opportunity"),
            description=item.get("description", ""),
            evidence_paper_ids=item.get("evidence_paper_ids"),
            evidence_quotes=item.get("evidence_quotes"),
            priority=item.get("priority", "medium"),
        )
        db.add(rec)
        records.append(rec)

    db.commit()
    logger.info("Gap analysis: %d gaps identified for topic %d", len(records), topic.id)
    return records
