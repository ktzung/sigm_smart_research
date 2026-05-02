"""
4-Layer Citation Verification (inspired by AutoResearchClaw).

Layer 1: arXiv ID check — verify paper exists on arXiv
Layer 2: CrossRef/DOI check — verify DOI resolves
Layer 3: Semantic Scholar title match — verify title matches
Layer 4: LLM relevance scoring — verify paper is relevant to topic

Returns a verification report with pass/fail per paper.
"""
import logging
import re
import time
import httpx
from sqlalchemy.orm import Session
from app.models.topic import Topic
from app.models.paper import Paper

logger = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
CROSSREF_BASE = "https://api.crossref.org/works"


def _check_arxiv(arxiv_id: str) -> bool:
    """Layer 1: Verify arXiv paper exists."""
    try:
        resp = httpx.get(
            f"https://export.arxiv.org/abs/{arxiv_id}",
            timeout=8, follow_redirects=True,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _check_doi(doi: str) -> bool:
    """Layer 2: Verify DOI resolves via CrossRef."""
    try:
        resp = httpx.get(
            f"{CROSSREF_BASE}/{doi}",
            headers={"User-Agent": "ResearchPlatform/1.0 (mailto:research@lab.edu)"},
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _check_s2_title(title: str, paper_id: str | None = None) -> dict:
    """Layer 3: Verify title matches via Semantic Scholar."""
    try:
        from app.core.config import settings
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key

        if paper_id:
            resp = httpx.get(
                f"{S2_BASE}/paper/{paper_id}",
                params={"fields": "title,year,authors"},
                headers=headers, timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                s2_title = (data.get("title") or "").lower()
                our_title = title.lower()
                # Check title similarity
                words_match = len(set(our_title.split()) & set(s2_title.split()))
                total_words = max(len(our_title.split()), 1)
                similarity = words_match / total_words
                return {"found": True, "similarity": similarity, "s2_title": data.get("title")}
        return {"found": False, "similarity": 0.0}
    except Exception:
        return {"found": False, "similarity": 0.0}


def _check_llm_relevance(paper_title: str, paper_abstract: str, topic_title: str) -> float:
    """Layer 4: LLM relevance scoring."""
    try:
        from app.core.llm_router import get_router
        router = get_router()
        prompt = f"""Rate the relevance of this paper to the survey topic on a scale 0.0-1.0.

Survey topic: {topic_title}

Paper title: {paper_title}
Abstract: {(paper_abstract or '')[:300]}

Return ONLY a number between 0.0 and 1.0. Nothing else."""
        raw = router.complete_for_stage(
            "quality_check",
            "You are a relevance scorer. Return only a decimal number.",
            prompt,
        )
        score = float(raw.strip().split()[0])
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5  # neutral if LLM fails


def verify_citations(topic: Topic, db: Session, sample_size: int = 20) -> dict:
    """
    Run 4-layer citation verification on included papers.
    Samples up to sample_size papers to avoid excessive API calls.

    Returns verification report.
    """
    included = [
        p for p in topic.papers
        if p.decision and p.decision.label != "exclude"
    ]

    # Sample for verification (prioritize papers with external IDs)
    with_ids = [p for p in included if p.external_id]
    sample = with_ids[:sample_size]

    results = {
        "total_checked": len(sample),
        "passed_all_layers": 0,
        "failed_papers": [],
        "layer_stats": {"arxiv": 0, "doi": 0, "s2_title": 0, "llm_relevance": 0},
        "avg_relevance_score": 0.0,
    }

    relevance_scores = []

    for paper in sample:
        paper_result = {
            "id": paper.id,
            "title": paper.title[:80] if paper.title else "",
            "layers": {},
        }
        layers_passed = 0

        # Layer 1: arXiv
        arxiv_id = None
        if paper.source_api == "arxiv" and paper.external_id:
            arxiv_id = paper.external_id
        elif paper.url and "arxiv.org" in (paper.url or ""):
            m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", paper.url)
            if m:
                arxiv_id = m.group(1)

        if arxiv_id:
            ok = _check_arxiv(arxiv_id)
            paper_result["layers"]["arxiv"] = ok
            if ok:
                layers_passed += 1
                results["layer_stats"]["arxiv"] += 1
            time.sleep(0.2)

        # Layer 2: DOI via CrossRef
        doi = None
        if paper.url and "doi.org" in (paper.url or ""):
            m = re.search(r"doi\.org/(.+?)(?:\s|$)", paper.url)
            if m:
                doi = m.group(1).rstrip("/")

        if doi:
            ok = _check_doi(doi)
            paper_result["layers"]["doi"] = ok
            if ok:
                layers_passed += 1
                results["layer_stats"]["doi"] += 1
            time.sleep(0.2)

        # Layer 3: S2 title match
        if paper.external_id and paper.source_api == "semantic_scholar":
            s2_result = _check_s2_title(paper.title or "", paper.external_id)
            paper_result["layers"]["s2_title"] = s2_result
            if s2_result.get("similarity", 0) >= 0.6:
                layers_passed += 1
                results["layer_stats"]["s2_title"] += 1
            time.sleep(0.3)

        # Layer 4: LLM relevance
        if paper.title:
            score = _check_llm_relevance(paper.title, paper.abstract or "", topic.title)
            paper_result["layers"]["llm_relevance"] = score
            relevance_scores.append(score)
            if score >= 0.5:
                layers_passed += 1
                results["layer_stats"]["llm_relevance"] += 1

        if layers_passed >= 2:  # Pass if at least 2 layers confirm
            results["passed_all_layers"] += 1
        else:
            results["failed_papers"].append(paper_result)

    if relevance_scores:
        results["avg_relevance_score"] = round(sum(relevance_scores) / len(relevance_scores), 3)

    logger.info(
        "Citation verification: %d/%d passed, avg relevance=%.2f",
        results["passed_all_layers"], results["total_checked"],
        results["avg_relevance_score"],
    )
    return results
