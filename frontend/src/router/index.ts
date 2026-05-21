import { createRouter, createWebHistory } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { usePresentationStore } from '@/stores/presentation'
import { useAiStore } from '@/stores/ai'
import { useUiStore } from '@/stores/ui'
import type { FlowStep } from '@/types'
import {
  buildFlowContext,
  getRedirectForStep,
  deriveCompletedSteps,
} from '@/lib/flowAccess'

const ROUTE_TO_STEP: Record<string, FlowStep> = {
  create: 'create',
  recommendations: 'recommendations',
  sections: 'sections',
  builder: 'builder',
  'template-upload': 'upload',
  preview: 'preview',
  output: 'output',
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/pages/DashboardPage.vue'),
    },
    {
      path: '/create',
      name: 'create',
      component: () => import('@/pages/CreatePresentationPage.vue'),
    },
    {
      path: '/recommendations',
      name: 'recommendations',
      component: () => import('@/pages/AiRecommendationsPage.vue'),
    },
    {
      path: '/sections',
      name: 'sections',
      component: () => import('@/pages/SectionManagerPage.vue'),
    },
    {
      path: '/builder',
      name: 'builder',
      component: () => import('@/pages/SlideBuilderPage.vue'),
    },
    {
      path: '/templates',
      name: 'templates',
      component: () => import('@/pages/TemplateManagementPage.vue'),
    },
    {
      path: '/templates/upload',
      name: 'template-upload',
      component: () => import('@/pages/TemplateUploadPage.vue'),
    },
    {
      path: '/preview',
      name: 'preview',
      component: () => import('@/pages/PreviewGeneratePage.vue'),
    },
    {
      path: '/output',
      name: 'output',
      component: () => import('@/pages/OutputPage.vue'),
    },
  ],
})

function getFlowContext() {
  const slidesStore = useSlidesStore()
  const presentationStore = usePresentationStore()
  const aiStore = useAiStore()
  return buildFlowContext({
    currentPresentation: presentationStore.currentPresentation,
    recommendationSectionsLength: aiStore.recommendation?.sections?.length ?? 0,
    sectionsLength: slidesStore.sections.length,
    generatedFileId: presentationStore.generatedFileId,
  })
}

router.beforeEach((to) => {
  const step = ROUTE_TO_STEP[to.name as string]
  if (!step) return

  const ctx = getFlowContext()
  const redirect = getRedirectForStep(step, ctx)
  if (redirect) return redirect
})

router.afterEach((to) => {
  const routeName = to.name as string
  const step = ROUTE_TO_STEP[routeName]
  if (step) {
    const uiStore = useUiStore()
    uiStore.setCurrentStep(step)
    const derived = deriveCompletedSteps(getFlowContext())
    uiStore.$patch({ completedSteps: derived })
  }
})

export default router
