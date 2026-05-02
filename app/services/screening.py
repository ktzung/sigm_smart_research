"""Screening and ranking module: rule-based pre-filter + LLM scoring."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router, _strip_json_fences
from app.models.paper import Paper, PaperDecision
from app.models.topic import Topic

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

# Rule-based exclusion: papers older than this year are deprioritized
MIN_YEAR = 2015
EXCLUDE_SCORE_THRESHOLD = 0.2

# Known predatory/low-quality venue patterns to deprioritize
_PREDATORY_PATTERNS = [
    "international journal of advanced research",
    "international journal of innovative research",
    "global journal of",
    "american journal of",
    "european journal of research",
    "ijarcce", "ijarcet", "ijert", "ijaiem", "ijcsit",
    "wseas", "scirp", "omics", "hindawi open access",  # some hindawi journals are fine, but flag for LLM
]

# High-quality venue keywords — boost these
_QUALITY_VENUES = [
    "neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "aaai", "ijcai",
    "acl", "emnlp", "naacl", "kdd", "sigkdd", "www", "sigir",
    "ieee transactions", "acm transactions", "nature", "science",
    "journal of machine learning research", "jmlr",
    "artificial intelligence", "pattern recognition",
    "neural networks", "neurocomputing", "information sciences",
]


def _venue_quality_hint(venue: str) -> str:
    """Return 'high', 'low', or 'unknown' based on venue name heuristics."""
    if not venue:
        return "unknown"
    v = venue.lower()
    if any(q in v for q in _QUALITY_VENUES):
        return "high"
    if any(p in v for p in _PREDATORY_PATTERNS):
        return "low"
    return "unknown"


def _rule_based_prefilter(paper: Paper) -> tuple[bool, str]:
    """Returns (should_exclude, reason). Quick heuristics before LLM call."""
    if paper.year and paper.year < MIN_YEAR:
        return True, f"Paper year {paper.year} is before {MIN_YEAR}"
    if not paper.abstract or len(paper.abstract) < 50:
        return True, "Abstract too short or missing"
    return False, ""


def screen_paper(paper: Paper, topic: Topic, db: Session, force: bool = False) -> PaperDecision:
    """Screen a single paper. Returns or updates its PaperDecision.
    force=True re-screens even if a decision already exists (except manual overrides).
    """
    # Skip only manual overrides unless forced
    if paper.decision and paper.decision.method == "manual" and not force:
        return paper.decision
    # Skip non-overridden existing decisions unless forced
    if paper.decision and not force:
        return paper.decision

    exclude, rule_reason = _rule_based_prefilter(paper)
    if exclude:
        decision = _upsert_decision(paper, db, label="exclude", score=0.0, reason=rule_reason, method="rule")
        return decision

    # LLM screening
    template = _jinja_env.get_template("screening.j2")
    venue_quality = _venue_quality_hint(paper.venue or "")
    user_prompt = template.render(
        topic_title=topic.title,
        title=paper.title,
        abstract=paper.abstract or "",
        year=paper.year or "unknown",
        venue=paper.venue or "unknown",
        venue_quality_hint=venue_quality,
    )
    router = get_router()
    raw = router.complete_for_stage("screen", "You are a paper screener. Return only valid JSON.", user_prompt)

    try:
        cleaned = _strip_json_fences(raw)
        data = json.loads(cleaned)
        label = data.get("label", "exclude")
        score = float(data.get("relevance_score", 0.0))
        reason = data.get("reason", "")
        # Validate label is one of the expected values
        if label not in ("direct", "adjacent", "foundational", "exclude"):
            logger.warning("LLM returned unexpected label '%s' for paper %d, defaulting to exclude", label, paper.id)
            label = "exclude"
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("LLM screening returned invalid JSON for paper %d: %s | raw=%r", paper.id, e, raw[:200])
        label, score, reason = "exclude", 0.0, f"LLM parse error: {e}"

    decision = _upsert_decision(paper, db, label=label, score=score, reason=reason, method="llm")
    return decision


def _upsert_decision(paper: Paper, db: Session, label: str, score: float, reason: str, method: str) -> PaperDecision:
    if paper.decision:
        paper.decision.label = label
        paper.decision.relevance_score = score
        paper.decision.reason = reason
        paper.decision.method = method
    else:
        decision = PaperDecision(
            paper_id=paper.id,
            label=label,
            relevance_score=score,
            reason=reason,
            method=method,
        )
        db.add(decision)
        paper.decision = decision
    db.commit()
    return paper.decision


def screen_all_papers(topic: Topic, db: Session, force: bool = False) -> dict:
    """Screen papers for a topic.
    force=False: only screen papers without a decision (default, incremental).
    force=True:  re-screen all papers with LLM, preserving manual overrides.
    """
    if force:
        papers = topic.papers  # re-screen everything
        logger.info("Force re-screening all %d papers for topic %d", len(papers), topic.id)
    else:
        papers = [p for p in topic.papers if p.decision is None]
        logger.info("Screening %d unscreened papers for topic %d", len(papers), topic.id)

    counts: dict[str, int] = {}
    for paper in papers:
        decision = screen_paper(paper, topic, db, force=force)
        counts[decision.label] = counts.get(decision.label, 0) + 1
    logger.info("Screening complete for topic %d: %s", topic.id, counts)
    return counts