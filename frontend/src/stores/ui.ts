import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { FlowStep } from '@/types'

const FLOW_STEPS: FlowStep[] = [
  'create',
  'recommendations',
  'sections',
  'builder',
  'upload',
  'preview',
  'output',
]

const STEP_LABELS: Record<FlowStep, string> = {
  create: 'Define Intent',
  recommendations: 'AI Recommendations',
  sections: 'Manage Sections',
  builder: 'Build Slides',
  upload: 'Upload Templates',
  preview: 'Preview & Generate',
  output: 'Download',
}

const STEP_ROUTES: Record<FlowStep, string> = {
  create: '/create',
  recommendations: '/recommendations',
  sections: '/sections',
  builder: '/builder',
  upload: '/templates/upload',
  preview: '/preview',
  output: '/output',
}

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const currentStep = ref<FlowStep>('create')
  const completedSteps = ref<Set<FlowStep>>(new Set())
  const activeModal = ref<string | null>(null)
  const rightPanelTab = ref<'data' | 'commentary'>('data')

  const currentStepIndex = computed(() =>
    FLOW_STEPS.indexOf(currentStep.value),
  )

  const steps = computed(() =>
    FLOW_STEPS.map((step, index) => ({
      id: step,
      label: STEP_LABELS[step],
      route: STEP_ROUTES[step],
      isActive: step === currentStep.value,
      isCompleted: completedSteps.value.has(step),
      isPending: !completedSteps.value.has(step) && step !== currentStep.value,
      index,
    })),
  )

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setCurrentStep(step: FlowStep) {
    currentStep.value = step
  }

  function completeStep(step: FlowStep) {
    completedSteps.value.add(step)
  }

  function openModal(modalId: string) {
    activeModal.value = modalId
  }

  function closeModal() {
    activeModal.value = null
  }

  function setRightPanelTab(tab: 'data' | 'commentary') {
    rightPanelTab.value = tab
  }

  function $reset() {
    sidebarCollapsed.value = false
    currentStep.value = 'create'
    completedSteps.value = new Set()
    activeModal.value = null
    rightPanelTab.value = 'data'
  }

  return {
    sidebarCollapsed,
    currentStep,
    completedSteps,
    activeModal,
    rightPanelTab,
    currentStepIndex,
    steps,
    toggleSidebar,
    setCurrentStep,
    completeStep,
    openModal,
    closeModal,
    setRightPanelTab,
    $reset,
  }
})
