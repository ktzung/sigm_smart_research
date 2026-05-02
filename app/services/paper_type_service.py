"""Paper type system: pipeline variants and outline generation."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.pipelines.orchestrator import STAGES_CORE, STAGES_Q1

logger = logging.getLogger(__name__)

VALID_PAPER_TYPES = [
    "survey", "research_paper", "review",
    "case_study", "technical_report", "thesis_chapter",
]

PAPER_TYPE_PIPELINES: dict[str, list[str]] = {
    "survey": STAGES_CORE + STAGES_Q1,
    "research_paper": [
        "query_plan", "discover", "screen", "ingest", "extract",
        "problem_statement", "methodology", "experiment_design",
        "results", "discussion", "review",
    ],
    "review": [
        "query_plan", "discover", "screen", "ingest", "extract",
        "scope_definition", "literature_search", "critical_analysis",
        "synthesize", "review",
    ],
    "case_study": [
        "query_plan", "discover", "screen", "ingest",
        "context_description", "data_collection", "analysis",
        "lessons_learned", "review",
    ],
    "technical_report": [
        "query_plan", "discover", "screen", "ingest", "extract",
        "executive_summary", "technical_background",
        "implementation_details", "recommendations", "review",
    ],
    "thesis_chapter": [
        "query_plan", "discover", "screen", "ingest", "extract",
        "chapter_intro", "related_work", "contribution",
        "chapter_conclusion", "review",
    ],
}

# Required stages per paper type (for validation)
REQUIRED_STAGES: dict[str, list[str]] = {
    "survey": ["query_plan", "discover", "screen", "draft", "review"],
    "research_paper": ["problem_statement", "methodology", "results", "discussion"],
    "review": ["scope_definition", "literature_search", "critical_analysis"],
    "case_study": ["context_description", "data_collection", "analysis", "lessons_learned"],
    "technical_report": ["executive_summary", "technical_background", "recommendations"],
    "thesis_chapter": ["chapter_intro", "related_work", "contribution", "chapter_conclusion"],
}

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

OUTLINE_PROMPTS: dict[str, str] = {
    "survey": "Generate a structured outline for a systematic survey paper on: {title}",
    "research_paper": "Generate a structured outline for a research paper on: {title}",
    "review": "Generate a structured outline for a literature review on: {title}",
    "case_study": "Generate a structured outline for a case study on: {title}",
    "technical_report": "Generate a structured outline for a technical report on: {title}",
    "thesis_chapter": "Generate a structured outline for a thesis chapter on: {title}",
}


def get_prompt_template(paper_type: str, stage: str) -> str:
    """Return the Jinja2 template path for a given paper_type + stage combination.

    Falls back to a generic stage template, then a default template if no
    specific one exists.
    """
    if paper_type not in VALID_PAPER_TYPES:
        raise ValueError(
            f"Invalid paper_type '{paper_type}'. Valid: {VALID_PAPER_TYPES}"
        )
    prompts_dir = Path(__file__).parent.parent / "prompts"
    # Most-specific: <paper_type>/<stage>.j2
    specific = prompts_dir / paper_type / f"{stage}.j2"
    if specific.exists():
        return str(specific.relative_to(prompts_dir))
    # Stage-level fallback: <stage>.j2
    stage_level = prompts_dir / f"{stage}.j2"
    if stage_level.exists():
        return str(stage_level.relative_to(prompts_dir))
    # Generic default
    return f"default.j2"


def get_pipeline_stages(paper_type: str) -> list[str]:
    if paper_type not in PAPER_TYPE_PIPELINES:
        raise ValueError(
            f"Invalid paper_type '{paper_type}'. Valid: {VALID_PAPER_TYPES}"
        )
    return PAPER_TYPE_PIPELINES[paper_type]


def generate_outline(topic: Topic, db: Session) -> dict:
    """Generate a paper outline using LLM based on paper_type."""
    paper_type = getattr(topic, "paper_type", "survey") or "survey"
    prompt_template = OUTLINE_PROMPTS.get(paper_type, OUTLINE_PROMPTS["survey"])
    user_prompt = prompt_template.format(title=topic.title) + (
        f"\n\nDescription: {topic.description}" if topic.description else ""
    )
    router = get_router()
    try:
        raw = router.complete_for_stage(
            "draft",
            "You are an academic writing expert. Return a JSON outline with sections array.",
            user_prompt,
        )
        # Try to parse as JSON, fallback to text
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"outline": raw, "paper_type": paper_type}
    except Exception as e:
        logger.error("Outline generation failed: %s", e)
        return {"error": str(e), "paper_type": paper_type}
