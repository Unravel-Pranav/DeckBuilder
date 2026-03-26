// ─── Enums & Primitives ───

export type PresentationType = 'financial' | 'business' | 'research' | 'custom'
export type ToneType = 'formal' | 'analytical' | 'storytelling'
export type FontStyle = 'modern' | 'corporate' | 'minimal'
export type ColorScheme = 'dark' | 'light' | 'brand'
export type CommentarySource = 'ai' | 'manual' | 'prompt'

// ─── Structural Slide Layouts ─────────────────────────────────────────────────

/**
 * SlideStructure — the physical grid layout of a slide.
 * Content is added into regions independently.
 */
export type SlideStructure =
  | 'blank'       // 1 region  — full slide
  | 'two-col'     // 2 regions — left / right
  | 'two-row'     // 2 regions — top / bottom
  | 'grid-2x2'    // 4 regions — TL / TR / BL / BR

/**
 * A slot inside a slide that can hold exactly one component.
 */
export interface SlideRegion {
  id: string
  component: SlideComponent | null
}

export function getRegionCount(structure: SlideStructure): number {
  switch (structure) {
    case 'blank':    return 1
    case 'two-col':  return 2
    case 'two-row':  return 2
    case 'grid-2x2': return 4
  }
}

export function createRegions(structure: SlideStructure): SlideRegion[] {
  return Array.from({ length: getRegionCount(structure) }, () => ({
    id: crypto.randomUUID(),
    component: null,
  }))
}

export const REGION_LABELS: Record<SlideStructure, string[]> = {
  'blank':    ['Full Slide'],
  'two-col':  ['Left', 'Right'],
  'two-row':  ['Top', 'Bottom'],
  'grid-2x2': ['Top Left', 'Top Right', 'Bottom Left', 'Bottom Right'],
}

// ─── Legacy LayoutType (deprecated, kept for backward compat) ─────────────────

/** @deprecated Use SlideStructure instead */
export type LayoutCategory =
  | 'full_width' | 'two_column' | 'grid' | 'title' | 'kpi' | 'section'

/** @deprecated Use SlideStructure instead */
export type LayoutType =
  | 'full-chart' | 'full-table' | 'commentary-only'
  | 'chart-commentary' | 'table-commentary' | 'quadrant-2c' | 'quadrant-1c1t'
  | 'mixed' | 'quadrant-2c1t1text' | 'quadrant-2c2t'
  | 'title-content' | 'title-2col'
  | 'kpi-highlight'
  | 'section-divider'

export type ChartType = 'bar' | 'pie' | 'line' | 'doughnut' | 'area' | 'scatter'

export type TemplateCategory = 'chart' | 'table' | 'text' | 'slide' | 'uploaded'

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

export interface UploadedSlideData {
  templateId: number
  slideIndex: number
  title: string
  layoutName: string
}

export interface UploadedSlideComponent {
  id: string
  type: 'uploaded_slide'
  templateId?: string
  data: UploadedSlideData
  config: Record<string, unknown>
}

export type SlideComponent = ChartComponent | TableComponent | TextComponent | UploadedSlideComponent

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
export function isUploadedSlideComponent(c: SlideComponent): c is UploadedSlideComponent {
  return c.type === 'uploaded_slide'
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
  defaultStructure?: SlideStructure
  defaultComponents?: Omit<SlideComponent, 'id'>[]
  intelligence?: TemplateIntelligence
}

// ─── Section → Template Binding ───

export interface Slide {
  id: string
  title: string
  structure: SlideStructure
  regions: SlideRegion[]
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
  structure: SlideStructure
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
