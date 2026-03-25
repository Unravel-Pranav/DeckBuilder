import type { Section, Slide, SlideComponent, Presentation, ChartDataset } from '@/types'
import { LAYOUT_BY_ID, getBackendPreference } from '@/lib/layoutDefinitions'

// Re-export for backward compatibility with any component that imported LAYOUT_TO_BACKEND
export { getBackendPreference as LAYOUT_TO_BACKEND }

// Resolve the dominant layout_preference for a section from its slides
function resolveLayoutPreference(slides: Slide[]): string {
  if (!slides.length) return 'Content (2x2 Grid)'
  return getBackendPreference(slides[0].layout)
}

/**
 * Transforms frontend presentation data to the format expected by the backend PPT engine.
 * @param deckTemplateId — DB `templates.id` with an attached .pptx; used as base deck for export.
 */
export function transformToBackendFormat(
  presentation: Presentation,
  sections: Section[],
  deckTemplateId?: number | null,
) {
  return {
    report: {
      id: presentation.id,
      name: presentation.name,
      ...(deckTemplateId != null ? { template_id: deckTemplateId } : {}),
      property_type: presentation.intent.type === 'business' ? 'Office' : 'Industrial',
      property_sub_type: 'figures',
      quarter: '2025 Q1',
    },
    sections: sections.map((section: Section) => ({
      id: section.id,
      name: section.name,
      display_order: section.order,
      // Wire the frontend layout selection to the backend orchestrator
      layout_preference: resolveLayoutPreference(section.slides),
      elements: section.slides.reduce((acc: any[], slide: Slide, slideIdx: number) => {
        // Resolve layout definition from the registry (falls back gracefully to undefined)
        const layoutDef = LAYOUT_BY_ID[slide.layout]
        const useFullTable = layoutDef?.fullTableMode ?? false
        const quadrantPositions = layoutDef?.quadrantPositions ?? null

        // Flatten slides into elements for the backend orchestrator
        const slideElements = slide.components.map((comp: SlideComponent, compIdx: number) => {
          const quadrantPin =
            quadrantPositions != null ? (quadrantPositions[compIdx] ?? null) : null

          const element: any = {
            id: comp.id,
            element_type: comp.type === 'text' ? 'commentary' : comp.type,
            label: slide.title,
            display_order: slideIdx * 10 + compIdx,
            config: {
              // layout_category so the backend can apply category-specific logic
              layout_category: layoutDef?.category ?? 'full_width',
              ...(quadrantPin != null ? { quadrant_position: quadrantPin } : {}),
            },
          }

          if (comp.type === 'chart') {
            const chartData = []
            const labels = comp.data.labels
            for (let i = 0; i < labels.length; i++) {
              const row: any = { quarter: labels[i] }
              comp.data.datasets.forEach((ds: ChartDataset) => {
                row[ds.label] = ds.data[i]
              })
              chartData.push(row)
            }
            element.config = {
              ...element.config,
              chart_type: mapChartType(comp.data.type),
              chart_name: slide.title,
              chart_data: chartData,
              primary_y_axis_title: comp.data.datasets[0]?.label || '',
            }
          } else if (comp.type === 'table') {
            const tableData = comp.data.rows.map((row: string[]) => {
              const rowObj: any = {}
              comp.data.headers.forEach((header: string, i: number) => {
                rowObj[header] = row[i]
              })
              return rowObj
            })
            element.config = {
              ...element.config,
              table_data: tableData,
              figure_name: slide.title,
              ...(useFullTable ? { render_full_table: true } : {}),
            }
          } else if (comp.type === 'text') {
            element.config = {
              ...element.config,
              commentary_text: comp.data?.content || '',
            }
          }

          return element
        })

        // Preserve slide-level commentary even when there is no explicit text component.
        const hasTextComponent = slide.components.some((c) => c.type === 'text')
        if (!hasTextComponent && slide.commentary?.trim()) {
          slideElements.push({
            id: `${slide.id}-commentary`,
            element_type: 'commentary',
            label: slide.title,
            display_order: slideIdx * 10 + slide.components.length,
            config: {
              commentary_text: slide.commentary.trim(),
            },
          })
        }

        return [...acc, ...slideElements]
      }, [])
    }))
  }
}

function mapChartType(type: string): string {
  const map: Record<string, string> = {
    bar: 'Bar Chart',
    line: 'Line - Single axis',
    pie: 'Pie Chart',
    doughnut: 'Donut Chart',
    area: 'Combo - Area + Bar',
    scatter: 'Line - Multi axis',
  }
  return map[type] || 'Bar Chart'
}

const envApi = import.meta.env.VITE_API_BASE_URL as string | undefined
export const API_BASE_URL = envApi ?? 'http://localhost:8000/api/v1'

/** FastAPI often returns `detail` as a string or a validation error list. */
export function formatFastApiDetail(detail: unknown): string | null {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === 'object' && 'msg' in item) {
        return String((item as { msg: string }).msg)
      }
      return JSON.stringify(item)
    })
    return parts.join(' ')
  }
  return null
}

export async function generatePPT(payload: any) {
  const response = await fetch(`${API_BASE_URL}/generation/generate-custom`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to generate PPT')
  }

  return await response.json()
}

/**
 * Downloads a file from the server
 */
export function downloadFile(fileId: string, fileName: string) {
  const url = `${API_BASE_URL}/generation/download/${fileId}`
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', fileName)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/**
 * Fetches available PPT templates from the backend filesystem.
 * No database required — reads from the individual_templates directory.
 */
export interface BackendTemplate {
  filename: string
  stem: string
  name: string
  category: 'chart' | 'table' | 'front_page' | 'last_page' | 'base' | 'other'
  chart_type: string | null
  table_type: string | null
  size: number
}

export interface BackendTemplatesResponse {
  templates: BackendTemplate[]
  count: number
  categories: Record<string, BackendTemplate[]>
}

export async function fetchPptTemplates(): Promise<BackendTemplatesResponse> {
  const response = await fetch(`${API_BASE_URL}/ppt-templates/`)
  if (!response.ok) {
    throw new Error('Failed to fetch PPT templates')
  }
  return await response.json()
}

/** DB template row (reusable presentation structure) from DeckBuilder API. */
export interface DeckTemplate {
  id: number
  name: string
  base_type: string
  is_default: boolean
  attended: boolean
  ppt_status: string
  ppt_attached_time: string | null
  ppt_url: string | null
  created_at: string
  last_modified: string
}

export interface DeckTemplateListResponse {
  total_count: number
  items: DeckTemplate[]
}

export async function fetchDeckTemplates(): Promise<DeckTemplateListResponse> {
  const response = await fetch(`${API_BASE_URL}/templates`)
  if (!response.ok) {
    throw new Error('Failed to fetch templates')
  }
  return await response.json()
}

export function deckTemplatePptDownloadUrl(templateId: number): string {
  return `${API_BASE_URL}/templates/${templateId}/ppt/download`
}

export async function uploadDeckTemplatePpt(
  templateId: number,
  file: File,
): Promise<DeckTemplate> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`${API_BASE_URL}/templates/${templateId}/ppt`, {
    method: 'POST',
    body,
  })
  if (!response.ok) {
    let message = `Failed to upload template PPT (${response.status})`
    try {
      const err = (await response.json()) as { detail?: unknown }
      const d = formatFastApiDetail(err?.detail)
      if (d) message = d
    } catch {
      /* ignore */
    }
    throw new Error(message)
  }
  return await response.json()
}
