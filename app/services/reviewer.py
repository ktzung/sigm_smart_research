"""Reviewer simulation module."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import ReviewReport, DraftSection

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def run_review(topic: Topic, db: Session) -> ReviewReport:
    """Simulate a Q1/Q2 reviewer critique of all draft sections."""
    drafts = (
        db.query(DraftSection)
        .filter_by(topic_id=topic.id)
        .order_by(DraftSection.section_name, DraftSection.version.desc())
        .all()
    )

    if not drafts:
        raise ValueError("No draft sections found. Run writing module first.")

    # Deduplicate: keep latest version per section
    seen: set[str] = set()
    unique_drafts: list[DraftSection] = []
    for d in drafts:
        if d.section_name not in seen:
            seen.add(d.section_name)
            unique_drafts.append(d)

    draft_content = "\n\n".join(
        f"## {d.section_name.upper()}\n{d.content}" for d in unique_drafts
    )
    draft_content = draft_content[:10000]  # token budget

    template = _jinja_env.get_template("reviewer.j2")
    user_prompt = template.render(topic_title=topic.title, draft_content=draft_content)

    router = get_router()
    raw = router.complete_for_stage(
        "review",
        "You are a strict peer reviewer. Return only valid JSON.",
        user_prompt,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Reviewer JSON parse failed: %s", raw[:200])
        data = {"raw_review": raw}

    report = ReviewReport(
        topic_id=topic.id,
        major_weaknesses=data.get("major_weaknesses"),
        minor_issues=data.get("minor_issues"),
        revision_priorities=data.get("revision_priorities"),
        overall_score=data.get("overall_score"),
        raw_review=raw,
    )
    db.add(report)
    db.commit()
    logger.info("Review complete for topic %d: score=%s", topic.id, report.overall_score)
    return report


# ── PIVOT / REFINE decision (inspired by AutoResearchClaw Stage 15) ───────────

SCORE_WEIGHTS = {
    "strong_accept": 1.0,
    "accept":        0.8,
    "weak_accept":   0.6,
    "borderline":    0.4,
    "weak_reject":   0.2,
    "reject":        0.0,
}

DECISION_PROCEED  = "PROCEED"   # Score >= 0.6 → paper is good enough
DECISION_REFINE   = "REFINE"    # 0.3 <= score < 0.6 → revise and re-review
DECISION_PIVOT    = "PIVOT"     # score < 0.3 → major structural issues, rethink


def make_pipeline_decision(report: ReviewReport) -> dict:
    """
    Autonomous PROCEED / REFINE / PIVOT decision based on review score.
    Mirrors AutoResearchClaw Stage 15 (RESEARCH_DECISION).

    Returns:
        {
            "decision": "PROCEED" | "REFINE" | "PIVOT",
            "score": float,
            "rationale": str,
            "recommended_action": str,
        }
    """
    score = SCORE_WEIGHTS.get(report.overall_score or "borderline", 0.4)

    if score >= 0.6:
        decision = DECISION_PROCEED
        rationale = f"Score '{report.overall_score}' meets acceptance threshold."
        action = "Proceed to Quality Check (Stage 14) and LaTeX Export (Stage 15)."
    elif score >= 0.3:
        decision = DECISION_REFINE
        rationale = f"Score '{report.overall_score}' indicates revision needed."
        action = (
            "Run Revision stage to address major weaknesses, then re-run Review. "
            f"Priority: {(report.revision_priorities or 'See major weaknesses')[:200]}"
        )
    else:
        decision = DECISION_PIVOT
        rationale = f"Score '{report.overall_score}' indicates fundamental issues."
        action = (
            "Consider re-running Gap Analysis and Draft stages with different approach. "
            f"Major issues: {(report.major_weaknesses or 'See review report')[:200]}"
        )

    logger.info(
        "Pipeline decision for topic review: %s (score=%.1f, overall=%s)",
        decision, score, report.overall_score,
    )

    return {
        "decision": decision,
        "score": score,
        "overall_score": report.overall_score,
        "rationale": rationale,
        "recommended_action": action,
    }
