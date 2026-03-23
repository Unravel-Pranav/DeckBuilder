# DeckBuilder — AI-Powered Presentation Builder

## Tech Stack

| Layer              | Technology                                      |
| ------------------ | ----------------------------------------------- |
| Framework          | Vue 3 (Composition API + `<script setup>`)      |
| Language           | TypeScript                                      |
| Build Tool         | Vite 8                                          |
| Component Library  | shadcn-vue (Reka UI primitives)                 |
| Styling            | Tailwind CSS v4 + CSS custom properties         |
| State Management   | Pinia                                           |
| Routing            | Vue Router 5                                    |
| Icons              | Lucide Vue Next                                 |
| Drag & Drop        | sortablejs-vue3                                 |
| Design System      | Minimalist Dark (custom amber + slate palette)  |
| Fonts              | Space Grotesk · Inter · JetBrains Mono          |

---

## Design System — Minimalist Dark

The UI uses a dark atmospheric design with layered slate tones and warm amber accents.

- **Background layers**: `#0A0A0F` (deepest) → `#12121A` (sidebar/elevated) → `rgba(26,26,36,0.6)` (cards)
- **Accent**: `#F59E0B` (amber-500) — used for all CTAs, focus rings, active states, glows
- **Cards**: Glass-effect with semi-transparent backgrounds, backdrop blur, and subtle 8% opacity borders
- **Ambient**: Fixed background orbs with blurred amber glow + subtle grid + noise texture
- **Typography**: Space Grotesk (headings), Inter (body), JetBrains Mono (labels/code)
- **Motion**: 200–300ms ease-out transitions, hover scales, ambient pulse animations

---

## Project Structure

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── assets/css/
│   │   └── main.css                    # Tailwind + design tokens + custom utilities
│   ├── components/
│   │   ├── ui/                         # shadcn-vue generated components (button, card, input, etc.)
│   │   ├── layout/
│   │   │   ├── AmbientBackground.vue   # Fixed ambient orbs + noise + grid overlay
│   │   │   ├── AppShell.vue            # Main layout: sidebar + topbar + content
│   │   │   ├── AppSidebar.vue          # Left navigation with step indicator
│   │   │   └── TopBar.vue             # Header bar with breadcrumbs + actions
│   │   ├── shared/
│   │   │   ├── GlassCard.vue           # Reusable glass-morphism card
│   │   │   ├── StepIndicator.vue       # Horizontal step progress pills
│   │   │   └── EmptyState.vue          # Empty state placeholder
│   │   ├── create/
│   │   │   ├── IntentForm.vue          # Presentation type/tone/design form
│   │   │   └── AiSuggestionPanel.vue   # Live AI suggestion preview
│   │   ├── recommendations/
│   │   │   └── SectionCard.vue         # Expandable section recommendation card
│   │   └── builder/
│   │       ├── SlideListPanel.vue      # Left panel: slide thumbnails + add from template
│   │       ├── LayoutSelector.vue      # Layout type strip (chart+text, table+text, etc.)
│   │       ├── TemplateSelector.vue    # Horizontal template preview strip
│   │       ├── TemplateSelectorPanel.vue # Right panel template browser with schema hints
│   │       ├── SlideCanvas.vue         # Main slide preview (bar/line/pie/area/table/text)
│   │       ├── DataInputPanel.vue      # JSON/CSV data input with validation
│   │       └── CommentaryPanel.vue     # AI/prompt/manual commentary generation
│   ├── pages/
│   │   ├── DashboardPage.vue           # Landing — recent presentations + create new
│   │   ├── CreatePresentationPage.vue  # Step 1 — intent definition + AI suggestions
│   │   ├── AiRecommendationsPage.vue   # Step 2 — AI-suggested sections (draggable)
│   │   ├── SectionManagerPage.vue      # Step 3 — drag-and-drop section/slide organizer
│   │   ├── SlideBuilderPage.vue        # Step 4 — 3-panel slide editor (core experience)
│   │   ├── TemplateUploadPage.vue      # Upload custom PPT + placeholder mapping
│   │   ├── TemplateManagementPage.vue  # Template library — browse/create/manage
│   │   ├── PreviewGeneratePage.vue     # Step 5 — slide carousel + generate PPT
│   │   └── OutputPage.vue             # Step 6 — download, share, version history
│   ├── stores/
│   │   ├── presentation.ts            # Presentation metadata, intent, settings
│   │   ├── slides.ts                  # Sections, slides, components, active state
│   │   ├── ai.ts                      # AI recommendations, commentary generation
│   │   ├── templates.ts              # Template library — built-in + custom
│   │   └── ui.ts                     # UI state — sidebar, current step, modals
│   ├── router/
│   │   └── index.ts                  # All routes with lazy loading
│   ├── types/
│   │   ├── presentation.ts           # All TypeScript interfaces
│   │   └── index.ts                  # Re-exports
│   ├── lib/
│   │   ├── utils.ts                  # cn() utility (clsx + tailwind-merge)
│   │   └── mockData.ts              # Mock data for all screens + template library
│   ├── App.vue                       # Root — AppShell + RouterView with transitions
│   └── main.ts                       # Entry — Pinia + Router + CSS
├── components.json                    # shadcn-vue configuration
├── tsconfig.json                      # TypeScript config with @ alias
├── vite.config.ts                     # Vite + Tailwind plugin + path aliases
└── package.json
```

---

## Application Flow

The app follows a linear wizard flow. The sidebar tracks progress through each step.

```
Dashboard → Create → AI Recommendations → Sections → Slide Builder → Preview → Output
    │                                                       ↑
    │           Template Library (standalone page) ─────────┘
    │           Template Upload (standalone page)  ─────────┘
```

### Step 1 — Dashboard (`/`)

- Grid of recent presentations with type icons, status badges, timestamps
- "New Presentation" CTA with amber glow
- "Create New" card with dashed border
- Resets all stores when starting fresh

### Step 2 — Create Presentation (`/create`)

- **Left side**: Intent form
  - Presentation type selection (Financial / Business / Research / Custom) as radio cards
  - Target audience text input
  - Tone toggle (Formal / Analytical / Storytelling)
  - Design preferences dropdowns (font style, color scheme)
  - Reference PPT upload (drag-and-drop zone)
- **Right side**: Live AI suggestion panel
  - Recommended sections list
  - Suggested chart types (pill badges)
  - Tone description
  - Estimated slide count
  - Reacts to form changes with a thinking animation
- Loading state on Continue button prevents double-clicks

### Step 3 — AI Recommendations (`/recommendations`)

- AI generates 4 recommended sections with template suggestions
- Each section is an expandable glass card showing:
  - Section name + description
  - Suggested template badges (chart-heavy, table-heavy, commentary, mixed)
  - Expandable template detail view
- **Drag-and-drop reordering** via grip handles (sortablejs)
- Accept/reject individual sections (checkmark toggle)
- "Accept All" and "Add Custom Section" actions
- AI style note with suggested visual approach
- Validates at least one section is accepted before continuing

### Step 4 — Section Manager (`/sections`)

- Full drag-and-drop section organizer with grip handles
- Expand any section to see and manage its slides
- **Drag-and-drop slide reordering** within sections
- Inline section name editing (click to edit)
- Add/remove sections and slides
- Add Section dialog with name + description
- Each slide shows its layout type badge

### Step 5 — Slide Builder (`/builder`) — Core Experience

Three-panel layout:

**Left Panel** — Slide list
- Grouped by section with section labels
- Slide thumbnails with active state highlighting
- "Add" button opens a **template picker dialog** with:
  - Blank slide option
  - Full slide template library (Title Page, Section Divider, Agenda, Closing, Team, Timeline, Comparison, Quote, KPI, Blank)
  - Mini layout previews for each template

**Center Panel** — Canvas
- **Layout selector strip**: Chart+Text, Table+Text, Full Chart, Full Table, Mixed, Text Only
- **Template selector strip**: Horizontal scrollable gallery of chart/table/text templates with mini previews (bar charts, line charts, pie/doughnut, tables, text blocks)
- **Slide canvas**: 16:9 aspect ratio preview rendering:
  - **Bar charts** — vertical bars with labels
  - **Line/Area charts** — SVG polylines with fill
  - **Pie/Doughnut charts** — conic-gradient with proper percentage calculation and legends
  - **Tables** — actual component data with headers and rows
  - **Commentary** — text content with whitespace preservation
- Inline slide title editing
- "Preview & Generate" continue button
- "Hide/Show Panel" toggle for the right panel

**Right Panel** — Collapsible, 3 tabs:
- **Templates tab**: Browse chart/table/text templates by category, see descriptions, apply to slide, view schema hints when applied
- **Data tab**: JSON editor with:
  - Auto-detected data type (chart vs table) based on current components
  - Dynamic schema examples matching the active type
  - JSON + schema validation (checks for required fields, not just valid JSON)
  - "Use Example" and "Copy" for schemas
  - Apply only replaces the matching component type, preserving others
  - Preserves current chart type (bar/line/pie etc.)
  - CSV upload placeholder
- **Commentary tab**: Three modes:
  - AI Generate — analyzes the dominant component type (chart/table/text) for context
  - From Prompt — user provides focus instructions, prompt is passed to AI
  - Manual — pre-fills with existing commentary for editing

### Step 6 — Preview & Generate (`/preview`)

- Full-width slide carousel with dot navigation
- Previous/Next navigation
- Right sidebar with:
  - Stats cards (section count, slide count)
  - Section list summary
  - "Edit Current Slide" navigates back to builder
- "Generate PPT" button with animated progress bar
- Properly tracks step in sidebar when editing slides

### Step 7 — Output (`/output`)

- Success state with checkmark animation
- Presentation summary card with section breakdown
- Action buttons: Download PPT, Edit, Share, Duplicate
- Version history (mock data with 3 versions)
- "Create Another Presentation" resets all stores

---

## Template Library (`/templates`)

A standalone management page accessible from the sidebar.

### Template Categories (4 types)

| Category | Description | Built-in Count |
|----------|-------------|----------------|
| **Slide** | Full pre-designed slide layouts | 10 |
| **Chart** | Chart component templates | 7 |
| **Table** | Table component templates | 4 |
| **Text** | Text/commentary component templates | 3 |

### Slide Templates (10)

| Template | Kind | Description |
|----------|------|-------------|
| Title Page | `title` | Opening slide with name, subtitle, author, date, logo |
| Section Divider | `section-divider` | Section break with number and title |
| Agenda / Contents | `agenda` | Table of contents listing all sections |
| Thank You / Closing | `closing` | Final slide with contact info |
| Team / About Us | `team` | Member cards with photo placeholders |
| Timeline / Milestones | `timeline` | Horizontal timeline with phases |
| Comparison / vs. | `comparison` | Side-by-side comparison layout |
| Quote / Key Stat | `quote` | Large quote with attribution |
| Big Number / KPI | `kpi` | Featured stat with context |
| Blank Canvas | `blank` | Empty slide to build from scratch |

### Chart Templates (7)

Bar (basic + stacked), Line (trend + multi-line), Pie, Doughnut, Area

### Table Templates (4)

Basic Data Table, Comparison Matrix, Financial Statement, KPI Scorecard

### Text Templates (3)

Key Insights (bullets), Narrative Block (paragraph), Callout/Highlight (big stat)

### Features

- **Filter tabs**: All, Slides, Charts, Tables, Text, My Templates — each with count
- **Search**: Full-text across name, description, chart type, slide kind
- **Grid / List view** toggle
- **Detail dialog**: Full-size preview, metadata, schema hint with copy button
- **Create custom template**: Form with category, type, description, schema hint, sample data
- **Duplicate** any template (creates a custom copy)
- **Delete** custom templates (built-in are protected)
- **Upload PPT** link to the template upload page

---

## Template Upload (`/templates/upload`)

- Drag-and-drop PPT file upload
- Simulated validation pipeline (uploading → validating → valid/invalid)
- Detected placeholder list with type badges
- **Visual layout preview**: 16:9 aspect ratio with positioned placeholder regions
- **Placeholder-to-data binding UI**: Dropdowns mapping each shape to a data field

---

## State Management (Pinia Stores)

### `presentationStore`
- Current presentation metadata (id, name, status)
- Intent data (type, audience, tone, design preferences, reference file)
- Recent presentations list
- `hasIntent` computed (validates audience is provided)

### `slidesStore`
- Sections array with nested slides
- Active slide/section tracking
- CRUD operations: add/remove/reorder sections and slides
- Component updates (chart, table, text data)
- Commentary updates with source tracking (ai/prompt/manual)
- Proper order re-indexing on remove operations

### `aiStore`
- AI recommendation state with loading/error
- Section recommendations with accept/reject/reorder
- Commentary generation with context detection and prompt support
- Error handling with try/catch/finally patterns

### `templatesStore`
- Built-in templates (24 total: 10 slide + 7 chart + 4 table + 3 text)
- Custom templates (user-created)
- Filtered view with search + category filter
- Helper methods: `getSlideTemplates()`, `getComponentTemplates()`
- CRUD: add, remove, duplicate custom templates

### `uiStore`
- Sidebar collapsed state
- Current flow step tracking
- Completed steps set
- Modal state
- Step definitions with labels, routes, and status

---

## Routing

| Path | Page | Description |
|------|------|-------------|
| `/` | DashboardPage | Recent presentations + create new |
| `/create` | CreatePresentationPage | Intent form + AI suggestions |
| `/recommendations` | AiRecommendationsPage | AI-recommended sections |
| `/sections` | SectionManagerPage | Section/slide organizer |
| `/builder` | SlideBuilderPage | 3-panel slide editor |
| `/templates` | TemplateManagementPage | Template library |
| `/templates/upload` | TemplateUploadPage | PPT template upload |
| `/preview` | PreviewGeneratePage | Slide carousel + generate |
| `/output` | OutputPage | Download + share |

All routes use lazy loading via dynamic `import()`.

---

## Key Concepts

### Template (slide component)
A reusable component definition for a single element within a slide:
- **Chart template**: Defines chart type, sample data, rendering config
- **Table template**: Defines column structure, sample rows
- **Text template**: Defines content pattern (bullets, narrative, callout)

### Slide Template (full slide)
A pre-designed full slide layout with default components and content:
- Title pages, section dividers, closing slides, agendas, timelines, etc.
- Includes `defaultLayout`, `defaultComponents`, and `schemaHint`

### Section
A logical grouping of slides (e.g., "Market Overview", "Financial Analysis").

### Report / Presentation
The final PPT output — a collection of sections containing slides.

---

## Running the App

```bash
cd frontend
npm install
npm run dev        # → http://localhost:5173
npm run build      # Production build
npx vue-tsc --noEmit  # Type checking
```
