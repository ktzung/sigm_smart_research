"""Stage 21 — Result Harvesting service."""
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.topic import Topic
from app.models.pipeline import DraftSection
from app.models.remote import SSHServer
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


class HarvestService:

    def generate_harvest_script(
        self, topic: Topic, server: SSHServer | None, db: Session
    ) -> DraftSection:
        require_stage_done(topic.id, "stage20", db)

        if server is None:
            raise HTTPException(400, detail="An SSH server must be selected before running this stage.")

        remote_dir = f"~/experiments/topic_{topic.id}"
        local_results_dir = f"./storage/results/topic_{topic.id}/"

        lines = [
            "#!/usr/bin/env bash",
            "# Harvest script — Stage 21",
            "# Set SSH_KEY_PATH before running: export SSH_KEY_PATH=/path/to/your/key",
            "",
            f"REMOTE_USER={server.username}",
            f"REMOTE_HOST={server.host}",
            f"REMOTE_DIR={remote_dir}",
            f"LOCAL_DIR={local_results_dir}",
            "",
            "# Create local results directory",
            f"mkdir -p {local_results_dir}",
            "",
            "# Pull CSV result files (metrics, logs)",
            f"rsync -avz --progress \\",
            f"  --include='*.csv' \\",
            f"  --exclude='*' \\",
            f"  -e 'ssh -i $SSH_KEY_PATH' \\",
            f"  $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/results/ $LOCAL_DIR",
            "",
            "# Pull model checkpoints (*.pt files)",
            f"rsync -avz --progress \\",
            f"  --include='*.pt' \\",
            f"  --exclude='*' \\",
            f"  -e 'ssh -i $SSH_KEY_PATH' \\",
            f"  $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/checkpoints/ $LOCAL_DIR",
            "",
            "# Pull plot images (*.png files)",
            f"rsync -avz --progress \\",
            f"  --include='*.png' \\",
            f"  --exclude='*' \\",
            f"  -e 'ssh -i $SSH_KEY_PATH' \\",
            f"  $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/results/ $LOCAL_DIR",
            "",
            "# Pull log files (*.log files)",
            f"rsync -avz --progress \\",
            f"  --include='*.log' \\",
            f"  --exclude='*' \\",
            f"  -e 'ssh -i $SSH_KEY_PATH' \\",
            f"  $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/logs/ $LOCAL_DIR",
            "",
            f"echo 'Harvest complete. Results saved to {local_results_dir}'",
        ]

        content = "\n".join(lines)
        draft = _upsert_draft(topic.id, "harvest_script", content, db)
        db.commit()

        update_execution_status(topic.id, "harvested", db)

        logger.info("Stage 21 harvest script generated for topic %d", topic.id)
        return draft


harvest_service = HarvestService()
