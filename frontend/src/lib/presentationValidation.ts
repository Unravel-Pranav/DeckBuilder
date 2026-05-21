import type { Section } from '@/types'

/**
 * Returns true when at least one slide has a chart, table, or text component in a region.
 */
export function hasExportableContent(sections: Section[]): boolean {
  for (const section of sections) {
    for (const slide of section.slides) {
      for (const region of slide.regions) {
        if (region.component) return true
      }
    }
  }
  return false
}

export interface ExportReadiness {
  ready: boolean
  sectionCount: number
  slideCount: number
  slidesWithComponents: number
}

export function getExportReadiness(sections: Section[]): ExportReadiness {
  let slideCount = 0
  let slidesWithComponents = 0

  for (const section of sections) {
    for (const slide of section.slides) {
      slideCount += 1
      const hasComponent = slide.regions.some((r) => !!r.component)
      if (hasComponent) slidesWithComponents += 1
    }
  }

  return {
    ready: slidesWithComponents > 0,
    sectionCount: sections.length,
    slideCount,
    slidesWithComponents,
  }
}
