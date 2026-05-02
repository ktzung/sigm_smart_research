"""
Quality Check stage - runs before LaTeX export:

Layer 1: LanguageTool API (free, open-source) - grammar & style
Layer 2: LLM paraphrase - rewrite AI-sounding sentences
Layer 3: Grammarly Plagiarism API (when credentials available) - originality score

Note on Grammarly API:
  - Requires Grammarly Business/Enterprise plan (NOT personal Pro)
  - Needs Client ID + Client Secret from developer.grammarly.com
  - Uses OAuth 2.0 client_credentials flow
  - Plagiarism check: uploads .txt file, polls for result
"""
import json
import logging
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.topic import Topic
from app.models.pipeline import DraftSection

logger = logging.getLogger(__name__)

LANGUAGETOOL_URL = "https://api.languagetool.org/v2/check"
GRAMMARLY_TOKEN_URL = "https://auth.grammarly.com/v4/api/oauth2/token"
GRAMMARLY_PLAGIARISM_URL = "https://api.grammarly.com/ecosystem/api/v1/plagiarism"


# ── Layer 1: LanguageTool ─────────────────────────────────────────────────────

def check_grammar_languagetool(text: str, language: str = "en-US") -> dict:
    """
    Free grammar/style check via LanguageTool public API.
    Returns {matches: [...], error_count: int, categories: {...}}
    """
    try:
        resp = httpx.post(
            LANGUAGETOOL_URL,
            data={"text": text[:20000], "language": language},  # free tier: 20k chars
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        matches = data.get("matches", [])

        # Categorize issues
        categories: dict[str, int] = {}
        for m in matches:
            cat = m.get("rule", {}).get("category", {}).get("id", "OTHER")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "error_count": len(matches),
            "categories": categories,
            "top_issues": [
                {
                    "message": m.get("message", ""),
                    "context": m.get("context", {}).get("text", "")[:80],
                    "suggestions": [r.get("value") for r in m.get("replacements", [])[:3]],
                    "offset": m.get("offset"),
                    "length": m.get("length"),
                }
                for m in matches[:20]  # top 20 issues
            ],
        }
    except Exception as e:
        logger.warning("LanguageTool check failed: %s", e)
        return {"error_count": -1, "error": str(e)}


# ── Layer 2: LLM Paraphrase ───────────────────────────────────────────────────

def paraphrase_section(section_name: str, content: str, issues: list) -> str:
    """
    Use LLM to improve a section based on grammar issues and reduce AI-sounding text.
    """
    from app.core.llm_router import get_router

    issues_summary = "\n".join(
        f"- {i['message']}: ...{i['context']}..." for i in issues[:10]
    ) if issues else "No specific issues found."

    prompt = f"""You are an expert academic editor improving a survey paper section.

Section: {section_name}

Grammar/Style Issues Found:
{issues_summary}

Original Text:
{content[:4000]}

Instructions:
1. Fix all grammar and style issues listed above
2. Reduce AI-generated patterns (vary sentence structure, avoid repetitive phrases)
3. Maintain all [CITE:paper_id] citation placeholders exactly as-is
4. Keep academic tone and all factual content unchanged
5. Do NOT add new claims or remove existing ones

Return only the improved text, no explanations."""

    router = get_router()
    try:
        improved = router.complete_for_stage(
            "quality_check",
            "You are an expert academic editor. Improve the text while preserving all citations.",
            prompt,
        )
        return improved.strip() if improved.strip() else content
    except Exception as e:
        logger.warning("LLM paraphrase failed for section %s: %s", section_name, e)
        return content


# ── Layer 3: Grammarly Plagiarism API ────────────────────────────────────────

def _get_grammarly_token(scope: str) -> str | None:
    """Get OAuth2 access token from Grammarly."""
    if not settings.grammarly_client_id or not settings.grammarly_client_secret:
        return None
    try:
        resp = httpx.post(
            GRAMMARLY_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.grammarly_client_id,
                "client_secret": settings.grammarly_client_secret,
                "scope": scope,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        logger.warning("Grammarly OAuth failed: %s", e)
        return None


def check_plagiarism_grammarly(text: str) -> dict:
    """
    Check originality via Grammarly Plagiarism Detection API.
    Requires GRAMMARLY_CLIENT_ID + GRAMMARLY_CLIENT_SECRET (Business/Enterprise).

    Flow: POST /plagiarism → upload .txt → GET /plagiarism/{id} (poll)
    Returns: {originality: 0.0-1.0, status: str, available: bool}
    """
    if not settings.grammarly_client_id:
        return {
            "available": False,
            "reason": (
                "Grammarly API requires Business/Enterprise credentials. "
                "Personal Pro account does not include API access. "
                "Get Client ID + Secret at developer.grammarly.com"
            ),
        }

    token = _get_grammarly_token("plagiarism-api:read plagiarism-api:write")
    if not token:
        return {"available": False, "reason": "Failed to obtain Grammarly OAuth token"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "user-agent": "ChimCanhCut-Research-Platform/1.0",
    }

    try:
        # Step 1: Request transaction
        resp = httpx.post(
            GRAMMARLY_PLAGIARISM_URL,
            headers=headers,
            json={"filename": "survey_draft.txt"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        score_request_id = data["score_request_id"]
        upload_url = data["file_upload_url"]

        # Step 2: Upload text as .txt file
        text_bytes = text[:100000].encode("utf-8")  # max 100k chars
        upload_resp = httpx.put(
            upload_url,
            content=text_bytes,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        upload_resp.raise_for_status()

        # Step 3: Poll for result (max 60s)
        for attempt in range(12):
            time.sleep(5)
            result_resp = httpx.get(
                f"{GRAMMARLY_PLAGIARISM_URL}/{score_request_id}",
                headers=headers,
                timeout=15,
            )
            result_resp.raise_for_status()
            result = result_resp.json()
            status = result.get("status")

            if status == "COMPLETED":
                score = result.get("score", {})
                originality = score.get("originality")
                return {
                    "available": True,
                    "status": "COMPLETED",
                    "originality": originality,
                    "originality_pct": f"{originality * 100:.1f}%" if originality else "N/A",
                    "assessment": (
                        "High originality" if originality and originality >= 0.85
                        else "Moderate originality - review flagged sections"
                        if originality and originality >= 0.70
                        else "Low originality - significant revision needed"
                    ),
                }
            elif status == "FAILED":
                return {"available": True, "status": "FAILED",
                        "reason": result.get("error_reason", "Unknown")}

        return {"available": True, "status": "TIMEOUT",
                "reason": "Grammarly did not return result within 60s"}

    except Exception as e:
        logger.error("Grammarly plagiarism check failed: %s", e)
        return {"available": True, "status": "ERROR", "reason": str(e)}


# ── Main stage function ───────────────────────────────────────────────────────

def run_quality_check(topic: Topic, db: Session, paraphrase: bool = True) -> dict:
    """
    Run full quality check pipeline on all draft sections.
    Returns comprehensive quality report.
    """
    # Get latest drafts
    all_drafts = db.query(DraftSection).filter_by(topic_id=topic.id).all()
    latest: dict[str, DraftSection] = {}
    for d in all_drafts:
        if d.section_name not in latest or d.version > latest[d.section_name].version:
            latest[d.section_name] = d

    if not latest:
        raise ValueError("No draft sections found. Run the draft stage first.")

    full_text = "\n\n".join(
        f"=== {name.upper()} ===\n{d.content}"
        for name, d in latest.items()
    )

    report: dict = {
        "sections_checked": len(latest),
        "grammar": {},
        "paraphrase": {},
        "plagiarism": {},
    }

    # Layer 1: Grammar check on full text
    logger.info("Running LanguageTool grammar check...")
    grammar_result = check_grammar_languagetool(full_text)
    report["grammar"] = grammar_result
    logger.info("Grammar: %d issues found", grammar_result.get("error_count", 0))

    # Layer 2: LLM paraphrase per section (if enabled)
    if paraphrase:
        logger.info("Running LLM paraphrase on %d sections...", len(latest))
        paraphrase_stats = {"sections_improved": 0, "sections_unchanged": 0}
        for section_name, draft in latest.items():
            # Only paraphrase if grammar issues found or section is long enough
            if len(draft.content) < 200:
                continue
            improved = paraphrase_section(
                section_name, draft.content,
                grammar_result.get("top_issues", []),
            )
            if improved != draft.content:
                # Save as new version
                new_draft = DraftSection(
                    topic_id=topic.id,
                    section_name=section_name,
                    content=improved,
                    version=draft.version + 1,
                    citation_map=draft.citation_map,
                )
                db.add(new_draft)
                paraphrase_stats["sections_improved"] += 1
            else:
                paraphrase_stats["sections_unchanged"] += 1
        db.commit()
        report["paraphrase"] = paraphrase_stats
        logger.info("Paraphrase: %d sections improved", paraphrase_stats["sections_improved"])

    # Layer 3: Grammarly plagiarism check
    logger.info("Running Grammarly plagiarism check...")
    plagiarism_result = check_plagiarism_grammarly(full_text)
    report["plagiarism"] = plagiarism_result

    return report
