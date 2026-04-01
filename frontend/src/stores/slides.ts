import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Section, Slide, SlideComponent, SlideStructure, CommentarySource } from '@/types'
import { createRegions, getRegionCount } from '@/types'

export const useSlidesStore = defineStore('slides', () => {
  const sections = ref<Section[]>([])
  const activeSlideId = ref<string | null>(null)
  const activeSectionId = ref<string | null>(null)
  const activeRegionIndex = ref<number>(0)

  const allSlides = computed(() => sections.value.flatMap((s) => s.slides))

  const activeSlide = computed(() =>
    allSlides.value.find((s) => s.id === activeSlideId.value) ?? null,
  )

  const activeSection = computed(() =>
    sections.value.find((s) => s.id === activeSectionId.value) ?? null,
  )

  const totalSlideCount = computed(() => allSlides.value.length)

  const activeRegion = computed(() => {
    const slide = activeSlide.value
    if (!slide) return null
    return slide.regions[activeRegionIndex.value] ?? null
  })

  function setSections(newSections: Section[]) {
    sections.value = newSections
  }

  function addSection(name: string, description: string) {
    sections.value.push({
      id: crypto.randomUUID(),
      name,
      description,
      slides: [],
      order: sections.value.length,
      recommendedTemplateIds: [],
    })
  }

  function removeSection(sectionId: string) {
    sections.value = sections.value
      .filter((s) => s.id !== sectionId)
      .map((s, i) => ({ ...s, order: i }))
    if (activeSectionId.value === sectionId) {
      activeSectionId.value = sections.value[0]?.id ?? null
      activeSlideId.value = sections.value[0]?.slides[0]?.id ?? null
    }
  }

  function updateSectionOrder(orderedIds: string[]) {
    const sectionMap = new Map(sections.value.map((s) => [s.id, s]))
    sections.value = orderedIds
      .map((id, idx) => {
        const section = sectionMap.get(id)
        if (section) section.order = idx
        return section
      })
      .filter((s): s is Section => !!s)
  }

  function addSlide(sectionId: string, structure: SlideStructure) {
    const section = sections.value.find((s) => s.id === sectionId)
    if (!section) return

    const slide: Slide = {
      id: crypto.randomUUID(),
      title: `Slide ${section.slides.length + 1}`,
      structure,
      regions: createRegions(structure),
      commentary: '',
      commentarySource: 'manual',
      order: section.slides.length,
    }
    section.slides.push(slide)
    activeSlideId.value = slide.id
    activeSectionId.value = sectionId
    activeRegionIndex.value = 0
  }

  function removeSlide(sectionId: string, slideId: string) {
    const section = sections.value.find((s) => s.id === sectionId)
    if (!section) return
    section.slides = section.slides
      .filter((s) => s.id !== slideId)
      .map((s, i) => ({ ...s, order: i }))
    if (activeSlideId.value === slideId) {
      activeSlideId.value = section.slides[0]?.id ?? null
    }
  }

  function updateSlideStructure(slideId: string, structure: SlideStructure) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (!slide) return

    const oldRegions = slide.regions
    const newCount = getRegionCount(structure)
    const newRegions = createRegions(structure)

    // Carry over existing components into the new regions (as many as fit)
    const existingComponents = oldRegions
      .map((r) => r.component)
      .filter((c): c is SlideComponent => c !== null)
    for (let i = 0; i < Math.min(existingComponents.length, newCount); i++) {
      newRegions[i].component = existingComponents[i]
    }

    slide.structure = structure
    slide.regions = newRegions

    if (activeRegionIndex.value >= newCount) {
      activeRegionIndex.value = 0
    }
  }

  function setRegionComponent(slideId: string, regionIndex: number, component: SlideComponent) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (!slide || regionIndex < 0 || regionIndex >= slide.regions.length) return
    slide.regions[regionIndex].component = component
  }

  function clearRegion(slideId: string, regionIndex: number) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (!slide || regionIndex < 0 || regionIndex >= slide.regions.length) return
    slide.regions[regionIndex].component = null
  }

  /** Flat list of all non-null components across regions (convenience accessor) */
  function getSlideComponents(slideId: string): SlideComponent[] {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (!slide) return []
    return slide.regions
      .map((r) => r.component)
      .filter((c): c is SlideComponent => c !== null)
  }

  function updateSlideCommentary(
    slideId: string,
    commentary: string,
    source: CommentarySource,
  ) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (!slide) return
    slide.commentary = commentary
    slide.commentarySource = source

    const textRegion = slide.regions.find((r) => r.component?.type === 'text')
    if (textRegion?.component && textRegion.component.type === 'text') {
      textRegion.component.data = { content: commentary }
    }
  }

  function setActiveSlide(slideId: string | null) {
    activeSlideId.value = slideId
    activeRegionIndex.value = 0
    if (slideId) {
      const section = sections.value.find((s) =>
        s.slides.some((sl) => sl.id === slideId),
      )
      if (section) activeSectionId.value = section.id
    }
  }

  function setActiveRegion(index: number) {
    activeRegionIndex.value = index
  }

  function $reset() {
    sections.value = []
    activeSlideId.value = null
    activeSectionId.value = null
    activeRegionIndex.value = 0
  }

  return {
    sections,
    activeSlideId,
    activeSectionId,
    activeRegionIndex,
    allSlides,
    activeSlide,
    activeSection,
    activeRegion,
    totalSlideCount,
    setSections,
    addSection,
    removeSection,
    updateSectionOrder,
    addSlide,
    removeSlide,
    updateSlideStructure,
    setRegionComponent,
    clearRegion,
    getSlideComponents,
    updateSlideCommentary,
    setActiveSlide,
    setActiveRegion,
    $reset,
  }
})
