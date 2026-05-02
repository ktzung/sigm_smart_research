from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from app.core.logging import setup_logging
from app.core.database import init_db, SessionLocal
from app.api import router

setup_logging()
init_db()

def _cleanup_stuck_runs():
    """Mark any 'running' pipeline runs as failed on startup (server was restarted)."""
    from datetime import datetime, timezone
    from app.models.pipeline import PipelineRun
    db = SessionLocal()
    try:
        stuck = db.query(PipelineRun).filter_by(status="running").all()
        if stuck:
            import logging
            logging.getLogger(__name__).warning(
                "Found %d stuck pipeline run(s) from previous session - marking as failed", len(stuck)
            )
            for r in stuck:
                r.status = "failed"
                r.error = "Interrupted: server restarted"
                r.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
    finally:
        db.close()

_cleanup_stuck_runs()

app = FastAPI(
    title="Research Automation Platform",
    description="End-to-end academic survey workflow automation",
    version="1.0.0",
)

app.include_router(router, prefix="/api/v1")

# Serve simple HTML UI
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/", include_in_schema=False)
    def serve_ui():
        return FileResponse(
            "static/index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
        )

# Serve generated files (PDFs, figures)
storage_dir = Path("storage")
storage_dir.mkdir(exist_ok=True)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")


@app.get("/health")
def health():
    from app.core.config import settings
    return {"status": "ok", "routing": "task-aware"}


@app.get("/api/v1/config/routing")
def get_routing_table():
    """Show which model handles each pipeline stage."""
    from app.core.llm_router import STAGE_ROUTING
    return {
        stage: {"provider": p, "model": m, "temperature": t, "max_tokens": mt}
        for stage, (p, m, t, mt, *_) in STAGE_ROUTING.items()
    }


@app.post("/api/v1/config/routing/{stage}")
def override_stage_routing(stage: str, provider: str, model: str):
    """Override routing for a specific stage at runtime. Persists to storage/routing_overrides.json."""
    import json
    from app.core.llm_router import STAGE_ROUTING, reset_router
    if stage not in STAGE_ROUTING:
        raise HTTPException(400, f"Unknown stage: {stage}. Valid: {list(STAGE_ROUTING.keys())}")
    _, _, temperature, max_tokens, category = STAGE_ROUTING[stage]
    STAGE_ROUTING[stage] = (provider, model, temperature, max_tokens, category)
    reset_router()

    # Persist to file so overrides survive server restart
    overrides_path = Path("storage/routing_overrides.json")
    try:
        existing = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
        existing[stage] = {"provider": provider, "model": model}
        overrides_path.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to persist routing override: %s", e)

    return {"stage": stage, "provider": provider, "model": model}


def _load_persisted_routing_overrides():
    """Load routing overrides from storage on startup."""
    import json
    from app.core.llm_router import STAGE_ROUTING, reset_router
    overrides_path = Path("storage/routing_overrides.json")
    if not overrides_path.exists():
        return
    try:
        overrides = json.loads(overrides_path.read_text())
        changed = False
        for stage, ov in overrides.items():
            if stage in STAGE_ROUTING:
                _, _, temperature, max_tokens, category = STAGE_ROUTING[stage]
                STAGE_ROUTING[stage] = (ov["provider"], ov["model"], temperature, max_tokens, category)
                changed = True
        if changed:
            reset_router()
            import logging
            logging.getLogger(__name__).info("Loaded %d persisted routing overrides", len(overrides))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load routing overrides: %s", e)


_load_persisted_routing_overrides()


@app.delete("/api/v1/config/routing")
def reset_all_routing():
    """Reset all stage routing overrides to defaults and clear persisted file."""
    overrides_path = Path("storage/routing_overrides.json")
    if overrides_path.exists():
        overrides_path.unlink()
    from app.core.llm_router import reset_router
    reset_router()
    return {"status": "reset", "message": "All routing overrides cleared. Restart server to reload defaults."}
