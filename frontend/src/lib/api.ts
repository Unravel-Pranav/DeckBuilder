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
  const now = new Date()
  const quarter = `${now.getFullYear()} Q${Math.ceil((now.getMonth() + 1) / 3)}`

  return {
    report: {
      id: presentation.id,
      name: presentation.name,
      ...(deckTemplateId != null ? { template_id: deckTemplateId } : {}),
      property_type: presentation.intent.type === 'business' ? 'Office' : 'Industrial',
      property_sub_type: 'figures',
      quarter,
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
              const row: any = { category: labels[i] }
              comp.data.datasets.forEach((ds: ChartDataset) => {
                row[ds.label] = ds.data[i]
              })
              chartData.push(row)
            }
            const isMultiAxis = comp.data.type === 'scatter' && comp.data.datasets.length > 1
            element.config = {
              ...element.config,
              chart_type: mapChartType(comp.data.type, comp.data.datasets.length),
              chart_name: slide.title,
              chart_data: chartData,
              primary_y_axis_title: comp.data.datasets[0]?.label || '',
              axisConfig: {
                xAxis: [{ key: 'category', name: 'Category' }],
                yAxis: comp.data.datasets.map((ds: ChartDataset, i: number) => ({
                  key: ds.label,
                  name: ds.label,
                  isPrimary: i === 0,
                })),
                isMultiAxis,
              },
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
          } else if (comp.type === 'uploaded_slide') {
            element.element_type = 'uploaded_slide'
            element.config = {
              ...element.config,
              source_template_id: comp.data.templateId,
              source_slide_index: comp.data.slideIndex,
            }
          }

          slideElements.push(element)
        })

        // Only include slide-level commentary when the user deliberately wrote or
        // requested it (manual entry or prompt-based generation). Auto-populated
        // boilerplate from template generation is excluded. If commentary was
        // placed in a region as a text component it is already handled above.
        const hasTextInRegion = slide.regions.some((r) => r.component?.type === 'text')
        const wasUserAuthored = slide.commentarySource === 'manual' || slide.commentarySource === 'prompt'
        if (!hasTextInRegion && slide.commentary?.trim() && wasUserAuthored) {
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

function mapChartType(type: string, datasetCount: number = 1): string {
  if (type === 'line') {
    return datasetCount > 1 ? 'Line - Multi axis' : 'Line - Single axis'
  }
  if (type === 'area') {
    return datasetCount > 1 ? 'Area - Multi axis' : 'Area - Single axis'
  }
  const map: Record<string, string> = {
    bar: 'Bar Chart',
    pie: 'Pie Chart',
    doughnut: 'Donut Chart',
    scatter: 'Line - Multi axis',
  }
  return map[type] || 'Bar Chart'
}

const envApi = import.meta.env.VITE_API_BASE_URL as string | undefined
export const API_BASE_URL = envApi ?? 'http://localhost:8000/api/v1'

/**
 * Standardized API response format from backend.
 */
export interface ApiResponse<T> {
  success: boolean
  error_code: string | null
  data: T | null
  error: {
    message: string
    details: string[] | null
  } | null
}

/**
 * Extracts data from standardized API response or throws an error.
 */
export function unwrapResponse<T>(response: ApiResponse<T>): T {
  if (!response.success || response.data === null) {
    const message = response.error?.message || 'Unknown error'
    const details = response.error?.details?.join(', ')
    throw new Error(details ? `${message}: ${details}` : message)
  }
  return response.data
}

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

/**
 * Formats error from new API response format.
 */
export function formatApiError(response: ApiResponse<unknown>): string {
  if (response.error) {
    const details = response.error.details?.join(', ')
    return details ? `${response.error.message}: ${details}` : response.error.message
  }
  return 'Unknown error'
}

export interface GeneratePPTResult {
  file_id: string
  file_path: string
  filename: string
  created_at: string
  title: string
  author: string
  sections_count: number
}

export async function generatePPT(payload: any): Promise<GeneratePPTResult> {
  const response = await fetch(`${API_BASE_URL}/generation/generate-custom`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  const json: ApiResponse<GeneratePPTResult> = await response.json()

  if (!response.ok || !json.success) {
    throw new Error(formatApiError(json))
  }

  return unwrapResponse(json)
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
  const json: ApiResponse<BackendTemplatesResponse> = await response.json()

  if (!response.ok || !json.success) {
    throw new Error(formatApiError(json))
  }

  return unwrapResponse(json)
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
  const json: ApiResponse<DeckTemplateListResponse> = await response.json()

  if (!response.ok || !json.success) {
    throw new Error(formatApiError(json))
  }

  return unwrapResponse(json)
}

export function deckTemplatePptDownloadUrl(templateId: number): string {
  return `${API_BASE_URL}/templates/${templateId}/ppt/download`
}

export interface UploadedSlideInfo {
  index: number
  title: string
  layout_name: string
  shape_count: number
}

export async function fetchTemplateSlides(templateId: number): Promise<UploadedSlideInfo[]> {
  const response = await fetch(`${API_BASE_URL}/templates/${templateId}/slides`)
  const json: ApiResponse<{ template_id: number; slides: UploadedSlideInfo[] }> = await response.json()

  if (!response.ok || !json.success) {
    throw new Error(formatApiError(json))
  }

  return unwrapResponse(json).slides
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

  const json: ApiResponse<DeckTemplate> = await response.json()

  if (!response.ok || !json.success) {
    throw new Error(formatApiError(json))
  }

  return unwrapResponse(json)
}
