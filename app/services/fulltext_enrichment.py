"""
Enrich abstract-only papers with full text using 3 methods (in order):
  1. Semantic Scholar BATCH API  → get TLDR, arXiv ID, openAccessPdf URL
  2. arXiv PDF download          → for papers with arXiv ID from S2
  3. Unpaywall API               → for papers with DOI (from S2 externalIds)
"""
import logging
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.paper import Paper
from app.services.ingestion import download_pdf, parse_pdf

logger = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_FIELDS    = "abstract,tldr,openAccessPdf,externalIds"
BATCH_SIZE   = 50  # S2 allows up to 500, but 50 is safe


def _s2_batch_enrich(papers: list[Paper], db: Session) -> dict[int, dict]:
    """
    Fetch richer metadata for a batch of papers from S2.
    Returns {paper_id: {pdf_url, arxiv_id, doi, tldr, abstract}}
    """
    s2_papers = [p for p in papers if p.external_id and p.source_api == "semantic_scholar"]
    if not s2_papers:
        return {}

    headers = {"Content-Type": "application/json"}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    results: dict[int, dict] = {}
    for i in range(0, len(s2_papers), BATCH_SIZE):
        batch = s2_papers[i:i + BATCH_SIZE]
        ids   = [p.external_id for p in batch]
        try:
            resp = httpx.post(
                S2_BATCH_URL,
                headers=headers,
                params={"fields": S2_FIELDS},
                json={"ids": ids},
                timeout=20,
            )
            if resp.status_code != 200:
                logger.warning("S2 batch failed: %d %s", resp.status_code, resp.text[:100])
                continue
            data_list = resp.json()
            for paper, data in zip(batch, data_list):
                if not data:
                    continue
                ext_ids  = data.get("externalIds") or {}
                pdf_info = data.get("openAccessPdf") or {}
                arxiv_id = ext_ids.get("ArXiv")
                doi      = ext_ids.get("DOI")
                pdf_url  = pdf_info.get("url")
                # Fallback: construct arXiv PDF URL
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                tldr = (data.get("tldr") or {}).get("text", "")
                results[paper.id] = {
                    "pdf_url":  pdf_url,
                    "arxiv_id": arxiv_id,
                    "doi":      doi,
                    "tldr":     tldr,
                    "abstract": data.get("abstract") or "",
                }
        except Exception as e:
            logger.warning("S2 batch error: %s", e)
        time.sleep(0.5)  # be polite

    return results


def _unpaywall_get_pdf(doi: str) -> str | None:
    """Get open-access PDF URL from Unpaywall for a given DOI."""
    try:
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": "research-platform@example.com"},
            timeout=8,
        )
        if resp.status_code == 200:
            best = resp.json().get("best_oa_location") or {}
            return best.get("url_for_pdf")
    except Exception as e:
        logger.debug("Unpaywall failed for doi %s: %s", doi, e)
    return None


def enrich_paper(paper: Paper, s2_data: dict | None, db: Session) -> dict:
    """
    Enrich a single abstract-only paper using available data.
    Priority: S2 openAccessPdf > arXiv PDF > Unpaywall
    """
    result = {"method": None, "pdf_found": False, "downloaded": False,
              "chunks_before": len(paper.chunks), "chunks_after": 0}

    if not s2_data:
        return result

    # Update TLDR / richer abstract
    if s2_data.get("tldr") and not paper.abstract:
        paper.abstract = s2_data["tldr"]
        db.commit()

    if s2_data.get("abstract") and len(s2_data["abstract"]) > len(paper.abstract or ""):
        paper.abstract = s2_data["abstract"]
        db.commit()

    # Try to get PDF URL
    pdf_url = s2_data.get("pdf_url")

    # Method 3: Unpaywall fallback if we have DOI but no PDF yet
    if not pdf_url and s2_data.get("doi"):
        pdf_url = _unpaywall_get_pdf(s2_data["doi"])
        if pdf_url:
            result["method"] = "unpaywall"
            logger.info("Unpaywall found PDF for paper %d", paper.id)

    if not pdf_url:
        # Still no PDF - update abstract chunk with richer text and return
        if s2_data.get("tldr") or s2_data.get("abstract"):
            paper.parsed = False  # force re-parse with richer abstract
            db.commit()
            chunks = parse_pdf(paper, db)
            result["chunks_after"] = len(chunks)
        return result

    # We have a PDF URL - update and download
    result["pdf_found"] = True
    if not result["method"]:
        result["method"] = "arxiv" if "arxiv.org" in pdf_url else "s2_oa"

    paper.pdf_url = pdf_url
    paper.parsed  = False  # force re-parse
    db.commit()

    downloaded = download_pdf(paper, db)
    result["downloaded"] = downloaded

    chunks = parse_pdf(paper, db)
    result["chunks_after"] = len(chunks)
    return result


def enrich_all_abstract_only(topic_id: int, db: Session) -> dict:
    """
    Enrich all abstract-only papers for a topic using all methods:
    1. S2 batch → arXiv ID → PDF download
    2. Unpaywall → DOI → OA PDF
    3. IEEE Xplore → DOI → OA PDF (when key is active)
    """
    from app.models.topic import Topic
    topic = db.query(Topic).filter_by(id=topic_id).first()
    included      = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]

    if not abstract_only:
        return {"total": 0, "enriched": 0, "pdf_downloaded": 0, "richer_abstract": 0}

    logger.info("Enriching %d abstract-only papers", len(abstract_only))

    # Step 1: S2 batch (gets arXiv IDs + OA PDF URLs + DOIs)
    s2_results = _s2_batch_enrich(abstract_only, db)
    doi_map = {p.id: s2_results[p.id]["doi"]
               for p in abstract_only
               if p.id in s2_results and s2_results[p.id].get("doi")}

    stats = {"total": len(abstract_only), "enriched": 0,
             "pdf_downloaded": 0, "richer_abstract": 0,
             "methods": {"arxiv": 0, "s2_oa": 0, "unpaywall": 0, "ieee": 0}}

    for paper in abstract_only:
        s2_data = s2_results.get(paper.id)
        chunks_before = len(paper.chunks)
        result = enrich_paper(paper, s2_data, db)
        if result["downloaded"]:
            stats["pdf_downloaded"] += 1
            stats["enriched"] += 1
            m = result.get("method", "arxiv")
            stats["methods"][m] = stats["methods"].get(m, 0) + 1
        elif result["chunks_after"] > chunks_before:
            stats["richer_abstract"] += 1
            stats["enriched"] += 1

    # Step 2: IEEE Xplore for remaining abstract-only papers
    still_abstract = [p for p in abstract_only if p.parsed and len(p.chunks) <= 1]
    if still_abstract and settings.ieee_api_key:
        from app.services.ieee_enrichment import enrich_with_ieee
        ieee_stats = enrich_with_ieee(still_abstract, doi_map, db)
        if isinstance(ieee_stats, dict) and ieee_stats.get("pdf_downloaded"):
            stats["pdf_downloaded"] += ieee_stats["pdf_downloaded"]
            stats["enriched"]       += ieee_stats["pdf_downloaded"]
            stats["methods"]["ieee"] = ieee_stats["pdf_downloaded"]
        logger.info("IEEE enrichment: %s", ieee_stats)

    logger.info("Enrichment complete: %s", stats)
    return stats
