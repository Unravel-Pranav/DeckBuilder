import { defineStore } from 'pinia'
import { ref } from 'vue'

const LS_ID = 'deckbuilder:export_deck_template_id'
const LS_NAME = 'deckbuilder:export_deck_template_name'

/**
 * DB template whose uploaded .pptx is used as the base (cover + masters) for Generate.
 */
export const useDeckTemplateStore = defineStore('deckTemplate', () => {
  const selectedTemplateId = ref<number | null>(null)
  const selectedTemplateName = ref<string | null>(null)

  function hydrateFromStorage() {
    const rawId = localStorage.getItem(LS_ID)
    const name = localStorage.getItem(LS_NAME)
    if (rawId && /^\d+$/.test(rawId)) {
      selectedTemplateId.value = parseInt(rawId, 10)
      selectedTemplateName.value = name || `Template #${rawId}`
    }
  }

  function setExportDeck(id: number, name: string) {
    selectedTemplateId.value = id
    selectedTemplateName.value = name
    localStorage.setItem(LS_ID, String(id))
    localStorage.setItem(LS_NAME, name)
  }

  function clearExportDeck() {
    selectedTemplateId.value = null
    selectedTemplateName.value = null
    localStorage.removeItem(LS_ID)
    localStorage.removeItem(LS_NAME)
  }

  hydrateFromStorage()

  return {
    selectedTemplateId,
    selectedTemplateName,
    setExportDeck,
    clearExportDeck,
    hydrateFromStorage,
  }
})
