import { describe, it, expect } from 'vitest'
import { hasExportableContent, getExportReadiness } from './presentationValidation'
import type { Section } from '@/types'

const emptySection: Section = {
  id: 's1',
  name: 'Test',
  description: '',
  order: 0,
  recommendedTemplateIds: [],
  slides: [{
    id: 'sl1',
    title: 'Slide',
    structure: 'two-col',
    regions: [{ id: 'r1', component: null }],
    commentary: '',
    commentarySource: 'manual',
    regionCommentary: {},
    order: 0,
  }],
}

describe('presentationValidation', () => {
  it('returns false when no components', () => {
    expect(hasExportableContent([emptySection])).toBe(false)
  })

  it('returns true when a region has a component', () => {
    const withChart = structuredClone(emptySection)
    withChart.slides[0].regions[0].component = {
      id: 'c1',
      type: 'chart',
      data: { type: 'bar', labels: ['A'], datasets: [{ label: 'V', data: [1] }] },
      config: {},
    }
    expect(hasExportableContent([withChart])).toBe(true)
    expect(getExportReadiness([withChart]).ready).toBe(true)
  })
})
