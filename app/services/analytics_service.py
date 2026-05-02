"""Stage 22 — Analytics & Drafting service."""
import csv
import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection, GapRecord
from app.services.remote_prereqs import require_stage_done, update_execution_status

logger = logging.getLogger(__name__)


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


def _read_csv_metrics(results_dir: Path) -> list[dict]:
    """Read all CSV files in results_dir and return list of row dicts."""
    rows = []
    for csv_file in results_dir.glob("*.csv"):
        try:
            with open(csv_file, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append({"file": csv_file.name, **row})
        except Exception as e:
            logger.warning("Failed to read CSV %s: %s", csv_file, e)
    return rows


class AnalyticsService:

    def generate_experiments_section(self, topic: Topic, db: Session) -> DraftSection:
        require_stage_done(topic.id, "stage21", db)

        results_dir = Path(f"./storage/results/topic_{topic.id}")
        csv_files = list(results_dir.glob("*.csv")) if results_dir.exists() else []

        if not csv_files:
            raise HTTPException(400, detail="No harvested results found. Run Stage 21 first.")

        metrics_data = _read_csv_metrics(results_dir)

        # Read gap records for baseline comparison context
        gaps = db.query(GapRecord).filter_by(topic_id=topic.id).all()
        gaps_summary = "\n".join(
            f"- [{g.priority}] {g.gap_type}: {g.description}" for g in gaps
        )

        metrics_json = json.dumps(metrics_data[:50], indent=2)  # cap at 50 rows for prompt

        user_prompt = f"""You are an academic ML researcher writing the Experiments section of a research paper.

## Topic
{topic.title}

## Harvested Metrics (CSV data)
{metrics_json}

## Research Gaps Addressed
{gaps_summary}

## Task
Generate a complete LaTeX \\section{{Experiments}} that includes:
1. A description of the experimental setup (datasets, hardware, hyperparameters)
2. A LaTeX table (\\begin{{table}}) with the numeric results from the CSV data
3. Figure references (\\ref{{fig:...}}) for plots (assume figures are in ./figures/)
4. A baseline comparison paragraph referencing the gaps above
5. An ablation study subsection if multiple configurations are present in the data

Output ONLY valid LaTeX starting with \\section{{Experiments}}. Do not include preamble or document tags.
"""

        router = get_router()
        latex_content = router.complete_for_stage(
            "stage22",
            "You are an expert academic writer generating LaTeX experiment sections.",
            user_prompt,
        )

        draft = _upsert_draft(topic.id, "experiments", latex_content, db)
        db.commit()

        update_execution_status(topic.id, "analyzed", db)

        logger.info("Stage 22 experiments section generated for topic %d", topic.id)
        return draft


analytics_service = AnalyticsService()
