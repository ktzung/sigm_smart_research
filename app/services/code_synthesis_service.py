"""Stage 17 — Code Synthesis service."""
import json
import logging
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection
from app.models.github import GitHubRepo, CodeAnalysis
from app.services.remote_prereqs import require_stage_done

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

# Maps section delimiter → DraftSection section_name
_SECTION_MAP = {
    "train.py": "code_train",
    "config.yaml": "code_config",
    "requirements.txt": "code_requirements",
}


def _parse_llm_output(text: str) -> dict[str, str]:
    """Parse LLM output into {section_name: content} using ### headers as delimiters."""
    result: dict[str, str] = {}
    pattern = re.compile(r"^###\s+(train\.py|config\.yaml|requirements\.txt)\s*$", re.MULTILINE)
    parts = pattern.split(text)
    # parts[0] is preamble, then alternating: header, content
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Strip markdown code fences if present
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        section_name = _SECTION_MAP.get(header)
        if section_name:
            result[section_name] = content.strip()
    return result


def _upsert_draft(topic_id: int, section_name: str, content: str, db: Session) -> DraftSection:
    existing = (
        db.query(DraftSection)
        .filter_by(topic_id=topic_id, section_name=section_name)
        .order_by(DraftSection.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1
    draft = DraftSection(topic_id=topic_id, section_name=section_name, content=content, version=version)
    db.add(draft)
    return draft


class CodeSynthesisService:

    def synthesize_code(self, topic: Topic, db: Session) -> list[DraftSection]:
        require_stage_done(topic.id, "stage16", db)

        # Read hybrid_design DraftSection
        hybrid_draft = (
            db.query(DraftSection)
            .filter_by(topic_id=topic.id, section_name="hybrid_design")
            .order_by(DraftSection.version.desc())
            .first()
        )
        hybrid_design_content = hybrid_draft.content if hybrid_draft else ""

        # Read latest CodeAnalysis (optional)
        code_analysis_summary = None
        repo = (
            db.query(GitHubRepo)
            .filter_by(topic_id=topic.id)
            .order_by(GitHubRepo.id.desc())
            .first()
        )
        if repo and repo.analysis_status == "done":
            analysis = (
                db.query(CodeAnalysis)
                .filter_by(github_repo_id=repo.id)
                .order_by(CodeAnalysis.id.desc())
                .first()
            )
            if analysis:
                code_analysis_summary = (
                    f"Languages: {json.dumps(analysis.languages)}\n"
                    f"Dependencies: {json.dumps(analysis.dependencies)}\n"
                    f"Key Modules: {json.dumps(analysis.key_modules)}"
                )

        # Build extraction summary from paper extractions
        extraction_records = []
        for paper in topic.papers:
            if paper.extraction:
                extraction_records.append({
                    "title": paper.title,
                    "method": paper.extraction.method_type,
                    "dataset": paper.extraction.dataset_name,
                })
        extraction_summary = json.dumps(extraction_records[:20], indent=2) if extraction_records else None

        template = _jinja_env.get_template("code_synthesis.j2")
        user_prompt = template.render(
            hybrid_design_content=hybrid_design_content,
            extraction_summary=extraction_summary,
            code_analysis_summary=code_analysis_summary,
        )

        router = get_router()
        llm_output = router.complete_for_stage(
            "stage17",
            "You are an expert ML engineer. Generate complete, runnable experiment code.",
            user_prompt,
        )

        parsed = _parse_llm_output(llm_output)

        # Ensure all three sections are present (fallback to empty string)
        drafts: list[DraftSection] = []
        for section_name in ["code_train", "code_config", "code_requirements"]:
            content = parsed.get(section_name, f"# {section_name} — generation failed\n")
            draft = _upsert_draft(topic.id, section_name, content, db)
            drafts.append(draft)

        db.commit()
        logger.info("Stage 17 code synthesis complete for topic %d (%d sections)", topic.id, len(drafts))
        return drafts


code_synthesis_service = CodeSynthesisService()
