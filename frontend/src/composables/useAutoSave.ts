/**
 * Composable for auto-saving presentation drafts to the backend.
 *
 * Usage — call `autoSave()` inside any navigation handler (Next / Previous / Save).
 * The save is fire-and-forget by default; navigation is never blocked.
 */

import { toRaw } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import { useAiStore } from '@/stores/ai'
import { saveDraft } from '@/lib/api'
import type { DraftPayload } from '@/lib/api'

function buildDraftPayload(): DraftPayload | null {
  const presentationStore = usePresentationStore()
  const slidesStore = useSlidesStore()
  const uiStore = useUiStore()
  const aiStore = useAiStore()

  const pres = presentationStore.currentPresentation
  if (!pres) return null

  const intentSnapshot = { ...toRaw(presentationStore.intent), referenceFile: null }

  return {
    id: pres.id,
    name: pres.name,
    current_step: uiStore.currentStep,
    state: {
      presentation: {
        ...toRaw(pres),
        intent: { ...toRaw(pres.intent), referenceFile: null },
      },
      intent: intentSnapshot,
      sections: toRaw(slidesStore.sections),
      activeSlideId: slidesStore.activeSlideId,
      activeSectionId: slidesStore.activeSectionId,
      completedSteps: [...uiStore.completedSteps],
      recommendation: aiStore.recommendation ? toRaw(aiStore.recommendation) : null,
      generatedFileId: presentationStore.generatedFileId,
      generatedFilename: presentationStore.generatedFilename,
    },
  }
}

export function useAutoSave() {
  async function autoSave(): Promise<void> {
    const payload = buildDraftPayload()
    if (!payload) return
    try {
      await saveDraft(payload)
    } catch (err) {
      console.warn('[auto-save] failed, falling back to sessionStorage only', err)
    }
  }

  function autoSaveFireAndForget(): void {
    autoSave()
  }

  return { autoSave, autoSaveFireAndForget }
}
