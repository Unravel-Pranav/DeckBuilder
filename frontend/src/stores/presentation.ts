import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  PresentationType,
  ToneType,
  AudienceExpertise,
  HeroStat,
  DesignPreferences,
  PresentationIntent,
  Presentation,
} from '@/types'

export const usePresentationStore = defineStore('presentation', () => {
  const currentPresentation = ref<Presentation | null>(null)
  const recentPresentations = ref<Presentation[]>([])

  const generatedFileId = ref<string | null>(null)
  const generatedFilename = ref<string | null>(null)

  const heroFields = ref<HeroStat[]>([
    { key: 'vacancy_rate',              label: 'Vacancy Rate',             value: '', trend: 'neutral' },
    { key: 'sf_net_absorption',         label: 'SF Net Absorption',        value: '', trend: 'neutral' },
    { key: 'sf_construction_delivered', label: 'SF Construction Delivered', value: '', trend: 'neutral' },
    { key: 'sf_under_construction',     label: 'SF Under Construction',    value: '', trend: 'neutral' },
    { key: 'lease_rate',                label: 'NNN / Lease Rate',         value: '', trend: 'neutral' },
  ])

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

  function setObjective(objective: string) {
    intent.value.objective = objective || undefined
  }

  function setKeyMetrics(metrics: string[]) {
    intent.value.keyMetrics = metrics
  }

  function setAudienceExpertise(expertise: AudienceExpertise) {
    intent.value.audienceExpertise = expertise
  }

  function updateHeroField(key: string, field: 'label' | 'value' | 'trend', val: string) {
    const stat = heroFields.value.find(s => s.key === key)
    if (stat) (stat as Record<string, string>)[field] = val
  }

  function heroFieldsPayload(): Record<string, { label: string; value: string; trend: string }> {
    return Object.fromEntries(
      heroFields.value.map(f => [f.key, { label: f.label, value: f.value, trend: f.trend }])
    )
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

  function setGeneratedFile(fileId: string, filename: string) {
    generatedFileId.value = fileId
    generatedFilename.value = filename
  }

  function clearGeneratedFile() {
    generatedFileId.value = null
    generatedFilename.value = null
  }

  function $reset() {
    currentPresentation.value = null
    generatedFileId.value = null
    generatedFilename.value = null
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
    generatedFileId,
    generatedFilename,
    setType,
    setTone,
    setAudience,
    setDesignPreferences,
    setReferenceFile,
    setObjective,
    setKeyMetrics,
    setAudienceExpertise,
    heroFields,
    updateHeroField,
    heroFieldsPayload,
    createPresentation,
    setRecentPresentations,
    setGeneratedFile,
    clearGeneratedFile,
    $reset,
  }
})
