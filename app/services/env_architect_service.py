"""Stage 18 — Environment Architect service."""
import logging
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection
from app.models.remote import RemoteExecution, SSHServer
from app.services.remote_prereqs import require_stage_done

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

# CUDA-related package name patterns
_CUDA_PATTERNS = re.compile(
    r"\b(torch|torchvision|torchaudio|tensorflow(-gpu)?|cupy|cuda|cudnn|"
    r"nvidia-|jax\[cuda|triton|xformers)\b",
    re.IGNORECASE,
)


def _detect_cuda(requirements_txt: str) -> bool:
    return bool(_CUDA_PATTERNS.search(requirements_txt))


def _parse_env_output(text: str) -> dict[str, str]:
    """Parse LLM output into {section_name: content}."""
    result: dict[str, str] = {}
    pattern = re.compile(r"^###\s+(environment_file|ssh_commands)\s*$", re.MULTILINE)
    parts = pattern.split(text)
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        result[header] = content.strip()
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


class EnvArchitectService:

    def generate_env(self, topic: Topic, db: Session) -> list[DraftSection]:
        require_stage_done(topic.id, "stage17", db)

        # Read code_requirements DraftSection
        req_draft = (
            db.query(DraftSection)
            .filter_by(topic_id=topic.id, section_name="code_requirements")
            .order_by(DraftSection.version.desc())
            .first()
        )
        requirements_txt = req_draft.content if req_draft else ""
        has_cuda = _detect_cuda(requirements_txt)

        # Get SSH server info for gpu_type and scheduler_type
        rec = db.query(RemoteExecution).filter_by(topic_id=topic.id).first()
        gpu_type = "unknown"
        scheduler_type = "standalone"
        if rec and rec.ssh_server_id:
            server = db.query(SSHServer).filter_by(id=rec.ssh_server_id).first()
            if server:
                gpu_type = server.gpu_type
                scheduler_type = server.scheduler_type

        template = _jinja_env.get_template("env_architect.j2")
        user_prompt = template.render(
            requirements_txt_content=requirements_txt,
            gpu_type=gpu_type,
            scheduler_type=scheduler_type,
            has_cuda=has_cuda,
        )

        router = get_router()
        llm_output = router.complete_for_stage(
            "stage18",
            "You are a DevOps engineer specializing in ML infrastructure. Generate environment setup files.",
            user_prompt,
        )

        parsed = _parse_env_output(llm_output)

        drafts: list[DraftSection] = []
        env_content = parsed.get("environment_file", "# environment file generation failed\n")
        ssh_content = parsed.get("ssh_commands", "# ssh commands generation failed\n")

        drafts.append(_upsert_draft(topic.id, "env_environment_file", env_content, db))
        drafts.append(_upsert_draft(topic.id, "env_ssh_commands", ssh_content, db))

        db.commit()
        logger.info(
            "Stage 18 env architect complete for topic %d (cuda=%s, scheduler=%s)",
            topic.id, has_cuda, scheduler_type,
        )
        return drafts


env_architect_service = EnvArchitectService()
