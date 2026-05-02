from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PaperDecisionRead(BaseModel):
    label: str
    relevance_score: Optional[float]
    reason: Optional[str]
    method: str
    overridden: bool

    model_config = {"from_attributes": True}


class ExtractionRecordRead(BaseModel):
    problem_formulation: Optional[str]
    method_type: Optional[str]
    assumptions: Optional[str]
    setting: Optional[str]
    datasets: Optional[list]
    evaluation_protocol: Optional[str]
    strengths: Optional[str]
    limitations: Optional[str]
    relevance_to_topic: Optional[str]

    model_config = {"from_attributes": True}


class PaperRead(BaseModel):
    id: int
    title: str
    authors: Optional[list]
    abstract: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    citation_count: Optional[int]
    url: Optional[str]
    pdf_url: Optional[str]
    source_api: Optional[str]
    pdf_downloaded: bool
    parsed: bool
    extracted: bool
    code_repo_url: Optional[str] = None
    code_repo_stars: Optional[int] = None
    code_framework: Optional[str] = None
    decision: Optional[PaperDecisionRead]
    extraction: Optional[ExtractionRecordRead]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaperDecisionUpdate(BaseModel):
    """Allows researcher to override a screening decision."""
    label: str
    reason: Optional[str] = None
