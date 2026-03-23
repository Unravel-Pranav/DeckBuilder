import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  PresentationType,
  ToneType,
  DesignPreferences,
  PresentationIntent,
  Presentation,
} from '@/types'

export const usePresentationStore = defineStore('presentation', () => {
  const currentPresentation = ref<Presentation | null>(null)
  const recentPresentations = ref<Presentation[]>([])

  const intent = ref<PresentationIntent>({
    type: 'business',
    audience: '',
    tone: 'formal',
    designPreferences: {
      fontStyle: 'modern',
      colorScheme: 'dark',
    },
    referenceFile: null,
  })

  const hasIntent = computed(() =>
    intent.value.type !== null && intent.value.audience.trim().length > 0,
  )
  const presentationName = computed(
    () => currentPresentation.value?.name ?? 'Untitled Presentation',
  )

  function setType(type: PresentationType) {
    intent.value.type = type
  }

  function setTone(tone: ToneType) {
    intent.value.tone = tone
  }

  function setAudience(audience: string) {
    intent.value.audience = audience
  }

  function setDesignPreferences(prefs: DesignPreferences) {
    intent.value.designPreferences = prefs
  }

  function setReferenceFile(file: File | null) {
    intent.value.referenceFile = file
  }

  function createPresentation(name: string) {
    currentPresentation.value = {
      id: crypto.randomUUID(),
      name,
      intent: { ...intent.value },
      sections: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      status: 'draft',
    }
  }

  function setRecentPresentations(presentations: Presentation[]) {
    recentPresentations.value = presentations
  }

  function $reset() {
    currentPresentation.value = null
    intent.value = {
      type: 'business',
      audience: '',
      tone: 'formal',
      designPreferences: { fontStyle: 'modern', colorScheme: 'dark' },
      referenceFile: null,
    }
  }

  return {
    currentPresentation,
    recentPresentations,
    intent,
    hasIntent,
    presentationName,
    setType,
    setTone,
    setAudience,
    setDesignPreferences,
    setReferenceFile,
    createPresentation,
    setRecentPresentations,
    $reset,
  }
})
