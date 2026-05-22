<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import SlideListPanel from '@/components/builder/SlideListPanel.vue'
import SlideCanvas from '@/components/builder/SlideCanvas.vue'
import { mapDataToChartComponent } from '@/lib/schema'
import DataInputPanel from '@/components/builder/DataInputPanel.vue'
import CommentaryPanel from '@/components/builder/CommentaryPanel.vue'
import HeroStatsPanel from '@/components/builder/HeroStatsPanel.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  ArrowRight,
  Database,
  MessageSquare,
  Hash,
  Layers,
} from 'lucide-vue-next'

import { useAutoSave } from '@/composables/useAutoSave'

const router = useRouter()
const slidesStore = useSlidesStore()
const uiStore = useUiStore()
const { autoSaveFireAndForget } = useAutoSave()

// Right panel always visible; tab auto-switches based on region/slide context
const rightTab = ref<string>('data')
const rightPanelOpen = ref(true)

const hasData = computed(() => slidesStore.sections.length > 0)

// Is the currently active slide the first slide (cover slide)?
const isCoverSlide = computed(() => {
  const allSlides = slidesStore.allSlides
  if (!slidesStore.activeSlideId) return false
  return allSlides.length > 0 && allSlides[0].id === slidesStore.activeSlideId
})

// Dynamic tab label for the data panel
const dataTabLabel = computed(() => {
  const region = slidesStore.activeRegion
  if (!region?.component) return 'Add Content'
  if (region.component.type === 'chart') return 'Chart Data'
  if (region.component.type === 'table') return 'Table Data'
  return 'Data'
})

onMounted(() => {
  if (!slidesStore.activeSlideId && slidesStore.allSlides.length > 0) {
    slidesStore.setActiveSlide(slidesStore.allSlides[0].id)
  }
})

function openPanel(tab: 'data' | 'commentary' | 'kpi') {
  rightTab.value = tab
  rightPanelOpen.value = true
}

// Auto-switch to KPI tab when cover slide is selected
watch(isCoverSlide, (val) => {
  if (val) openPanel('kpi')
})

// When region changes, switch panel tab to match content type
watch(() => slidesStore.activeRegion, (region) => {
  if (!region?.component) return
  if (region.component.type === 'text') {
    rightTab.value = 'commentary'
  } else {
    rightTab.value = 'data'
  }
})

function onRegionClick(componentType: string | null) {
  if (isCoverSlide.value) {
    // On cover slide, let user pick between KPI and data panels
    openPanel(componentType === 'text' ? 'commentary' : 'data')
    return
  }
  if (componentType === 'text') {
    openPanel('commentary')
  } else {
    // Empty or chart/table region → always open data panel
    openPanel('data')
  }
}

function onCommentaryClick() {
  openPanel('commentary')
}

const DEFAULT_CHART_DATA = { type: 'bar', x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], y_axis: [120, 150, 180, 210], label: 'Value' }
const DEFAULT_TABLE_DATA = { headers: ['Metric', 'Value', 'Change'], rows: [['Revenue', '$0', '+0%'], ['Margin', '0%', '+0pp']] }

function onQuickAdd(regionIndex: number, type: 'chart' | 'table' | 'text') {
  if (!slidesStore.activeSlideId) return
  slidesStore.setActiveRegion(regionIndex)

  if (type === 'chart') {
    const data = mapDataToChartComponent(DEFAULT_CHART_DATA as Record<string, unknown>, 'bar')
    slidesStore.setRegionComponent(slidesStore.activeSlideId, regionIndex, { id: crypto.randomUUID(), type: 'chart', data, config: {} })
    openPanel('data')
  } else if (type === 'table') {
    slidesStore.setRegionComponent(slidesStore.activeSlideId, regionIndex, { id: crypto.randomUUID(), type: 'table', data: DEFAULT_TABLE_DATA, config: {} })
    openPanel('data')
  } else {
    slidesStore.setRegionComponent(slidesStore.activeSlideId, regionIndex, { id: crypto.randomUUID(), type: 'text', data: { content: '' }, config: { format: 'paragraph' } })
    openPanel('commentary')
  }
}

function handleContinue() {
  uiStore.completeStep('builder')
  uiStore.setCurrentStep('preview')
  autoSaveFireAndForget()
  router.push('/preview')
}
</script>

<template>
  <!-- Empty state when no sections -->
  <div v-if="!hasData" class="flex h-[calc(100vh-4rem)] items-center justify-center">
    <div class="text-center max-w-md px-6">
      <div class="w-16 h-16 rounded-2xl bg-amber-500/10 flex items-center justify-center mx-auto mb-6">
        <Layers :size="32" :stroke-width="1.5" class="text-amber-500/60" />
      </div>
      <h2 class="text-xl font-display font-semibold mb-2">No slides to build</h2>
      <p class="text-sm text-muted-foreground mb-6">
        Start by creating a presentation and adding sections. Your slides will appear here once you've set up your content structure.
      </p>
      <Button
        class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-10 px-6 rounded-lg"
        @click="router.push('/create')"
      >
        Create Presentation
      </Button>
    </div>
  </div>

  <!-- Main builder UI -->
  <div v-else class="flex h-[calc(100vh-4rem)] overflow-hidden">
    <!-- Left panel: Slide list -->
    <div class="w-56 flex-shrink-0 hidden lg:block">
      <SlideListPanel />
    </div>

    <!-- Center: Canvas -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Layout selector is now inline inside SlideCanvas title bar -->
      <SlideCanvas @region-click="onRegionClick" @commentary-click="onCommentaryClick" @quick-add="onQuickAdd" />

      <!-- Bottom bar -->
      <div class="px-6 py-3 border-t border-border flex items-center justify-end">
        <Button
          class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-9 px-6 rounded-lg shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98] text-sm"
          @click="handleContinue"
        >
          Preview & Generate
          <ArrowRight :size="16" :stroke-width="2" class="ml-1.5" />
        </Button>
      </div>
    </div>

    <!-- Right panel: always visible, context-aware tabs -->
    <Transition name="slide-panel">
      <div
        v-if="rightPanelOpen"
        class="w-80 flex-shrink-0 flex flex-col border-l border-border overflow-hidden"
        :style="{ background: 'var(--surface-elevated)' }"
      >
        <Tabs v-model="rightTab" class="flex flex-col h-full min-h-0">
          <TabsList class="w-full grid bg-foreground/[0.03] rounded-none border-b border-border h-auto p-0"
            :class="isCoverSlide ? 'grid-cols-3' : 'grid-cols-2'"
          >
            <TabsTrigger
              value="data"
              class="flex items-center gap-1 py-3 text-[11px] font-medium rounded-none data-[state=active]:bg-transparent data-[state=active]:text-amber-500 data-[state=active]:border-b-2 data-[state=active]:border-amber-500 data-[state=active]:shadow-none text-muted-foreground"
            >
              <Database :size="12" :stroke-width="1.5" />
              {{ dataTabLabel }}
            </TabsTrigger>
            <TabsTrigger
              value="commentary"
              class="flex items-center gap-1 py-3 text-[11px] font-medium rounded-none data-[state=active]:bg-transparent data-[state=active]:text-amber-500 data-[state=active]:border-b-2 data-[state=active]:border-amber-500 data-[state=active]:shadow-none text-muted-foreground"
            >
              <MessageSquare :size="12" :stroke-width="1.5" />
              Text
            </TabsTrigger>
            <TabsTrigger
              v-if="isCoverSlide"
              value="kpi"
              class="flex items-center gap-1 py-3 text-[11px] font-medium rounded-none data-[state=active]:bg-transparent data-[state=active]:text-amber-500 data-[state=active]:border-b-2 data-[state=active]:border-amber-500 data-[state=active]:shadow-none text-muted-foreground"
            >
              <Hash :size="12" :stroke-width="1.5" />
              KPI Stats
            </TabsTrigger>
          </TabsList>

          <div class="flex-1 min-h-0 overflow-y-auto">
            <div class="p-4">
              <TabsContent value="data" class="mt-0">
                <DataInputPanel />
              </TabsContent>
              <TabsContent value="commentary" class="mt-0">
                <CommentaryPanel />
              </TabsContent>
              <TabsContent v-if="isCoverSlide" value="kpi" class="mt-0">
                <HeroStatsPanel />
              </TabsContent>
            </div>
          </div>
        </Tabs>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: all 250ms ease-out;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  opacity: 0;
  overflow: hidden;
}
</style>
