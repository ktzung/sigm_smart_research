"""GitHub integration endpoints."""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.core.security import encrypt_secret, decrypt_secret
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.github import GitHubRepo, CodeAnalysis
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["github"])


class LinkRepoRequest(BaseModel):
    repo_url: str
    github_token: str | None = None  # for private repos


class SuggestRequest(BaseModel):
    section: str


@router.post("/topics/{topic_id}/github", status_code=201)
def link_github_repo(
    topic_id: int,
    body: LinkRepoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link a GitHub repo to a topic and validate accessibility."""
    # Validate URL format
    if not body.repo_url.startswith("https://github.com/"):
        raise HTTPException(400, detail="Repository URL must start with https://github.com/")

    # Quick accessibility check via GitHub API
    parts = body.repo_url.rstrip("/").split("github.com/")[-1].split("/")
    if len(parts) < 2:
        raise HTTPException(400, detail="Invalid GitHub repository URL format")
    owner, repo_name = parts[0], parts[1]
    headers = {"Accept": "application/vnd.github+json"}
    if body.github_token:
        headers["Authorization"] = f"Bearer {body.github_token}"
    try:
        resp = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}", headers=headers, timeout=10)
        if resp.status_code == 404:
            raise HTTPException(400, detail="Repository not accessible: not found or private")
        if resp.status_code not in (200, 301):
            raise HTTPException(400, detail=f"Repository not accessible: HTTP {resp.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, detail=f"Repository not accessible: {e}")

    encrypted_token = None
    if body.github_token:
        encrypted_token = encrypt_secret(body.github_token)

    gh_repo = GitHubRepo(
        topic_id=topic_id,
        user_id=current_user.id,
        repo_url=body.repo_url,
        encrypted_token=encrypted_token,
        analysis_status="pending",
    )
    db.add(gh_repo)
    db.commit()
    db.refresh(gh_repo)
    audit_service.log_event(
        user_id=current_user.id,
        lab_id=None,
        topic_id=topic_id,
        event_type="github_link",
        event_data={"repo_url": body.repo_url},
        status="success",
        db=db,
    )
    return {"id": gh_repo.id, "repo_url": gh_repo.repo_url, "analysis_status": gh_repo.analysis_status}


@router.post("/topics/{topic_id}/github/refresh")
def refresh_analysis(
    topic_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-run code analysis for the linked GitHub repo (Requirements 2.11)."""
    repo = db.query(GitHubRepo).filter_by(topic_id=topic_id).order_by(GitHubRepo.id.desc()).first()
    if not repo:
        raise HTTPException(404, detail="No GitHub repo linked to this topic")
    if repo.analysis_status == "running":
        raise HTTPException(409, detail="Code analysis already in progress for this repository")
    repo.analysis_status = "pending"
    db.commit()
    return trigger_analysis(topic_id=topic_id, background_tasks=background_tasks, current_user=current_user, db=db)


@router.post("/topics/{topic_id}/github/analyze")
def trigger_analysis(
    topic_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger code analysis for the linked GitHub repo."""
    repo = db.query(GitHubRepo).filter_by(topic_id=topic_id).order_by(GitHubRepo.id.desc()).first()
    if not repo:
        raise HTTPException(404, detail="No GitHub repo linked to this topic")
    if repo.analysis_status == "running":
        raise HTTPException(409, detail="Code analysis already in progress for this repository")

    repo.analysis_status = "running"
    db.commit()
    repo_id = repo.id
    user_id = current_user.id

    def _do_analysis():
        _db = SessionLocal()
        try:
            _repo = _db.query(GitHubRepo).filter_by(id=repo_id).first()
            _run_code_analysis(_repo, _db)
            _repo.analysis_status = "done"
            _db.commit()
            audit_service.log_event(
                user_id=user_id,
                lab_id=None,
                topic_id=topic_id,
                event_type="github_analysis",
                event_data={"repo_id": repo_id, "status": "done"},
                status="success",
                db=_db,
            )
        except Exception as e:
            logger.error("Code analysis failed for repo %d: %s", repo_id, e)
            _repo = _db.query(GitHubRepo).filter_by(id=repo_id).first()
            if _repo:
                _repo.analysis_status = "failed"
                _db.commit()
        finally:
            _db.close()

    background_tasks.add_task(_do_analysis)
    return {"repo_id": repo_id, "status": "running", "message": "Code analysis started in background"}


@router.get("/topics/{topic_id}/github/status")
def get_analysis_status(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current analysis status and progress, including full analysis data when done."""
    repo = db.query(GitHubRepo).filter_by(topic_id=topic_id).order_by(GitHubRepo.id.desc()).first()
    if not repo:
        raise HTTPException(404, detail="No GitHub repo linked to this topic")
    latest = db.query(CodeAnalysis).filter_by(github_repo_id=repo.id).order_by(CodeAnalysis.id.desc()).first()
    result = {
        "repo_id": repo.id,
        "repo_url": repo.repo_url,
        "analysis_status": repo.analysis_status,
        "progress_pct": latest.progress_pct if latest else 0,
        "current_step": latest.current_step if latest else None,
    }
    # Include full analysis data when done
    if latest and repo.analysis_status == "done":
        result["languages"] = latest.languages
        result["key_modules"] = latest.key_modules
        result["dependencies"] = latest.dependencies
        result["readme_summary"] = latest.readme_summary
        result["directory_tree"] = latest.directory_tree
        result["quality_issues"] = latest.quality_issues
    return result


@router.post("/topics/{topic_id}/github/suggest")
def get_impl_suggestion(
    topic_id: int,
    body: SuggestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate implementation suggestion for a paper section using code analysis."""
    from app.models.topic import Topic
    from app.core.llm_router import get_router as get_llm_router

    topic = db.query(Topic).filter_by(id=topic_id).first()
    if not topic:
        raise HTTPException(404, detail="Topic not found")

    repo = db.query(GitHubRepo).filter_by(topic_id=topic_id).order_by(GitHubRepo.id.desc()).first()
    if not repo or repo.analysis_status != "done":
        raise HTTPException(400, detail="Code analysis not complete. Run /analyze first.")

    latest = db.query(CodeAnalysis).filter_by(github_repo_id=repo.id).order_by(CodeAnalysis.id.desc()).first()
    code_context = ""
    if latest:
        code_context = (
            f"Repository: {repo.repo_url}\n"
            f"Languages: {latest.languages}\n"
            f"Key modules: {latest.key_modules}\n"
            f"Dependencies: {latest.dependencies}\n"
            f"README: {(latest.readme_summary or '')[:500]}\n"
        )

    llm_router = get_llm_router()
    suggestion = llm_router.complete_for_stage(
        "draft",
        "You are an expert software engineer helping implement research paper ideas.",
        f"Paper: {topic.title}\nSection: {body.section}\n\nCode context:\n{code_context}\n\n"
        "Generate implementation suggestions (code snippets or pseudocode) for this section.",
    )
    return {"section": body.section, "suggestion": suggestion}


def _run_code_analysis(repo: GitHubRepo, db: Session) -> CodeAnalysis:
    """Fetch repo content and run analysis. Updates progress_pct."""
    import base64

    analysis = CodeAnalysis(github_repo_id=repo.id, progress_pct=0, current_step="Starting")
    db.add(analysis)
    db.commit()

    parts = repo.repo_url.rstrip("/").split("github.com/")[-1].split("/")
    owner, repo_name = parts[0], parts[1]
    headers = {"Accept": "application/vnd.github+json"}
    if repo.encrypted_token:
        try:
            token = decrypt_secret(repo.encrypted_token)
            headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass

    def _update(pct: int, step: str):
        analysis.progress_pct = pct
        analysis.current_step = step
        db.commit()

    _update(10, "Fetching repository metadata")
    meta_resp = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}", headers=headers, timeout=15)
    meta = meta_resp.json() if meta_resp.status_code == 200 else {}  # noqa: F841

    _update(30, "Fetching languages")
    lang_resp = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}/languages", headers=headers, timeout=15)
    languages = lang_resp.json() if lang_resp.status_code == 200 else {}

    _update(50, "Fetching directory tree")
    tree_resp = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/HEAD?recursive=1",
        headers=headers, timeout=15
    )
    tree_data = tree_resp.json() if tree_resp.status_code == 200 else {}
    tree_items = tree_data.get("tree", [])
    dir_tree = "\n".join(
        item["path"] for item in tree_items[:100] if item.get("type") == "blob"
    )

    _update(70, "Fetching README")
    readme_resp = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}/readme", headers=headers, timeout=15)
    readme_summary = ""
    if readme_resp.status_code == 200:
        try:
            content = base64.b64decode(readme_resp.json().get("content", "")).decode("utf-8", errors="ignore")
            readme_summary = content[:2000]
        except Exception:
            pass

    _update(85, "Detecting key modules")
    key_modules = [
        {"path": item["path"], "name": item["path"].split("/")[-1]}
        for item in tree_items
        if item.get("type") == "blob" and item["path"].endswith((".py", ".js", ".ts", ".java", ".go"))
    ][:20]

    _update(95, "Detecting dependencies")
    dependencies: list[str] = []
    for dep_file in ["requirements.txt", "package.json", "go.mod", "pom.xml"]:
        dep_resp = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/contents/{dep_file}",
            headers=headers, timeout=10
        )
        if dep_resp.status_code == 200:
            try:
                raw = base64.b64decode(dep_resp.json().get("content", "")).decode("utf-8", errors="ignore")
                dependencies = [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")][:30]
                break
            except Exception:
                pass

    from datetime import datetime, timezone
    analysis.languages = languages
    analysis.directory_tree = dir_tree
    analysis.key_modules = key_modules
    analysis.readme_summary = readme_summary
    analysis.dependencies = dependencies
    analysis.quality_issues = []
    analysis.progress_pct = 100
    analysis.current_step = "Complete"
    analysis.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return analysis
