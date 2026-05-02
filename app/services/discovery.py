"""Paper discovery via Semantic Scholar, arXiv, IEEE, CrossRef, and OpenAlex APIs."""
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.topic import Topic, QueryPlan, QueryBundle
from app.models.paper import Paper, PaperSource

logger = logging.getLogger(__name__)

S2_BASE        = "https://api.semanticscholar.org/graph/v1"
ARXIV_BASE     = "http://export.arxiv.org/api/query"
CROSSREF_BASE  = "https://api.crossref.org/works"
OPENALEX_BASE  = "https://api.openalex.org/works"


def _safe_year(value) -> int | None:
    """Convert a year value to int, returning None for missing or non-numeric values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _s2_search(query: str, limit: int = 20) -> list[dict]:
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,abstract,year,venue,citationCount,externalIds,openAccessPdf,url",
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{S2_BASE}/paper/search", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _arxiv_search(query: str, limit: int = 20) -> list[dict]:
    import xml.etree.ElementTree as ET
    params = {"search_query": f"all:{query}", "max_results": limit, "sortBy": "relevance"}
    with httpx.Client(timeout=30) as client:
        resp = client.get(ARXIV_BASE, params=params)
        resp.raise_for_status()

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall("atom:entry", ns):
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href")
        arxiv_id = entry.findtext("atom:id", "", ns).split("/abs/")[-1]
        results.append({
            "title": (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " "),
            "abstract": (entry.findtext("atom:summary", "", ns) or "").strip(),
            "year": (entry.findtext("atom:published", "", ns) or "")[:4],
            "authors": [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)],
            "pdf_url": pdf_url,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "external_id": arxiv_id,
            "source_api": "arxiv",
        })
    return results


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _crossref_search(query: str, limit: int = 20) -> list[dict]:
    """Search CrossRef for journal/conference papers with DOI."""
    try:
        params = {
            "query": query,
            "rows": limit,
            "select": "title,author,published,container-title,DOI,URL,abstract,is-referenced-by-count,type",
            "filter": "has-abstract:true",
            "sort": "relevance",
        }
        with httpx.Client(timeout=20) as client:
            resp = client.get(CROSSREF_BASE, params=params,
                              headers={"User-Agent": "ResearchPlatform/1.0 (mailto:research@lab.edu)"})
            resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
        results = []
        for item in items:
            title_list = item.get("title", [])
            if not title_list:
                continue
            title = title_list[0]
            authors = [
                f"{a.get('given','')} {a.get('family','')}".strip()
                for a in item.get("author", [])[:8]
            ]
            pub_date = item.get("published", {}).get("date-parts", [[None]])[0]
            year = pub_date[0] if pub_date else None
            venue = (item.get("container-title") or [""])[0]
            doi = item.get("DOI", "")
            results.append({
                "title": title,
                "authors": authors,
                "abstract": item.get("abstract", ""),
                "year": year,
                "venue": venue,
                "citation_count": item.get("is-referenced-by-count"),
                "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                "pdf_url": None,
                "external_id": doi,
                "source_api": "crossref",
                "doi": doi,
            })
        return results
    except Exception as e:
        logger.warning("CrossRef search failed: %s", e)
        return []


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _openalex_search(query: str, limit: int = 25) -> list[dict]:
    """Search OpenAlex — 250M+ works, free, no API key required.
    Best coverage for journal papers, conference proceedings, and books.
    """
    try:
        params = {
            "search": query,
            "per-page": min(limit, 50),
            "select": "id,title,authorships,publication_year,primary_location,open_access,cited_by_count,doi,abstract_inverted_index,type",
            "filter": "has_abstract:true",
            "sort": "relevance_score:desc",
            "mailto": "research@lab.edu",  # polite pool — faster responses
        }
        with httpx.Client(timeout=25) as client:
            resp = client.get(OPENALEX_BASE, params=params)
            resp.raise_for_status()
        results = []
        for item in resp.json().get("results", []):
            title = item.get("title") or ""
            if not title:
                continue

            # Reconstruct abstract from inverted index
            abstract = ""
            inv_idx = item.get("abstract_inverted_index") or {}
            if inv_idx:
                word_positions = [(pos, word) for word, positions in inv_idx.items() for pos in positions]
                word_positions.sort(key=lambda x: x[0])
                abstract = " ".join(w for _, w in word_positions)

            authors = [
                a.get("author", {}).get("display_name", "")
                for a in (item.get("authorships") or [])[:8]
            ]

            loc = item.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name", "")

            oa = item.get("open_access") or {}
            pdf_url = oa.get("oa_url")

            doi = item.get("doi", "")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi.replace("https://doi.org/", "")

            url = f"https://doi.org/{doi}" if doi else item.get("id", "")

            results.append({
                "title": title,
                "authors": [a for a in authors if a],
                "abstract": abstract[:2000],
                "year": item.get("publication_year"),
                "venue": venue,
                "citation_count": item.get("cited_by_count"),
                "url": url,
                "pdf_url": pdf_url,
                "external_id": doi or item.get("id", "").split("/")[-1],
                "source_api": "openalex",
                "doi": doi,
            })
        logger.debug("OpenAlex returned %d results for query: %s", len(results), query[:50])
        return results
    except Exception as e:
        logger.warning("OpenAlex search failed: %s", e)
        return []


def _normalize_s2(item: dict) -> dict:
    pdf_info = item.get("openAccessPdf") or {}
    ext_ids  = item.get("externalIds") or {}
    # Prefer openAccessPdf, fallback to arXiv PDF
    pdf_url = pdf_info.get("url")
    if not pdf_url and ext_ids.get("ArXiv"):
        pdf_url = f"https://arxiv.org/pdf/{ext_ids['ArXiv']}"
    return {
        "title": item.get("title", ""),
        "authors": [a.get("name", "") for a in (item.get("authors") or [])],
        "abstract": item.get("abstract", ""),
        "year": item.get("year"),
        "venue": item.get("venue", ""),
        "citation_count": item.get("citationCount"),
        "url": item.get("url", ""),
        "pdf_url": pdf_url,
        "external_id": item.get("paperId", ""),
        "source_api": "semantic_scholar",
        # Store full externalIds for enrichment later
        "doi": ext_ids.get("DOI"),
        "arxiv_id": ext_ids.get("ArXiv"),
    }


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy deduplication: lowercase, remove punctuation/articles."""
    import re
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)          # remove punctuation
    t = re.sub(r'\b(a|an|the|of|in|on|for|and|with|via|using|based)\b', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _is_duplicate(title: str, existing_normalized: set[str]) -> bool:
    """Check if title is a near-duplicate of any existing title."""
    norm = _normalize_title(title)
    if norm in existing_normalized:
        return True
    # Check for high overlap (handles arXiv vs published version title differences)
    norm_words = set(norm.split())
    if len(norm_words) < 4:
        return False
    for existing in existing_normalized:
        ex_words = set(existing.split())
        if len(ex_words) < 4:
            continue
        overlap = len(norm_words & ex_words) / max(len(norm_words), len(ex_words))
        if overlap >= 0.85:
            return True
    return False


def discover_papers(topic: Topic, plan: QueryPlan, db: Session) -> list[Paper]:
    """Run all query bundles and store discovered papers, deduplicating by title."""
    existing_titles = {p.title.lower() for p in topic.papers}
    existing_normalized = {_normalize_title(t) for t in existing_titles}
    new_papers: list[Paper] = []

    # ── Phase 1: Query-based discovery (S2, arXiv, IEEE, CrossRef, OpenAlex) ──
    for bundle in plan.bundles:
        raw_results: list[dict] = []

        if bundle.source in ("semantic_scholar", "both"):
            try:
                items = _s2_search(bundle.query_text, settings.max_papers_per_query)
                raw_results.extend([_normalize_s2(i) for i in items])
            except Exception as e:
                logger.warning("S2 search failed for bundle %d: %s", bundle.id, e)

        if bundle.source in ("arxiv", "both"):
            try:
                items = _arxiv_search(bundle.query_text, settings.max_papers_per_query)
                raw_results.extend(items)
            except Exception as e:
                logger.warning("arXiv search failed for bundle %d: %s", bundle.id, e)

        # IEEE Open Access — triggered by source="ieee", source="both", or direct label
        if bundle.source in ("ieee", "both") or bundle.label == "direct":
            try:
                from app.services.ieee_enrichment import ieee_discover_oa, _ieee_key_active
                if settings.ieee_api_key and _ieee_key_active():
                    ieee_items = ieee_discover_oa(bundle.query_text, db)
                    raw_results.extend(ieee_items)
            except Exception as e:
                logger.debug("IEEE discovery skipped: %s", e)

        # CrossRef — journal papers with DOI (for direct/adjacent queries)
        if bundle.label in ("direct", "adjacent") and bundle.source in ("both", "semantic_scholar"):
            try:
                cr_items = _crossref_search(bundle.query_text, min(settings.max_papers_per_query, 15))
                raw_results.extend(cr_items)
                logger.debug("CrossRef returned %d items for bundle %d", len(cr_items), bundle.id)
            except Exception as e:
                logger.debug("CrossRef search skipped: %s", e)

        # OpenAlex — 250M+ works, best coverage for journal + conference papers
        try:
            oa_items = _openalex_search(bundle.query_text, min(settings.max_papers_per_query, 25))
            raw_results.extend(oa_items)
            logger.debug("OpenAlex returned %d items for bundle %d", len(oa_items), bundle.id)
        except Exception as e:
            logger.debug("OpenAlex search skipped: %s", e)

        for item in raw_results:
            title_lower = (item.get("title") or "").lower()
            if not title_lower or _is_duplicate(item.get("title", ""), existing_normalized):
                continue
            existing_titles.add(title_lower)
            existing_normalized.add(_normalize_title(item.get("title", "")))

            paper = Paper(
                topic_id=topic.id,
                title=item.get("title", ""),
                authors=item.get("authors"),
                abstract=item.get("abstract"),
                year=_safe_year(item.get("year")),
                venue=item.get("venue"),
                citation_count=item.get("citation_count"),
                url=item.get("url"),
                pdf_url=item.get("pdf_url"),
                external_id=item.get("external_id"),
                source_api=item.get("source_api"),
            )
            db.add(paper)
            db.flush()

            source_record = PaperSource(
                paper_id=paper.id,
                query_bundle_id=bundle.id,
                source_api=item.get("source_api", ""),
                raw_data=item,
            )
            db.add(source_record)
            new_papers.append(paper)

    db.commit()
    logger.info("Discovered %d new papers (query-based) for topic %d", len(new_papers), topic.id)

    # ── Phase 2: Awesome-list discovery (GitHub curated lists) ───────────────
    try:
        from app.services.awesome_discovery import discover_from_awesome_lists
        awesome_items = discover_from_awesome_lists(topic.title, max_repos=5, max_papers=80)
        awesome_added = 0
        for item in awesome_items:
            title_lower = (item.get("title") or "").lower()
            if not title_lower or _is_duplicate(item.get("title", ""), existing_normalized):
                continue
            existing_titles.add(title_lower)
            existing_normalized.add(_normalize_title(item.get("title", "")))
            paper = Paper(
                topic_id=topic.id,
                title=item.get("title", ""),
                authors=item.get("authors"),
                abstract=item.get("abstract"),
                year=_safe_year(item.get("year")),
                venue=item.get("venue"),
                citation_count=item.get("citation_count"),
                url=item.get("url"),
                pdf_url=item.get("pdf_url"),
                external_id=item.get("external_id"),
                source_api=item.get("source_api", "awesome_github"),
            )
            db.add(paper)
            db.flush()
            new_papers.append(paper)
            awesome_added += 1
        if awesome_added:
            db.commit()
            logger.info("Awesome-list added %d new papers for topic %d", awesome_added, topic.id)
    except Exception as e:
        logger.warning("Awesome-list discovery failed: %s", e)

    logger.info("Total discovered: %d papers for topic %d", len(new_papers), topic.id)
    return new_papers


def snowball_citations(topic: Topic, db: Session, max_papers: int = 50) -> list[Paper]:
    """
    Citation snowballing: from included papers, find their references (backward)
    and papers that cite them (forward) via Semantic Scholar.
    Adds newly found papers to the topic.
    """
    from app.models.paper import Paper as PaperModel
    import time

    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    s2_papers = [p for p in included if p.external_id and p.source_api == "semantic_scholar"]

    if not s2_papers:
        logger.info("No S2 papers for snowballing in topic %d", topic.id)
        return []

    existing_titles = {p.title.lower() for p in topic.papers}
    existing_normalized = {_normalize_title(t) for t in existing_titles}
    new_papers: list[Paper] = []

    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    # Sample top-cited papers for snowballing (avoid too many API calls)
    seed_papers = sorted(s2_papers, key=lambda p: p.citation_count or 0, reverse=True)[:10]

    for seed in seed_papers:
        if len(new_papers) >= max_papers:
            break
        try:
            # Backward: references of this paper
            resp = httpx.get(
                f"{S2_BASE}/paper/{seed.external_id}/references",
                params={"fields": "title,authors,abstract,year,venue,citationCount,externalIds,openAccessPdf,url", "limit": 20},
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                refs = [r.get("citedPaper", {}) for r in resp.json().get("data", [])]
                for item in refs:
                    if len(new_papers) >= max_papers:
                        break
                    norm = _normalize_s2(item)
                    if not norm["title"] or _is_duplicate(norm["title"], existing_normalized):
                        continue
                    paper = _add_paper(topic.id, norm, db)
                    if paper:
                        existing_normalized.add(_normalize_title(norm["title"]))
                        new_papers.append(paper)
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Snowball failed for paper %s: %s", seed.external_id, e)

    if new_papers:
        db.commit()
    logger.info("Snowballing added %d papers for topic %d", len(new_papers), topic.id)
    return new_papers


def _add_paper(topic_id: int, item: dict, db: Session) -> "Paper | None":
    """Add a single normalized paper dict to DB."""
    try:
        paper = Paper(
            topic_id=topic_id,
            title=item.get("title", ""),
            authors=item.get("authors"),
            abstract=item.get("abstract"),
            year=_safe_year(item.get("year")),
            venue=item.get("venue"),
            citation_count=item.get("citation_count"),
            url=item.get("url"),
            pdf_url=item.get("pdf_url"),
            external_id=item.get("external_id"),
            source_api=item.get("source_api", "snowball"),
        )
        db.add(paper)
        db.flush()
        return paper
    except Exception as e:
        logger.debug("Failed to add paper: %s", e)
        return None
