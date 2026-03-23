import { createRouter, createWebHistory } from 'vue-router'

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

export default router
