<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import type { LayoutType } from '@/types'
import { LAYOUTS_BY_CATEGORY, CATEGORY_LABELS } from '@/lib/layoutDefinitions'
import type { LayoutCategory } from '@/lib/layoutDefinitions'
import {
  BarChart3,
  Table2,
  Columns2,
  FileText,
  LayoutGrid,
  PanelLeft,
  Rows3,
  Grid2x2,
  PanelRight,
  AlignJustify,
  Heading1,
  Heading2,
  TrendingUp,
  SeparatorHorizontal,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const LAYOUT_ICONS: Record<string, typeof BarChart3> = {
  'full-chart':         BarChart3,
  'full-table':         Table2,
  'commentary-only':    FileText,
  'chart-commentary':   PanelLeft,
  'table-commentary':   Columns2,
  'quadrant-2c':        Rows3,
  'quadrant-1c1t':      PanelRight,
  'mixed':              LayoutGrid,
  'quadrant-2c1t1text': Grid2x2,
  'quadrant-2c2t':      AlignJustify,
  'title-content':      Heading1,
  'title-2col':         Heading2,
  'kpi-highlight':      TrendingUp,
  'section-divider':    SeparatorHorizontal,
}

const CATEGORY_ORDER: LayoutCategory[] = [
  'full_width',
  'two_column',
  'grid',
  'title',
  'kpi',
  'section',
]

const activeLayout = computed(() => slidesStore.activeSlide?.layout)

function setLayout(layoutId: string) {
  if (slidesStore.activeSlideId) {
    slidesStore.updateSlideLayout(slidesStore.activeSlideId, layoutId as LayoutType)
  }
}
</script>

<template>
  <!-- Single-row scrollable strip: [label · btn btn | label · btn | ...] -->
  <div class="flex items-center gap-0 border-b border-border bg-background/60 overflow-x-auto no-scrollbar h-9 px-3">

    <template v-for="(category, ci) in CATEGORY_ORDER" :key="category">
      <!-- Vertical divider between groups (skip before first) -->
      <div
        v-if="ci > 0"
        class="w-px self-stretch bg-border mx-2 my-1.5 flex-shrink-0"
      />

      <!-- Category label -->
      <span class="text-[8.5px] font-mono uppercase tracking-[0.13em] text-muted-foreground/50 mr-1.5 flex-shrink-0 select-none leading-none">
        {{ CATEGORY_LABELS[category] }}
      </span>

      <!-- Layout buttons -->
      <div class="flex items-center gap-0.5 flex-shrink-0">
        <button
          v-for="layout in LAYOUTS_BY_CATEGORY[category]"
          :key="layout.id"
          :title="layout.tooltip"
          class="group flex items-center gap-1.5 px-2.5 h-6 rounded-[5px] text-[10.5px] font-medium whitespace-nowrap transition-all duration-100 select-none"
          :class="
            activeLayout === layout.id
              ? 'bg-amber-500/[0.14] text-amber-500 ring-1 ring-amber-500/30 shadow-[0_1px_6px_rgba(245,158,11,0.1)]'
              : 'text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] ring-1 ring-transparent hover:ring-border'
          "
          @click="setLayout(layout.id)"
        >
          <component
            :is="LAYOUT_ICONS[layout.id] ?? FileText"
            :size="11"
            :stroke-width="activeLayout === layout.id ? 2 : 1.5"
            class="flex-shrink-0 transition-all duration-100"
            :class="activeLayout === layout.id ? 'text-amber-500' : 'text-muted-foreground/60 group-hover:text-muted-foreground'"
          />
          {{ layout.label }}
        </button>
      </div>
    </template>

  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
