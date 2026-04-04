import { createRouter, createWebHistory } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { usePresentationStore } from '@/stores/presentation'
import { useAiStore } from '@/stores/ai'
import { useUiStore } from '@/stores/ui'
import type { FlowStep } from '@/types'

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

router.beforeEach((to) => {
  const slidesStore = useSlidesStore()
  const presentationStore = usePresentationStore()
  const aiStore = useAiStore()

  const hasSections = slidesStore.sections.length > 0
  const hasPresentation = !!presentationStore.currentPresentation
  const hasRecommendations = (aiStore.recommendation?.sections?.length ?? 0) > 0

  switch (to.name) {
    case 'recommendations':
      if (!hasPresentation) {
        return { name: 'create' }
      }
      break

    case 'sections':
      if (!hasRecommendations && !hasSections) {
        return hasPresentation ? { name: 'recommendations' } : { name: 'create' }
      }
      break

    case 'builder':
    case 'preview':
    case 'output':
      if (!hasSections) {
        return { name: 'create' }
      }
      break
  }
})

router.afterEach((to) => {
  const routeName = to.name as string
  const step = ROUTE_TO_STEP[routeName]
  if (step) {
    const uiStore = useUiStore()
    uiStore.setCurrentStep(step)
  }
})

export default router
