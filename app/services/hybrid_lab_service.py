"""Stage 16 — Hybrid Lab Design service."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection, SynthesisResult, TaxonomyCandidate, GapRecord
from app.models.github import GitHubRepo, CodeAnalysis
from app.services.remote_prereqs import get_or_create_remote_execution

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


class HybridLabService:

    def generate_hybrid_design(self, topic: Topic, db: Session) -> DraftSection:
        # Read synthesis result
        synthesis = (
            db.query(SynthesisResult)
            .filter_by(topic_id=topic.id)
            .order_by(SynthesisResult.created_at.desc())
            .first()
        )
        synthesis_text = ""
        if synthesis:
            synthesis_text = "\n".join(filter(None, [
                synthesis.recurring_patterns,
                synthesis.contradictions,
                synthesis.benchmark_coverage,
            ]))

        # Read taxonomy
        taxonomy = (
            db.query(TaxonomyCandidate)
            .filter_by(topic_id=topic.id)
            .order_by(TaxonomyCandidate.created_at.desc())
            .first()
        )
        taxonomy_json = json.dumps(taxonomy.dimensions if taxonomy else {}, indent=2)

        # Read gaps
        gaps = db.query(GapRecord).filter_by(topic_id=topic.id).all()
        gaps_json = json.dumps(
            [{"type": g.gap_type, "description": g.description, "priority": g.priority} for g in gaps],
            indent=2,
        )

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
                    f"README: {(analysis.readme_summary or '')[:600]}"
                )
        if not code_analysis_summary:
            logger.warning(
                "Topic %d: no completed CodeAnalysis found — proceeding without code context",
                topic.id,
            )

        template = _jinja_env.get_template("hybrid_design.j2")
        user_prompt = template.render(
            topic_title=topic.title,
            synthesis_text=synthesis_text,
            taxonomy_json=taxonomy_json,
            gaps_json=gaps_json,
            code_analysis_summary=code_analysis_summary,
        )

        router = get_router()
        content = router.complete_for_stage(
            "stage16",
            "You are a senior ML researcher. Produce a detailed, grounded Hybrid Design Document.",
            user_prompt,
        )

        # Upsert DraftSection
        existing = (
            db.query(DraftSection)
            .filter_by(topic_id=topic.id, section_name="hybrid_design")
            .order_by(DraftSection.version.desc())
            .first()
        )
        version = (existing.version + 1) if existing else 1
        draft = DraftSection(
            topic_id=topic.id,
            section_name="hybrid_design",
            content=content,
            version=version,
        )
        db.add(draft)
        db.commit()

        # Upsert RemoteExecution with status "generated"
        rec = get_or_create_remote_execution(topic.id, db)
        rec.execution_status = "generated"
        db.commit()

        logger.info("Stage 16 hybrid_design generated for topic %d", topic.id)
        return draft


hybrid_lab_service = HybridLabService()
