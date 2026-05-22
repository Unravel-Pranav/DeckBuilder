import { defineStore } from 'pinia'
import { ref } from 'vue'
import { API_BASE_URL, formatApiError } from '@/lib/api'
import type { ApiResponse } from '@/lib/api'
import type {
  AiRecommendation,
  ChartType,
  RecommendationAgentResponse,
  SectionRecommendation,
  SlideStructure,
  TemplateRecommendation,
} from '@/types'

interface AiRecommendationData {
  sections: Array<{
    id: string
    name: string
    description: string
    suggested_templates: Array<{
      id: string
      name: string
      type: string
      layout: string
      preview_description: string
    }>
    accepted: boolean
  }>
  suggested_style: string
  suggested_chart_types: string[]
}

export const useAiStore = defineStore('ai', () => {
  const recommendation = ref<AiRecommendation | null>(null)
  const isLoading = ref(false)
  const isGeneratingCommentary = ref(false)
  const error = ref<string | null>(null)

  // Recommendation agent state
  const agentPlan = ref<RecommendationAgentResponse | null>(null)
  const isGeneratingPlan = ref(false)

  async function fetchRecommendations(
    type: string = 'business',
    audience: string = '',
    tone: string = 'formal',
  ): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const res = await fetch(`${API_BASE_URL}/ai/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, audience, tone }),
      })

      const json: ApiResponse<AiRecommendationData> = await res.json()

      if (!res.ok || !json.success || !json.data) {
        throw new Error(formatApiError(json))
      }

      const data = json.data

      const layoutMap: Record<string, SlideStructure> = {
        'chart-commentary': 'two-col',
        'table-commentary': 'two-col',
        'full-chart': 'blank',
        'full-table': 'blank',
        'commentary-only': 'blank',
        'mixed': 'grid-2x2',
      }

      recommendation.value = {
        sections: data.sections.map((s) => ({
          id: s.id,
          name: s.name,
          description: s.description,
          suggestedTemplates: (s.suggested_templates || []).map((t) => ({
            id: t.id,
            name: t.name,
            type: t.type as TemplateRecommendation['type'],
            structure: layoutMap[t.layout] || 'two-col',
            previewDescription: t.preview_description || '',
          })),
          accepted: s.accepted ?? true,
        })),
        suggestedStyle: data.suggested_style,
        suggestedChartTypes: data.suggested_chart_types as ChartType[],
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
    slideId?: string
    elementId?: string
    elementType?: string
    elementData?: Record<string, unknown>
    presentationName?: string
  }

  async function generateCommentary(context: string | CommentaryContext, prompt?: string): Promise<string> {
    isGeneratingCommentary.value = true
    try {
      const ctx: CommentaryContext = typeof context === 'string'
        ? { componentType: context as CommentaryContext['componentType'] }
        : context

      const res = await fetch(`${API_BASE_URL}/ai/commentary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          component_type: ctx.componentType,
          section_name: ctx.sectionName || undefined,
          intent_type: ctx.intentType || undefined,
          intent_tone: ctx.intentTone || undefined,
          prompt: prompt || ctx.prompt || undefined,
          slide_id: ctx.slideId || undefined,
          element_id: ctx.elementId || undefined,
          element_type: ctx.elementType || undefined,
          element_data: ctx.elementData || undefined,
          presentation_name: ctx.presentationName || undefined,
          slide_title: ctx.slideTitle || undefined,
        }),
      })

      const json: ApiResponse<{ commentary: string }> = await res.json()

      if (!res.ok || !json.success || !json.data) {
        throw new Error(formatApiError(json))
      }

      return json.data.commentary
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to generate commentary'
      error.value = message
      return `Commentary unavailable: ${message}`
    } finally {
      isGeneratingCommentary.value = false
    }
  }

  async function generatePlan(params: {
    presentationType: string
    audience: string
    tone: string
    objective?: string
    keyMetrics?: string[]
    audienceExpertise?: string
    dataSource?: Record<string, unknown> | null
  }): Promise<RecommendationAgentResponse | null> {
    isGeneratingPlan.value = true
    error.value = null

    try {
      const res = await fetch(`${API_BASE_URL}/recommendations/generate-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          presentation_type: params.presentationType,
          audience: params.audience,
          tone: params.tone,
          objective: params.objective || null,
          key_metrics: params.keyMetrics || [],
          audience_expertise: params.audienceExpertise || 'mixed',
          data_source: params.dataSource || null,
        }),
      })

      const json: ApiResponse<RecommendationAgentResponse> = await res.json()

      if (!res.ok || !json.success || !json.data) {
        throw new Error(formatApiError(json))
      }

      agentPlan.value = json.data

      // Also populate recommendation in the legacy format so existing section cards work
      const plan = json.data
      recommendation.value = {
        sections: plan.sections.map((s) => ({
          id: crypto.randomUUID(),
          name: s.name,
          description: s.description,
          suggestedTemplates: s.slot_assignments
            .filter((slot) => slot.element_type !== 'commentary')
            .slice(0, 2)
            .map((slot) => ({
              id: crypto.randomUUID(),
              name: slot.element_type === 'table' ? 'Table View' : 'Chart View',
              type: (slot.element_type === 'table' ? 'table-heavy' : 'chart-heavy') as TemplateRecommendation['type'],
              structure: 'two-col' as SlideStructure,
              previewDescription: slot.insight_directive || '',
              templateRef: s.template_id != null ? String(s.template_id) : undefined,
            })),
          accepted: true,
        })),
        suggestedStyle: `AI plan (confidence: ${plan.reviewer_score}/10)`,
        suggestedChartTypes: ['bar', 'line'] as ChartType[],
      }

      return json.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to generate plan'
      return null
    } finally {
      isGeneratingPlan.value = false
    }
  }

  function $reset() {
    recommendation.value = null
    agentPlan.value = null
    isLoading.value = false
    isGeneratingCommentary.value = false
    isGeneratingPlan.value = false
    error.value = null
  }

  return {
    recommendation,
    agentPlan,
    isLoading,
    isGeneratingCommentary,
    isGeneratingPlan,
    error,
    fetchRecommendations,
    generatePlan,
    toggleSectionAccepted,
    removeSectionRecommendation,
    addCustomSection,
    acceptAll,
    reorderSections,
    generateCommentary,
    $reset,
  }
})
