import { describe, it, expect } from 'vitest'
import {
  buildFlowContext,
  canAccessStep,
  getRedirectForStep,
  deriveCompletedSteps,
} from './flowAccess'

describe('flowAccess', () => {
  const base = buildFlowContext({
    currentPresentation: { id: '1' },
    recommendationSectionsLength: 2,
    sectionsLength: 1,
    generatedFileId: null,
  })

  it('allows output only when file id exists', () => {
    expect(canAccessStep('output', base)).toBe(false)
    const withFile = buildFlowContext({
      currentPresentation: { id: '1' },
      recommendationSectionsLength: 2,
      sectionsLength: 1,
      generatedFileId: 'file-uuid',
    })
    expect(canAccessStep('output', withFile)).toBe(true)
  })

  it('redirects output to preview when no file', () => {
    const redirect = getRedirectForStep('output', base)
    expect(redirect).toEqual({ name: 'preview', query: { needsGenerate: '1' } })
  })

  it('derives completed steps from context', () => {
    const steps = deriveCompletedSteps(base)
    expect(steps.has('create')).toBe(true)
    expect(steps.has('sections')).toBe(true)
    expect(steps.has('output')).toBe(false)
  })
})
