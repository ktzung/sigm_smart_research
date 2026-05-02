from datetime import datetime, date
from typing import Optional, Literal
from pydantic import BaseModel, HttpUrl, field_validator


# ── User Profile ──────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    avatar_url: Optional[str] = None
    title: Optional[str] = None          # e.g. "Associate Professor", "PhD Candidate"
    bio: Optional[str] = None
    orcid: Optional[str] = None          # e.g. "0000-0002-1825-0097"
    google_scholar_url: Optional[str] = None
    researchgate_url: Optional[str] = None
    website_url: Optional[str] = None


class ProfileRead(BaseModel):
    user_id: int
    avatar_url: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None
    orcid: Optional[str] = None
    google_scholar_url: Optional[str] = None
    researchgate_url: Optional[str] = None
    website_url: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Publication ───────────────────────────────────────────────────────────────

PubType = Literal["journal", "conference", "book_chapter", "preprint"]


class PublicationCreate(BaseModel):
    title: str
    authors: list[str]
    venue: str
    year: int
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: int = 0
    pub_type: PubType

    @field_validator("year")
    @classmethod
    def year_reasonable(cls, v: int) -> int:
        if not (1900 <= v <= 2100):
            raise ValueError("year must be between 1900 and 2100")
        return v

    @field_validator("authors")
    @classmethod
    def authors_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("authors list must not be empty")
        return v


class PublicationUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    venue: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: Optional[int] = None
    pub_type: Optional[PubType] = None


class PublicationRead(BaseModel):
    id: int
    user_id: int
    title: str
    authors: list
    venue: str
    year: int
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: int
    pub_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Project ───────────────────────────────────────────────────────────────────

ProjectStatus = Literal["ongoing", "completed", "planned"]


class ProjectCreate(BaseModel):
    title: str
    description: str
    role: str
    funding_source: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    status: ProjectStatus
    collaborators: list[str] = []


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    funding_source: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    collaborators: Optional[list[str]] = None


class ProjectRead(BaseModel):
    id: int
    user_id: int
    title: str
    description: str
    role: str
    funding_source: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    status: str
    collaborators: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Lab News ──────────────────────────────────────────────────────────────────

class NewsCreate(BaseModel):
    title: str
    content: str
    pinned: bool = False
    published_at: Optional[datetime] = None  # defaults to now if not provided


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    pinned: Optional[bool] = None
    published_at: Optional[datetime] = None


class NewsRead(BaseModel):
    id: int
    lab_id: int
    author_id: int
    title: str
    content: str
    published_at: datetime
    pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Lab Homepage composite response ──────────────────────────────────────────

class MemberDisplay(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None
    role: str
    profile_url: str
    orcid: Optional[str] = None
    google_scholar_url: Optional[str] = None
    website_url: Optional[str] = None
    publication_count: int = 0


class LabStats(BaseModel):
    total_publications: int
    total_projects: int
    total_active_members: int


class LabHomepageRead(BaseModel):
    lab_id: int
    lab_name: str
    lab_description: Optional[str] = None
    news: list[NewsRead]
    events: list["EventRead"] = []
    members: dict[str, list[MemberDisplay]]
    statistics: LabStats


# ── Full user profile page ────────────────────────────────────────────────────

class UserProfilePage(BaseModel):
    user_id: int
    display_name: str
    email: str
    profile: Optional[ProfileRead] = None
    publications: list[PublicationRead] = []
    projects: list[ProjectRead] = []


# ── Lab Event ─────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_date: datetime
    location: Optional[str] = None
    event_type: str = "seminar"
    url: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[datetime] = None
    location: Optional[str] = None
    event_type: Optional[str] = None
    url: Optional[str] = None


class EventRead(BaseModel):
    id: int
    lab_id: int
    author_id: int
    title: str
    description: Optional[str] = None
    event_date: datetime
    location: Optional[str] = None
    event_type: str
    url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lab Slides ────────────────────────────────────────────────────────────────

class LabSlideCreate(BaseModel):
    image_url: str
    caption: Optional[str] = None
    location: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class LabSlideUpdate(BaseModel):
    caption: Optional[str] = None
    location: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LabSlideRead(BaseModel):
    id: int
    lab_id: int
    image_url: str
    caption: Optional[str]
    location: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── News Detail ───────────────────────────────────────────────────────────────

class NewsDetailRead(NewsRead):
    author_display_name: str


# ── Config GUI ────────────────────────────────────────────────────────────────

class ConfigGuiRead(BaseModel):
    llm_provider: str
    openai_model: str
    perplexity_model: str
    anthropic_model: str
    gemini_model: str
    ollama_model: str
    ollama_base_url: str
    groq_model: str
    has_openai_key: bool
    has_perplexity_key: bool
    has_anthropic_key: bool
    has_gemini_key: bool
    has_groq_key: bool
    has_minimax_key: bool | None = False
    minimax_model: str | None = None
    minimax_base_url: str | None = None


class ConfigSaveRequest(BaseModel):
    llm_provider: Optional[str] = None
    openai_model: Optional[str] = None
    perplexity_model: Optional[str] = None
    anthropic_model: Optional[str] = None
    gemini_model: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    groq_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    minimax_model: Optional[str] = None
    minimax_base_url: Optional[str] = None
    minimax_api_key: Optional[str] = None
