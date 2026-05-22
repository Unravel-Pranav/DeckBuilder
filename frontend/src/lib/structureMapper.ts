import { createRegions } from '@/types'
import type {
  Section,
  Slide,
  SlideComponent,
  SlideStructure,
  ChartType,
  SectionRecommendation,
  PresentationIntent,
} from '@/types'
import { autoGenerateSlides } from '@/lib/slideGenerator'

export interface StructureGenerateResponse {
  sections: Array<{
    name: string
    sectionname_alias: string
    display_order: number
    elements: Array<{
      element_type: string
      label?: string | null
      display_order: number
      config: Record<string, unknown>
    }>
  }>
  total_elements: number
}

function backendChartTypeToFrontend(chartType: string): ChartType {
  const lower = chartType.toLowerCase()
  if (lower.includes('pie')) return 'pie'
  if (lower.includes('donut')) return 'doughnut'
  if (lower.includes('line')) return 'line'
  if (lower.includes('area')) return 'area'
  if (lower.includes('scatter')) return 'scatter'
  return 'bar'
}

function elementToComponent(el: StructureGenerateResponse['sections'][0]['elements'][0]): SlideComponent | null {
  const cfg = el.config ?? {}
  if (el.element_type === 'chart') {
    const chartData = (cfg.chart_data as Array<Record<string, unknown>>) ?? []
    const labels = chartData.map((row) => String(row.Category ?? row.category ?? ''))
    const valueKeys = chartData.length
      ? Object.keys(chartData[0]).filter((k) => k !== 'Category' && k !== 'category')
      : ['Value1']
    const chartType = backendChartTypeToFrontend(String(cfg.chart_type ?? 'Bar Chart'))
    return {
      id: crypto.randomUUID(),
      type: 'chart',
      data: {
        type: chartType,
        labels: labels.length ? labels : ['Q1', 'Q2', 'Q3', 'Q4'],
        datasets: valueKeys.map((key, i) => ({
          label: key,
          data: chartData.map((row) => Number(row[key] ?? 0)),
          ...(chartType === 'pie' || chartType === 'doughnut'
            ? { backgroundColor: ['#F59E0B', '#FBBF24', '#D97706', '#92400E'] }
            : { borderColor: '#F59E0B' }),
          ...(i === 0 ? {} : {}),
        })),
      },
      config: {},
    }
  }
  if (el.element_type === 'table') {
    const rows = (cfg.table_data as Array<Record<string, string>>) ?? []
    const columns = (cfg.table_columns_sequence as string[]) ?? Object.keys(rows[0] ?? {})
    return {
      id: crypto.randomUUID(),
      type: 'table',
      data: {
        headers: columns,
        rows: rows.map((row) => columns.map((col) => String(row[col] ?? ''))),
      },
      config: {},
    }
  }
  if (el.element_type === 'commentary') {
    const content = String(cfg.content ?? cfg.commentary_text ?? el.label ?? '')
    return {
      id: crypto.randomUUID(),
      type: 'text',
      data: { content },
      config: { format: 'paragraph' },
    }
  }
  return null
}

function pickStructureForElements(count: number): SlideStructure {
  if (count <= 1) return 'blank'
  if (count <= 2) return 'two-col'
  return 'grid-2x2'
}

/**
 * Maps backend structure/generate output into wizard Section[] for slidesStore.
 */
export function mapStructureToSections(
  response: StructureGenerateResponse,
  acceptedSections: SectionRecommendation[],
): Section[] {
  return response.sections.map((sec, sectionIndex) => {
    const rec = acceptedSections[sectionIndex]
    const elements = [...sec.elements].sort((a, b) => a.display_order - b.display_order)
    const structure = pickStructureForElements(Math.max(elements.length, 1))
    const regions = createRegions(structure)
    elements.forEach((el, regionIdx) => {
      const comp = elementToComponent(el)
      if (comp && regions[regionIdx]) regions[regionIdx].component = comp
    })

    const slides: Slide[] = elements.length
      ? [{
          id: crypto.randomUUID(),
          title: sec.name,
          structure,
          regions,
          commentary: '',
          commentarySource: 'manual' as const,
          regionCommentary: {},
          order: 0,
          templateId: rec?.suggestedTemplates[0]?.id,
        }]
      : []

    if (slides.length === 0) {
      const structure: SlideStructure = 'two-col'
      const regions = createRegions(structure)
      return {
        id: crypto.randomUUID(),
        name: sec.name,
        description: rec?.description ?? '',
        order: sectionIndex,
        recommendedTemplateIds: [],
        slides: [{
          id: crypto.randomUUID(),
          title: sec.name,
          structure,
          regions,
          commentary: '',
          commentarySource: 'manual',
          regionCommentary: {},
          order: 0,
        }],
      }
    }

    return {
      id: rec?.id ?? crypto.randomUUID(),
      name: sec.name,
      description: rec?.description ?? '',
      order: sectionIndex,
      recommendedTemplateIds: rec?.suggestedTemplates.map((t) => t.id) ?? [],
      slides,
    }
  })
}

/**
 * Try structure API; fall back to local slideGenerator on failure.
 */
export async function buildSectionsFromOutline(
  generateStructure: (sections: SectionRecommendation[], intent: PresentationIntent) => Promise<StructureGenerateResponse>,
  intent: PresentationIntent,
  acceptedSections: SectionRecommendation[],
): Promise<Section[]> {
  try {
    const response = await generateStructure(acceptedSections, intent)
    if (response.sections?.length) {
      return mapStructureToSections(response, acceptedSections)
    }
  } catch (err) {
    console.warn('[structure] API failed, using local slide generator', err)
  }
  return autoGenerateSlides({ intent, acceptedSections })
}
