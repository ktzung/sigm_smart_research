"""
Awesome-list discovery: search GitHub for curated "awesome-{topic}" lists,
parse paper links from README, then resolve metadata via S2/CrossRef/OpenAlex.

Flow:
  1. GitHub Search API → find "awesome-{topic}" repos
  2. Fetch README.md of each repo
  3. Extract paper links (arxiv, doi, proceedings, ACL, etc.)
  4. Resolve each link to paper metadata
  5. Return normalized paper dicts
"""
import re
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
S2_BASE    = "https://api.semanticscholar.org/graph/v1"

# Patterns that indicate a link points to a paper
_PAPER_URL_PATTERNS = [
    re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I),
    re.compile(r"doi\.org/(.+?)(?:\s|\"|\)|\]|$)", re.I),
    re.compile(r"proceedings\.mlr\.press/v\d+/\w+\.html", re.I),
    re.compile(r"openreview\.net/forum\?id=", re.I),
    re.compile(r"aclanthology\.org/\S+", re.I),
    re.compile(r"papers\.nips\.cc/paper/", re.I),
    re.compile(r"ieeexplore\.ieee\.org/document/\d+", re.I),
    re.compile(r"dl\.acm\.org/doi/", re.I),
    re.compile(r"semanticscholar\.org/paper/[a-f0-9]{40}", re.I),
]

# Markdown link pattern: [text](url)
_MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')


def _github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_api_token:
        h["Authorization"] = f"Bearer {settings.github_api_token}"
    return h


def _search_awesome_repos(topic: str, max_repos: int = 5) -> list[dict]:
    """Search GitHub for awesome-list repos matching the topic."""
    queries = [
        f"awesome {topic} in:name,description",
        f"awesome-{topic.replace(' ', '-')} in:name",
    ]
    repos = []
    seen_ids = set()
    headers = _github_headers()

    for q in queries:
        try:
            resp = httpx.get(
                f"{GITHUB_API}/search/repositories",
                params={"q": q, "sort": "stars", "order": "desc", "per_page": 5},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            for r in resp.json().get("items", []):
                if r["id"] not in seen_ids and r.get("stargazers_count", 0) >= 50:
                    seen_ids.add(r["id"])
                    repos.append(r)
                    if len(repos) >= max_repos:
                        return repos
        except Exception as e:
            logger.warning("GitHub search failed for query '%s': %s", q, e)

    return repos[:max_repos]


def _fetch_readme(owner: str, repo: str) -> str:
    """Fetch raw README content."""
    headers = _github_headers()
    for branch in ("main", "master"):
        try:
            resp = httpx.get(
                f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
    return ""


def _extract_paper_links(readme: str) -> list[tuple[str, str]]:
    """Extract (title, url) pairs that look like paper links from README markdown."""
    results = []
    seen_urls = set()

    for title, url in _MD_LINK.findall(readme):
        url = url.strip().rstrip(")")
        if url in seen_urls:
            continue
        # Check if URL matches any paper pattern
        if any(p.search(url) for p in _PAPER_URL_PATTERNS):
            seen_urls.add(url)
            results.append((title.strip(), url))

    return results


def _resolve_arxiv(arxiv_id: str) -> dict | None:
    """Resolve arXiv ID to paper metadata via S2."""
    try:
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key
        resp = httpx.get(
            f"{S2_BASE}/paper/arXiv:{arxiv_id}",
            params={"fields": "title,authors,abstract,year,venue,citationCount,externalIds,openAccessPdf,url"},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            ext = d.get("externalIds") or {}
            pdf = (d.get("openAccessPdf") or {}).get("url") or f"https://arxiv.org/pdf/{arxiv_id}"
            return {
                "title": d.get("title", ""),
                "authors": [a.get("name", "") for a in (d.get("authors") or [])[:8]],
                "abstract": d.get("abstract", ""),
                "year": d.get("year"),
                "venue": d.get("venue", "arXiv"),
                "citation_count": d.get("citationCount"),
                "url": d.get("url") or f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": pdf,
                "external_id": arxiv_id,
                "source_api": "awesome_github",
                "doi": ext.get("DOI"),
            }
    except Exception as e:
        logger.debug("arXiv resolve failed for %s: %s", arxiv_id, e)
    return None


def _resolve_doi(doi: str, fallback_title: str = "") -> dict | None:
    """Resolve DOI via CrossRef."""
    try:
        resp = httpx.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "ResearchPlatform/1.0 (mailto:research@lab.edu)"},
            timeout=10,
        )
        if resp.status_code == 200:
            m = resp.json().get("message", {})
            title_list = m.get("title", [fallback_title])
            title = title_list[0] if title_list else fallback_title
            authors = [
                f"{a.get('given','')} {a.get('family','')}".strip()
                for a in m.get("author", [])[:8]
            ]
            pub = m.get("published", {}).get("date-parts", [[None]])[0]
            year = pub[0] if pub else None
            venue = (m.get("container-title") or [""])[0]
            return {
                "title": title,
                "authors": [a for a in authors if a],
                "abstract": m.get("abstract", ""),
                "year": year,
                "venue": venue,
                "citation_count": m.get("is-referenced-by-count"),
                "url": f"https://doi.org/{doi}",
                "pdf_url": None,
                "external_id": doi,
                "source_api": "awesome_github",
                "doi": doi,
            }
    except Exception as e:
        logger.debug("DOI resolve failed for %s: %s", doi, e)
    return None


def _resolve_link(title: str, url: str) -> dict | None:
    """Resolve a paper URL to metadata."""
    # arXiv
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url, re.I)
    if m:
        return _resolve_arxiv(m.group(1))

    # DOI
    m = re.search(r"doi\.org/(.+?)(?:\s|\"|\)|\]|$)", url, re.I)
    if m:
        return _resolve_doi(m.group(1).rstrip("/"), title)

    # Semantic Scholar direct link
    m = re.search(r"semanticscholar\.org/paper/[^/]+/([a-f0-9]{40})", url, re.I)
    if m:
        try:
            headers = {}
            if settings.semantic_scholar_api_key:
                headers["x-api-key"] = settings.semantic_scholar_api_key
            resp = httpx.get(
                f"{S2_BASE}/paper/{m.group(1)}",
                params={"fields": "title,authors,abstract,year,venue,citationCount,externalIds,openAccessPdf,url"},
                headers=headers, timeout=10,
            )
            if resp.status_code == 200:
                d = resp.json()
                ext = d.get("externalIds") or {}
                return {
                    "title": d.get("title", title),
                    "authors": [a.get("name", "") for a in (d.get("authors") or [])[:8]],
                    "abstract": d.get("abstract", ""),
                    "year": d.get("year"),
                    "venue": d.get("venue", ""),
                    "citation_count": d.get("citationCount"),
                    "url": d.get("url", url),
                    "pdf_url": (d.get("openAccessPdf") or {}).get("url"),
                    "external_id": m.group(1),
                    "source_api": "awesome_github",
                    "doi": ext.get("DOI"),
                }
        except Exception:
            pass

    # Fallback: return minimal record with just title and URL
    if title and len(title) > 10:
        return {
            "title": title,
            "authors": [],
            "abstract": "",
            "year": None,
            "venue": "",
            "citation_count": None,
            "url": url,
            "pdf_url": None,
            "external_id": url,
            "source_api": "awesome_github",
            "doi": None,
        }
    return None


def discover_from_awesome_lists(topic_title: str, max_repos: int = 5, max_papers: int = 100) -> list[dict]:
    """
    Main entry point: find awesome-lists for topic and extract paper metadata.

    Returns list of normalized paper dicts (same format as discovery.py).
    """
    if not settings.github_api_token:
        logger.info("GITHUB_API_TOKEN not set — awesome-list discovery skipped (rate limit: 60 req/hr)")
        return []

    logger.info("Searching GitHub awesome-lists for topic: %s", topic_title)

    # Use key terms from topic title for search
    search_term = " ".join(topic_title.split()[:4])  # first 4 words
    repos = _search_awesome_repos(search_term, max_repos)

    if not repos:
        logger.info("No awesome-list repos found for: %s", search_term)
        return []

    logger.info("Found %d awesome-list repos", len(repos))

    all_papers: list[dict] = []
    seen_titles: set[str] = set()

    for repo in repos:
        owner = repo["owner"]["login"]
        name  = repo["name"]
        stars = repo.get("stargazers_count", 0)
        logger.info("Processing %s/%s (⭐ %d)", owner, name, stars)

        readme = _fetch_readme(owner, name)
        if not readme:
            continue

        links = _extract_paper_links(readme)
        logger.info("  Found %d paper links in %s/%s", len(links), owner, name)

        for title, url in links:
            if len(all_papers) >= max_papers:
                break
            paper = _resolve_link(title, url)
            if not paper or not paper.get("title"):
                continue
            title_lower = paper["title"].lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
            all_papers.append(paper)

        if len(all_papers) >= max_papers:
            break

    logger.info("Awesome-list discovery: %d unique papers from %d repos", len(all_papers), len(repos))
    return all_papers
