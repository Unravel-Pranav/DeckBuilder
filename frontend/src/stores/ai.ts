import { defineStore } from 'pinia'
import { ref } from 'vue'
import { API_BASE_URL, formatApiError } from '@/lib/api'
import type { ApiResponse } from '@/lib/api'
import type {
  AiRecommendation,
  SectionRecommendation,
  SlideStructure,
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
            type: t.type,
            structure: layoutMap[t.layout] || 'two-col',
            previewDescription: t.preview_description || '',
          })),
          accepted: s.accepted ?? true,
        })),
        suggestedStyle: data.suggested_style,
        suggestedChartTypes: data.suggested_chart_types,
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
