# DeckBuilder (Auto Deck)

AI-assisted PowerPoint builder: Vue 3 wizard + FastAPI backend + PPT engine.

## Projects

| Directory | Purpose |
|-----------|---------|
| [`frontend/`](frontend/) | Vue 3 + Pinia wizard UI (primary user app) |
| [`backend/`](backend/) | FastAPI API, SQLite drafts, PPT generation engine |
| [`hello/`](hello/) | Legacy CBRE-scale app (separate deployment; not used by the wizard) |
| [`docs/`](docs/) | Architecture and flow documentation |

## Quick start

```bash
# Backend
cd backend
uv sync
cp .env.example .env   # add NVIDIA_API_KEY for live AI
uv run uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — API defaults to http://localhost:8000/api/v1

## Wizard flow (6 steps)

Dashboard → Create → AI Outline → Sections → Builder → Preview → Output

Optional **brand export deck** is configured on Preview (not a sidebar step).

## V2 CSV agent (optional)

CSV/XLSX → deck pipeline is available under `/api/v2/agent` and tested via `backend/streamlit_app.py`. See [`backend/README.md`](backend/README.md).

## Auth (production)

Set `API_KEY` in `backend/.env` to require `X-API-Key` on all API routes except `/health`.

## Tests

```bash
cd backend && uv run pytest
cd frontend && npm test
```
