import type {
  Section,
  Slide,
  SlideComponent,
  SectionRecommendation,
  PresentationIntent,
  SlideStructure,
  ChartType,
} from '@/types'
import { createRegions } from '@/types'
import { slideTemplates } from './mockData'

interface GenerationContext {
  intent: PresentationIntent
  acceptedSections: SectionRecommendation[]
}

const INTENT_CHART_PREFERENCES: Record<string, ChartType[]> = {
  financial: ['bar', 'line', 'pie'],
  business: ['bar', 'doughnut', 'line'],
  research: ['scatter', 'line', 'bar'],
  custom: ['bar', 'pie'],
}

const INTENT_TONE_STYLES: Record<string, { commentaryLength: 'short' | 'medium' | 'long'; useCallouts: boolean }> = {
  formal: { commentaryLength: 'medium', useCallouts: false },
  analytical: { commentaryLength: 'long', useCallouts: true },
  storytelling: { commentaryLength: 'long', useCallouts: false },
}

function pickChartType(intent: PresentationIntent, index: number): ChartType {
  const prefs = INTENT_CHART_PREFERENCES[intent.type] ?? ['bar']
  return prefs[index % prefs.length]
}

function pickStructure(templateType: string): SlideStructure {
  const map: Record<string, SlideStructure> = {
    'chart-heavy': 'two-col',
    'table-heavy': 'two-col',
    commentary: 'blank',
    mixed: 'grid-2x2',
  }
  return map[templateType] ?? 'two-col'
}

function generateChartComponent(chartType: ChartType, label: string): SlideComponent {
  const mockLabels: Record<ChartType, string[]> = {
    bar: ['Q1', 'Q2', 'Q3', 'Q4'],
    line: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    pie: ['Segment A', 'Segment B', 'Segment C', 'Segment D'],
    doughnut: ['Complete', 'Remaining'],
    area: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6'],
    scatter: ['A', 'B', 'C', 'D', 'E'],
  }
  const mockData: Record<ChartType, number[]> = {
    bar: [65, 80, 55, 90],
    line: [20, 35, 45, 40, 60, 75],
    pie: [35, 25, 22, 18],
    doughnut: [72, 28],
    area: [100, 180, 150, 250, 220, 310],
    scatter: [12, 45, 23, 67, 34],
  }

  return {
    id: crypto.randomUUID(),
    type: 'chart',
    data: {
      type: chartType,
      labels: mockLabels[chartType],
      datasets: [{
        label,
        data: mockData[chartType],
        ...(chartType === 'pie' || chartType === 'doughnut'
          ? { backgroundColor: ['#F59E0B', '#FBBF24', '#D97706', '#92400E'] }
          : { borderColor: '#F59E0B' }),
      }],
    },
    config: {},
  }
}

function generateTableComponent(sectionName: string): SlideComponent {
  return {
    id: crypto.randomUUID(),
    type: 'table',
    data: {
      headers: ['Metric', 'Current', 'Previous', 'Change'],
      rows: [
        [`${sectionName} KPI 1`, '$12.5M', '$10.2M', '+22%'],
        [`${sectionName} KPI 2`, '85%', '78%', '+7pp'],
        [`${sectionName} KPI 3`, '4.2x', '3.8x', '+0.4x'],
      ],
    },
    config: {},
  }
}

function generateTextComponent(content: string): SlideComponent {
  return {
    id: crypto.randomUUID(),
    type: 'text',
    data: { content },
    config: { format: 'paragraph' },
  }
}

function generateCommentary(sectionName: string, intent: PresentationIntent): string {
  const toneStyle = INTENT_TONE_STYLES[intent.tone] ?? INTENT_TONE_STYLES.formal

  const commentaries: Record<string, Record<string, string>> = {
    financial: {
      short: `Key financial metrics for ${sectionName} show positive momentum.`,
      medium: `${sectionName} analysis reveals strong financial performance with consistent growth across key metrics. Operating efficiency has improved, contributing to margin expansion.`,
      long: `The ${sectionName} data demonstrates robust financial health. Revenue growth has outpaced market benchmarks, driven by strategic investments in high-margin segments. Cost optimization initiatives have yielded measurable improvements in operating leverage, supporting the overall profitability trajectory.`,
    },
    business: {
      short: `${sectionName} highlights key strategic outcomes.`,
      medium: `The ${sectionName} presents a clear picture of strategic progress. Key initiatives are on track, with measurable outcomes across priority areas.`,
      long: `${sectionName} underscores the organization's strategic momentum. Cross-functional alignment has accelerated execution, with key milestones achieved ahead of schedule. The competitive landscape analysis reveals differentiated positioning that supports sustained growth.`,
    },
    research: {
      short: `Findings from ${sectionName} analysis.`,
      medium: `${sectionName} findings indicate statistically significant patterns across the analyzed dataset. Key variables show strong correlation with the hypothesized outcomes.`,
      long: `The ${sectionName} analysis employs a multi-variable approach to isolate key drivers. Preliminary findings confirm the core hypothesis, with observed effect sizes exceeding baseline expectations. Confidence intervals remain within acceptable bounds, supporting the validity of the conclusions drawn.`,
    },
  }

  const intentComms = commentaries[intent.type] ?? commentaries.business
  return intentComms[toneStyle.commentaryLength] ?? intentComms.medium
}

function generateSlideFromTemplate(
  template: SectionRecommendation['suggestedTemplates'][0],
  sectionName: string,
  intent: PresentationIntent,
  slideIndex: number,
): Slide {
  const structure = pickStructure(template.type)
  const regions = createRegions(structure)

  if (template.type === 'chart-heavy') {
    regions[0].component = generateChartComponent(pickChartType(intent, slideIndex), `${sectionName} — ${template.name}`)
    if (regions.length > 1) {
      regions[1].component = generateTextComponent(generateCommentary(sectionName, intent))
    }
  } else if (template.type === 'table-heavy') {
    regions[0].component = generateTableComponent(sectionName)
    if (regions.length > 1) {
      regions[1].component = generateTextComponent(generateCommentary(sectionName, intent))
    }
  } else if (template.type === 'commentary') {
    regions[0].component = generateTextComponent(generateCommentary(sectionName, intent))
  } else if (template.type === 'mixed') {
    regions[0].component = generateChartComponent(pickChartType(intent, slideIndex), `${sectionName} — Chart 1`)
    if (regions.length > 1) regions[1].component = generateChartComponent(pickChartType(intent, slideIndex + 1), `${sectionName} — Chart 2`)
    if (regions.length > 2) regions[2].component = generateTableComponent(sectionName)
    if (regions.length > 3) regions[3].component = generateTextComponent(generateCommentary(sectionName, intent))
  }

  return {
    id: crypto.randomUUID(),
    title: template.name,
    structure,
    regions,
    commentary: generateCommentary(sectionName, intent),
    commentarySource: 'ai',
    order: slideIndex,
    templateId: template.id,
  }
}

export function autoGenerateSlides(ctx: GenerationContext): Section[] {
  const { intent, acceptedSections } = ctx
  const totalSections = acceptedSections.length

  return acceptedSections.map((rec, sectionIndex) => {
    const slides: Slide[] = []
    let contentSlidesGenerated = 0

    if (sectionIndex === 0 && intent.type !== 'custom') {
      const titleTmpl = slideTemplates.find((t) => t.slideKind === 'title')
      if (titleTmpl?.defaultComponents) {
        const regions = createRegions('blank')
        regions[0].component = { ...titleTmpl.defaultComponents[0], id: crypto.randomUUID() } as SlideComponent
        slides.push({
          id: crypto.randomUUID(),
          title: 'Title Page',
          structure: 'blank',
          regions,
          commentary: '',
          commentarySource: 'manual',
          order: 0,
          templateId: titleTmpl.id,
        })
      }
    }

    if (totalSections > 2) {
      const dividerTmpl = slideTemplates.find((t) => t.slideKind === 'section-divider')
      if (dividerTmpl?.defaultComponents) {
        const regions = createRegions('blank')
        const comp = { ...dividerTmpl.defaultComponents[0], id: crypto.randomUUID() } as SlideComponent
        if (comp.type === 'text') {
          comp.data = { content: `${String(sectionIndex + 1).padStart(2, '0')}\n\n${rec.name}\n\n${rec.description}` }
        }
        regions[0].component = comp
        slides.push({
          id: crypto.randomUUID(),
          title: rec.name,
          structure: 'blank',
          regions,
          commentary: '',
          commentarySource: 'manual',
          order: slides.length,
          templateId: dividerTmpl.id,
        })
      }
    }

    rec.suggestedTemplates.forEach((tmpl) => {
      slides.push(generateSlideFromTemplate(tmpl, rec.name, intent, slides.length))
      contentSlidesGenerated += 1
    })

    if (contentSlidesGenerated === 0) {
      slides.push(generateSlideFromTemplate(
        {
          id: crypto.randomUUID(),
          name: 'Custom Bar',
          type: 'chart-heavy',
          structure: 'two-col',
          previewDescription: 'Default chart slide for custom flow',
        },
        rec.name,
        intent,
        slides.length,
      ))
    }

    if (sectionIndex === totalSections - 1 && intent.type !== 'custom') {
      const closingTmpl = slideTemplates.find((t) => t.slideKind === 'closing')
      if (closingTmpl?.defaultComponents) {
        const regions = createRegions('blank')
        regions[0].component = { ...closingTmpl.defaultComponents[0], id: crypto.randomUUID() } as SlideComponent
        slides.push({
          id: crypto.randomUUID(),
          title: 'Thank You',
          structure: 'blank',
          regions,
          commentary: '',
          commentarySource: 'manual',
          order: slides.length,
          templateId: closingTmpl.id,
        })
      }
    }

    return {
      id: rec.id,
      name: rec.name,
      description: rec.description,
      slides,
      order: sectionIndex,
      recommendedTemplateIds: rec.suggestedTemplates.map((t) => t.id),
      selectedTemplateId: rec.suggestedTemplates[0]?.id,
    }
  })
}
