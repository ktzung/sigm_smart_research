"""Cross-paper synthesis module."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import SynthesisResult

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def _build_papers_json(topic: Topic) -> str:
    papers_data = []
    for paper in topic.papers:
        if not paper.extraction:
            continue
        ext = paper.extraction
        papers_data.append({
            "id": paper.id,
            "title": paper.title,
            "year": paper.year,
            "method_type": ext.method_type,
            "setting": ext.setting,
            "datasets": ext.datasets,
            "strengths": ext.strengths,
            "limitations": ext.limitations,
            "relevance_to_topic": ext.relevance_to_topic,
        })
    return json.dumps(papers_data, indent=2)[:8000]


def synthesize(topic: Topic, db: Session) -> SynthesisResult:
    papers_json = _build_papers_json(topic)
    if not papers_json or papers_json == "[]":
        raise ValueError("No extracted papers available for synthesis")

    template = _jinja_env.get_template("synthesis.j2")
    user_prompt = template.render(topic_title=topic.title, papers_json=papers_json)

    router = get_router()
    raw = router.complete_for_stage("synthesize", "You are a senior researcher. Return only valid JSON.", user_prompt)

    from app.utils.json_utils import extract_json
    data = extract_json(raw, dict)

    result = SynthesisResult(
        topic_id=topic.id,
        comparison_table=data.get("comparison_table"),
        recurring_patterns=data.get("recurring_patterns"),
        contradictions=data.get("contradictions"),
        method_clusters=data.get("method_clusters"),
        benchmark_coverage=data.get("benchmark_coverage"),
    )
    db.add(result)
    db.commit()
    logger.info("Synthesis complete for topic %d", topic.id)
    return result
