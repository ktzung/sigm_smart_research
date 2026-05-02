from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, AliasChoices, field_validator, model_validator


VALID_PAPER_TYPES = [
    "survey",
    "research_paper",
    "review",
    "case_study",
    "technical_report",
    "thesis_chapter",
]

PaperType = Literal[
    "survey",
    "research_paper",
    "review",
    "case_study",
    "technical_report",
    "thesis_chapter",
]


class AuthorInfo(BaseModel):
    name: str                          # Display name on paper
    email: Optional[str] = None
    affiliation: Optional[str] = None  # Institution/organization
    orcid: Optional[str] = None        # ORCID ID (optional)
    is_corresponding: bool = False


class TopicCreate(BaseModel):
    title: str
    description: Optional[str] = None
    lab_id: Optional[int] = None
    paper_type: str = Field(
        default="survey",
        validation_alias=AliasChoices("paper_type", "target_paper_type"),
    )
    target_quality: str = "Q1/Q2"
    literature_scarce: bool = False
    adjacent_fields: Optional[list[str]] = None
    constraints: Optional[dict] = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @field_validator("paper_type", mode="before")
    @classmethod
    def validate_paper_type(cls, v: str) -> str:
        if v not in VALID_PAPER_TYPES:
            valid = ", ".join(VALID_PAPER_TYPES)
            raise ValueError(
                f"Invalid paper_type. Valid values: {valid}"
            )
        return v


class TopicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    adjacent_fields: Optional[list[str]] = None
    # Paper metadata
    paper_abstract: Optional[str] = None
    paper_keywords: Optional[str] = None
    authors_info: Optional[list[AuthorInfo]] = None


class TopicRead(BaseModel):
    id: int
    lab_id: Optional[int] = None
    title: str
    description: Optional[str]
    paper_type: PaperType
    target_paper_type: Optional[PaperType] = None
    target_quality: str
    literature_scarce: bool
    adjacent_fields: Optional[list[str]]
    paper_abstract: Optional[str] = None
    paper_keywords: Optional[str] = None
    authors_info: Optional[list] = None
    created_at: datetime

    @model_validator(mode="after")
    def _sync_backward_field(self):
        if self.target_paper_type is None:
            self.target_paper_type = self.paper_type
        return self

    model_config = {"from_attributes": True}
