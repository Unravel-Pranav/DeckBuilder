import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Section, Slide, SlideComponent, LayoutType, CommentarySource } from '@/types'

export const useSlidesStore = defineStore('slides', () => {
  const sections = ref<Section[]>([])
  const activeSlideId = ref<string | null>(null)
  const activeSectionId = ref<string | null>(null)

  const allSlides = computed(() => sections.value.flatMap((s) => s.slides))

  const activeSlide = computed(() =>
    allSlides.value.find((s) => s.id === activeSlideId.value) ?? null,
  )

  const activeSection = computed(() =>
    sections.value.find((s) => s.id === activeSectionId.value) ?? null,
  )

  const totalSlideCount = computed(() => allSlides.value.length)

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

  function addSlide(sectionId: string, layout: LayoutType) {
    const section = sections.value.find((s) => s.id === sectionId)
    if (!section) return

    const slide: Slide = {
      id: crypto.randomUUID(),
      title: `Slide ${section.slides.length + 1}`,
      layout,
      components: [],
      commentary: '',
      commentarySource: 'manual',
      order: section.slides.length,
    }
    section.slides.push(slide)
    activeSlideId.value = slide.id
    activeSectionId.value = sectionId
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

  function updateSlideLayout(slideId: string, layout: LayoutType) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (slide) slide.layout = layout
  }

  function updateSlideComponents(slideId: string, components: SlideComponent[]) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (slide) slide.components = components
  }

  function updateSlideCommentary(
    slideId: string,
    commentary: string,
    source: CommentarySource,
  ) {
    const slide = allSlides.value.find((s) => s.id === slideId)
    if (slide) {
      slide.commentary = commentary
      slide.commentarySource = source
    }
  }

  function setActiveSlide(slideId: string | null) {
    activeSlideId.value = slideId
    if (slideId) {
      const section = sections.value.find((s) =>
        s.slides.some((sl) => sl.id === slideId),
      )
      if (section) activeSectionId.value = section.id
    }
  }

  function $reset() {
    sections.value = []
    activeSlideId.value = null
    activeSectionId.value = null
  }

  return {
    sections,
    activeSlideId,
    activeSectionId,
    allSlides,
    activeSlide,
    activeSection,
    totalSlideCount,
    setSections,
    addSection,
    removeSection,
    updateSectionOrder,
    addSlide,
    removeSlide,
    updateSlideLayout,
    updateSlideComponents,
    updateSlideCommentary,
    setActiveSlide,
    $reset,
  }
})
