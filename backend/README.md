# Auto Deck API — Backend

FastAPI backend for AI-powered PowerPoint generation. Accepts structured JSON describing report sections (charts, tables, commentary), generates OOXML-compliant `.pptx` files using a multi-stage pipeline, and serves them for download.

## Quick Start

```bash
cd backend

# Install dependencies (Python >= 3.11 required)
uv sync                        # or: pip install -e .

# Configure environment
cp .env.example .env           # then set NVIDIA_API_KEY
# Optional: API_KEY=...        # requires X-API-Key header on /api/v1 and /api/v2 (disabled when empty)

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Health check: `GET /health`
- Frontend expects: `http://localhost:8000/api/v1`

---

## Architecture Overview

```
                        Frontend (Vue 3)
                             │
                    ┌────────┴────────┐
                    ▼                  ▼
              V1 Controllers     V2 Agent Controller
              (report-based)     (data-driven pipeline)
                    │                  │
                    ▼                  ▼
               PptService        Orchestrator Pipeline
                    │            (ingest → viz → plan → assemble → generate)
                    │                  │
                    └──────┬───────────┘
                           ▼
                    pptx_builder.py
                    (per-request PresentationGenerator)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        FrontendJSON  SlideOrchest-  OrchestratorRenderer
        Processor     rator (layout)  (ZIP/XML rendering)
                                       │
                           ┌───────────┼───────────┐
                           ▼           ▼           ▼
                     OpenXMLChart  DataPopulator  SlideImporter
                     Cloner        (chart/table   (last slide
                     (test_open_   population)    template merge)
                      xml.py)
```

### Layer Responsibilities

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **Controllers** | HTTP routing, validation, response wrapping | `api/v1/*.py`, `api/v2/agent_controller.py` |
| **Services** | Business logic, orchestration | `services/ppt_service.py`, `services/template_service.py`, `services/ai_service.py` |
| **Repositories** | Data access (SQLAlchemy async) | `repositories/*.py` |
| **Models** | ORM table definitions | `models/*.py` |
| **Schemas** | Pydantic request/response models | `schemas/*.py` |
| **PPT Engine** | PowerPoint generation pipeline | `ppt_engine/` (see below) |
| **Tools** | Agent pipeline tools (ingest, viz, ppt) | `tools/*.py` |
| **Agents** | V2 pipeline orchestration | `agents/orchestrator.py` |

---

## API Reference

### V1 — Report-Based Generation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/templates` | List all DB templates |
| `POST` | `/api/v1/templates` | Create template with sections |
| `GET` | `/api/v1/templates/{id}` | Template detail with sections |
| `PATCH` | `/api/v1/templates/{id}` | Update template |
| `DELETE` | `/api/v1/templates/{id}` | Delete template |
| `POST` | `/api/v1/templates/{id}/ppt` | Upload `.pptx` deck to template |
| `GET` | `/api/v1/templates/{id}/slides` | Slide metadata from uploaded deck |
| `GET` | `/api/v1/templates/{id}/ppt/download` | Download uploaded deck |
| `GET` | `/api/v1/reports` | List reports |
| `POST` | `/api/v1/reports` | Create report from template |
| `GET` | `/api/v1/reports/{id}` | Report detail with sections |
| `PUT` | `/api/v1/reports/{id}` | Update report |
| `DELETE` | `/api/v1/reports/{id}` | Delete report |
| `GET` | `/api/v1/sections/{id}` | Section detail |
| `PATCH` | `/api/v1/sections/{id}` | Update section |
| `DELETE` | `/api/v1/sections/{id}` | Delete section |
| `POST` | `/api/v1/ai/recommendations` | Generate AI section recommendations |
| `POST` | `/api/v1/ai/commentary` | Generate AI commentary for a section |
| `POST` | `/api/v1/structure/generate` | Generate full report structure |
| `POST` | `/api/v1/generation/generate` | Generate PPT from saved report |
| `POST` | `/api/v1/generation/generate-custom` | Generate PPT from raw JSON payload |
| `GET` | `/api/v1/generation/download/{file_id}` | Download generated PPT |
| `GET` | `/api/v1/ppt-templates/` | List available chart/table `.pptx` templates |
| `GET` | `/api/v1/ppt-templates/categories` | Template category summary |
| `GET` | `/api/v1/drafts` | List saved wizard drafts |
| `PUT` | `/api/v1/drafts` | Save/update wizard draft |
| `GET` | `/api/v1/drafts/{id}` | Load draft by ID |
| `DELETE` | `/api/v1/drafts/{id}` | Delete draft |

### V2 — Agent Pipeline (Data-Driven)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v2/agent/upload` | Upload CSV/XLSX data file |
| `POST` | `/api/v2/agent/generate` | Start async generation job |
| `GET` | `/api/v2/agent/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v2/agent/jobs/{job_id}/download` | Download completed PPT |

---

## Database

SQLite (async via `aiosqlite`). Tables are auto-created on startup via `Base.metadata.create_all`.

### Tables

| Table | Model | Purpose |
|-------|-------|---------|
| `templates` | `TemplateModel` | Named presentation templates (Office/Industrial) |
| `template_sections` | `TemplateSectionModel` | Sections within a template |
| `template_section_elements` | `TemplateSectionElementModel` | Chart/table/commentary elements per section |
| `template_section_templates` | *(M2M association)* | Links templates to sections |
| `reports` | `ReportModel` | User reports created from templates |
| `report_sections` | `ReportSectionModel` | Sections in a report |
| `report_section_elements` | `ReportSectionElementModel` | Elements per report section |
| `generated_reports` | `GeneratedReportModel` | Generation audit trail |
| `drafts` | `DraftModel` | Saved wizard state (JSON blob) |

### Seed Data

On first startup (empty `templates` table), `SeedService` creates 3 demo templates:

- **Office Quarterly Template** (6 sections)
- **Industrial Quarterly Template** (5 sections)
- **Custom Analysis Template** (2 sections)

Each section includes sample chart, table, and commentary elements.

---

## PPT Engine

The engine lives in `app/ppt_engine/` and transforms structured JSON into `.pptx` files through multiple stages.

### Generation Pipeline

```
1. FrontendJSONProcessor   — Parse frontend JSON into orchestrator Section/Block objects
2. SlideOrchestrator       — Determine slide layouts (full_width, grid_2x2, etc.)
3. PresentationGenerator   — Coordinate rendering workflow
4. OrchestratorRenderer    — Render each block to PPTX via ZIP/XML manipulation
5. OpenXMLChartCloner      — Clone chart/table shapes from templates with full styling
6. ChartDataPopulator      — Populate chart Excel data + table cell values
7. SlideImporter           — Merge last-slide/cover templates via ZIP-level copy
8. Normalization           — Fix XML declarations, flag_bits, embedded .xlsx storage
```

### Template System

Two independent template concepts:

| Concept | Source | Purpose |
|---------|--------|---------|
| **Engine templates** | `individual_templates/*.pptx` | Chart/table/slide `.pptx` files cloned during generation |
| **DB deck templates** | SQLite `templates` table + `data/template_decks/` | Named templates with optional uploaded `.pptx` base deck |

Engine templates are registered in `ppt_template_registry.py`. Only files whose stem matches the registry are exposed via `GET /api/v1/ppt-templates/`.

### Registered Engine Templates (23 files)

**Charts:** `bar_chart`, `line_chart`, `multi_line_chart`, `horizontal_bar_chart`, `stacked_bar_chart`, `pie_chart`, `donut_chart`, `combo_chart_singlebar_line`, `combo_chart_doublebar_line`, `combo_chart_stackedbar_line`, `combo_chart_area_bar`, `Single_column_stacked_chart`

**Tables:** `table`, `market_stats_table`, `market_stats_sub_table`, `industrial_figures_template`

**Slide bases:** `first_slide_base`, `base_clean`, `last_slide`, `snapshot_first_slide_base`, `snapshot_base_clean`, `snapshot_last_slide`, `submarket_first_slide_base`

---

## V2 Agent Pipeline

The V2 pipeline provides end-to-end generation from raw data files:

```
Upload CSV/XLSX → Profile Data → Recommend Charts → Plan Sections → Assemble Elements → Generate PPT
```

### Pipeline Steps

1. **Data Profiling** (`ingest_tool`) — Parse uploaded file, detect column types, compute stats
2. **Visualization** (`viz_tool`) — Rule-based chart type recommendation per data shape
3. **Planning** (`ai_service`) — LLM-powered section recommendations (NVIDIA NIM)
4. **Section Assembly** — Map data columns to chart axes, build element configs
5. **Insight Generation** — LLM commentary per section (with template fallback)
6. **PPT Generation** (`ppt_tool`) — Delegates to `pptx_builder.generate_presentation()`

### Modes

| Mode | Behavior |
|------|----------|
| `full` | Complete pipeline: data + structure + PPT |
| `structure_only` | AI recommendations only, no PPT output |
| `ppt_only` | Skip AI planning, generate from provided structure |
| `skeleton` | Minimal structure + PPT |

---

## Configuration

All settings via environment variables (`.env` file). See `.env.example`.

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_API_KEY` | *(required for AI)* | NVIDIA NIM API key for LLM |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | OpenAI-compatible API base |
| `NVIDIA_MODEL` | `meta/llama-3.1-8b-instruct` | LLM model name |
| `NVIDIA_MAX_TOKENS` | `1024` | Max completion tokens |
| `NVIDIA_TEMPERATURE` | `0.7` | Sampling temperature |
| `DATABASE_URL` | `sqlite+aiosqlite:///./autodeck.db` | Database connection string |

---

## Project Structure

```
backend/
├── pyproject.toml                    # Dependencies and build config
├── uv.lock                          # Dependency lockfile
├── .env.example                     # Environment variable template
├── requirements-dev.txt             # Extra dev deps (Streamlit)
├── streamlit_app.py                 # Agent pipeline test UI
├── test_ui.py                       # V2 agent test UI
└── app/
    ├── main.py                      # FastAPI app, lifespan, middleware
    ├── agents/                      # V2 orchestration pipeline
    │   ├── orchestrator.py          #   Linear async pipeline
    │   ├── ppt_agent.py             #   LangGraph-style agent (experimental)
    │   └── state.py                 #   Shared state TypedDict
    ├── api/
    │   ├── v1/                      # 9 REST controllers
    │   └── v2/                      # Agent controller (async jobs)
    ├── core/
    │   ├── config.py                # Pydantic Settings
    │   ├── database.py              # SQLAlchemy async engine + session
    │   ├── dependencies.py          # FastAPI dependency injection
    │   ├── exceptions.py            # Domain exceptions + handlers
    │   └── paths.py                 # backend_root() resolver
    ├── models/                      # SQLAlchemy ORM models (9 tables)
    ├── repositories/                # Data access layer
    ├── schemas/                     # Pydantic request/response models
    ├── services/                    # Business logic layer
    ├── tools/                       # Agent pipeline tools
    ├── ppt_engine/                  # PPT generation engine
    │   ├── pptx_builder.py          #   Main generation entry point
    │   ├── pptx_update.py           #   In-place PPT updates
    │   ├── ppt_helpers_utils/
    │   │   ├── ppt_helpers/
    │   │   │   ├── orchestrator_renderer.py  # Block → PPTX rendering
    │   │   │   ├── slide_orchestrator.py     # Layout engine
    │   │   │   ├── data_populator.py         # Chart/table data population
    │   │   │   ├── test_open_xml.py          # ZIP-level chart/table cloner
    │   │   │   ├── chart_formatting.py       # Axis formatting
    │   │   │   ├── chart_utils.py            # Label utilities
    │   │   │   └── content_height_calculator.py  # Pagination math
    │   │   ├── services/
    │   │   │   ├── presentation_generator.py # Workflow coordinator
    │   │   │   ├── frontend_json_processor.py # JSON → orchestrator blocks
    │   │   │   ├── template_config.py        # Slide constraints + configs
    │   │   │   └── ppt_template_registry.py  # Template filename registry
    │   │   ├── static_data/                  # Mock industrial data
    │   │   └── individual_templates/         # .pptx chart/table templates
    │   └── utils/                   # Slide numbering, organizing
    └── utils/
        ├── formatting.py            # Number/text formatting helpers
        └── logger.py               # Structured logging setup
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy[asyncio]` | ORM + async database |
| `aiosqlite` | SQLite async driver |
| `pydantic` / `pydantic-settings` | Validation + config |
| `python-pptx` | PowerPoint read/write |
| `lxml` | XML manipulation for OOXML |
| `pandas` / `numpy` | Data processing |
| `openpyxl` | Excel file handling |
| `openai` | NVIDIA NIM LLM client |
| `python-dotenv` | Environment file loading |

Dev: `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `httpx`

---

## Development

```bash
# Linting
ruff check app/

# Type checking
mypy app/

# Run tests
pytest

# Streamlit test UI
pip install -r requirements-dev.txt
streamlit run streamlit_app.py
```
