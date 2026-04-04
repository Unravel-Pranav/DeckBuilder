<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import { useAutoSave } from '@/composables/useAutoSave'
import { toast } from 'vue-sonner'
import type { FlowStep } from '@/types'
import {
  LayoutDashboard,
  Sparkles,
  FileText,
  Layers,
  PenTool,
  Upload,
  Eye,
  Download,
  ChevronLeft,
  ChevronRight,
  Presentation,
  LayoutTemplate,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const uiStore = useUiStore()
const { autoSaveFireAndForget } = useAutoSave()

const FLOW_ORDER: FlowStep[] = [
  'create', 'recommendations', 'sections', 'builder', 'upload', 'preview', 'output',
]

const STEP_PREREQUISITES: Record<FlowStep, string> = {
  create: '',
  recommendations: 'Define Intent',
  sections: 'AI Recommendations',
  builder: 'Manage Sections',
  upload: 'Build Slides',
  preview: 'Build Slides',
  output: 'Preview & Generate',
}

const stepIcons = {
  create: Sparkles,
  recommendations: FileText,
  sections: Layers,
  builder: PenTool,
  upload: Upload,
  preview: Eye,
  output: Download,
} as const

const isOnDashboard = computed(() => route.name === 'dashboard')
const isOnTemplates = computed(() => route.name === 'templates')

function canNavigateToStep(step: typeof uiStore.steps.value[number]): boolean {
  if (step.isActive || step.isCompleted) return true

  const targetIdx = FLOW_ORDER.indexOf(step.id as FlowStep)
  const currentIdx = uiStore.currentStepIndex

  if (targetIdx <= currentIdx) return true

  for (let i = 0; i < targetIdx; i++) {
    const prevStep = FLOW_ORDER[i]
    if (prevStep === 'upload') continue
    if (!uiStore.completedSteps.has(prevStep)) return false
  }
  return true
}

function navigateToStep(step: typeof uiStore.steps.value[number]) {
  if (!canNavigateToStep(step)) {
    const prereq = STEP_PREREQUISITES[step.id as FlowStep]
    toast.warning(`Complete "${prereq}" first`, {
      description: `You need to finish the previous step before going to ${step.label}.`,
    })
    return
  }
  autoSaveFireAndForget()
  router.push(step.route)
}

function navigateTo(routePath: string) {
  autoSaveFireAndForget()
  router.push(routePath)
}
</script>

<template>
  <aside
    class="fixed left-0 top-0 bottom-0 z-40 flex flex-col border-r border-border transition-all duration-300"
    :class="uiStore.sidebarCollapsed ? 'w-16' : 'w-64'"
    :style="{ backgroundColor: 'var(--surface-elevated)' }"
  >
    <!-- Logo area -->
    <div class="flex items-center gap-3 px-4 h-16 border-b border-border">
      <div class="flex-shrink-0 w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center">
        <Presentation :size="18" class="text-[#09090B]" />
      </div>
      <Transition name="fade">
        <span
          v-if="!uiStore.sidebarCollapsed"
          class="font-display font-semibold text-lg tracking-tight whitespace-nowrap"
        >
          Auto Deck
        </span>
      </Transition>
    </div>

    <!-- Dashboard link -->
    <div class="px-3 pt-4 pb-2">
      <button
        class="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-200"
        :class="
          isOnDashboard
            ? 'bg-[var(--accent-muted)] text-amber-500'
            : 'text-muted-foreground hover:text-foreground hover:bg-foreground/5'
        "
        @click="navigateTo('/')"
      >
        <LayoutDashboard :size="18" :stroke-width="1.5" />
        <Transition name="fade">
          <span v-if="!uiStore.sidebarCollapsed" class="whitespace-nowrap">Dashboard</span>
        </Transition>
      </button>
    </div>

    <!-- Template Library link -->
    <div class="px-3 pb-2">
      <button
        class="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-200"
        :class="
          isOnTemplates
            ? 'bg-[var(--accent-muted)] text-amber-500'
            : 'text-muted-foreground hover:text-foreground hover:bg-foreground/5'
        "
        @click="navigateTo('/templates')"
      >
        <LayoutTemplate :size="18" :stroke-width="1.5" />
        <Transition name="fade">
          <span v-if="!uiStore.sidebarCollapsed" class="whitespace-nowrap">Templates</span>
        </Transition>
      </button>
    </div>

    <!-- Flow steps -->
    <nav class="flex-1 px-3 py-2 overflow-y-auto">
      <Transition name="fade">
        <p
          v-if="!uiStore.sidebarCollapsed"
          class="px-3 mb-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground/60"
        >
          Build Flow
        </p>
      </Transition>

      <div class="space-y-1">
        <button
          v-for="step in uiStore.steps"
          :key="step.id"
          class="relative flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-200"
          :class="[
            step.isActive
              ? 'bg-[var(--accent-muted)] text-amber-500'
              : step.isCompleted
                ? 'text-foreground/80 hover:bg-foreground/5'
                : canNavigateToStep(step)
                  ? 'text-muted-foreground hover:text-foreground/80 hover:bg-foreground/5'
                  : 'text-muted-foreground/40 cursor-not-allowed',
          ]"
          @click="navigateToStep(step)"
        >
          <!-- Step number / check -->
          <div
            class="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-mono border transition-all duration-200"
            :class="[
              step.isActive
                ? 'border-amber-500/50 text-amber-500 bg-amber-500/10'
                : step.isCompleted
                  ? 'border-amber-500/30 text-amber-500 bg-amber-500/5'
                  : 'border-border text-muted-foreground',
            ]"
          >
            <component
              v-if="step.isActive || step.isCompleted"
              :is="stepIcons[step.id as keyof typeof stepIcons]"
              :size="12"
              :stroke-width="1.5"
            />
            <span v-else>{{ step.index + 1 }}</span>
          </div>

          <Transition name="fade">
            <span v-if="!uiStore.sidebarCollapsed" class="whitespace-nowrap truncate">
              {{ step.label }}
            </span>
          </Transition>

          <!-- Active indicator dot -->
          <div
            v-if="step.isActive"
            class="absolute right-3 w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"
            style="box-shadow: 0 0 8px rgba(245, 158, 11, 0.6)"
          />
        </button>
      </div>
    </nav>

    <!-- Collapse toggle -->
    <div class="px-3 py-3 border-t border-border">
      <button
        class="flex items-center justify-center w-full py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-all duration-200"
        @click="uiStore.toggleSidebar()"
      >
        <ChevronLeft v-if="!uiStore.sidebarCollapsed" :size="18" :stroke-width="1.5" />
        <ChevronRight v-else :size="18" :stroke-width="1.5" />
      </button>
    </div>
  </aside>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 200ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
