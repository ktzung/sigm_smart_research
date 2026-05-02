"""Verify claude-pipeline-upgrade changes. Run: python _verify_upgrade.py"""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:abc@localhost:5432/research_platform")

errors = []

# ── 1. Writing stages → anthropic/claude-sonnet-4-5 ──────────────────────────
print("=== 1. Writing stage routing ===")
from app.core.llm_router import resolve_model_for_stage

WRITING = ["synthesize", "taxonomy", "gaps", "idea_generation", "draft", "review", "revision"]
BULK    = ["screen", "extract"]

for s in WRITING:
    p, m, t, mt = resolve_model_for_stage(s)
    ok = p == "anthropic" and m == "claude-sonnet-4-5"
    print(f"  [{'OK' if ok else 'FAIL'}] {s}: {p}/{m}")
    if not ok:
        errors.append(f"Writing stage {s} routes to {p}/{m}, expected anthropic/claude-sonnet-4-5")

# ── 2. Bulk stages → openai/gpt-4o-mini ──────────────────────────────────────
print("\n=== 2. Bulk stage routing ===")
for s in BULK:
    p, m, t, mt = resolve_model_for_stage(s)
    ok = p == "openai" and m == "gpt-4o-mini"
    print(f"  [{'OK' if ok else 'FAIL'}] {s}: {p}/{m}")
    if not ok:
        errors.append(f"Bulk stage {s} routes to {p}/{m}, expected openai/gpt-4o-mini")

# ── 3. Per-topic override still works ────────────────────────────────────────
print("\n=== 3. Per-topic override ===")
overrides = {"stage:synthesize": {"provider": "openai", "model": "gpt-4o"}}
p, m, _, _ = resolve_model_for_stage("synthesize", overrides)
ok = p == "openai" and m == "gpt-4o"
print(f"  [{'OK' if ok else 'FAIL'}] stage override: {p}/{m}")
if not ok:
    errors.append("Per-topic stage override broken")

# ── 4. STAGES_CORE order ──────────────────────────────────────────────────────
print("\n=== 4. STAGES_CORE order ===")
from app.pipelines.orchestrator import STAGES_CORE
try:
    ig = STAGES_CORE.index("idea_generation")
    ga = STAGES_CORE.index("gaps")
    dr = STAGES_CORE.index("draft")
    ok = ga < ig < dr
    print(f"  [{'OK' if ok else 'FAIL'}] gaps={ga}, idea_generation={ig}, draft={dr}")
    if not ok:
        errors.append("STAGES_CORE order wrong: idea_generation not between gaps and draft")
except ValueError as e:
    errors.append(f"STAGES_CORE missing stage: {e}")
    print(f"  [FAIL] {e}")

# ── 5. Survey pipeline includes idea_generation ───────────────────────────────
print("\n=== 5. Survey pipeline ===")
from app.services.paper_type_service import get_pipeline_stages
survey = get_pipeline_stages("survey")
ok = "idea_generation" in survey
print(f"  [{'OK' if ok else 'FAIL'}] idea_generation in survey pipeline")
if ok:
    ig2 = survey.index("idea_generation")
    ga2 = survey.index("gaps")
    dr2 = survey.index("draft")
    order_ok = ga2 < ig2 < dr2
    print(f"  [{'OK' if order_ok else 'FAIL'}] order: gaps={ga2}, idea_generation={ig2}, draft={dr2}")
    if not order_ok:
        errors.append("Survey pipeline order wrong")
else:
    errors.append("idea_generation not in survey pipeline")

# ── 6. IdeaRecord model ───────────────────────────────────────────────────────
print("\n=== 6. IdeaRecord model ===")
from app.models.pipeline import IdeaRecord
cols = [c.name for c in IdeaRecord.__table__.columns]
required = ["id", "topic_id", "title", "novelty_argument", "methodology_hint", "difficulty", "expected_impact", "created_at"]
for col in required:
    ok = col in cols
    print(f"  [{'OK' if ok else 'FAIL'}] column: {col}")
    if not ok:
        errors.append(f"IdeaRecord missing column: {col}")

# ── 7. Service imports cleanly ────────────────────────────────────────────────
print("\n=== 7. Service imports ===")
try:
    from app.services.idea_generation_service import generate_ideas, _apply_defaults, _parse_ideas_json
    print("  [OK] idea_generation_service imports")
except Exception as e:
    errors.append(f"idea_generation_service import failed: {e}")
    print(f"  [FAIL] {e}")

# ── 8. _apply_defaults logic ─────────────────────────────────────────────────
print("\n=== 8. _apply_defaults ===")
from app.services.idea_generation_service import _apply_defaults
cases = [
    ({"title": "T", "novelty_argument": "N", "methodology_hint": "M"}, "medium", "medium"),
    ({"title": "T", "novelty_argument": "N", "methodology_hint": "M", "difficulty": "hard"}, "hard", "medium"),
    ({"title": "T", "novelty_argument": "N", "methodology_hint": "M", "difficulty": "invalid", "expected_impact": "high"}, "medium", "high"),
]
for idea, exp_d, exp_i in cases:
    result = _apply_defaults(idea)
    ok = result["difficulty"] == exp_d and result["expected_impact"] == exp_i
    print(f"  [{'OK' if ok else 'FAIL'}] difficulty={result['difficulty']}, impact={result['expected_impact']}")
    if not ok:
        errors.append(f"_apply_defaults wrong: got {result['difficulty']}/{result['expected_impact']}, expected {exp_d}/{exp_i}")

# ── 9. Jinja2 template exists ─────────────────────────────────────────────────
print("\n=== 9. Jinja2 template ===")
from pathlib import Path
tmpl = Path("app/prompts/idea_generation.j2")
ok = tmpl.exists()
print(f"  [{'OK' if ok else 'FAIL'}] app/prompts/idea_generation.j2")
if not ok:
    errors.append("idea_generation.j2 template missing")

# ── 10. Alembic migration exists ─────────────────────────────────────────────
print("\n=== 10. Alembic migration ===")
mig = Path("alembic/versions/009_idea_records.py")
ok = mig.exists()
print(f"  [{'OK' if ok else 'FAIL'}] alembic/versions/009_idea_records.py")
if not ok:
    errors.append("Migration 009_idea_records.py missing")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"RESULT: {len(errors)} error(s):")
    for e in errors:
        print(f"  [FAIL] {e}")
    sys.exit(1)
else:
    print("RESULT: All checks passed — research_platform upgrade complete")
    print()
    print("Next steps:")
    print("  1. Set ANTHROPIC_API_KEY in .env")
    print("  2. Run: alembic upgrade head  (creates idea_records table)")
    print("  3. Restart server: uvicorn main:app --reload")
