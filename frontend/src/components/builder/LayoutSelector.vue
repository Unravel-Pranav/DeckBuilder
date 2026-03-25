<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { STRUCTURE_REGISTRY } from '@/lib/layoutDefinitions'
import type { SlideStructure } from '@/types'
import { Square, Columns2, Rows2, Grid2x2 } from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const STRUCTURE_ICONS: Record<SlideStructure, typeof Square> = {
  'blank':    Square,
  'two-col':  Columns2,
  'two-row':  Rows2,
  'grid-2x2': Grid2x2,
}

const activeStructure = computed(() => slidesStore.activeSlide?.structure)

function setStructure(id: SlideStructure) {
  if (slidesStore.activeSlideId) {
    slidesStore.updateSlideStructure(slidesStore.activeSlideId, id)
  }
}
</script>

<template>
  <div class="flex items-center gap-2 border-b border-border bg-background/60 h-12 px-4">
    <span class="text-[9px] font-mono uppercase tracking-[0.15em] text-muted-foreground/50 mr-1 select-none">
      Structure
    </span>

    <button
      v-for="def in STRUCTURE_REGISTRY"
      :key="def.id"
      :title="def.tooltip"
      class="group flex items-center gap-2 px-3 h-8 rounded-lg text-[11px] font-medium whitespace-nowrap transition-all duration-150 select-none"
      :class="
        activeStructure === def.id
          ? 'bg-amber-500/[0.14] text-amber-500 ring-1 ring-amber-500/30 shadow-[0_1px_6px_rgba(245,158,11,0.12)]'
          : 'text-muted-foreground hover:text-foreground hover:bg-foreground/[0.05] ring-1 ring-transparent hover:ring-border'
      "
      @click="setStructure(def.id)"
    >
      <!-- Mini structural preview -->
      <div
        class="w-5 h-4 rounded-[2px] border overflow-hidden flex-shrink-0 transition-colors duration-150"
        :class="
          activeStructure === def.id
            ? 'border-amber-500/40'
            : 'border-muted-foreground/20 group-hover:border-muted-foreground/40'
        "
      >
        <!-- Blank: single block -->
        <div v-if="def.id === 'blank'" class="w-full h-full"
          :class="activeStructure === def.id ? 'bg-amber-500/25' : 'bg-muted-foreground/10'"
        />

        <!-- Two-col: vertical divider -->
        <div v-else-if="def.id === 'two-col'" class="w-full h-full flex">
          <div class="flex-1" :class="activeStructure === def.id ? 'bg-amber-500/25' : 'bg-muted-foreground/10'" />
          <div class="w-px" :class="activeStructure === def.id ? 'bg-amber-500/40' : 'bg-muted-foreground/20'" />
          <div class="flex-1" :class="activeStructure === def.id ? 'bg-amber-500/15' : 'bg-muted-foreground/5'" />
        </div>

        <!-- Two-row: horizontal divider -->
        <div v-else-if="def.id === 'two-row'" class="w-full h-full flex flex-col">
          <div class="flex-1" :class="activeStructure === def.id ? 'bg-amber-500/25' : 'bg-muted-foreground/10'" />
          <div class="h-px" :class="activeStructure === def.id ? 'bg-amber-500/40' : 'bg-muted-foreground/20'" />
          <div class="flex-1" :class="activeStructure === def.id ? 'bg-amber-500/15' : 'bg-muted-foreground/5'" />
        </div>

        <!-- 2x2 grid -->
        <div v-else class="w-full h-full grid grid-cols-2 grid-rows-2 gap-px"
          :class="activeStructure === def.id ? 'bg-amber-500/40' : 'bg-muted-foreground/20'"
        >
          <div :class="activeStructure === def.id ? 'bg-amber-500/25' : 'bg-muted-foreground/10'" />
          <div :class="activeStructure === def.id ? 'bg-amber-500/20' : 'bg-muted-foreground/8'" />
          <div :class="activeStructure === def.id ? 'bg-amber-500/15' : 'bg-muted-foreground/6'" />
          <div :class="activeStructure === def.id ? 'bg-amber-500/10' : 'bg-muted-foreground/4'" />
        </div>
      </div>

      {{ def.label }}
    </button>
  </div>
</template>
