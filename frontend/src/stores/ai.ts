import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  AiRecommendation,
  SectionRecommendation,
  PresentationIntent,
  SlideComponent,
} from '@/types'

export const useAiStore = defineStore('ai', () => {
  const recommendation = ref<AiRecommendation | null>(null)
  const isLoading = ref(false)
  const isGeneratingCommentary = ref(false)
  const error = ref<string | null>(null)

  async function fetchRecommendations(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      // TODO: Replace with real API call: POST /api/presentations
      await new Promise((resolve) => setTimeout(resolve, 2000))

      recommendation.value = {
        sections: [
          {
            id: crypto.randomUUID(),
            name: 'Executive Summary',
            description: 'High-level overview of key findings and recommendations',
            suggestedTemplates: [
              { id: crypto.randomUUID(), name: 'Key Metrics Dashboard', type: 'chart-heavy', layout: 'chart-commentary', previewDescription: 'Bar chart with KPI highlights and commentary' },
              { id: crypto.randomUUID(), name: 'Summary Table', type: 'table-heavy', layout: 'table-commentary', previewDescription: 'Condensed data table with key takeaways' },
            ],
            accepted: true,
          },
          {
            id: crypto.randomUUID(),
            name: 'Market Overview',
            description: 'Current market landscape, trends, and competitive positioning',
            suggestedTemplates: [
              { id: crypto.randomUUID(), name: 'Market Trend Lines', type: 'chart-heavy', layout: 'full-chart', previewDescription: 'Multi-line chart showing market trends over time' },
              { id: crypto.randomUUID(), name: 'Competitive Matrix', type: 'table-heavy', layout: 'table-commentary', previewDescription: 'Comparison table of key competitors' },
              { id: crypto.randomUUID(), name: 'Market Insights', type: 'commentary', layout: 'commentary-only', previewDescription: 'AI-generated market analysis narrative' },
            ],
            accepted: true,
          },
          {
            id: crypto.randomUUID(),
            name: 'Financial Analysis',
            description: 'Revenue, costs, profitability, and financial projections',
            suggestedTemplates: [
              { id: crypto.randomUUID(), name: 'Revenue Breakdown', type: 'chart-heavy', layout: 'chart-commentary', previewDescription: 'Stacked bar chart with revenue by segment' },
              { id: crypto.randomUUID(), name: 'P&L Summary', type: 'table-heavy', layout: 'full-table', previewDescription: 'Detailed profit & loss statement table' },
            ],
            accepted: true,
          },
          {
            id: crypto.randomUUID(),
            name: 'Key Insights & Recommendations',
            description: 'Strategic recommendations based on data analysis',
            suggestedTemplates: [
              { id: crypto.randomUUID(), name: 'Insight Cards', type: 'mixed', layout: 'mixed', previewDescription: 'Visual cards with icons and insight summaries' },
              { id: crypto.randomUUID(), name: 'Action Items', type: 'commentary', layout: 'commentary-only', previewDescription: 'Prioritized list of recommended actions' },
            ],
            accepted: true,
          },
        ],
        suggestedStyle: 'Professional with data-driven visual emphasis',
        suggestedChartTypes: ['bar', 'line', 'pie'],
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch recommendations'
    } finally {
      isLoading.value = false
    }
  }

  function toggleSectionAccepted(sectionId: string) {
    if (!recommendation.value) return
    const section = recommendation.value.sections.find((s) => s.id === sectionId)
    if (section) section.accepted = !section.accepted
  }

  function removeSectionRecommendation(sectionId: string) {
    if (!recommendation.value) return
    recommendation.value.sections = recommendation.value.sections.filter(
      (s) => s.id !== sectionId,
    )
  }

  function addCustomSection(section: SectionRecommendation) {
    if (!recommendation.value) return
    recommendation.value.sections.push(section)
  }

  function acceptAll() {
    if (!recommendation.value) return
    recommendation.value.sections.forEach((s) => (s.accepted = true))
  }

  function reorderSections(oldIndex: number, newIndex: number) {
    if (!recommendation.value) return
    const sections = [...recommendation.value.sections]
    const [moved] = sections.splice(oldIndex, 1)
    sections.splice(newIndex, 0, moved)
    recommendation.value.sections = sections
  }

  interface CommentaryContext {
    componentType: 'chart' | 'table' | 'text' | 'default'
    sectionName?: string
    intentType?: string
    intentTone?: string
    slideTitle?: string
    prompt?: string
  }

  async function generateCommentary(context: string | CommentaryContext, prompt?: string): Promise<string> {
    isGeneratingCommentary.value = true
    try {
      // TODO: Replace with real API call: POST /api/presentations/:id/commentary
      await new Promise((resolve) => setTimeout(resolve, 1500))

      const ctx: CommentaryContext = typeof context === 'string'
        ? { componentType: context as CommentaryContext['componentType'] }
        : context

      if (prompt?.trim()) {
        const toneMap: Record<string, string> = {
          formal: 'In a professional tone',
          analytical: 'With analytical depth',
          storytelling: 'In a narrative style',
        }
        const tonePrefix = ctx.intentTone ? `${toneMap[ctx.intentTone] ?? ''}: ` : ''
        return `${tonePrefix}Based on your direction: "${prompt.trim().slice(0, 80)}" — The analysis of ${ctx.sectionName ?? 'this section'} reveals actionable patterns. Key findings support the strategic priorities outlined, with measurable outcomes across the focus areas you specified.`
      }

      const intentCommentaries: Record<string, Record<string, string>> = {
        financial: {
          chart: `The ${ctx.sectionName ?? 'financial'} data shows consistent growth trajectory. Revenue increased 23% YoY driven by expansion into high-margin segments. Operating leverage improvements contributed to margin expansion of 240bps.`,
          table: `Comparative financial analysis for ${ctx.sectionName ?? 'this period'} reveals strong performance against benchmarks. Key ratios exceed industry averages, with particular strength in capital efficiency metrics.`,
          text: `${ctx.sectionName ?? 'Financial'} insights indicate a robust fiscal position. Strategic investments are generating above-target returns, supporting the long-term growth thesis.`,
          default: `${ctx.sectionName ?? 'This section'} presents key financial metrics demonstrating strong organizational performance and clear strategic direction.`,
        },
        business: {
          chart: `${ctx.sectionName ?? 'Business'} metrics demonstrate strong execution against strategic objectives. Market share gains of 3.2pp reflect successful positioning and competitive differentiation.`,
          table: `The ${ctx.sectionName ?? 'operational'} scorecard shows progress across all priority areas. Key initiatives are on track with measurable outcomes exceeding initial targets.`,
          text: `Strategic analysis of ${ctx.sectionName ?? 'this area'} reveals a clear path to sustainable competitive advantage. Cross-functional alignment has accelerated execution velocity.`,
          default: `${ctx.sectionName ?? 'This section'} highlights key strategic outcomes and their implications for the organization's growth trajectory.`,
        },
        research: {
          chart: `${ctx.sectionName ?? 'Research'} findings show statistically significant results (p < 0.05). The observed effect size of 0.72 exceeds baseline expectations, confirming the primary hypothesis.`,
          table: `Systematic analysis of ${ctx.sectionName ?? 'the dataset'} reveals significant variance across experimental conditions. Controlled variables remained within acceptable bounds throughout the study period.`,
          text: `The ${ctx.sectionName ?? 'research'} methodology employed a rigorous multi-variable approach. Results are reproducible and consistent with established theoretical frameworks.`,
          default: `${ctx.sectionName ?? 'This section'} presents key findings from the analytical framework, with implications for both theory and practice.`,
        },
      }

      const intentMap = intentCommentaries[ctx.intentType ?? 'business'] ?? intentCommentaries.business
      return intentMap[ctx.componentType] ?? intentMap.default

    } finally {
      isGeneratingCommentary.value = false
    }
  }

  function $reset() {
    recommendation.value = null
    isLoading.value = false
    isGeneratingCommentary.value = false
    error.value = null
  }

  return {
    recommendation,
    isLoading,
    isGeneratingCommentary,
    error,
    fetchRecommendations,
    toggleSectionAccepted,
    removeSectionRecommendation,
    addCustomSection,
    acceptAll,
    reorderSections,
    generateCommentary,
    $reset,
  }
})
