<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import { mockSections } from '@/lib/mockData'
import SlideListPanel from '@/components/builder/SlideListPanel.vue'
import LayoutSelector from '@/components/builder/LayoutSelector.vue'
import TemplateSelector from '@/components/builder/TemplateSelector.vue'
import SlideCanvas from '@/components/builder/SlideCanvas.vue'
import DataInputPanel from '@/components/builder/DataInputPanel.vue'
import CommentaryPanel from '@/components/builder/CommentaryPanel.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ArrowRight,
  Database,
  MessageSquare,
  PanelRightOpen,
  PanelRightClose,
} from 'lucide-vue-next'

const rightTab = ref<string>('data')
const rightPanelOpen = ref(false)

const router = useRouter()
const slidesStore = useSlidesStore()
const uiStore = useUiStore()

onMounted(() => {
  if (slidesStore.sections.length === 0) {
    slidesStore.setSections(mockSections)
  }
  if (!slidesStore.activeSlideId && slidesStore.allSlides.length > 0) {
    slidesStore.setActiveSlide(slidesStore.allSlides[0].id)
  }
})

function openPanel(tab: 'data' | 'commentary') {
  rightTab.value = tab
  rightPanelOpen.value = true
}

watch(() => slidesStore.activeSlideId, () => {
  rightPanelOpen.value = false
})

function onRegionClick(componentType: string | null) {
  if (!componentType) {
    rightPanelOpen.value = false
    return
  }
  if (componentType === 'chart' || componentType === 'table') {
    openPanel('data')
  } else if (componentType === 'text') {
    openPanel('commentary')
  }
}

function onCommentaryClick() {
  openPanel('commentary')
}

function handleContinue() {
  uiStore.completeStep('builder')
  uiStore.setCurrentStep('preview')
  router.push('/preview')
}
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)] overflow-hidden">
    <!-- Left panel: Slide list -->
    <div class="w-56 flex-shrink-0 hidden lg:block">
      <SlideListPanel />
    </div>

    <!-- Center: Canvas (takes remaining space) -->
    <div class="flex-1 flex flex-col min-w-0">
      <LayoutSelector />
      <TemplateSelector />
      <SlideCanvas @region-click="onRegionClick" @commentary-click="onCommentaryClick" />

      <!-- Continue bar -->
      <div class="px-6 py-3 border-t border-border flex items-center justify-between">
        <!-- Right panel toggle -->
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-200"
          :class="rightPanelOpen ? 'text-amber-500 bg-amber-500/10' : 'text-muted-foreground hover:text-foreground/80 hover:bg-foreground/5'"
          @click="rightPanelOpen = !rightPanelOpen"
        >
          <PanelRightClose v-if="rightPanelOpen" :size="14" :stroke-width="1.5" />
          <PanelRightOpen v-else :size="14" :stroke-width="1.5" />
          {{ rightPanelOpen ? 'Hide Panel' : 'Show Panel' }}
        </button>

        <Button
          class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-9 px-6 rounded-lg shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98] text-sm"
          @click="handleContinue"
        >
          Preview & Generate
          <ArrowRight :size="16" :stroke-width="2" class="ml-1.5" />
        </Button>
      </div>
    </div>

    <!-- Right panel: Data + Commentary (collapsible, auto-opens on object interaction) -->
    <Transition name="slide-panel">
      <div
        v-if="rightPanelOpen"
        class="w-80 flex-shrink-0 flex flex-col border-l border-border overflow-hidden"
        :style="{ background: 'var(--surface-elevated)' }"
      >
        <Tabs
          v-model="rightTab"
          class="flex flex-col h-full min-h-0"
        >
          <TabsList class="w-full grid grid-cols-2 bg-foreground/[0.03] rounded-none border-b border-border h-auto p-0">
            <TabsTrigger
              value="data"
              class="flex items-center gap-1 py-3 text-[11px] font-medium rounded-none data-[state=active]:bg-transparent data-[state=active]:text-amber-500 data-[state=active]:border-b-2 data-[state=active]:border-amber-500 data-[state=active]:shadow-none text-muted-foreground"
            >
              <Database :size="12" :stroke-width="1.5" />
              Data
            </TabsTrigger>
            <TabsTrigger
              value="commentary"
              class="flex items-center gap-1 py-3 text-[11px] font-medium rounded-none data-[state=active]:bg-transparent data-[state=active]:text-amber-500 data-[state=active]:border-b-2 data-[state=active]:border-amber-500 data-[state=active]:shadow-none text-muted-foreground"
            >
              <MessageSquare :size="12" :stroke-width="1.5" />
              Text
            </TabsTrigger>
          </TabsList>

          <ScrollArea class="flex-1 min-h-0">
            <div class="p-4">
              <TabsContent value="data" class="mt-0">
                <DataInputPanel />
              </TabsContent>
              <TabsContent value="commentary" class="mt-0">
                <CommentaryPanel />
              </TabsContent>
            </div>
          </ScrollArea>
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
