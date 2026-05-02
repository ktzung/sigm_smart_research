"""Knowledge extraction from parsed paper chunks."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.paper import Paper, ExtractionRecord
from app.models.topic import Topic

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

MAX_TEXT_CHARS = 6000  # keep prompt within token budget


def _build_paper_text(paper: Paper) -> str:
    """Concatenate chunks into a single text, prioritizing key sections."""
    priority = ["abstract", "introduction", "method", "experiments", "conclusion"]
    sections: dict[str, list[str]] = {}
    for chunk in paper.chunks:
        sec = chunk.section or "body"
        sections.setdefault(sec, []).append(chunk.text)

    parts = []
    for sec in priority:
        if sec in sections:
            parts.append(f"[{sec.upper()}]\n" + " ".join(sections[sec]))
    for sec, texts in sections.items():
        if sec not in priority:
            parts.append(f"[{sec.upper()}]\n" + " ".join(texts))

    full_text = "\n\n".join(parts)
    return full_text[:MAX_TEXT_CHARS]


def extract_paper(paper: Paper, topic: Topic, db: Session) -> ExtractionRecord:
    """Extract structured knowledge from a paper."""
    paper_text = _build_paper_text(paper)
    if not paper_text:
        paper_text = paper.abstract or paper.title or ""

    template = _jinja_env.get_template("extraction.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        title=paper.title,
        authors=", ".join(paper.authors or []),
        year=paper.year or "unknown",
        paper_text=paper_text,
    )

    router = get_router()
    raw = router.complete_for_stage("extract", "You are a research analyst. Return only valid JSON.", user_prompt)

    from app.utils.json_utils import extract_json
    data = extract_json(raw, dict)

    # Upsert extraction record
    if paper.extraction:
        rec = paper.extraction
    else:
        rec = ExtractionRecord(paper_id=paper.id)
        db.add(rec)

    rec.problem_formulation = data.get("problem_formulation")
    rec.method_type = data.get("method_type")
    rec.assumptions = data.get("assumptions")
    rec.setting = data.get("setting")
    rec.datasets = data.get("datasets")
    rec.evaluation_protocol = data.get("evaluation_protocol")
    rec.strengths = data.get("strengths")
    rec.limitations = data.get("limitations")
    rec.relevance_to_topic = data.get("relevance_to_topic")
    rec.raw_json = data

    paper.extracted = True
    db.commit()
    logger.info("Extracted knowledge from paper %d", paper.id)
    return rec


def extract_all_papers(topic: Topic, db: Session) -> int:
    """Extract from all included (non-excluded) papers. Self-heals on failure."""
    included = [
        p for p in topic.papers
        if p.decision and p.decision.label != "exclude" and not p.extracted
    ]
    success = 0
    failed = 0
    for paper in included:
        try:
            extract_paper(paper, topic, db)
            success += 1
        except Exception as e:
            logger.error("Extraction failed for paper %d: %s", paper.id, e)
            failed += 1
            # Self-heal: create minimal extraction from abstract if full extraction fails
            if paper.abstract and not paper.extraction:
                try:
                    _create_minimal_extraction(paper, topic, db)
                    success += 1
                    failed -= 1
                    logger.info("Self-healed extraction for paper %d using abstract", paper.id)
                except Exception as e2:
                    logger.warning("Self-heal also failed for paper %d: %s", paper.id, e2)

    logger.info("Extraction complete: %d success, %d failed", success, failed)
    return success


def _create_minimal_extraction(paper, topic: Topic, db: Session) -> ExtractionRecord:
    """Create minimal extraction from abstract when full extraction fails."""
    rec = ExtractionRecord(paper_id=paper.id)
    db.add(rec)
    rec.problem_formulation = f"See abstract: {(paper.abstract or '')[:200]}"
    rec.method_type = "unknown (extraction failed, using abstract)"
    rec.relevance_to_topic = f"Paper included in {topic.title} corpus"
    rec.raw_json = {"source": "minimal_fallback", "abstract": paper.abstract}
    paper.extracted = True
    db.commit()
    return rec
