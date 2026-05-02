"""
IEEE Xplore API enrichment.
Adds richer metadata and open-access PDF URLs for IEEE papers.

Note: IEEE API key requires manual activation by IEEE (1-2 business days).
Check status at: https://developer.ieee.org/
"""
import logging
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.paper import Paper
from app.services.ingestion import download_pdf, parse_pdf

logger = logging.getLogger(__name__)

IEEE_SEARCH_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
IEEE_DOI_URL    = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


def _ieee_key_active() -> bool:
    """Quick check if IEEE key is active."""
    if not settings.ieee_api_key:
        return False
    try:
        resp = httpx.get(
            IEEE_SEARCH_URL,
            params={"apikey": settings.ieee_api_key, "querytext": "test", "max_records": 1},
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _ieee_lookup_doi(doi: str) -> dict | None:
    """Look up a single paper by DOI via IEEE API."""
    try:
        resp = httpx.get(
            IEEE_SEARCH_URL,
            params={
                "apikey": settings.ieee_api_key,
                "doi": doi,
                "max_records": 1,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        articles = resp.json().get("articles", [])
        return articles[0] if articles else None
    except Exception as e:
        logger.debug("IEEE DOI lookup failed for %s: %s", doi, e)
        return None


def _ieee_search_oa(query: str, max_records: int = 25) -> list[dict]:
    """Search IEEE Open Access articles."""
    try:
        resp = httpx.get(
            IEEE_SEARCH_URL,
            params={
                "apikey": settings.ieee_api_key,
                "querytext": query,
                "open_access": "True",
                "max_records": max_records,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("articles", [])
    except Exception as e:
        logger.warning("IEEE OA search failed: %s", e)
    return []


def enrich_with_ieee(papers: list[Paper], doi_map: dict[int, str], db: Session) -> dict:
    """
    Enrich papers using IEEE API:
    1. DOI lookup → check access_type, get pdf_url for OA papers
    2. Download PDF if open_access
    Returns stats.
    """
    if not settings.ieee_api_key:
        return {"skipped": "no IEEE API key configured"}

    # Check if key is active
    if not _ieee_key_active():
        return {"skipped": "IEEE API key not yet activated (pending IEEE approval)"}

    stats = {"checked": 0, "oa_found": 0, "pdf_downloaded": 0, "errors": 0}
    ieee_papers = [(p, doi_map[p.id]) for p in papers if p.id in doi_map]

    for paper, doi in ieee_papers:
        try:
            art = _ieee_lookup_doi(doi)
            stats["checked"] += 1
            if not art:
                continue

            access_type = art.get("access_type", "")
            pdf_url     = art.get("pdf_url", "")
            abstract    = art.get("abstract", "")

            # Update abstract if richer
            if abstract and len(abstract) > len(paper.abstract or ""):
                paper.abstract = abstract
                db.commit()

            if access_type == "open_access" and pdf_url:
                stats["oa_found"] += 1
                paper.pdf_url = pdf_url
                paper.parsed  = False
                db.commit()
                downloaded = download_pdf(paper, db)
                if downloaded:
                    parse_pdf(paper, db)
                    stats["pdf_downloaded"] += 1
                    logger.info("IEEE OA PDF downloaded for paper %d", paper.id)

            time.sleep(0.1)  # IEEE rate limit: 10 req/s
        except Exception as e:
            stats["errors"] += 1
            logger.warning("IEEE enrich failed for paper %d: %s", paper.id, e)

    return stats


def ieee_discover_oa(topic_title: str, db: Session) -> list[dict]:
    """
    Search IEEE for Open Access papers on the topic.
    Returns list of paper metadata dicts for new papers to add.
    """
    if not _ieee_key_active():
        logger.info("IEEE API not active, skipping OA discovery")
        return []

    articles = _ieee_search_oa(topic_title, max_records=25)
    results = []
    for art in articles:
        results.append({
            "title":        art.get("title", ""),
            "authors":      [a.get("full_name", "") for a in art.get("authors", {}).get("authors", [])],
            "abstract":     art.get("abstract", ""),
            "year":         art.get("publication_year"),
            "venue":        art.get("publication_title", ""),
            "citation_count": art.get("citing_paper_count"),
            "url":          art.get("html_url", ""),
            "pdf_url":      art.get("pdf_url", ""),
            "external_id":  art.get("doi", ""),
            "source_api":   "ieee",
            "doi":          art.get("doi", ""),
        })
    logger.info("IEEE OA discovery found %d papers", len(results))
    return results
