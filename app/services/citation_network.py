"""
Citation network analysis:
- Find highly-cited papers in the corpus (authority papers)
- Identify citation clusters (research communities)
- Find seminal works via S2 citation data
- Generate citation statistics for the survey
"""
import json
import logging
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.topic import Topic
from app.models.pipeline import SynthesisResult

logger = logging.getLogger(__name__)


def _get_s2_citations(paper_id: str, limit: int = 5) -> list[dict]:
    """Get papers that cite this paper (for influence analysis)."""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    try:
        resp = httpx.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations",
            params={"fields": "title,year,citationCount", "limit": limit},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return [c["citingPaper"] for c in resp.json().get("data", [])]
    except Exception as e:
        logger.debug("S2 citations failed for %s: %s", paper_id, e)
    return []


def _get_s2_references(paper_id: str, limit: int = 10) -> list[dict]:
    """Get papers this paper references (for foundational work detection)."""
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    try:
        resp = httpx.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references",
            params={"fields": "title,year,citationCount", "limit": limit},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return [r["citedPaper"] for r in resp.json().get("data", [])]
    except Exception as e:
        logger.debug("S2 references failed for %s: %s", paper_id, e)
    return []


def analyze_citation_network(topic: Topic, db: Session) -> dict:
    """
    Analyze citation relationships among included papers.
    Returns network stats and identifies authority/hub papers.
    """
    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    s2_papers = [p for p in included if p.external_id and p.source_api == "semantic_scholar"]

    logger.info("Analyzing citation network for %d S2 papers", len(s2_papers))

    # Sort by citation count - top cited are likely authority papers
    by_citations = sorted(
        [p for p in included if p.citation_count],
        key=lambda p: p.citation_count or 0,
        reverse=True,
    )

    authority_papers = [
        {"id": p.id, "title": p.title, "year": p.year, "citations": p.citation_count}
        for p in by_citations[:10]
    ]

    # Year distribution
    year_dist: dict[int, int] = {}
    for p in included:
        if p.year:
            year_dist[p.year] = year_dist.get(p.year, 0) + 1

    # Venue distribution
    venue_dist: dict[str, int] = {}
    for p in included:
        if p.venue:
            v = p.venue[:50]
            venue_dist[v] = venue_dist.get(v, 0) + 1
    top_venues = sorted(venue_dist.items(), key=lambda x: x[1], reverse=True)[:10]

    # Cross-citation within corpus (which included papers cite each other)
    internal_citations: list[dict] = []
    included_ids = {p.external_id for p in s2_papers if p.external_id}

    # Sample top 10 papers for cross-citation check (avoid too many API calls)
    for paper in s2_papers[:10]:
        if not paper.external_id:
            continue
        refs = _get_s2_references(paper.external_id, limit=20)
        for ref in refs:
            ref_id = ref.get("paperId", "")
            if ref_id and ref_id in included_ids:
                internal_citations.append({
                    "from": paper.title[:50],
                    "to": ref.get("title", "")[:50],
                })
        time.sleep(0.3)

    network_stats = {
        "total_included": len(included),
        "with_citation_count": len(by_citations),
        "authority_papers": authority_papers,
        "year_distribution": dict(sorted(year_dist.items())),
        "top_venues": [{"venue": v, "count": c} for v, c in top_venues],
        "internal_citations_found": len(internal_citations),
        "internal_citation_pairs": internal_citations[:20],
    }

    # Store in synthesis result
    existing = (
        db.query(SynthesisResult)
        .filter_by(topic_id=topic.id)
        .order_by(SynthesisResult.created_at.desc())
        .first()
    )
    if existing:
        existing.method_clusters = {
            **(existing.method_clusters or {}),
            "citation_network": network_stats,
        }
        db.commit()

    logger.info("Citation network: %d authority papers, %d internal citations",
                len(authority_papers), len(internal_citations))
    return network_stats
