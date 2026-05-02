"""Stage 20 — Execution & Monitoring service."""
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.topic import Topic
from app.models.pipeline import DraftSection
from app.models.remote import SSHServer, RemoteExecution
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


class ExecutionService:

    def generate_exec_script(
        self, topic: Topic, server: SSHServer | None, db: Session
    ) -> list[DraftSection]:
        require_stage_done(topic.id, "stage19", db)

        if server is None:
            raise HTTPException(400, detail="An SSH server must be selected before running this stage.")

        # Check not already running
        rec = db.query(RemoteExecution).filter_by(topic_id=topic.id).first()
        if rec and rec.execution_status == "running":
            raise HTTPException(409, detail="Experiment is already running for this topic.")

        remote_dir = f"~/experiments/topic_{topic.id}"
        log_file = f"{remote_dir}/logs/train.log"

        if server.scheduler_type == "slurm":
            exec_content = self._generate_sbatch(topic, server, remote_dir, log_file)
        else:
            exec_content = self._generate_standalone(topic, server, remote_dir, log_file)

        monitoring_content = self._generate_monitoring(server, remote_dir, log_file, server.scheduler_type)

        drafts = [
            _upsert_draft(topic.id, "exec_script", exec_content, db),
            _upsert_draft(topic.id, "exec_monitoring", monitoring_content, db),
        ]
        db.commit()

        update_execution_status(topic.id, "running", db)

        logger.info("Stage 20 exec script generated for topic %d (scheduler=%s)", topic.id, server.scheduler_type)
        return drafts

    def _generate_standalone(self, topic: Topic, server: SSHServer, remote_dir: str, log_file: str) -> str:
        return "\n".join([
            "#!/usr/bin/env bash",
            "# Execution script — standalone (nohup/tmux) — Stage 20",
            "# Set SSH_KEY_PATH before running: export SSH_KEY_PATH=/path/to/your/key",
            "",
            f"REMOTE_USER={server.username}",
            f"REMOTE_HOST={server.host}",
            f"REMOTE_DIR={remote_dir}",
            "",
            "# Option A: Run with nohup (detached)",
            f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST \\",
            f"  \"cd $REMOTE_DIR && nohup python train.py --config config.yaml > {log_file} 2>&1 &\"",
            "",
            "# Option B: Run inside a tmux session (recommended for interactive monitoring)",
            f"# ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST \\",
            f"#   \"tmux new-session -d -s train_{topic.id} 'cd $REMOTE_DIR && python train.py --config config.yaml 2>&1 | tee {log_file}'\"",
            "",
            "echo 'Experiment launched. Use the monitoring script to track progress.'",
        ])

    def _generate_sbatch(self, topic: Topic, server: SSHServer, remote_dir: str, log_file: str) -> str:
        gpu_type = server.gpu_type or "gpu"
        return "\n".join([
            "#!/usr/bin/env bash",
            "# Execution script — Slurm sbatch — Stage 20",
            "# Set SSH_KEY_PATH before running: export SSH_KEY_PATH=/path/to/your/key",
            "",
            f"REMOTE_USER={server.username}",
            f"REMOTE_HOST={server.host}",
            f"REMOTE_DIR={remote_dir}",
            "",
            "# Upload sbatch job script",
            f"cat > /tmp/job_{topic.id}.sh << 'SBATCH_EOF'",
            "#!/bin/bash",
            f"#SBATCH --job-name=topic_{topic.id}",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --cpus-per-task=8",
            f"#SBATCH --gres=gpu:1",
            f"#SBATCH --constraint={gpu_type}",
            "#SBATCH --time=24:00:00",
            f"#SBATCH --output={log_file}",
            "#SBATCH --error={remote_dir}/logs/train.err",
            "",
            f"cd {remote_dir}",
            "module load cuda",
            "conda activate experiment_env",
            "python train.py --config config.yaml",
            "SBATCH_EOF",
            "",
            f"scp -i $SSH_KEY_PATH /tmp/job_{topic.id}.sh $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/job.sh",
            f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST \"cd $REMOTE_DIR && sbatch job.sh\"",
            "",
            "echo 'Slurm job submitted. Use the monitoring script to track progress.'",
        ])

    def _generate_monitoring(self, server: SSHServer, remote_dir: str, log_file: str, scheduler_type: str) -> str:
        lines = [
            "#!/usr/bin/env bash",
            "# Monitoring commands — Stage 20",
            "# Set SSH_KEY_PATH before running: export SSH_KEY_PATH=/path/to/your/key",
            "",
            f"REMOTE_USER={server.username}",
            f"REMOTE_HOST={server.host}",
            "",
            "# 1. Check GPU utilization",
            f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST 'nvidia-smi'",
            "",
            "# 2. Tail training log",
            f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST 'tail -f {log_file}'",
        ]
        if scheduler_type == "slurm":
            lines += [
                "",
                "# 3. Check Slurm job status",
                f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST 'squeue -u $USER'",
                "",
                "# 4. Cancel job if needed",
                f"# ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST 'scancel <JOB_ID>'",
            ]
        else:
            lines += [
                "",
                "# 3. Check if process is running",
                f"ssh -i $SSH_KEY_PATH $REMOTE_USER@$REMOTE_HOST 'pgrep -fl train.py'",
            ]
        return "\n".join(lines)


execution_service = ExecutionService()
