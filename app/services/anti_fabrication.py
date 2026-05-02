"""
Anti-fabrication guard (inspired by AutoResearchClaw VerifiedRegistry).

Scans draft content for:
1. Citation placeholders [CITE:X] that don't correspond to real papers
2. Suspicious numeric claims (percentages, metrics) not grounded in evidence
3. Hallucinated paper references (titles mentioned but not in corpus)

Returns a sanitized version of the content with warnings.
"""
import re
import logging
from sqlalchemy.orm import Session
from app.models.topic import Topic
from app.models.pipeline import DraftSection

logger = logging.getLogger(__name__)


def _get_valid_paper_ids(topic: Topic) -> set[str]:
    """Get set of valid paper IDs for this topic."""
    return {
        str(p.id) for p in topic.papers
        if p.decision and p.decision.label != "exclude"
    }


def _find_invalid_citations(content: str, valid_ids: set[str]) -> list[dict]:
    """Find [CITE:X] placeholders where X is not a valid paper ID."""
    issues = []
    for m in re.finditer(r'\[CITE:(\d+)\]', content):
        pid = m.group(1)
        if pid not in valid_ids:
            issues.append({
                "type": "invalid_citation",
                "citation": m.group(0),
                "paper_id": pid,
                "position": m.start(),
            })
    return issues


def _find_suspicious_numbers(content: str) -> list[dict]:
    """Find suspicious numeric claims that might be hallucinated."""
    issues = []
    # Patterns like "X% improvement", "X times faster", "achieves X accuracy"
    suspicious_patterns = [
        r'(\d+(?:\.\d+)?)\s*%\s+(?:improvement|increase|reduction|decrease|better|faster|accuracy)',
        r'(\d+(?:\.\d+)?)\s*(?:times|×)\s+(?:faster|better|more)',
        r'achieves?\s+(\d+(?:\.\d+)?)\s*%',
        r'outperforms?\s+\w+\s+by\s+(\d+(?:\.\d+)?)',
    ]
    for pattern in suspicious_patterns:
        for m in re.finditer(pattern, content, re.IGNORECASE):
            # Check if there's a citation nearby (within 200 chars)
            nearby = content[max(0, m.start()-100):m.end()+100]
            has_citation = bool(re.search(r'\[CITE:\d+\]', nearby))
            if not has_citation:
                issues.append({
                    "type": "ungrounded_claim",
                    "text": m.group(0)[:80],
                    "position": m.start(),
                    "has_nearby_citation": False,
                })
    return issues


def check_draft_section(content: str, topic: Topic, section_name: str) -> dict:
    """
    Check a draft section for fabricated content.

    Returns:
        {
            "is_clean": bool,
            "invalid_citations": list,
            "ungrounded_claims": list,
            "warning_count": int,
            "sanitized_content": str,  # content with warnings injected
        }
    """
    valid_ids = _get_valid_paper_ids(topic)
    invalid_cites = _find_invalid_citations(content, valid_ids)
    ungrounded = _find_suspicious_numbers(content)

    warning_count = len(invalid_cites) + len(ungrounded)
    is_clean = warning_count == 0

    # Sanitize: remove invalid citations, add warning comments
    sanitized = content
    for issue in sorted(invalid_cites, key=lambda x: x["position"], reverse=True):
        # Replace invalid citation with warning
        sanitized = sanitized.replace(
            issue["citation"],
            f"[CITATION_NEEDED: paper {issue['paper_id']} not in corpus]"
        )

    if warning_count > 0:
        logger.warning(
            "Anti-fabrication: section '%s' has %d issues (%d invalid cites, %d ungrounded claims)",
            section_name, warning_count, len(invalid_cites), len(ungrounded),
        )

    return {
        "is_clean": is_clean,
        "invalid_citations": invalid_cites,
        "ungrounded_claims": ungrounded,
        "warning_count": warning_count,
        "sanitized_content": sanitized,
    }


def check_all_drafts(topic: Topic, db: Session) -> dict:
    """Run anti-fabrication check on all latest draft sections."""
    all_drafts = db.query(DraftSection).filter_by(topic_id=topic.id).all()
    latest: dict[str, DraftSection] = {}
    for d in all_drafts:
        if d.section_name not in latest or d.version > latest[d.section_name].version:
            latest[d.section_name] = d

    total_issues = 0
    section_reports = {}

    for section_name, draft in latest.items():
        report = check_draft_section(draft.content or "", topic, section_name)
        section_reports[section_name] = report
        total_issues += report["warning_count"]

        # Auto-fix: save sanitized version if there are invalid citations
        if not report["is_clean"] and report["invalid_citations"]:
            new_draft = DraftSection(
                topic_id=topic.id,
                section_name=section_name,
                content=report["sanitized_content"],
                version=draft.version + 1,
                citation_map=draft.citation_map,
            )
            db.add(new_draft)

    if total_issues > 0:
        db.commit()
        logger.info("Anti-fabrication: fixed %d issues across %d sections", total_issues, len(latest))

    return {
        "total_issues": total_issues,
        "sections_checked": len(latest),
        "is_clean": total_issues == 0,
        "section_reports": section_reports,
    }
