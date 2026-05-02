"""Survey writing module - generates section drafts grounded in evidence."""
import json
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic
from app.models.pipeline import DraftSection, SynthesisResult, TaxonomyCandidate, GapRecord
from app.models.github import GitHubRepo, CodeAnalysis

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)

# Default sections for surveys
SURVEY_SECTIONS = [
    "introduction", "background", "problem_formulation", 
    "taxonomy", "literature_review", "critical_analysis", 
    "future_directions", "conclusion",
]

# Sections for other paper types (from paper_type_service)
PAPER_TYPE_SECTIONS = {
    "research_paper": ["introduction", "problem_statement", "methodology", "experiment_design", "results", "discussion", "conclusion"],
    "review": ["introduction", "scope_definition", "literature_search", "critical_analysis", "synthesize", "conclusion"],
    "case_study": ["introduction", "context_description", "data_collection", "analysis", "lessons_learned", "conclusion"],
    "technical_report": ["executive_summary", "technical_background", "implementation_details", "recommendations", "conclusion"],
    "thesis_chapter": ["chapter_intro", "related_work", "contribution", "chapter_conclusion"],
}

def get_sections_for_topic(topic: Topic) -> list[str]:
    ptype = getattr(topic, "paper_type", "survey") or "survey"
    return PAPER_TYPE_SECTIONS.get(ptype, SURVEY_SECTIONS)



def _build_context(topic: Topic, db: Session) -> dict:
    papers_summary = []
    for paper in topic.papers:
        if not paper.extraction:
            continue
        papers_summary.append(
            f"[{paper.id}] {paper.title} ({paper.year}) - {paper.extraction.method_type or 'N/A'}"
        )

    synthesis = (
        db.query(SynthesisResult).filter_by(topic_id=topic.id)
        .order_by(SynthesisResult.created_at.desc()).first()
    )
    taxonomy = (
        db.query(TaxonomyCandidate).filter_by(topic_id=topic.id)
        .order_by(TaxonomyCandidate.created_at.desc()).first()
    )
    gaps = db.query(GapRecord).filter_by(topic_id=topic.id).all()

    return {
        "papers_summary": "\n".join(papers_summary),
        "synthesis_summary": json.dumps({
            "patterns": synthesis.recurring_patterns if synthesis else "",
            "contradictions": synthesis.contradictions if synthesis else "",
        }),
        "taxonomy_summary": json.dumps(taxonomy.dimensions if taxonomy else {}),
        "gaps_summary": "\n".join(
            f"[{g.priority}] {g.gap_type}: {g.description}" for g in gaps
        ),
        "code_context": _build_github_context(topic, db),
    }

def _build_github_context(topic: Topic, db: Session) -> str:
    repo = db.query(GitHubRepo).filter_by(topic_id=topic.id).order_by(GitHubRepo.id.desc()).first()
    if not repo or repo.analysis_status != "done":
        return ""
    
    latest = db.query(CodeAnalysis).filter_by(github_repo_id=repo.id).order_by(CodeAnalysis.id.desc()).first()
    if not latest:
        return ""
        
    return f"""
Linked GitHub Repository: {repo.repo_url}
Programming Languages: {json.dumps(latest.languages)}
Key Modules: {json.dumps(latest.key_modules)}
Dependencies: {json.dumps(latest.dependencies)}
README Summary: {(latest.readme_summary or '')[:800]}
Directory Structure: {(latest.directory_tree or '')[:500]}
"""


def _build_citation_map(topic: Topic) -> dict[str, str]:
    """Build paper_id → 'Author et al., Year' mapping for citation resolution."""
    cmap: dict[str, str] = {}
    for paper in topic.papers:
        if not paper.extraction:
            continue
        authors = paper.authors or []
        if authors:
            first = (authors[0] or "").strip()
            last_name = first.split()[-1] if first.split() else "Unknown"
        else:
            last_name = "Unknown"
        year = paper.year or "n.d."
        suffix = " et al." if len(authors) > 1 else ""
        cmap[str(paper.id)] = f"{last_name}{suffix}, {year}"
    return cmap


def _resolve_citations(content: str, citation_map: dict[str, str]) -> str:
    """Replace [CITE:42] with [Smith et al., 2023] using citation_map."""
    import re
    def replace(m):
        pid = m.group(1)
        label = citation_map.get(pid, f"Ref.{pid}")
        return f"[{label}]"
    return re.sub(r'\[CITE:(\d+)\]', replace, content)


def draft_section(topic: Topic, section_name: str, db: Session) -> DraftSection:
    """Generate a single section draft."""
    ctx = _build_context(topic, db)
    template = _jinja_env.get_template("writing.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        section_name=section_name,
        **ctx,
    )

    router = get_router()
    content = router.complete_for_stage(
        "draft",
        "You are an expert academic writer. Write grounded, evidence-based survey content.",
        user_prompt,
    )

    # Build citation map and resolve [CITE:id] → [Author et al., Year]
    citation_map = _build_citation_map(topic)
    content_resolved = _resolve_citations(content, citation_map)

    # Determine version
    existing = (
        db.query(DraftSection)
        .filter_by(topic_id=topic.id, section_name=section_name)
        .order_by(DraftSection.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1

    draft = DraftSection(
        topic_id=topic.id,
        section_name=section_name,
        content=content_resolved,
        version=version,
        citation_map=citation_map,
    )
    db.add(draft)
    db.commit()
    logger.info("Drafted section '%s' v%d for topic %d", section_name, version, topic.id)
    return draft


def draft_all_sections(topic: Topic, db: Session) -> list[DraftSection]:
    drafts = []
    sections = get_sections_for_topic(topic)
    for section in sections:
        try:
            draft = draft_section(topic, section, db)
            drafts.append(draft)
        except Exception as e:
            logger.error("Failed to draft section '%s': %s", section, e)
    return drafts
