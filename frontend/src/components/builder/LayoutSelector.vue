<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import type { LayoutType } from '@/types'
import {
  BarChart3,
  Table2,
  Columns2,
  FileText,
  LayoutGrid,
  PanelLeft,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const layouts: { id: LayoutType; label: string; icon: typeof BarChart3 }[] = [
  { id: 'chart-commentary', label: 'Chart + Text', icon: PanelLeft },
  { id: 'table-commentary', label: 'Table + Text', icon: Columns2 },
  { id: 'full-chart', label: 'Full Chart', icon: BarChart3 },
  { id: 'full-table', label: 'Full Table', icon: Table2 },
  { id: 'mixed', label: 'Mixed', icon: LayoutGrid },
  { id: 'commentary-only', label: 'Text Only', icon: FileText },
]

const activeLayout = computed(() => slidesStore.activeSlide?.layout)

function setLayout(layout: LayoutType) {
  if (slidesStore.activeSlideId) {
    slidesStore.updateSlideLayout(slidesStore.activeSlideId, layout)
  }
}
</script>

<template>
  <div class="flex items-center gap-1.5 px-4 py-2 border-b border-border overflow-x-auto">
    <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 mr-2 flex-shrink-0">Layout</span>
    <button
      v-for="layout in layouts"
      :key="layout.id"
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium whitespace-nowrap transition-all duration-200"
      :class="
        activeLayout === layout.id
          ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
          : 'text-muted-foreground hover:text-foreground/80 hover:bg-foreground/5 border border-transparent'
      "
      @click="setLayout(layout.id)"
    >
      <component :is="layout.icon" :size="12" :stroke-width="1.5" />
      {{ layout.label }}
    </button>
  </div>
</template>
