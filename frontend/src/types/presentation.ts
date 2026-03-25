// ─── Enums & Primitives ───

export type PresentationType = 'financial' | 'business' | 'research' | 'custom'
export type ToneType = 'formal' | 'analytical' | 'storytelling'
export type FontStyle = 'modern' | 'corporate' | 'minimal'
export type ColorScheme = 'dark' | 'light' | 'brand'
export type CommentarySource = 'ai' | 'manual' | 'prompt'

/**
 * layout_category — broad grouping that drives backend routing and UI organisation.
 * Mirrors the LayoutCategory type in lib/layoutDefinitions.ts.
 */
export type LayoutCategory =
  | 'full_width'   // Single element spans full slide
  | 'two_column'   // Two side-by-side panels
  | 'grid'         // Full 2×2 four-quadrant grid
  | 'title'        // Title / intro slide
  | 'kpi'          // KPI / highlight numbers
  | 'section'      // Section divider

export type LayoutType =
  // ── full_width ──────────────────────────────────────────────────────────────
  | 'full-chart'          // One chart, full slide width
  | 'full-table'          // One table, full slide width — all rows shown
  | 'commentary-only'     // Text commentary, full width
  // ── two_column ─────────────────────────────────────────────────────────────
  | 'chart-commentary'    // Chart (left) + commentary text (right)
  | 'table-commentary'    // Table (left) + commentary text (right)
  | 'quadrant-2c'         // 2 charts side-by-side
  | 'quadrant-1c1t'       // 1 chart (left) + 1 table (right)
  // ── grid (4-quadrant) ───────────────────────────────────────────────────────
  | 'mixed'               // Auto-ordered: charts → tables → commentary
  | 'quadrant-2c1t1text'  // 2 Charts (top) + Table (BL) + Commentary (BR)
  | 'quadrant-2c2t'       // 2 Charts (top) + 2 Tables (bottom) — all rows shown
  // ── title ───────────────────────────────────────────────────────────────────
  | 'title-content'       // Bold title + body text / commentary
  | 'title-2col'          // Bold title + two content columns
  // ── kpi ─────────────────────────────────────────────────────────────────────
  | 'kpi-highlight'       // Large KPI numbers with supporting context
  // ── section ─────────────────────────────────────────────────────────────────
  | 'section-divider'     // Visual section break slide

export type ChartType = 'bar' | 'pie' | 'line' | 'doughnut' | 'area' | 'scatter'

export type TemplateCategory = 'chart' | 'table' | 'text' | 'slide'

export type SlideKind =
  | 'title'
  | 'section-divider'
  | 'closing'
  | 'agenda'
  | 'team'
  | 'timeline'
  | 'comparison'
  | 'quote'
  | 'kpi'
  | 'content'
  | 'blank'

export type FlowStep =
  | 'create'
  | 'recommendations'
  | 'sections'
  | 'builder'
  | 'upload'
  | 'preview'
  | 'output'

// ─── Strict Component Model ───

export interface ChartConfig {
  showLegend?: boolean
  showGrid?: boolean
  stacked?: boolean
  colorPalette?: string[]
}

export interface TableConfig {
  striped?: boolean
  highlightFirst?: boolean
  compact?: boolean
}

export interface TextConfig {
  format: 'bullets' | 'paragraph' | 'callout' | 'numbered'
}

export interface ChartData {
  type: ChartType
  labels: string[]
  datasets: ChartDataset[]
}

export interface ChartDataset {
  label: string
  data: number[]
  backgroundColor?: string[]
  borderColor?: string
}

export interface TableData {
  headers: string[]
  rows: string[][]
}

export interface ChartComponent {
  id: string
  type: 'chart'
  templateId?: string
  data: ChartData
  config: ChartConfig
}

export interface TableComponent {
  id: string
  type: 'table'
  templateId?: string
  data: TableData
  config: TableConfig
}

export interface TextComponent {
  id: string
  type: 'text'
  templateId?: string
  data: { content: string }
  config: TextConfig
}

export type SlideComponent = ChartComponent | TableComponent | TextComponent

// Legacy-compatible helper
export function isChartComponent(c: SlideComponent): c is ChartComponent {
  return c.type === 'chart'
}
export function isTableComponent(c: SlideComponent): c is TableComponent {
  return c.type === 'table'
}
export function isTextComponent(c: SlideComponent): c is TextComponent {
  return c.type === 'text'
}

// ─── Schema Contract ───

export interface DataSchema {
  type: 'chart' | 'table' | 'text'
  required: string[]
  optional?: string[]
  example: Record<string, unknown>
}

// ─── Template Intelligence ───

export interface TemplateIntelligence {
  supportedDataShapes: DataSchema[]
  bestUseCases: PresentationType[]
  fallbackType?: ChartType | 'table' | 'text'
  autoSelectScore?: number
}

export interface SlidePreviewElement {
  type: 'heading' | 'subheading' | 'body' | 'image-placeholder' | 'icon-row' | 'list' | 'divider' | 'accent-bar'
  label: string
  x: number
  y: number
  w: number
  h: number
}

export interface SlidePreviewData {
  title: string
  subtitle?: string
  elements: SlidePreviewElement[]
  accentPosition?: 'top' | 'left' | 'center' | 'bottom'
}

export interface SlideTemplate {
  id: string
  name: string
  category: TemplateCategory
  chartType?: ChartType
  slideKind?: SlideKind
  description: string
  previewData: ChartData | TableData | string | SlidePreviewData
  schemaHint: string
  defaultLayout?: LayoutType
  defaultComponents?: Omit<SlideComponent, 'id'>[]
  intelligence?: TemplateIntelligence
}

// ─── Section → Template Binding ───

export interface Slide {
  id: string
  title: string
  layout: LayoutType
  components: SlideComponent[]
  commentary: string
  commentarySource: CommentarySource
  order: number
  templateId?: string
}

export interface Section {
  id: string
  name: string
  description: string
  slides: Slide[]
  order: number
  recommendedTemplateIds: string[]
  selectedTemplateId?: string
}

// ─── Presentation ───

export interface DesignPreferences {
  fontStyle: FontStyle
  colorScheme: ColorScheme
}

export interface PresentationIntent {
  type: PresentationType
  audience: string
  tone: ToneType
  designPreferences: DesignPreferences
  referenceFile: File | null
}

export interface Presentation {
  id: string
  name: string
  intent: PresentationIntent
  sections: Section[]
  createdAt: string
  updatedAt: string
  status: 'draft' | 'generating' | 'complete'
}

// ─── Versioned Generation ───

export interface GeneratedReport {
  id: string
  presentationId: string
  version: number
  generatedAt: string
  slidesSnapshot: Section[]
  intentSnapshot: PresentationIntent
  fileUrl?: string
}

// ─── AI Recommendations ───

export interface AiRecommendation {
  sections: SectionRecommendation[]
  suggestedStyle: string
  suggestedChartTypes: ChartType[]
}

export interface SectionRecommendation {
  id: string
  name: string
  description: string
  suggestedTemplates: TemplateRecommendation[]
  accepted: boolean
}

export interface TemplateRecommendation {
  id: string
  name: string
  type: 'chart-heavy' | 'table-heavy' | 'commentary' | 'mixed'
  layout: LayoutType
  previewDescription: string
  templateRef?: string
}

// ─── Template Upload ───

export interface UploadedTemplate {
  id: string
  fileName: string
  placeholders: TemplatePlaceholder[]
  status: 'validating' | 'valid' | 'invalid'
}

export interface TemplatePlaceholder {
  id: string
  shapeLabel: string
  boundField: string | null
  type: 'chart' | 'table' | 'text' | 'image'
  x: number
  y: number
  width: number
  height: number
}

// ─── Backend API Contract ───

export interface ApiSyncPoint {
  endpoint: string
  method: 'GET' | 'POST' | 'PUT'
  trigger: string
  payload?: string
  response?: string
}

export const API_SYNC_POINTS: ApiSyncPoint[] = [
  {
    endpoint: '/api/presentations',
    method: 'POST',
    trigger: 'After intent definition (Create page → Continue)',
    payload: 'PresentationIntent',
    response: 'AiRecommendation',
  },
  {
    endpoint: '/api/presentations/:id/structure',
    method: 'POST',
    trigger: 'After section finalization (Sections page → Continue)',
    payload: 'Section[] with selectedTemplateIds',
    response: 'Section[] with auto-generated slides',
  },
  {
    endpoint: '/api/presentations/:id/commentary',
    method: 'POST',
    trigger: 'During builder (Generate Commentary button)',
    payload: '{ slideId, components, sectionContext, intent }',
    response: '{ commentary: string }',
  },
  {
    endpoint: '/api/presentations/:id/generate',
    method: 'POST',
    trigger: 'Preview page → Generate PPT',
    payload: 'Full presentation snapshot',
    response: 'GeneratedReport with fileUrl',
  },
  {
    endpoint: '/api/presentations/:id/versions',
    method: 'GET',
    trigger: 'Output page load',
    response: 'GeneratedReport[]',
  },
]
