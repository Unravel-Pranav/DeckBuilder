import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SlideTemplate } from '@/types'
import { chartTemplates, tableTemplates, textTemplates, slideTemplates } from '@/lib/mockData'
import { fetchPptTemplates, type BackendTemplate } from '@/lib/api'

/** Category filter for the /templates page (backend .pptx library only). */
export type LibraryCategoryFilter = 'all' | BackendTemplate['category']

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
  const libraryCategoryFilter = ref<LibraryCategoryFilter>('all')

  const allTemplates = computed(() => [
    ...builtInTemplates.value,
    ...customTemplates.value,
  ])

  /** Backend PPT engine templates for TemplateManagementPage (search + category). */
  const filteredLibraryTemplates = computed(() => {
    let list = backendPptTemplates.value
    if (libraryCategoryFilter.value !== 'all') {
      list = list.filter((t) => t.category === libraryCategoryFilter.value)
    }
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

  const libraryCategoryCounts = computed(() => {
    const list = backendPptTemplates.value
    const counts: Record<LibraryCategoryFilter, number> = {
      all: list.length,
      chart: 0,
      table: 0,
      front_page: 0,
      last_page: 0,
      base: 0,
      other: 0,
    }
    for (const t of list) {
      counts[t.category]++
    }
    return counts
  })

  async function loadBackendTemplates() {
    if (backendPptTemplates.value.length > 0) return
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

  function setLibraryCategoryFilter(filter: LibraryCategoryFilter) {
    libraryCategoryFilter.value = filter
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
    libraryCategoryFilter,
    allTemplates,
    filteredLibraryTemplates,
    libraryCategoryCounts,
    loadBackendTemplates,
    getSlideTemplates,
    getComponentTemplates,
    addCustomTemplate,
    removeCustomTemplate,
    duplicateTemplate,
    setLibraryCategoryFilter,
    setSearch,
  }
})
