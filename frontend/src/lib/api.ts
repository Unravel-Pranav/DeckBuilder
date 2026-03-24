import type { Section, Slide, SlideComponent, Presentation, ChartDataset } from '@/types'

/**
 * Transforms frontend presentation data to the format expected by the backend PPT engine.
 */
export function transformToBackendFormat(presentation: Presentation, sections: Section[]) {
  return {
    report: {
      id: presentation.id,
      name: presentation.name,
      property_type: presentation.intent.type === 'business' ? 'Office' : 'Industrial', // Mapping for demo
      property_sub_type: 'figures', // Default for demo
      quarter: '2025 Q1', // Default for demo
    },
    sections: sections.map((section: Section) => ({
      id: section.id,
      name: section.name,
      display_order: section.order,
      elements: section.slides.reduce((acc: any[], slide: Slide, slideIdx: number) => {
        // Flatten slides into elements for the backend orchestrator
        const slideElements = slide.components.map((comp: SlideComponent, compIdx: number) => {
          const element: any = {
            id: comp.id,
            element_type: comp.type === 'text' ? 'commentary' : comp.type,
            label: slide.title,
            display_order: slideIdx * 10 + compIdx,
            config: {},
          }

          if (comp.type === 'chart') {
            // Transform Chart.js format to row-oriented format
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
              chart_type: mapChartType(comp.data.type),
              chart_name: slide.title,
              chart_data: chartData,
              primary_y_axis_title: comp.data.datasets[0]?.label || '',
            }
          } else if (comp.type === 'table') {
            // Transform Table headers/rows to row-oriented format
            const tableData = comp.data.rows.map((row: string[]) => {
              const rowObj: any = {}
              comp.data.headers.forEach((header: string, i: number) => {
                rowObj[header] = row[i]
              })
              return rowObj
            })
            element.config = {
              table_data: tableData,
              figure_name: slide.title,
            }
          } else if (comp.type === 'text') {
            element.config = {
              commentary_text: comp.data?.content || '',
            }
          }

          return element
        })

        // Preserve slide-level commentary even when there is no explicit text component.
        // This keeps user-entered text from being dropped in backend payloads.
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

const API_BASE_URL = 'http://localhost:8000/api/v1'

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
