# System walkthrough

See the root [`README.md`](../README.md) for setup. This document summarizes how data moves through Auto Deck.

## Persistence layers

1. **Pinia + sessionStorage** — live wizard state per browser tab
2. **SQLite drafts** (`PUT /api/v1/drafts`) — resume across sessions
3. **localStorage** — selected brand export deck id (also stored in draft payload)
4. **Generated files** — PPT on disk + `generated_reports` table + in-memory cache

## Main API calls (wizard)

| Step | API |
|------|-----|
| AI Outline | `POST /ai/recommendations`, then `POST /structure/generate` (fallback: client `slideGenerator`) |
| Builder commentary | `POST /ai/commentary` |
| Preview generate | `POST /generation/generate-custom`, `GET /generation/download/{file_id}` |
| Auto-save | `PUT /drafts` |

## Navigation

Router and sidebar both use [`frontend/src/lib/flowAccess.ts`](../frontend/src/lib/flowAccess.ts) predicates. Output requires a successful generation (`generatedFileId`).

## Backend layout

- `backend/app/api/v1/` — wizard REST API
- `backend/app/ppt_engine/` — JSON → `.pptx` pipeline
- `backend/app/api/v2/agent/` — CSV upload jobs (Streamlit tester; not in Vue UI)

## Legacy

`hello/` is a separate application — see [`hello/README.md`](../hello/README.md).
