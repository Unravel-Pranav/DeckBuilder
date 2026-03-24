import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SlideTemplate, TemplateCategory } from '@/types'
import { chartTemplates, tableTemplates, textTemplates, slideTemplates } from '@/lib/mockData'
import { fetchPptTemplates, type BackendTemplate } from '@/lib/api'

export type FilterCategory = 'all' | TemplateCategory | 'custom' | 'ppt'

export const useTemplatesStore = defineStore('templates', () => {
  const builtInTemplates = ref<SlideTemplate[]>([
    ...chartTemplates,
    ...tableTemplates,
    ...textTemplates,
    ...slideTemplates,
  ])
  const customTemplates = ref<SlideTemplate[]>([])
  const backendPptTemplates = ref<BackendTemplate[]>([])
  const isLoadingBackend = ref(false)
  const backendError = ref<string | null>(null)
  const searchQuery = ref('')
  const activeFilter = ref<FilterCategory>('all')

  const allTemplates = computed(() => [
    ...builtInTemplates.value,
    ...customTemplates.value,
  ])

  const filteredTemplates = computed(() => {
    let list: SlideTemplate[]
    if (activeFilter.value === 'custom') {
      list = customTemplates.value
    } else if (activeFilter.value === 'all') {
      list = allTemplates.value
    } else if (activeFilter.value === 'ppt') {
      // PPT filter shows nothing in the slide templates list — shown separately
      list = []
    } else {
      list = allTemplates.value.filter((t) => t.category === activeFilter.value)
    }

    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q) ||
          (t.chartType && t.chartType.includes(q)) ||
          (t.slideKind && t.slideKind.includes(q)),
      )
    }

    return list
  })

  const filteredPptTemplates = computed(() => {
    if (activeFilter.value !== 'ppt' && activeFilter.value !== 'all') return []
    
    let list = backendPptTemplates.value
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.filename.toLowerCase().includes(q) ||
          (t.chart_type && t.chart_type.toLowerCase().includes(q)) ||
          (t.table_type && t.table_type.toLowerCase().includes(q)),
      )
    }
    return list
  })

  const templateCounts = computed(() => ({
    all: allTemplates.value.length + backendPptTemplates.value.length,
    chart: allTemplates.value.filter((t) => t.category === 'chart').length,
    table: allTemplates.value.filter((t) => t.category === 'table').length,
    text: allTemplates.value.filter((t) => t.category === 'text').length,
    slide: allTemplates.value.filter((t) => t.category === 'slide').length,
    custom: customTemplates.value.length,
    ppt: backendPptTemplates.value.length,
  }))

  async function loadBackendTemplates() {
    if (backendPptTemplates.value.length > 0) return // Already loaded
    isLoadingBackend.value = true
    backendError.value = null
    try {
      const response = await fetchPptTemplates()
      backendPptTemplates.value = response.templates
    } catch (e: any) {
      backendError.value = e.message || 'Failed to load backend templates'
      console.warn('Could not load backend PPT templates:', e)
    } finally {
      isLoadingBackend.value = false
    }
  }

  function getSlideTemplates() {
    return allTemplates.value.filter((t) => t.category === 'slide')
  }

  function getComponentTemplates() {
    return allTemplates.value.filter((t) => t.category !== 'slide')
  }

  function addCustomTemplate(template: Omit<SlideTemplate, 'id'>) {
    customTemplates.value.push({
      ...template,
      id: `custom-${crypto.randomUUID()}`,
    })
  }

  function removeCustomTemplate(id: string) {
    customTemplates.value = customTemplates.value.filter((t) => t.id !== id)
  }

  function duplicateTemplate(id: string) {
    const source = allTemplates.value.find((t) => t.id === id)
    if (!source) return
    customTemplates.value.push({
      ...structuredClone(source),
      id: `custom-${crypto.randomUUID()}`,
      name: `${source.name} (Copy)`,
    })
  }

  function setFilter(filter: FilterCategory) {
    activeFilter.value = filter
  }

  function setSearch(query: string) {
    searchQuery.value = query
  }

  return {
    builtInTemplates,
    customTemplates,
    backendPptTemplates,
    isLoadingBackend,
    backendError,
    searchQuery,
    activeFilter,
    allTemplates,
    filteredTemplates,
    filteredPptTemplates,
    templateCounts,
    loadBackendTemplates,
    getSlideTemplates,
    getComponentTemplates,
    addCustomTemplate,
    removeCustomTemplate,
    duplicateTemplate,
    setFilter,
    setSearch,
  }
})
