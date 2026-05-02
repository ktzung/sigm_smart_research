"""Pipeline operation endpoints - one endpoint per stage."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.topic import Topic
from app.models.pipeline import PipelineRun
from app.schemas.pipeline import (
    QueryPlanRead, SynthesisResultRead, TaxonomyCandidateRead,
    GapRecordRead, DraftSectionRead, ReviewReportRead, PipelineRunRead,
)
from app.services import export as export_svc, audit_service
from app.middleware.auth import get_current_user
from app.middleware.plan_enforcement import check_pipeline_run_limit, check_paper_ingest_limit, increment_usage
from app.models.auth import User
from app.models.lab import LabMember

router = APIRouter(prefix="/topics/{topic_id}")

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


def _get_topic_or_404(topic_id: int, user: User, db: Session) -> Topic:
    topic = db.query(Topic).filter_by(id=topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Ownership: owner OR lab member
    if topic.user_id != user.id:
        if not topic.lab_id:
            raise HTTPException(403, detail="Not authorized to access this topic")
        # Check lab membership
        member = db.query(LabMember).filter_by(lab_id=topic.lab_id, user_id=user.id).first()
        if not member:
            raise HTTPException(403, detail="Not authorized to access this topic")

    # Inject model routing overrides into context for this request
    _inject_topic_routing(topic)
    return topic


def _create_run(topic_id: int, stage: str, db: Session) -> PipelineRun:
    """Create a PipelineRun record and mark it running."""
    topic = db.query(Topic).filter_by(id=topic_id).first()
    run = PipelineRun(
        topic_id=topic_id, stage=stage,
        user_id=topic.user_id if topic else None,
        lab_id=topic.lab_id if topic else None,
        status="running", started_at=_utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _inject_topic_routing(topic: Topic) -> None:
    """Inject topic model routing overrides into the context var for this request."""
    from app.core.llm_router import _topic_routing_ctx
    _topic_routing_ctx.set(topic.model_routing_overrides or {})


def _finish_run(run: PipelineRun, result: dict, db: Session):
    run.status = "done"
    run.result_summary = result
    run.finished_at = _utcnow()
    db.commit()


def _fail_run(run: PipelineRun, error: str, db: Session):
    run.status = "failed"
    run.error = error
    run.finished_at = _utcnow()
    db.commit()


def _require_min_role(lab_id: int | None, user: User, min_role: str, db: Session):
    if not lab_id:
        return # Personal topic, owner has all rights
    from app.services.lab_service import require_min_role as _req
    _req(lab_id, user.id, min_role, db)

# ── Stage endpoints ───────────────────────────────────────────────────────────

@router.post("/query-plan")
def create_query_plan(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.query_planning import generate_query_plan
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "query_plan", db)
    try:
        plan = generate_query_plan(topic, db)
        _finish_run(run, {"plan_id": plan.id, "bundles": len(plan.bundles)}, db)
        return {"run_id": run.id, "status": "done"}
    except Exception as e:
        _fail_run(run, str(e), db)
        raise HTTPException(500, detail=str(e))

@router.post("/discover")
def discover(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.discovery import discover_papers
    from app.models.topic import QueryPlan as QP
    topic = _get_topic_or_404(topic_id, current_user, db)
    plan = db.query(QP).filter_by(topic_id=topic_id).order_by(QP.id.desc()).first()
    if not plan:
        raise HTTPException(400, detail="Generate a query plan first")
    run = _create_run(topic_id, "discover", db)
    try:
        papers = discover_papers(topic, plan, db)
        _finish_run(run, {"new_papers": len(papers)}, db)
        return {"run_id": run.id, "status": "done"}
    except Exception as e:
        _fail_run(run, str(e), db)
        raise HTTPException(500, detail=str(e))

@router.post("/screen")
def screen(
    topic_id: int,
    force: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.screening import screen_all_papers
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "screen", db)
    run_id = run.id

    # Capture routing overrides NOW on the request thread — ContextVar is
    # not inherited by background threads, so we pass the value explicitly.
    routing_overrides: dict = topic.model_routing_overrides or {}

    def _do_screen():
        from app.core.llm_router import _topic_routing_ctx
        # Re-inject routing overrides into the background thread's context
        _topic_routing_ctx.set(routing_overrides)

        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            if not _topic or not _run:
                return
            counts = screen_all_papers(_topic, _db, force=force)
            _finish_run(_run, {"label_counts": counts, "force": force}, _db)
        except Exception as e:
            import traceback
            logger.error("Screen stage failed for topic %d: %s\n%s", topic_id, e, traceback.format_exc())
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            if _run:
                _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do_screen)
    return {"run_id": run_id, "status": "running", "message": "Screening started"}


@router.post("/ingest")
def ingest(
    topic_id: int,
    force: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.ingestion import ingest_paper
    topic = _get_topic_or_404(topic_id, current_user, db)
    
    # Plan enforcement for papers
    check_paper_ingest_limit(current_user, db)

    # Count what needs doing before starting
    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    pending  = [p for p in included if not p.parsed or force]
    already  = len(included) - len(pending)

    if not pending:
        run = _create_run(topic_id, "ingest", db)
        _finish_run(run, {"ingested": 0, "skipped": already, "message": "All papers already ingested. Use force=true to re-ingest."}, db)
        return {"run_id": run.id, "status": "done", "ingested": 0, "skipped": already}

    run = _create_run(topic_id, "ingest", db)
    run_id = run.id
    paper_ids = [p.id for p in pending]

    def _do():
        _db = SessionLocal()
        try:
            from app.models.paper import Paper as PaperModel
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            done_count = 0
            for pid in paper_ids:
                paper = _db.query(PaperModel).filter_by(id=pid).first()
                if paper:
                    ingest_paper(paper, _db)
                    done_count += 1
                    # Update progress in result_summary every 10 papers
                    if done_count % 10 == 0:
                        _run.result_summary = {"ingested": done_count, "total": len(paper_ids), "skipped": already}
                        _db.commit()
            _finish_run(_run, {"ingested": done_count, "skipped": already, "total": len(included)}, _db)
        except Exception as e:
            import traceback
            logger.error("Ingest stage failed for topic %d: %s\n%s", topic_id, e, traceback.format_exc())
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            if _run:
                _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": f"Ingesting {len(pending)} papers in background ({already} already done)"}


@router.post("/extract")
def extract(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.extraction import extract_all_papers
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "extract", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            count = extract_all_papers(_topic, _db)
            _finish_run(_run, {"extracted": count}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Extraction started in background"}


@router.post("/synthesize")
def synthesize(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.synthesis import synthesize as _synthesize
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "synthesize", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            result_obj = _synthesize(_topic, _db)
            _finish_run(_run, {"synthesis_id": result_obj.id}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Synthesis started in background"}


@router.post("/taxonomy")
def build_taxonomy(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.taxonomy import build_taxonomy as _build
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "taxonomy", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            candidate = _build(_topic, _db)
            _finish_run(_run, {"taxonomy_id": candidate.id, "dimensions": list((candidate.dimensions or {}).keys())}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Taxonomy build started in background"}


@router.post("/gaps")
def analyze_gaps(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.gap_analysis import analyze_gaps as _analyze
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "gaps", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            gaps = _analyze(_topic, _db)
            _finish_run(_run, {"gaps_found": len(gaps)}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Gap analysis started in background"}


@router.post("/draft")
def draft_sections(
    topic_id: int, 
    section: str | None = None, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.writing import draft_section, draft_all_sections
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "draft", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            if section:
                d = draft_section(_topic, section, _db)
                _finish_run(_run, {"sections_drafted": 1, "section": d.section_name}, _db)
            else:
                drafts = draft_all_sections(_topic, _db)
                _finish_run(_run, {"sections_drafted": len(drafts)}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Drafting started in background"}


@router.post("/review")
def review(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.reviewer import run_review
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "review", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            report = run_review(_topic, _db)
            _finish_run(_run, {"review_id": report.id, "score": report.overall_score}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Review started in background"}


@router.post("/enrich")
def enrich_papers(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enrich abstract-only papers: find open-access PDFs via arXiv/S2/Unpaywall and re-ingest."""
    from app.services.fulltext_enrichment import enrich_all_abstract_only
    from app.models.paper import Paper as PaperModel
    topic = _get_topic_or_404(topic_id, current_user, db)

    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]

    if not abstract_only:
        return {"status": "done", "message": "No abstract-only papers to enrich", "total": 0}

    run = _create_run(topic_id, "ingest", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            stats = enrich_all_abstract_only(topic_id, _db)
            _finish_run(_run, stats, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {
        "run_id": run_id,
        "status": "running",
        "message": f"Enriching {len(abstract_only)} abstract-only papers in background",
        "total": len(abstract_only),
    }


@router.post("/pipeline")
def run_pipeline_endpoint(
    topic_id: int, 
    stages: list[str] | None = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.pipelines.orchestrator import (
        run_full_pipeline, run_paper_type_pipeline, run_pipeline as _run, STAGES_CORE,
    )
    topic = _get_topic_or_404(topic_id, current_user, db)

    # Role check: undergraduate_student may only run STAGES_CORE
    member = db.query(LabMember).filter_by(lab_id=topic.lab_id, user_id=current_user.id).first() if topic.lab_id else None
    user_role = member.role if member else None
    if user_role == "undergraduate_student":
        requested = stages or STAGES_CORE
        forbidden = [s for s in requested if s not in STAGES_CORE]
        if forbidden:
            raise HTTPException(403, detail="undergraduate_student can only run core pipeline stages (1-10)")

    # Plan enforcement for full pipeline runs
    if not stages:
        check_pipeline_run_limit(current_user, db)
        increment_usage(current_user.id, "pipeline_runs", db)

    if stages:
        runs = _run(topic, stages, db)
    else:
        paper_type = getattr(topic, "paper_type", None) or "survey"
        runs = run_paper_type_pipeline(topic, db) if paper_type != "survey" else run_full_pipeline(topic, db)

    return [{"stage": r.stage, "status": r.status, "summary": r.result_summary, "error": r.error} for r in runs]


@router.post("/prisma")
def run_prisma(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.prisma import generate_prisma
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_min_role(topic.lab_id, current_user, "master_student", db)
    run = _create_run(topic_id, "prisma", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            result = generate_prisma(_topic, _db)
            _finish_run(_run, result, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "PRISMA generation started"}


@router.post("/citation-network")
def run_citation_network(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.citation_network import analyze_citation_network
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_min_role(topic.lab_id, current_user, "master_student", db)
    run = _create_run(topic_id, "citation_network", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            stats  = analyze_citation_network(_topic, _db)
            _finish_run(_run, {"authority_papers": len(stats.get("authority_papers", [])),
                               "internal_citations": stats.get("internal_citations_found", 0)}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Citation network analysis started"}


@router.post("/revision")
def run_revision(
    topic_id: int, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.revision import revise_all_sections
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_min_role(topic.lab_id, current_user, "master_student", db)
    run = _create_run(topic_id, "revision", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            revised = revise_all_sections(_topic, _db)
            _finish_run(_run, {"sections_revised": len(revised)}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Revision started"}


# Scores that indicate the paper needs more revision
_REJECT_SCORES = {"reject", "weak_reject", "borderline"}
_ACCEPT_SCORES = {"strong_accept", "accept", "weak_accept"}


@router.post("/review-and-revise")
def review_and_revise(
    topic_id: int,
    max_rounds: int = 3,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Iterative Review → Revision loop. Runs up to max_rounds until score reaches weak_accept or better."""
    from app.services.reviewer import run_review
    from app.services.revision import revise_all_sections

    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_min_role(topic.lab_id, current_user, "master_student", db)
    run = _create_run(topic_id, "revision", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()

            rounds_done = 0
            final_score = None

            for round_num in range(1, max_rounds + 1):
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Review-and-revise round %d/%d for topic %d", round_num, max_rounds, topic_id)

                # Step 1: Review
                report = run_review(_topic, _db)
                final_score = report.overall_score
                rounds_done = round_num

                logger.info("Round %d score: %s", round_num, final_score)

                # Stop if acceptable
                if final_score in _ACCEPT_SCORES:
                    break

                # Step 2: Revise (only if more rounds remain)
                if round_num < max_rounds:
                    revise_all_sections(_topic, _db)
                    # Refresh topic object
                    _db.expire(_topic)
                    _topic = _db.query(Topic).filter_by(id=topic_id).first()

            _finish_run(_run, {
                "rounds_completed": rounds_done,
                "final_score": final_score,
                "converged": final_score in _ACCEPT_SCORES,
            }, _db)

        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {
        "run_id": run_id,
        "status": "running",
        "message": f"Iterative review-and-revise started (up to {max_rounds} rounds)",
    }


@router.post("/code-discovery")
def code_discovery(
    topic_id: int,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stage 5b: Find GitHub repos for included papers via Papers With Code API."""
    from app.services.code_discovery import discover_code_for_topic
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "code_discovery", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            stats = discover_code_for_topic(_topic, _db)
            _finish_run(_run, stats, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Code discovery started (Papers With Code + GitHub)"}


@router.post("/abstract")
def generate_abstract(
    topic_id: int,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate abstract and contributions list from existing draft sections."""
    from app.services.abstract_service import generate_abstract_and_contributions
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "draft", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            result = generate_abstract_and_contributions(_topic, _db)
            _finish_run(_run, {"abstract_len": len(result.get("abstract", "")), "contributions_len": len(result.get("contributions", ""))}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Generating abstract and contributions"}


@router.post("/snowball")
def snowball(
    topic_id: int,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Citation snowballing: find papers that cite/are cited by included papers."""
    from app.services.discovery import snowball_citations
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "discover", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            new_papers = snowball_citations(_topic, _db)
            _finish_run(_run, {"snowball_added": len(new_papers)}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Citation snowballing started"}


@router.post("/citation-verify")
def citation_verify(
    topic_id: int,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """4-layer citation verification (arXiv + DOI + S2 + LLM relevance)."""
    from app.services.citation_verifier import verify_citations
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "quality_check", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            report = verify_citations(_topic, _db)
            _finish_run(_run, report, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Citation verification started (4 layers)"}


@router.post("/anti-fabrication")
def anti_fabrication(
    topic_id: int,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Anti-fabrication check on all draft sections."""
    from app.services.anti_fabrication import check_all_drafts
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "quality_check", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            report = check_all_drafts(_topic, _db)
            _finish_run(_run, {"total_issues": report["total_issues"], "sections": report["sections_checked"], "is_clean": report["is_clean"]}, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running", "message": "Anti-fabrication check started"}


@router.get("/pipeline-decision")
def get_pipeline_decision(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get PROCEED/REFINE/PIVOT decision based on latest review."""
    from app.models.pipeline import ReviewReport
    from app.services.reviewer import make_pipeline_decision
    _get_topic_or_404(topic_id, current_user, db)
    report = db.query(ReviewReport).filter_by(topic_id=topic_id).order_by(ReviewReport.created_at.desc()).first()
    if not report:
        return {"decision": "NO_REVIEW", "message": "Run Review stage first"}
    return make_pipeline_decision(report)


@router.post("/quality-check")
def quality_check(
    topic_id: int, 
    paraphrase: bool = True, 
    background_tasks: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.services.quality_check import run_quality_check
    topic = _get_topic_or_404(topic_id, current_user, db)
    run = _create_run(topic_id, "quality_check", db)
    run_id = run.id
    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            report = run_quality_check(_topic, _db, paraphrase=paraphrase)
            grammar = report.get("grammar", {})
            plagiarism = report.get("plagiarism", {})
            _finish_run(_run, {
                "grammar_issues": grammar.get("error_count", 0),
                "sections_improved": report.get("paraphrase", {}).get("sections_improved", 0),
                "originality": plagiarism.get("originality_pct", "N/A"),
                "plagiarism_available": plagiarism.get("available", False),
            }, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()
    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running",
            "message": "Quality check started (grammar + paraphrase + plagiarism)"}
@router.post("/export-latex")
def export_latex_endpoint(
    topic_id: int,
    template: str = "IEEEtran",
    compile_pdf: bool = True,
    generate_figures: bool = True,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.latex_export import export_latex as _export, TEMPLATES
    topic = _get_topic_or_404(topic_id, current_user, db)
    _require_min_role(topic.lab_id, current_user, "master_student", db)
    if template not in TEMPLATES:
        raise HTTPException(400, detail=f"Unknown template. Choose: {list(TEMPLATES.keys())}")
    run = _create_run(topic_id, "export_latex", db)
    run_id = run.id

    def _do():
        _db = SessionLocal()
        try:
            _topic = _db.query(Topic).filter_by(id=topic_id).first()
            _run   = _db.query(PipelineRun).filter_by(id=run_id).first()
            output_dir = f"./storage/latex/topic_{topic_id}/{template}"
            result = _export(_topic, output_dir, _db,
                             template=template,
                             compile_to_pdf=compile_pdf,
                             generate_figures=generate_figures)
            _finish_run(_run, result, _db)
        except Exception as e:
            _run = _db.query(PipelineRun).filter_by(id=run_id).first()
            _fail_run(_run, str(e), _db)
        finally:
            _db.close()

    background_tasks.add_task(_do)
    return {"run_id": run_id, "status": "running",
            "message": f"Generating LaTeX ({template}) + figures + PDF compilation..."}


@router.get("/download-pdf")
def download_pdf_endpoint(
    topic_id: int, 
    template: str = "IEEEtran", 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download the compiled PDF."""
    from fastapi.responses import FileResponse as FR
    import os
    _ = _get_topic_or_404(topic_id, current_user, db)
    # Use absolute path to avoid CWD issues
    pdf_path = Path(f"./storage/latex/topic_{topic_id}/{template}/main.pdf").resolve()
    if not pdf_path.exists():
        raise HTTPException(404, detail=f"PDF not found at {pdf_path}. Run LaTeX Export first.")
    filename = f"survey_{topic_id}_{template}.pdf"
    return FR(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/view-pdf")
def view_pdf_status(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all compiled PDFs available for this topic."""
    _ = _get_topic_or_404(topic_id, current_user, db)
    latex_base = Path(f"./storage/latex/topic_{topic_id}").resolve()
    pdfs = []
    if latex_base.exists():
        for tmpl_dir in sorted(latex_base.iterdir()):
            if not tmpl_dir.is_dir():
                continue
            pdf = tmpl_dir / "main.pdf"
            tex = tmpl_dir / "main.tex"
            fig_dir = tmpl_dir / "figures"
            figures = sorted([f.name for f in fig_dir.glob("*.pdf")]) if fig_dir.exists() else []
            pdfs.append({
                "template":    tmpl_dir.name,
                "pdf_exists":  pdf.exists(),
                "pdf_size_kb": pdf.stat().st_size // 1024 if pdf.exists() else 0,
                "tex_exists":  tex.exists(),
                "figures":     figures,
                "download_url": f"/api/v1/topics/{topic_id}/download-pdf?template={tmpl_dir.name}",
            })
    return {"topic_id": topic_id, "pdfs": pdfs, "total": len([p for p in pdfs if p["pdf_exists"]])}


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/pipeline-runs", response_model=list[PipelineRunRead])
def get_pipeline_runs(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _ = _get_topic_or_404(topic_id, current_user, db)
    return (
        db.query(PipelineRun)
        .filter_by(topic_id=topic_id)
        .order_by(PipelineRun.id.desc())
        .all()
    )


@router.get("/pipeline-runs/latest")
def get_latest_run_per_stage(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return only the latest run per stage - used by UI for status display."""
    _ = _get_topic_or_404(topic_id, current_user, db)
    runs = (
        db.query(PipelineRun)
        .filter_by(topic_id=topic_id)
        .order_by(PipelineRun.id.desc())
        .all()
    )
    seen: dict[str, dict] = {}
    for r in runs:
        if r.stage not in seen:
            seen[r.stage] = {
                "stage": r.stage,
                "status": r.status,
                "summary": r.result_summary,
                "error": r.error,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
    return seen


@router.get("/drafts", response_model=list[DraftSectionRead])
def get_drafts(
    topic_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.models.pipeline import DraftSection
    _ = _get_topic_or_404(topic_id, current_user, db)
    return db.query(DraftSection).filter_by(topic_id=topic_id).all()


@router.get("/export")
def export_results(
    topic_id: int, 
    fmt: str = "json", 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    topic = _get_topic_or_404(topic_id, current_user, db)
    bundle = export_svc.build_export_bundle(topic, db)
    if fmt == "markdown":
        md = export_svc.export_markdown(bundle)
        return Response(content=md, media_type="text/markdown",
                        headers={"Content-Disposition": f"attachment; filename=survey_{topic_id}.md"})
    elif fmt == "docx":
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name
        export_svc.export_docx(bundle, path)
        with open(path, "rb") as f:
            content = f.read()
        os.unlink(path)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=survey_{topic_id}.docx"},
        )
    return bundle


@router.get("/papers/export-csv")
def export_papers_csv(
    topic_id: int,
    downloaded_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Xuất CSV thông tin các bài báo của topic.

    Query params:
      downloaded_only=true  → chỉ xuất các bài đã tải PDF về
      downloaded_only=false → xuất tất cả bài (mặc định)

    Các cột CSV:
      paper_id, topic_id, topic_title,
      title, authors, year, venue, citation_count,
      decision_label, relevance_score, decision_method,
      source_api, external_id, url, pdf_url,
      pdf_downloaded, pdf_path, parsed,
      abstract (100 ký tự đầu)
    """
    import csv
    import io

    topic = _get_topic_or_404(topic_id, current_user, db)

    papers = topic.papers
    if downloaded_only:
        papers = [p for p in papers if p.pdf_downloaded and p.pdf_path]

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([
        "paper_id", "topic_id", "topic_title",
        "title", "authors", "year", "venue", "citation_count",
        "decision_label", "relevance_score", "decision_method",
        "source_api", "external_id", "url", "pdf_url",
        "pdf_downloaded", "pdf_path", "parsed",
        "abstract_preview",
    ])

    for p in papers:
        # Authors: list → chuỗi "Tên 1; Tên 2; ..."
        authors_raw = p.authors or []
        if authors_raw and isinstance(authors_raw[0], dict):
            authors_str = "; ".join(
                a.get("name", "") for a in authors_raw if a.get("name")
            )
        else:
            authors_str = "; ".join(str(a) for a in authors_raw)

        # Decision
        label  = p.decision.label            if p.decision else ""
        score  = p.decision.relevance_score  if p.decision else ""
        method = p.decision.method           if p.decision else ""

        # Abstract preview (100 ký tự)
        abstract_preview = (p.abstract or "")[:100].replace("\n", " ")

        writer.writerow([
            p.id,
            topic_id,
            topic.title,
            p.title,
            authors_str,
            p.year or "",
            p.venue or "",
            p.citation_count if p.citation_count is not None else "",
            label,
            score,
            method,
            p.source_api or "",
            p.external_id or "",
            p.url or "",
            p.pdf_url or "",
            "yes" if p.pdf_downloaded else "no",
            p.pdf_path or "",
            "yes" if p.parsed else "no",
            abstract_preview,
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig: Excel đọc được tiếng Việt
    filename = f"papers_topic{topic_id}{'_downloaded' if downloaded_only else ''}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/papers/export-csv-all")
def export_all_topics_csv(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    # topic_id is in the path prefix but we ignore it here — export ALL topics of user
):
    """Xuất CSV tất cả bài báo đã tải PDF về, gộp tất cả topic của user hiện tại."""
    import csv
    import io
    from app.models.topic import Topic as TopicModel
    from app.models.paper import Paper as PaperModel

    # Lấy tất cả topic của user
    topics = db.query(TopicModel).filter_by(user_id=current_user.id).all()
    topic_map = {t.id: t.title for t in topics}
    topic_ids = list(topic_map.keys())

    if not topic_ids:
        return Response(
            content="paper_id,topic_id,topic_title,title\n".encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=papers_all.csv"},
        )

    papers = (
        db.query(PaperModel)
        .filter(
            PaperModel.topic_id.in_(topic_ids),
            PaperModel.pdf_downloaded == True,  # noqa: E712
        )
        .order_by(PaperModel.topic_id, PaperModel.id)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "paper_id", "topic_id", "topic_title",
        "title", "authors", "year", "venue", "citation_count",
        "decision_label", "relevance_score",
        "source_api", "external_id", "url", "pdf_url",
        "pdf_path", "parsed",
        "abstract_preview",
    ])

    for p in papers:
        authors_raw = p.authors or []
        if authors_raw and isinstance(authors_raw[0], dict):
            authors_str = "; ".join(a.get("name", "") for a in authors_raw if a.get("name"))
        else:
            authors_str = "; ".join(str(a) for a in authors_raw)

        label = p.decision.label           if p.decision else ""
        score = p.decision.relevance_score if p.decision else ""
        abstract_preview = (p.abstract or "")[:100].replace("\n", " ")

        writer.writerow([
            p.id,
            p.topic_id,
            topic_map.get(p.topic_id, ""),
            p.title,
            authors_str,
            p.year or "",
            p.venue or "",
            p.citation_count if p.citation_count is not None else "",
            label,
            score,
            p.source_api or "",
            p.external_id or "",
            p.url or "",
            p.pdf_url or "",
            p.pdf_path or "",
            "yes" if p.parsed else "no",
            abstract_preview,
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=papers_all_topics.csv"},
    )
