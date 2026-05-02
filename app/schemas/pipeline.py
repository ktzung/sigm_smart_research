from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class QueryBundleRead(BaseModel):
    id: int
    label: str
    query_text: str
    source: str

    model_config = {"from_attributes": True}


class QueryPlanRead(BaseModel):
    id: int
    topic_id: int
    bundles: list[QueryBundleRead]
    created_at: datetime

    model_config = {"from_attributes": True}


class SynthesisResultRead(BaseModel):
    id: int
    topic_id: int
    comparison_table: Optional[dict]
    recurring_patterns: Optional[str]
    contradictions: Optional[str]
    method_clusters: Optional[dict]
    benchmark_coverage: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TaxonomyCandidateRead(BaseModel):
    id: int
    topic_id: int
    dimensions: Optional[dict]
    paper_mapping: Optional[dict]
    explanation: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class GapRecordRead(BaseModel):
    id: int
    topic_id: int
    gap_type: str
    description: str
    evidence_paper_ids: Optional[list]
    evidence_quotes: Optional[str]
    priority: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DraftSectionRead(BaseModel):
    id: int
    topic_id: int
    section_name: str
    content: str
    citation_map: Optional[dict]
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewReportRead(BaseModel):
    id: int
    topic_id: int
    major_weaknesses: Optional[str]
    minor_issues: Optional[str]
    revision_priorities: Optional[str]
    overall_score: Optional[str]
    raw_review: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunRead(BaseModel):
    id: int
    topic_id: int
    stage: str
    status: str
    result_summary: Optional[dict]
    error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ExportBundle(BaseModel):
    topic: Any
    papers: list[Any]
    query_plan: Optional[Any]
    synthesis: Optional[Any]
    taxonomy: Optional[Any]
    gaps: list[Any]
    draft_sections: list[Any]
    review_report: Optional[Any]
