# Frontend Developer Guide — Auto Deck

This guide explains how the Vue 3 frontend works, how it communicates with the backend, and how to extend it.

---

## Quick Start

```bash
cd frontend
npm install
npm run dev           # http://localhost:5173
```

The frontend expects the backend at `http://localhost:8000/api/v1`. Override via `VITE_API_BASE_URL` in a `.env` file.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Vue 3 (Composition API + `<script setup>`) |
| Language | TypeScript |
| Build | Vite 8 |
| Components | shadcn-vue (Reka UI primitives) |
| Styling | Tailwind CSS v4 + CSS custom properties |
| State | Pinia |
| Routing | Vue Router 5 (lazy loaded) |
| Icons | Lucide Vue Next |
| Drag & Drop | sortablejs-vue3 |
| Fonts | Space Grotesk, Inter, JetBrains Mono |

---

## Application Flow

The app is a linear wizard. Each step is a page, and the sidebar tracks progress.

```
Dashboard → Create → AI Outline → Sections → Slide Builder → Preview → Output
                                              ↑ optional brand deck on Preview
              Slide library (/templates) ─────┘
              Upload brand deck (/templates/upload) ── optional
```

| Route | Page Component | Step |
|-------|---------------|------|
| `/` | `DashboardPage.vue` | Saved drafts + create new |
| `/create` | `CreatePresentationPage.vue` | 1. Define intent (type, audience, tone) |
| `/recommendations` | `AiRecommendationsPage.vue` | 2. Accept/reject AI outline (`POST /structure/generate` seeds slides) |
| `/sections` | `SectionManagerPage.vue` | 3. Organize sections & slides (drag-and-drop) |
| `/builder` | `SlideBuilderPage.vue` | 4. Edit slides (3-panel editor) |
| `/preview` | `PreviewGeneratePage.vue` | 5. Preview, optional brand deck, generate |
| `/output` | `OutputPage.vue` | 6. Download (requires `generatedFileId`) |
| `/templates` | `TemplateManagementPage.vue` | Engine slide library (standalone) |
| `/templates/upload` | `TemplateUploadPage.vue` | Upload brand export `.pptx` |

---

## Project Structure

```
src/
├── assets/css/main.css         # Tailwind config + design tokens
├── components/
│   ├── ui/                     # shadcn-vue primitives (Button, Card, Input, etc.)
│   ├── layout/                 # AppShell, AppSidebar, TopBar, AmbientBackground
│   ├── shared/                 # GlassCard, StepIndicator, EmptyState
│   ├── create/                 # IntentForm, AiSuggestionPanel
│   ├── recommendations/        # SectionCard
│   └── builder/                # SlideListPanel, SlideCanvas, DataInputPanel,
│                               # CommentaryPanel, LayoutSelector, TemplateSelector,
│                               # TemplateSelectorPanel
├── pages/                      # One page per route (listed above)
├── stores/                     # Pinia stores
├── router/index.ts             # Route definitions
├── types/presentation.ts       # TypeScript interfaces
├── lib/
│   ├── api.ts                  # Backend API client
│   ├── utils.ts                # cn() utility
│   ├── layoutDefinitions.ts    # Slide layout → backend mapping
│   └── mockData.ts             # Seed data for development
├── App.vue                     # Root layout
└── main.ts                     # Entry point
```

---

## State Management (Pinia Stores)

Five stores manage all application state. They are defined in `src/stores/`.

### `presentationStore` (`presentation.ts`)

Holds presentation metadata and user intent.

| Key state | Description |
|-----------|-------------|
| `presentation` | Current deck (id, name, status) |
| `recentPresentations` | Dashboard list |
| `intent` | Type, audience, tone, design preferences |
| `hasIntent` | Computed: validates minimum fields are set |

### `slidesStore` (`slides.ts`)

The core data model. Sections contain slides; slides contain regions; regions hold components.

```
Section[]
  └── Slide[]
        ├── title
        ├── structure       ("blank" | "two-col" | "two-row" | "grid-2x2")
        ├── regions[]       (positioned slots for components)
        │     └── component (chart | table | text | uploaded_slide)
        └── commentary      (optional text block)
```

Key actions: `addSection`, `removeSection`, `reorderSections`, `addSlide`, `removeSlide`, `reorderSlides`, `updateComponent`, `updateCommentary`.

### `aiStore` (`ai.ts`)

Manages AI interactions — section recommendations and commentary generation.

### `templatesStore` (`templates.ts`)

Built-in templates (24 total) + user-created custom templates. Filtered by category and search text. Also fetches backend PPT engine templates and deck templates from the database.

### `uiStore` (`ui.ts`)

UI chrome state: sidebar collapsed, current wizard step, completed steps.

---

## Backend Communication

All backend calls go through `src/lib/api.ts`.

### API Client Pattern

Every backend endpoint returns a standardized `ApiResponse<T>`:

```typescript
interface ApiResponse<T> {
  success: boolean
  error_code: string | null
  data: T | null
  error: { message: string; details: string[] | null } | null
}
```

The `unwrapResponse(json)` helper extracts `data` or throws an `Error` with the message. All fetch functions follow the same pattern:

```typescript
const response = await fetch(`${API_BASE_URL}/endpoint`)
const json: ApiResponse<MyType> = await response.json()
if (!response.ok || !json.success) throw new Error(formatApiError(json))
return unwrapResponse(json)
```

### Key API Functions

| Function | Endpoint | Purpose |
|----------|----------|---------|
| `generatePPT(payload)` | `POST /generation/generate-custom` | Send slide data, get file ID |
| `downloadFile(fileId, fileName)` | `GET /generation/download/{fileId}` | Trigger browser download |
| `fetchPptTemplates()` | `GET /ppt-templates/` | List engine `.pptx` templates |
| `fetchDeckTemplates()` | `GET /templates` | List DB deck templates |
| `uploadDeckTemplatePpt(id, file)` | `POST /templates/{id}/ppt` | Upload `.pptx` to a deck template |
| `fetchTemplateSlides(id)` | `GET /templates/{id}/slides` | Get slide metadata from uploaded deck |
| `saveDraft(payload)` | `PUT /drafts` | Save wizard state |
| `loadDraft(draftId)` | `GET /drafts/{draftId}` | Restore wizard state |
| `listDrafts()` | `GET /drafts` | List saved drafts |
| `deleteDraft(draftId)` | `DELETE /drafts/{draftId}` | Delete a draft |

### Data Transformation

`transformToBackendFormat()` in `api.ts` converts the frontend data model (sections, slides, regions, components) into the flat JSON structure the backend PPT engine expects:

```
Frontend                          Backend
─────────                         ──────────
Section                    →      { name, layout_preference, elements[] }
  Slide                    →      (grouped by slide_group index)
    Region                 →      element with quadrant_position
      Component (chart)    →      element_type: "chart", config: { chart_data, chart_type, ... }
      Component (table)    →      element_type: "table", config: { table_data, ... }
      Component (text)     →      element_type: "commentary", config: { commentary_text }
```

Chart types are mapped via `mapChartType()`:
- `bar` → `"Bar Chart"`
- `line` (1 dataset) → `"Line - Single axis"`
- `line` (2+ datasets) → `"Line - Multi axis"`
- `pie` → `"Pie Chart"`
- `doughnut` → `"Donut Chart"`

---

## Design System

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| Deepest background | `#0A0A0F` | Page base |
| Elevated background | `#12121A` | Sidebar, panels |
| Card background | `rgba(26,26,36,0.6)` | Glass cards |
| Accent | `#F59E0B` (amber-500) | CTAs, focus rings, active states |
| Border | `rgba(255,255,255,0.08)` | Card borders |

### Typography

| Font | Role |
|------|------|
| Space Grotesk | Headings |
| Inter | Body text |
| JetBrains Mono | Labels, code, monospace |

### Effects

- Glass-morphism cards with `backdrop-filter: blur`
- Ambient background orbs with amber glow
- Subtle grid + noise texture overlay
- 200-300ms ease-out transitions

---

## Slide Builder (Core Page)

The slide builder at `/builder` is the most complex page. It has three panels:

### Left Panel — Slide List
Slides grouped by section. Click to select. "Add" button opens a template picker dialog with 10 pre-designed slide templates + blank option.

### Center Panel — Canvas
1. **Layout selector strip** — Choose slide structure (Chart+Text, Table+Text, Full Chart, etc.)
2. **Template selector strip** — Pick a chart/table/text template to apply
3. **Canvas** — 16:9 live preview rendering charts (bar/line/pie/area), tables, and text

### Right Panel — Collapsible, 3 Tabs
1. **Templates** — Browse and apply component templates
2. **Data** — JSON editor with schema validation, auto-detected data type
3. **Commentary** — AI Generate / From Prompt / Manual entry

---

## Component Types

Four component types can be placed in slide regions:

### Chart Component
```typescript
{
  type: 'chart',
  data: {
    type: 'bar' | 'line' | 'pie' | 'doughnut' | 'area' | 'scatter',
    labels: string[],
    datasets: [{ label: string, data: number[] }]
  }
}
```

### Table Component
```typescript
{
  type: 'table',
  data: {
    headers: string[],
    rows: string[][]
  }
}
```

### Text Component
```typescript
{
  type: 'text',
  data: {
    content: string,
    format: 'bullets' | 'paragraph' | 'callout'
  }
}
```

### Uploaded Slide Component
```typescript
{
  type: 'uploaded_slide',
  data: {
    templateId: number,
    slideIndex: number
  }
}
```

---

## Slide Structures

Each slide has a `structure` that determines region layout:

| Structure | Regions | Description |
|-----------|---------|-------------|
| `blank` | 1 | Full-width single region |
| `two-col` | 2 | Side-by-side columns |
| `two-row` | 2 | Stacked rows |
| `grid-2x2` | 4 | 2x2 grid quadrants |

The `layoutDefinitions.ts` file maps these structures to backend layout preferences (e.g., `"Content (2x2 Grid)"`, `"Content (two-column)"`).

---

## Template System

Two independent template layers:

### Frontend Templates (Pinia store)
24 built-in templates (10 slide layouts, 7 chart, 4 table, 3 text). Users can create, duplicate, and delete custom templates. These live entirely in the frontend and define what the slide canvas renders.

### Backend Engine Templates
`.pptx` files on disk (23 registered). These are the actual PowerPoint templates used during PPT generation. The frontend fetches their metadata via `GET /api/v1/ppt-templates/` and displays them in the Template Management page.

### Backend Deck Templates
Named templates stored in the database with optional uploaded `.pptx` base decks. These define report structure (sections + elements) and can have a PPT deck attached for branding.

---

## Adding a New Page

1. Create `src/pages/MyPage.vue` using `<script setup lang="ts">`
2. Add a route in `src/router/index.ts` with lazy import
3. If it's a wizard step, add it to `uiStore.steps` in `src/stores/ui.ts`
4. Add a sidebar link in `src/components/layout/AppSidebar.vue`

## Adding a New Component Type

1. Define the TypeScript interface in `src/types/presentation.ts`
2. Add rendering logic in `src/components/builder/SlideCanvas.vue`
3. Add data editor support in `src/components/builder/DataInputPanel.vue`
4. Add the backend mapping in `transformToBackendFormat()` in `src/lib/api.ts`
5. Map the chart type in `mapChartType()` if it's a chart variant

## Adding a New API Call

1. Define request/response TypeScript interfaces in `src/lib/api.ts`
2. Create the fetch function following the `ApiResponse<T>` + `unwrapResponse()` pattern
3. Call it from a Pinia store action or directly from a component

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Backend API base URL |

Create a `.env` file in `frontend/` to override.

---

## Build & Tooling

```bash
npm run dev             # Development server with HMR
npm run build           # Production build to dist/
npm run preview         # Preview production build locally
npx vue-tsc --noEmit    # TypeScript type checking
```
