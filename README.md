# Research Automation Platform

End-to-end academic survey workflow automation. Covers paper discovery, screening, PDF ingestion, knowledge extraction, taxonomy building, gap analysis, draft writing, and reviewer simulation.

## Quick Start

### 1. Prerequisites

- Python 3.11+
- An LLM API key. OpenAI-compatible providers are supported, including MiniMax.

### 2. Setup

```bash
cd research_platform
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

If you want to use MiniMax instead of OpenAI, set `LLM_PROVIDER=minimax` and fill `MINIMAX_API_KEY`, `MINIMAX_MODEL`, and `MINIMAX_BASE_URL` in `.env`.

### 3. Run the API server

```bash
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 for the UI, or http://localhost:8000/docs for the API explorer.

### 4. Run the demo script

```bash
python scripts/demo.py
```

This creates the "Federated Learning under Concept Drift" topic and runs the full pipeline.

### 5. Run tests

```bash
pytest tests/ -v
```

---

## Architecture

```
main.py                  FastAPI app entry point
app/
  api/                   REST endpoints (topics, papers, pipeline ops)
  core/                  Config, DB engine, LLM provider
  models/                SQLAlchemy ORM models
  schemas/               Pydantic request/response schemas
  services/              Business logic per module
  prompts/               Jinja2 prompt templates (configurable)
  pipelines/             Orchestrator - runs stages in sequence
static/                  Simple HTML dashboard
scripts/                 Demo and utility scripts
tests/                   Pytest test suite
```

## Modules

| Module | Service | Description |
|---|---|---|
| Topic Intake | `api/topics.py` | Create and manage research topics |
| Query Planning | `services/query_planning.py` | LLM-generated search query bundles |
| Paper Discovery | `services/discovery.py` | Semantic Scholar + arXiv APIs |
| Screening | `services/screening.py` | Rule-based + LLM relevance scoring |
| PDF Ingestion | `services/ingestion.py` | Download + PyMuPDF parsing |
| Knowledge Extraction | `services/extraction.py` | Structured per-paper notes |
| Synthesis | `services/synthesis.py` | Cross-paper comparison and patterns |
| Taxonomy | `services/taxonomy.py` | Multi-dimensional taxonomy builder |
| Gap Analysis | `services/gap_analysis.py` | Evidence-grounded research gaps |
| Writing | `services/writing.py` | Section draft generation |
| Reviewer | `services/reviewer.py` | Q1/Q2 reviewer simulation |
| Export | `services/export.py` | JSON / Markdown / DOCX export |

## API Endpoints

```
POST   /api/v1/topics                        Create topic
GET    /api/v1/topics                        List topics
GET    /api/v1/topics/{id}                   Get topic
POST   /api/v1/topics/{id}/query-plan        Generate query plan
POST   /api/v1/topics/{id}/discover          Discover papers
POST   /api/v1/topics/{id}/screen            Screen papers
POST   /api/v1/topics/{id}/extract           Extract knowledge
POST   /api/v1/topics/{id}/synthesize        Cross-paper synthesis
POST   /api/v1/topics/{id}/taxonomy          Build taxonomy
POST   /api/v1/topics/{id}/gaps              Analyze gaps
POST   /api/v1/topics/{id}/draft             Generate drafts
POST   /api/v1/topics/{id}/review            Run reviewer
POST   /api/v1/topics/{id}/pipeline          Run full pipeline
GET    /api/v1/topics/{id}/export?fmt=json   Export results
GET    /api/v1/topics/{id}/export?fmt=markdown
PATCH  /api/v1/papers/{id}/decision          Override screening decision
POST   /api/v1/papers/{id}/ingest            Ingest single paper
```

## Configuration

All settings are in `.env`. Key variables:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENAI_MODEL` | Model name (default: gpt-4o-mini) |
| `OPENAI_BASE_URL` | Override for compatible APIs (Ollama, etc.) |
| `MINIMAX_API_KEY` | MiniMax API key |
| `MINIMAX_MODEL` | MiniMax model name (default: MiniMax-M2.7) |
| `MINIMAX_BASE_URL` | MiniMax OpenAI-compatible base URL |
| `DATABASE_URL` | SQLite (default) or PostgreSQL |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional, increases S2 rate limits |
| `MAX_PAPERS_PER_QUERY` | Papers fetched per query bundle |

## Customizing Prompts

All prompts are Jinja2 templates in `app/prompts/`. Edit them to tune behavior without touching code:

- `query_planning.j2` - search query generation
- `screening.j2` - relevance scoring
- `extraction.j2` - knowledge extraction
- `synthesis.j2` - cross-paper synthesis
- `taxonomy.j2` - taxonomy building
- `gap_analysis.j2` - gap identification
- `writing.j2` - section drafting
- `reviewer.j2` - reviewer simulation

## Using a Local LLM

Set in `.env`:
```
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3
```

## MiniMax, Claude Code, and MCP

MiniMax can be used directly by setting `LLM_PROVIDER=minimax`, or through Claude Code / MCP using the MiniMax Anthropic-compatible endpoints.

Claude Code setup:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<MINIMAX_API_KEY>",
    "ANTHROPIC_MODEL": "MiniMax-M2.7"
  }
}
```

MCP setup for web search and image understanding:

```bash
claude mcp add -s user MiniMax --env MINIMAX_API_KEY=<MINIMAX_API_KEY> --env MINIMAX_API_HOST=https://api.minimax.io -- uvx minimax-coding-plan-mcp -y
```

MiniMax CLI quick checks:

```bash
mmx auth login --api-key <MINIMAX_API_KEY>
mmx quota
mmx image generate --prompt "A research dashboard hero image" --out-dir ./out
```

## Notes

- PDF download requires papers to have an open-access PDF URL. Falls back to abstract-only parsing gracefully.
- Semantic Scholar API works without a key but is rate-limited. Get a free key at https://www.semanticscholar.org/product/api
- All generated claims include `[CITE:paper_id]` placeholders tied to database records - no hallucinated references.
