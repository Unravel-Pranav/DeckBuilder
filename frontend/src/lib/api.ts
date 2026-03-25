import type { Section, Slide, SlideComponent, Presentation, ChartDataset } from '@/types'
import { getBackendPreference } from '@/lib/layoutDefinitions'

export { getBackendPreference as LAYOUT_TO_BACKEND }

function resolveLayoutPreference(slides: Slide[]): string {
  if (!slides.length) return 'Content (2x2 Grid)'
  return getBackendPreference(slides[0].structure)
}

/**
 * Maps a region index to a quadrant_position for the backend.
 * blank → 0, two-col → 0|1, two-row → 0|2, grid-2x2 → 0|1|2|3
 */
function regionToQuadrant(structure: string, regionIndex: number): number {
  switch (structure) {
    case 'two-row': return regionIndex === 0 ? 0 : 2
    default: return regionIndex
  }
}

/**
 * Transforms frontend presentation data to the format expected by the backend PPT engine.
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
      layout_preference: resolveLayoutPreference(section.slides),
      elements: section.slides.reduce((acc: any[], slide: Slide, slideIdx: number) => {
        const slideElements: any[] = []
        const structure = slide.structure
        const isFullWidth = structure === 'blank'
        const layoutCategory = isFullWidth ? 'full_width'
          : (structure === 'grid-2x2' ? 'grid' : 'two_column')

        slide.regions.forEach((region, regionIdx) => {
          if (!region.component) return
          const comp = region.component

          const quadrantPosition = regionToQuadrant(structure, regionIdx)

          const element: any = {
            id: comp.id,
            element_type: comp.type === 'text' ? 'commentary' : comp.type,
            label: slide.title,
            display_order: slideIdx * 10 + regionIdx,
            slide_group: slideIdx,
            config: {
              layout_category: layoutCategory,
              ...(structure !== 'blank' ? { quadrant_position: quadrantPosition } : {}),
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
              render_full_table: isFullWidth,
            }
          } else if (comp.type === 'text') {
            element.config = {
              ...element.config,
              commentary_text: comp.data?.content || '',
            }
          }

          slideElements.push(element)
        })

        // Preserve slide-level commentary even when there is no explicit text component.
        const hasTextInRegion = slide.regions.some((r) => r.component?.type === 'text')
        if (!hasTextInRegion && slide.commentary?.trim()) {
          slideElements.push({
            id: `${slide.id}-commentary`,
            element_type: 'commentary',
            label: slide.title,
            display_order: slideIdx * 10 + slide.regions.length,
            slide_group: slideIdx,
            config: {
              commentary_text: slide.commentary.trim(),
            },
          })
        }

        return [...acc, ...slideElements]
      }, []),
    })),
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

export function downloadFile(fileId: string, fileName: string) {
  const url = `${API_BASE_URL}/generation/download/${fileId}`
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', fileName)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

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
