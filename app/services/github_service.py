"""GitHub integration service: repo validation, content fetching, code analysis, and LLM suggestions."""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import encrypt_secret, decrypt_secret
from app.core.llm_router import get_router
from app.models.github import GitHubRepo, CodeAnalysis
from app.models.topic import Topic

logger = logging.getLogger(__name__)

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

# ── Pydantic response models ──────────────────────────────────────────────────

class RepoContent(BaseModel):
    languages: dict[str, int]
    directory_tree: str
    key_modules: list[dict]
    readme_summary: str
    dependencies: list[str]


class AnalysisStatus(BaseModel):
    status: str          # pending | running | done | failed
    progress_pct: int    # 0-100
    current_step: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from a GitHub URL. Raises ValueError if not parseable."""
    url = url.rstrip("/")
    # Accept https://github.com/owner/repo or git@github.com:owner/repo
    ssh_match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)
    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"Not a GitHub URL: {url}")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot extract owner/repo from: {url}")
    return parts[0], parts[1].removesuffix(".git")


def _auth_headers(token: Optional[str]) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _build_tree_text(tree_items: list[dict], max_items: int = 200) -> str:
    """Convert GitHub tree API items into a readable directory listing."""
    lines: list[str] = []
    for item in tree_items[:max_items]:
        path: str = item.get("path", "")
        kind: str = item.get("type", "blob")
        prefix = "📁 " if kind == "tree" else "  "
        lines.append(f"{prefix}{path}")
    if len(tree_items) > max_items:
        lines.append(f"  ... ({len(tree_items) - max_items} more items)")
    return "\n".join(lines)


def _extract_dependencies(tree_items: list[dict], owner: str, repo: str, token: Optional[str]) -> list[str]:
    """Best-effort extraction of dependency names from common manifest files."""
    dep_files = {
        "requirements.txt", "requirements-dev.txt", "Pipfile",
        "package.json", "pyproject.toml", "setup.cfg", "setup.py",
        "Gemfile", "go.mod", "pom.xml", "build.gradle",
    }
    paths = {item["path"] for item in tree_items if item.get("type") == "blob"}
    found_file: Optional[str] = None
    for dep_file in dep_files:
        if dep_file in paths:
            found_file = dep_file
            break

    if not found_file:
        return []

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{found_file}"
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=_auth_headers(token))
        if resp.status_code != 200:
            return []
        content_b64 = resp.json().get("content", "")
        raw = base64.b64decode(content_b64).decode(errors="replace")
        deps: list[str] = []
        if found_file in ("requirements.txt", "requirements-dev.txt"):
            for line in raw.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # strip version specifiers
                    pkg = re.split(r"[>=<!;\[]", line)[0].strip()
                    if pkg:
                        deps.append(pkg)
        elif found_file == "package.json":
            import json
            try:
                data = json.loads(raw)
                deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
            except json.JSONDecodeError:
                pass
        elif found_file == "pyproject.toml":
            for line in raw.splitlines():
                m = re.match(r'^\s*"?([A-Za-z0-9_\-]+)', line)
                if m and "=" not in line[:5]:
                    deps.append(m.group(1))
        return deps[:50]
    except Exception as exc:
        logger.warning("Failed to extract dependencies: %s", exc)
        return []


def _identify_key_modules(tree_items: list[dict]) -> list[dict]:
    """Heuristically identify key source modules from the tree."""
    candidates: list[dict] = []
    for item in tree_items:
        if item.get("type") != "blob":
            continue
        path: str = item.get("path", "")
        # Python, JS/TS, Go, Java, Rust source files
        if re.search(r"\.(py|js|ts|go|java|rs|rb|cs)$", path):
            # Prefer top-level or shallow files
            depth = path.count("/")
            candidates.append({"name": path.split("/")[-1], "path": path, "depth": depth})

    # Sort by depth (shallowest first), take top 20
    candidates.sort(key=lambda x: x["depth"])
    result = []
    for c in candidates[:20]:
        result.append({"name": c["name"], "path": c["path"], "description": ""})
    return result


# ── Service ───────────────────────────────────────────────────────────────────

class GitHubService:
    """Handles GitHub repo validation, content fetching, code analysis, and LLM suggestions."""

    # ── Token helpers ─────────────────────────────────────────────────────────

    def store_token(self, token: str) -> str:
        """Encrypt a GitHub token for storage."""
        return encrypt_secret(token)

    def load_token(self, encrypted: Optional[str]) -> Optional[str]:
        """Decrypt a stored GitHub token. Returns None if nothing stored."""
        if not encrypted:
            return None
        try:
            return decrypt_secret(encrypted)
        except Exception:
            return None

    # ── Repo validation ───────────────────────────────────────────────────────

    def validate_repo_url(self, url: str, token: Optional[str] = None) -> bool:
        """
        Parse the GitHub URL and call the GitHub API to verify the repo is accessible.
        Raises HTTP 400 if the URL is invalid or the repo is not accessible.
        Returns True on success.
        """
        try:
            owner, repo = _parse_github_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(api_url, headers=_auth_headers(token))
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not reach GitHub API: {exc}",
            )

        if resp.status_code == 200:
            return True
        if resp.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository not accessible. Check the URL and token.",
            )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository not found: {url}",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub API returned {resp.status_code} for {url}",
        )

    # ── Content fetching ──────────────────────────────────────────────────────

    def fetch_repo_content(self, repo: GitHubRepo) -> RepoContent:
        """
        Fetch repository content via the GitHub API:
        languages, directory tree, README, and dependencies.
        """
        token = self.load_token(repo.encrypted_token)
        owner, repo_name = _parse_github_url(repo.repo_url)
        headers = _auth_headers(token)

        with httpx.Client(timeout=30) as client:
            # Languages
            lang_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}/languages",
                headers=headers,
            )
            languages: dict[str, int] = lang_resp.json() if lang_resp.status_code == 200 else {}

            # Directory tree (recursive)
            tree_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/HEAD",
                headers=headers,
                params={"recursive": "1"},
            )
            tree_items: list[dict] = []
            if tree_resp.status_code == 200:
                tree_items = tree_resp.json().get("tree", [])
            directory_tree = _build_tree_text(tree_items)

            # README
            readme_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}/readme",
                headers=headers,
            )
            readme_summary = ""
            if readme_resp.status_code == 200:
                content_b64 = readme_resp.json().get("content", "")
                try:
                    raw_readme = base64.b64decode(content_b64).decode(errors="replace")
                    # Truncate to first 2000 chars as a summary
                    readme_summary = raw_readme[:2000]
                except Exception:
                    readme_summary = ""

        key_modules = _identify_key_modules(tree_items)
        dependencies = _extract_dependencies(tree_items, owner, repo_name, token)

        return RepoContent(
            languages=languages,
            directory_tree=directory_tree,
            key_modules=key_modules,
            readme_summary=readme_summary,
            dependencies=dependencies,
        )

    # ── Code analysis ─────────────────────────────────────────────────────────

    def run_code_analysis(self, repo: GitHubRepo, db: Session) -> CodeAnalysis:
        """
        Run a full code analysis for the given repo.
        Creates a CodeAnalysis record, updates progress_pct/current_step at each step,
        and persists the final result to the DB.
        """
        # Create analysis record
        analysis = CodeAnalysis(
            github_repo_id=repo.id,
            progress_pct=0,
            current_step="initializing",
        )
        db.add(analysis)
        repo.analysis_status = "running"
        db.commit()
        db.refresh(analysis)

        def _save_progress(pct: int, step: str) -> None:
            analysis.progress_pct = max(0, min(100, pct))
            analysis.current_step = step
            repo.analysis_status = "running"
            db.commit()

        try:
            _save_progress(10, "fetching_languages")
            content = self.fetch_repo_content(repo)

            _save_progress(40, "building_directory_tree")
            analysis.languages = content.languages
            analysis.directory_tree = content.directory_tree
            db.commit()

            _save_progress(60, "identifying_key_modules")
            analysis.key_modules = content.key_modules
            db.commit()

            _save_progress(75, "extracting_dependencies")
            analysis.dependencies = content.dependencies
            db.commit()

            _save_progress(90, "summarizing_readme")
            analysis.readme_summary = content.readme_summary
            db.commit()

            # Mark complete
            analysis.progress_pct = 100
            analysis.current_step = "done"
            analysis.completed_at = _utcnow()
            repo.analysis_status = "done"
            db.commit()
            db.refresh(analysis)

        except Exception as exc:
            logger.error("Code analysis failed for repo %s: %s", repo.id, exc)
            analysis.current_step = "failed"
            repo.analysis_status = "failed"
            db.commit()
            raise

        return analysis

    # ── LLM suggestion ────────────────────────────────────────────────────────

    def generate_impl_suggestion(self, topic: Topic, section: str, db: Session) -> str:
        """
        Generate an implementation suggestion for a given topic section,
        using the latest code analysis as context.
        """
        # Load the most recent completed analysis for this topic's repos
        from sqlalchemy import select
        stmt = (
            select(CodeAnalysis)
            .join(GitHubRepo, CodeAnalysis.github_repo_id == GitHubRepo.id)
            .where(GitHubRepo.topic_id == topic.id)
            .where(GitHubRepo.analysis_status == "done")
            .order_by(CodeAnalysis.completed_at.desc())
            .limit(1)
        )
        analysis: Optional[CodeAnalysis] = db.execute(stmt).scalar_one_or_none()

        code_context = ""
        if analysis:
            langs = ", ".join(f"{k}: {v}" for k, v in (analysis.languages or {}).items())
            deps = ", ".join(analysis.dependencies or [])
            modules = ", ".join(m.get("path", "") for m in (analysis.key_modules or [])[:10])
            code_context = (
                f"Languages: {langs}\n"
                f"Key modules: {modules}\n"
                f"Dependencies: {deps}\n"
                f"README excerpt:\n{(analysis.readme_summary or '')[:500]}\n"
            )

        system_prompt = (
            "You are a research assistant helping to write implementation sections of academic papers. "
            "Use the provided code analysis context to generate accurate, specific suggestions."
        )
        user_prompt = (
            f"Topic: {topic.title}\n"
            f"Section to write: {section}\n\n"
            f"Code analysis context:\n{code_context}\n\n"
            "Generate a concise implementation suggestion for this section, "
            "referencing specific technologies and modules from the codebase."
        )

        router = get_router()
        return router.complete_for_stage(
            stage="draft",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            topic_overrides=topic.model_routing_overrides,
        )

    # ── Status ────────────────────────────────────────────────────────────────

    def get_analysis_status(self, repo_id: int, db: Session) -> dict:
        """Return the current analysis status for a repo."""
        from sqlalchemy import select

        repo = db.get(GitHubRepo, repo_id)
        if not repo:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

        stmt = (
            select(CodeAnalysis)
            .where(CodeAnalysis.github_repo_id == repo_id)
            .order_by(CodeAnalysis.triggered_at.desc())
            .limit(1)
        )
        analysis: Optional[CodeAnalysis] = db.execute(stmt).scalar_one_or_none()

        if not analysis:
            return {
                "status": repo.analysis_status,
                "progress_pct": 0,
                "current_step": "not_started",
            }

        return {
            "status": repo.analysis_status,
            "progress_pct": analysis.progress_pct,
            "current_step": analysis.current_step or "",
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

github_service = GitHubService()
