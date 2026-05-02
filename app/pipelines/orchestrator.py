"""End-to-end pipeline orchestrator."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.topic import Topic
from app.models.pipeline import PipelineRun
from app.models.github import GitHubRepo, CodeAnalysis
from app.services.audit_service import audit_service
from app.services import (
    query_planning, discovery, screening,
    ingestion, extraction, synthesis,
    taxonomy, gap_analysis, writing, reviewer,
)
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731

# ── Stage groups ──────────────────────────────────────────────────────────────
STAGES_CORE = [
    "query_plan",   # 1. Generate search queries
    "discover",     # 2. Fetch papers from S2 + arXiv
    "screen",       # 3. LLM relevance scoring
    "ingest",       # 4. PDF download + parse
    "extract",      # 5. Structured knowledge extraction
    "synthesize",   # 6. Cross-paper synthesis
    "taxonomy",     # 7. Multi-dimensional taxonomy
    "gaps",         # 8. Research gap analysis
    "idea_generation",  # 9. Novel research ideas (Claude Sonnet, Socratic)
    "draft",        # 10. Section drafts
    "review",       # 11. Reviewer simulation
]

STAGES_Q1 = [
    "prisma",           # 11. PRISMA methodology documentation
    "citation_network", # 12. Citation authority + cluster analysis
    "revision",         # 13. Revise drafts based on review feedback
    "quality_check",    # 14. Grammar + paraphrase + plagiarism check
    "export_latex",     # 15. LaTeX + BibTeX for journal submission
    "view_pdf",         # 16. View & download compiled PDF
]

STAGES_REMOTE = [
    "stage16",  # Hybrid Lab Design
    "stage17",  # Code Synthesis
    "stage18",  # Env Architect
    "stage19",  # Remote Deploy
    "stage20",  # Execution & Monitoring
    "stage21",  # Result Harvesting
    "stage22",  # Analytics & Drafting
]

STAGES = STAGES_CORE + STAGES_Q1


def _run_stage(topic: Topic, stage: str, db: Session) -> dict:
    # ── Core stages ───────────────────────────────────────────────────────────
    if stage == "query_plan":
        plan = query_planning.generate_query_plan(topic, db)
        return {"plan_id": plan.id, "bundles": len(plan.bundles)}

    elif stage == "discover":
        from app.models.topic import QueryPlan
        plan = db.query(QueryPlan).filter_by(topic_id=topic.id).order_by(QueryPlan.id.desc()).first()
        if not plan:
            raise ValueError("No query plan found. Run query_plan stage first.")
        papers = discovery.discover_papers(topic, plan, db)
        return {"new_papers": len(papers)}

    elif stage == "screen":
        counts = screening.screen_all_papers(topic, db)
        return {"label_counts": counts}

    elif stage == "ingest":
        included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
        pending  = [p for p in included if not p.parsed]
        for p in pending:
            ingestion.ingest_paper(p, db)
        return {"ingested": len(pending), "skipped": len(included) - len(pending)}

    elif stage == "extract":
        count = extraction.extract_all_papers(topic, db)
        return {"extracted": count}

    elif stage == "synthesize":
        result = synthesis.synthesize(topic, db)
        return {"synthesis_id": result.id}

    elif stage == "taxonomy":
        candidate = taxonomy.build_taxonomy(topic, db)
        return {"taxonomy_id": candidate.id, "dimensions": list((candidate.dimensions or {}).keys())}

    elif stage == "gaps":
        gaps = gap_analysis.analyze_gaps(topic, db)
        return {"gaps_found": len(gaps)}

    elif stage == "idea_generation":
        from app.services.idea_generation_service import generate_ideas
        ideas = generate_ideas(topic, db)
        return {"ideas_generated": len(ideas)}

    elif stage == "draft":
        # Check if topic has a linked GitHubRepo with completed code analysis
        repo = db.query(GitHubRepo).filter_by(topic_id=topic.id).order_by(GitHubRepo.id.desc()).first()
        if repo and repo.analysis_status == "done":
            analysis = (
                db.query(CodeAnalysis)
                .filter_by(github_repo_id=repo.id)
                .order_by(CodeAnalysis.id.desc())
                .first()
            )
            if analysis:
                logger.info(
                    "Topic %d has completed code analysis (repo %d) — injecting into draft context",
                    topic.id, repo.id,
                )
                # Attach analysis reference so writing service can access it if needed
                topic._code_analysis_context = analysis
            else:
                topic._code_analysis_context = None
        else:
            topic._code_analysis_context = None

        drafts = writing.draft_all_sections(topic, db)
        return {"sections_drafted": len(drafts)}

    elif stage == "review":
        report = reviewer.run_review(topic, db)
        return {"review_id": report.id, "score": report.overall_score}

    # ── Q1 stages ─────────────────────────────────────────────────────────────
    elif stage == "prisma":
        from app.services.prisma import generate_prisma
        result = generate_prisma(topic, db)
        return result

    elif stage == "citation_network":
        from app.services.citation_network import analyze_citation_network
        stats = analyze_citation_network(topic, db)
        return {
            "authority_papers": len(stats.get("authority_papers", [])),
            "internal_citations": stats.get("internal_citations_found", 0),
            "year_range": f"{min(stats.get('year_distribution', {0: 0}).keys())}"
                          f"-{max(stats.get('year_distribution', {0: 0}).keys())}",
        }

    elif stage == "revision":
        from app.services.revision import revise_all_sections
        revised = revise_all_sections(topic, db)
        return {"sections_revised": len(revised)}

    elif stage == "quality_check":
        from app.services.quality_check import run_quality_check
        report = run_quality_check(topic, db, paraphrase=True)
        grammar = report.get("grammar", {})
        plagiarism = report.get("plagiarism", {})
        return {
            "grammar_issues": grammar.get("error_count", 0),
            "sections_improved": report.get("paraphrase", {}).get("sections_improved", 0),
            "originality": plagiarism.get("originality_pct", "N/A (needs Grammarly Business)"),
            "plagiarism_available": plagiarism.get("available", False),
        }

    elif stage == "export_latex":
        from app.services.latex_export import export_latex
        output_dir = f"./storage/latex/topic_{topic.id}"
        result = export_latex(topic, output_dir, db)
        return result

    elif stage == "view_pdf":
        # Passive stage - just check what PDFs exist
        from pathlib import Path
        latex_base = Path(f"./storage/latex/topic_{topic.id}")
        pdfs = []
        if latex_base.exists():
            for tmpl_dir in latex_base.iterdir():
                pdf = tmpl_dir / "main.pdf"
                if pdf.exists():
                    size_kb = pdf.stat().st_size // 1024
                    pdfs.append({"template": tmpl_dir.name, "size_kb": size_kb, "path": str(pdf)})
        return {"pdfs_available": len(pdfs), "files": pdfs}

    # ── Remote stages ─────────────────────────────────────────────────────────
    elif stage == "stage16":
        from app.services.hybrid_lab_service import hybrid_lab_service
        draft = hybrid_lab_service.generate_hybrid_design(topic, db)
        return {"section_name": draft.section_name, "version": draft.version}

    elif stage == "stage17":
        from app.services.code_synthesis_service import code_synthesis_service
        drafts = code_synthesis_service.synthesize_code(topic, db)
        return {"sections": [d.section_name for d in drafts]}

    elif stage == "stage18":
        from app.services.env_architect_service import env_architect_service
        drafts = env_architect_service.generate_env(topic, db)
        return {"sections": [d.section_name for d in drafts]}

    elif stage == "stage19":
        from app.models.remote import RemoteExecution, SSHServer
        from app.services.remote_deploy_service import remote_deploy_service
        rec = db.query(RemoteExecution).filter_by(topic_id=topic.id).first()
        server = None
        if rec and rec.ssh_server_id:
            server = db.query(SSHServer).filter_by(id=rec.ssh_server_id).first()
        draft = remote_deploy_service.generate_deploy_script(topic, server, db)
        return {"section_name": draft.section_name, "version": draft.version}

    elif stage == "stage20":
        from app.models.remote import RemoteExecution, SSHServer
        from app.services.execution_service import execution_service
        rec = db.query(RemoteExecution).filter_by(topic_id=topic.id).first()
        server = None
        if rec and rec.ssh_server_id:
            server = db.query(SSHServer).filter_by(id=rec.ssh_server_id).first()
        drafts = execution_service.generate_exec_script(topic, server, db)
        return {"sections": [d.section_name for d in drafts]}

    elif stage == "stage21":
        from app.models.remote import RemoteExecution, SSHServer
        from app.services.harvest_service import harvest_service
        rec = db.query(RemoteExecution).filter_by(topic_id=topic.id).first()
        server = None
        if rec and rec.ssh_server_id:
            server = db.query(SSHServer).filter_by(id=rec.ssh_server_id).first()
        draft = harvest_service.generate_harvest_script(topic, server, db)
        return {"section_name": draft.section_name, "version": draft.version}

    elif stage == "stage22":
        from app.services.analytics_service import analytics_service
        draft = analytics_service.generate_experiments_section(topic, db)
        return {"section_name": draft.section_name, "version": draft.version}

    else:
        # Fallback: check if the stage is one of the drafted sections for this paper type
        from app.services.writing import get_sections_for_topic, draft_section
        sections = get_sections_for_topic(topic)
        if stage in sections:
            draft = draft_section(topic, stage, db)
            return {"version": draft.version, "length": len(draft.content or "")}
            
        raise ValueError(f"Unknown stage: {stage}")


def run_pipeline(topic: Topic, stages: list[str], db: Session) -> list[PipelineRun]:
    runs: list[PipelineRun] = []
    for stage in stages:
        run = PipelineRun(
            topic_id=topic.id, stage=stage,
            user_id=getattr(topic, "user_id", None),
            lab_id=getattr(topic, "lab_id", None),
            status="running", started_at=_utcnow(),
        )
        db.add(run)
        db.commit()
        try:
            logger.info("Stage '%s' starting for topic %d", stage, topic.id)
            result = _run_stage(topic, stage, db)
            run.status = "done"
            run.result_summary = result
            run.finished_at = _utcnow()
            logger.info("Stage '%s' done: %s", stage, result)
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            run.finished_at = _utcnow()
            logger.error("Stage '%s' failed: %s", stage, e)
        db.commit()
        try:
            audit_service.log_pipeline_run(
                user_id=getattr(topic, "user_id", None),
                lab_id=getattr(topic, "lab_id", None),
                topic_id=topic.id,
                stage=stage,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
                db=db,
            )
        except Exception:
            pass  # audit failures must not affect pipeline
        runs.append(run)
    return runs


def run_paper_type_pipeline(topic: Topic, db: Session) -> list[PipelineRun]:
    from app.services.paper_type_service import get_pipeline_stages
    paper_type = getattr(topic, "paper_type", None) or "survey"
    stages = get_pipeline_stages(paper_type)
    user_id = getattr(topic, "user_id", None)
    if user_id:
        try:
            audit_service.increment_usage(user_id, "pipeline_runs", db)
        except Exception:
            pass
    return run_pipeline(topic, stages, db)


def run_full_pipeline(topic: Topic, db: Session) -> list[PipelineRun]:
    from app.services.paper_type_service import get_pipeline_stages
    paper_type = getattr(topic, "paper_type", None) or getattr(topic, "target_paper_type", "survey")
    stages = get_pipeline_stages(paper_type)
    user_id = getattr(topic, "user_id", None)
    if user_id:
        try:
            audit_service.increment_usage(user_id, "pipeline_runs", db)
        except Exception:
            pass
    return run_pipeline(topic, stages, db)


def run_core_pipeline(topic: Topic, db: Session) -> list[PipelineRun]:
    return run_pipeline(topic, STAGES_CORE, db)


def run_q1_pipeline(topic: Topic, db: Session) -> list[PipelineRun]:
    return run_pipeline(topic, STAGES_Q1, db)


def run_remote_pipeline(topic: Topic, db: Session) -> list[PipelineRun]:
    """Run all remote execution stages (16–22) for the given topic."""
    return run_pipeline(topic, STAGES_REMOTE, db)
