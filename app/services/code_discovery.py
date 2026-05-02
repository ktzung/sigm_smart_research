"""
Stage 5b — Code Discovery Service.

For each included paper, find its GitHub repository via:
1. Papers With Code API (best — has paper↔repo mapping with stars/framework)
2. GitHub Search API fallback (for papers not in PwC)

Stores repo URL, stars, and framework in paper.code_repo_url etc.
"""
import logging
import re
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.topic import Topic
from app.models.paper import Paper

logger = logging.getLogger(__name__)

PWC_BASE    = "https://paperswithcode.com/api/v1"
GITHUB_API  = "https://api.github.com"

# Framework detection from repo topics/description
_FRAMEWORK_PATTERNS = {
    "pytorch":     re.compile(r"\bpytorch\b|\btorch\b", re.I),
    "tensorflow":  re.compile(r"\btensorflow\b|\btf\b", re.I),
    "jax":         re.compile(r"\bjax\b|\bflax\b|\bhaiku\b", re.I),
    "keras":       re.compile(r"\bkeras\b", re.I),
    "sklearn":     re.compile(r"\bscikit.learn\b|\bsklearn\b", re.I),
}


def _pwc_headers() -> dict:
    return {"User-Agent": "ResearchPlatform/1.0"}


def _github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_api_token:
        h["Authorization"] = f"Bearer {settings.github_api_token}"
    return h


def _detect_framework(text: str) -> str | None:
    """Detect ML framework from repo description/topics."""
    for fw, pattern in _FRAMEWORK_PATTERNS.items():
        if pattern.search(text):
            return fw
    return None


def find_repo_via_pwc(paper: Paper) -> dict | None:
    """
    Query Papers With Code API to find GitHub repo for a paper.
    Tries arXiv ID first, then title search.
    Returns {url, stars, framework} or None.
    """
    # Try arXiv ID lookup
    arxiv_id = None
    if paper.source_api == "arxiv" and paper.external_id:
        arxiv_id = paper.external_id
    elif paper.url and "arxiv.org" in paper.url:
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", paper.url or "")
        if m:
            arxiv_id = m.group(1)

    if arxiv_id:
        try:
            resp = httpx.get(
                f"{PWC_BASE}/papers/",
                params={"arxiv_id": arxiv_id},
                headers=_pwc_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    paper_id = results[0].get("id")
                    if paper_id:
                        return _get_pwc_repos(paper_id)
        except Exception as e:
            logger.debug("PwC arXiv lookup failed for %s: %s", arxiv_id, e)

    # Fallback: title search
    if paper.title:
        try:
            resp = httpx.get(
                f"{PWC_BASE}/papers/",
                params={"q": paper.title[:100]},
                headers=_pwc_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    paper_id = results[0].get("id")
                    if paper_id:
                        return _get_pwc_repos(paper_id)
        except Exception as e:
            logger.debug("PwC title search failed for paper %d: %s", paper.id, e)

    return None


def _get_pwc_repos(pwc_paper_id: str) -> dict | None:
    """Get repos for a PwC paper ID, return the top one by stars."""
    try:
        resp = httpx.get(
            f"{PWC_BASE}/papers/{pwc_paper_id}/repositories/",
            headers=_pwc_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        repos = resp.json().get("results", [])
        if not repos:
            return None
        # Sort by stars desc, prefer official repos
        repos.sort(key=lambda r: (r.get("is_official", False), r.get("stars", 0)), reverse=True)
        top = repos[0]
        url = top.get("url", "")
        stars = top.get("stars", 0)
        framework = top.get("framework", "") or ""
        if not framework:
            framework = _detect_framework(top.get("description", "") or "")
        return {"url": url, "stars": stars, "framework": framework or None}
    except Exception as e:
        logger.debug("PwC repos fetch failed for %s: %s", pwc_paper_id, e)
        return None


def find_repo_via_github(paper: Paper) -> dict | None:
    """
    Fallback: search GitHub for a repo matching the paper title.
    Less accurate than PwC but covers papers not in PwC database.
    """
    if not settings.github_api_token:
        return None  # Without token, rate limit is too low for bulk search
    if not paper.title:
        return None

    # Build search query: title keywords + common ML repo indicators
    keywords = " ".join(paper.title.split()[:6])
    query = f'"{keywords}" in:name,description,readme'

    try:
        resp = httpx.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 3},
            headers=_github_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        items = resp.json().get("items", [])
        if not items:
            return None
        top = items[0]
        # Only accept if stars > 10 to filter noise
        if top.get("stargazers_count", 0) < 10:
            return None
        desc = (top.get("description") or "") + " ".join(top.get("topics", []))
        framework = _detect_framework(desc)
        return {
            "url": top.get("html_url", ""),
            "stars": top.get("stargazers_count", 0),
            "framework": framework,
        }
    except Exception as e:
        logger.debug("GitHub search failed for paper %d: %s", paper.id, e)
        return None


def discover_code_for_paper(paper: Paper, db: Session) -> bool:
    """
    Find and store GitHub repo for a single paper.
    Returns True if a repo was found.
    """
    # Skip if already has a repo
    if paper.code_repo_url:
        return True

    # Try PwC first
    result = find_repo_via_pwc(paper)

    # Fallback to GitHub search
    if not result:
        result = find_repo_via_github(paper)

    if result and result.get("url"):
        paper.code_repo_url = result["url"]
        paper.code_repo_stars = result.get("stars")
        paper.code_framework = result.get("framework")
        db.commit()
        logger.info(
            "Paper %d: found repo %s (⭐%s, %s)",
            paper.id, result["url"], result.get("stars", "?"), result.get("framework", "unknown"),
        )
        return True

    return False


def discover_code_for_topic(topic: Topic, db: Session) -> dict:
    """
    Run code discovery for all included papers in a topic.
    Returns stats: {found, not_found, skipped}
    """
    included = [
        p for p in topic.papers
        if p.decision and p.decision.label != "exclude"
    ]

    stats = {"found": 0, "not_found": 0, "skipped": 0, "total": len(included)}

    for i, paper in enumerate(included):
        if paper.code_repo_url:
            stats["skipped"] += 1
            continue

        found = discover_code_for_paper(paper, db)
        if found:
            stats["found"] += 1
        else:
            stats["not_found"] += 1

        # Rate limiting: PwC allows ~1 req/sec, GitHub 5000/hr with token
        if i % 5 == 0:
            time.sleep(0.5)

    logger.info(
        "Code discovery for topic %d: found=%d not_found=%d skipped=%d",
        topic.id, stats["found"], stats["not_found"], stats["skipped"],
    )
    return stats
