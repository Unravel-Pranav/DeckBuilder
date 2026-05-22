import type { FlowStep } from '@/types'

export const LINEAR_FLOW_STEPS: FlowStep[] = [
  'create',
  'recommendations',
  'sections',
  'builder',
  'preview',
  'output',
]

export interface FlowContext {
  hasPresentation: boolean
  hasRecommendations: boolean
  hasSections: boolean
  generatedFileId: string | null
}

export function buildFlowContext(input: {
  currentPresentation: unknown | null
  recommendationSectionsLength: number
  sectionsLength: number
  generatedFileId: string | null
}): FlowContext {
  return {
    hasPresentation: !!input.currentPresentation,
    hasRecommendations: input.recommendationSectionsLength > 0,
    hasSections: input.sectionsLength > 0,
    generatedFileId: input.generatedFileId,
  }
}

/**
 * Single source of truth for wizard step access (router + sidebar).
 */
export function canAccessStep(step: FlowStep, ctx: FlowContext): boolean {
  switch (step) {
    case 'create':
      return true
    case 'recommendations':
      return ctx.hasPresentation
    case 'sections':
      return ctx.hasPresentation && (ctx.hasRecommendations || ctx.hasSections)
    case 'builder':
    case 'preview':
      return ctx.hasSections
    case 'output':
      return ctx.hasSections && !!ctx.generatedFileId
    case 'upload':
      return ctx.hasSections
    default:
      return false
  }
}

export function getRedirectForStep(step: FlowStep, ctx: FlowContext): { name: string; query?: Record<string, string> } | null {
  if (canAccessStep(step, ctx)) return null

  switch (step) {
    case 'recommendations':
      return { name: 'create' }
    case 'sections':
      return ctx.hasPresentation ? { name: 'recommendations' } : { name: 'create' }
    case 'builder':
    case 'preview':
      return { name: 'create' }
    case 'output':
      if (!ctx.hasSections) return { name: 'create' }
      return { name: 'preview', query: { needsGenerate: '1' } }
    default:
      return null
  }
}

export function deriveCompletedSteps(ctx: FlowContext): Set<FlowStep> {
  const completed = new Set<FlowStep>()
  if (ctx.hasPresentation) completed.add('create')
  if (ctx.hasRecommendations || ctx.hasSections) completed.add('recommendations')
  if (ctx.hasSections) {
    completed.add('sections')
    completed.add('builder')
    completed.add('preview')
  }
  if (ctx.generatedFileId) completed.add('output')
  return completed
}

export function stepPrerequisiteLabel(step: FlowStep): string {
  const labels: Record<FlowStep, string> = {
    create: '',
    recommendations: 'Define Intent',
    sections: 'AI Outline',
    builder: 'Manage Sections',
    upload: 'Build Slides',
    preview: 'Build Slides',
    output: 'Preview & Generate',
  }
  return labels[step]
}

export function canNavigateToStep(
  targetStep: FlowStep,
  currentStep: FlowStep,
  completedSteps: Set<FlowStep>,
  ctx: FlowContext,
): boolean {
  if (!canAccessStep(targetStep, ctx)) return false
  if (targetStep === currentStep || completedSteps.has(targetStep)) return true

  const targetIdx = LINEAR_FLOW_STEPS.indexOf(targetStep)
  const currentIdx = LINEAR_FLOW_STEPS.indexOf(currentStep)
  if (targetIdx < 0 || currentIdx < 0) return canAccessStep(targetStep, ctx)
  if (targetIdx <= currentIdx) return true

  for (let i = 0; i < targetIdx; i++) {
    const prev = LINEAR_FLOW_STEPS[i]
    if (!completedSteps.has(prev) && !deriveCompletedSteps(ctx).has(prev)) {
      return false
    }
  }
  return true
}
