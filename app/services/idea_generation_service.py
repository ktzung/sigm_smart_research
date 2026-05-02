"""Idea generation service — Stage: idea_generation.

Uses Claude Sonnet 4.5 with Socratic brainstorming methodology to propose
novel research ideas from the analyzed corpus (synthesis + taxonomy + gaps + papers).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.llm_router import get_router, _strip_json_fences
from app.models.paper import Paper
from app.models.pipeline import (
    GapRecord,
    IdeaRecord,
    SynthesisResult,
    TaxonomyCandidate,
)
from app.models.topic import Topic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a creative research strategist. "
    "Apply Socratic questioning to identify unexplored research directions. "
    "Return only valid JSON."
)

_VALID_DIFFICULTIES = {"easy", "medium", "hard"}
_VALID_IMPACTS = {"low", "medium", "high"}
_REQUIRED_TEXT_FIELDS = ("title", "novelty_argument", "methodology_hint")

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


# ── Internal helpers ──────────────────────────────────────────────────────────

@dataclass
class _IdeaContext:
    synthesis_summary: str
    taxonomy_summary: str
    gaps_json: str
    papers_json: str


def _load_context(topic: Topic, db: Session) -> _IdeaContext:
    """Load synthesis, taxonomy, gaps, and included papers from DB."""
    # SynthesisResult — latest
    synthesis = (
        db.query(SynthesisResult)
        .filter_by(topic_id=topic.id)
        .order_by(SynthesisResult.created_at.desc())
        .first()
    )
    synthesis_summary = ""
    if synthesis:
        parts = []
        if synthesis.recurring_patterns:
            parts.append(f"Recurring patterns:\n{synthesis.recurring_patterns}")
        if synthesis.contradictions:
            parts.append(f"Contradictions:\n{synthesis.contradictions}")
        if synthesis.benchmark_coverage:
            parts.append(f"Benchmark coverage:\n{synthesis.benchmark_coverage}")
        synthesis_summary = "\n\n".join(parts) or "No synthesis available."

    # TaxonomyCandidate — latest
    taxonomy = (
        db.query(TaxonomyCandidate)
        .filter_by(topic_id=topic.id)
        .order_by(TaxonomyCandidate.created_at.desc())
        .first()
    )
    taxonomy_summary = ""
    if taxonomy and taxonomy.dimensions:
        lines = []
        for dim, categories in taxonomy.dimensions.items():
            lines.append(f"- {dim}: {', '.join(str(c) for c in categories)}")
        taxonomy_summary = "\n".join(lines)
    else:
        taxonomy_summary = "No taxonomy available."

    # GapRecords — all for topic
    gaps = db.query(GapRecord).filter_by(topic_id=topic.id).all()
    gaps_data = [
        {
            "type": g.gap_type,
            "description": g.description,
            "priority": g.priority or "medium",
        }
        for g in gaps
    ]
    gaps_json = json.dumps(gaps_data, ensure_ascii=False, indent=2)

    # Included papers — label != "exclude", limit to 50 for token budget
    included_papers = [
        p for p in topic.papers
        if p.decision and p.decision.label != "exclude"
    ][:50]
    papers_data = [
        {
            "title": p.title,
            "venue": p.venue or "",
            "year": p.year or "",
            "label": p.decision.label if p.decision else "",
        }
        for p in included_papers
    ]
    papers_json = json.dumps(papers_data, ensure_ascii=False, indent=2)

    return _IdeaContext(
        synthesis_summary=synthesis_summary,
        taxonomy_summary=taxonomy_summary,
        gaps_json=gaps_json,
        papers_json=papers_json,
    )


def _apply_defaults(idea: dict) -> dict:
    """Ensure difficulty and expected_impact have valid values; default to 'medium'."""
    result = dict(idea)
    if result.get("difficulty") not in _VALID_DIFFICULTIES:
        result["difficulty"] = "medium"
    if result.get("expected_impact") not in _VALID_IMPACTS:
        result["expected_impact"] = "medium"
    return result


def _parse_ideas_json(raw: str) -> list[dict]:
    """Parse LLM output as a JSON list of idea dicts.

    Raises ValueError if output is not a valid JSON list.
    Skips items missing required text fields (title, novelty_argument, methodology_hint).
    """
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "idea_generation: LLM returned invalid JSON: %s | raw=%r",
            exc,
            raw[:500],
        )
        raise ValueError(f"idea_generation: LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            f"idea_generation: expected JSON list, got {type(data).__name__}"
        )

    valid_items: list[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning("idea_generation: item %d is not a dict, skipping", i)
            continue
        missing = [f for f in _REQUIRED_TEXT_FIELDS if not item.get(f)]
        if missing:
            logger.warning(
                "idea_generation: item %d missing required fields %s, skipping",
                i, missing,
            )
            continue
        valid_items.append(item)

    return valid_items


# ── Public API ────────────────────────────────────────────────────────────────

def generate_ideas(topic: Topic, db: Session) -> list[IdeaRecord]:
    """Generate and persist research ideas for a topic using Claude Sonnet 4.5.

    Reads synthesis, taxonomy, gaps, and included papers from DB.
    Calls LLM with Socratic brainstorming prompt.
    Persists 5–10 IdeaRecord rows and returns them.

    Raises:
        ValueError: if LLM output cannot be parsed as a valid JSON list.
    """
    ctx = _load_context(topic, db)

    template = _jinja_env.get_template("idea_generation.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        synthesis_summary=ctx.synthesis_summary,
        taxonomy_summary=ctx.taxonomy_summary,
        gaps_json=ctx.gaps_json,
        papers_json=ctx.papers_json,
    )

    router = get_router()
    raw = router.complete_for_stage("idea_generation", _SYSTEM_PROMPT, user_prompt)

    ideas_raw = _parse_ideas_json(raw)
    ideas_with_defaults = [_apply_defaults(idea) for idea in ideas_raw]

    # Cap at 10 ideas
    ideas_to_persist = ideas_with_defaults[:10]

    if len(ideas_to_persist) < 5:
        logger.warning(
            "idea_generation: only %d valid ideas generated for topic %d (expected 5–10)",
            len(ideas_to_persist),
            topic.id,
        )

    records: list[IdeaRecord] = []
    for idea in ideas_to_persist:
        record = IdeaRecord(
            topic_id=topic.id,
            title=idea["title"],
            novelty_argument=idea["novelty_argument"],
            methodology_hint=idea["methodology_hint"],
            difficulty=idea["difficulty"],
            expected_impact=idea["expected_impact"],
        )
        db.add(record)
        records.append(record)

    db.commit()
    for r in records:
        db.refresh(r)

    logger.info(
        "idea_generation: persisted %d ideas for topic %d",
        len(records),
        topic.id,
    )
    return records
