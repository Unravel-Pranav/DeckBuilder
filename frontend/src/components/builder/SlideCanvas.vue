<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { STRUCTURE_BY_ID } from '@/lib/layoutDefinitions'
import EmptyState from '@/components/shared/EmptyState.vue'
import type { ChartData, TableData, SlideRegion } from '@/types'
import {
  BarChart3,
  Table2,
  FileText,
  PenTool,
  TrendingUp,
  Plus,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()
const slide = computed(() => slidesStore.activeSlide)

const structureDef = computed(() => {
  const id = slide.value?.structure ?? 'blank'
  return STRUCTURE_BY_ID[id] ?? STRUCTURE_BY_ID['blank']
})

const gridClass = computed(() => structureDef.value?.gridClass ?? 'grid-cols-1')

function selectRegion(index: number) {
  slidesStore.setActiveRegion(index)
}

function getBarHeights(data: number[]): number[] {
  const max = Math.max(...data, 1)
  return data.map((v) => (v / max) * 100)
}

function getLinePoints(data: number[], width: number, height: number): string {
  if (data.length < 2) return ''
  const max = Math.max(...data, 1)
  return data
    .map((v, i) => `${(i / (data.length - 1)) * width},${height - (v / max) * (height - 4)}`)
    .join(' ')
}

function regionLabel(index: number): string {
  return structureDef.value?.regionLabels[index] ?? `Region ${index + 1}`
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <EmptyState
      v-if="!slide"
      :icon="PenTool"
      title="Select a slide"
      description="Choose a slide from the left panel to start editing."
    />

    <template v-else>
      <!-- Slide title input -->
      <div class="px-6 py-3 border-b border-border">
        <input
          :value="slide.title"
          class="bg-transparent text-lg font-display font-semibold tracking-tight outline-none w-full placeholder:text-muted-foreground/40"
          placeholder="Slide title..."
          @input="(e) => { if (slide) slide.title = (e.target as HTMLInputElement).value }"
        />
      </div>

      <!-- Canvas area -->
      <div class="flex-1 p-6 overflow-y-auto">
        <div
          class="w-full max-w-4xl mx-auto aspect-[16/9] rounded-xl border border-border p-4 grid gap-3"
          :class="gridClass"
          :style="{ background: 'var(--preview-surface-deep)' }"
        >
          <!-- Render each region -->
          <div
            v-for="(region, ri) in slide.regions"
            :key="region.id"
            class="rounded-lg border-2 transition-all duration-200 cursor-pointer flex flex-col overflow-hidden"
            :class="
              slidesStore.activeRegionIndex === ri
                ? 'border-amber-500/40 bg-amber-500/[0.04] shadow-[0_0_12px_rgba(245,158,11,0.08)]'
                : 'border-border/60 hover:border-border bg-[var(--glass-bg)]'
            "
            @click="selectRegion(ri)"
          >
            <!-- Region header -->
            <div class="flex items-center justify-between px-3 py-1.5 border-b"
              :class="slidesStore.activeRegionIndex === ri ? 'border-amber-500/20' : 'border-border/40'"
            >
              <span class="text-[9px] font-mono uppercase tracking-wider"
                :class="slidesStore.activeRegionIndex === ri ? 'text-amber-500/70' : 'text-muted-foreground/40'"
              >
                {{ regionLabel(ri) }}
              </span>
              <span v-if="region.component" class="text-[8px] font-mono px-1.5 py-0.5 rounded-full"
                :class="slidesStore.activeRegionIndex === ri ? 'bg-amber-500/10 text-amber-500' : 'bg-muted text-muted-foreground/60'"
              >
                {{ region.component.type }}
              </span>
            </div>

            <!-- Region content -->
            <div class="flex-1 p-3 flex flex-col min-h-0">

              <!-- Empty region placeholder -->
              <template v-if="!region.component">
                <div class="flex-1 flex flex-col items-center justify-center gap-2 text-muted-foreground/30">
                  <Plus :size="20" :stroke-width="1.5" />
                  <span class="text-[10px] font-mono">Add Component</span>
                </div>
              </template>

              <!-- Chart component -->
              <template v-else-if="region.component.type === 'chart'">
                <div class="flex items-center gap-2 mb-2">
                  <BarChart3 :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">
                    {{ (region.component.data as ChartData).type }} chart
                  </span>
                </div>

                <!-- Bar -->
                <template v-if="(region.component.data as ChartData).type === 'bar'">
                  <div class="flex-1 flex items-end gap-1.5 px-1">
                    <div
                      v-for="(val, i) in getBarHeights((region.component.data as ChartData).datasets[0].data)"
                      :key="i"
                      class="flex-1 rounded-t transition-all duration-500"
                      :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.5)', minHeight: '3px' }"
                    />
                  </div>
                  <div class="flex justify-between mt-1.5 px-0.5">
                    <span v-for="(label, i) in (region.component.data as ChartData).labels" :key="i"
                      class="text-[8px] font-mono text-muted-foreground/50">{{ label }}</span>
                  </div>
                </template>

                <!-- Line / Area -->
                <template v-else-if="(region.component.data as ChartData).type === 'line' || (region.component.data as ChartData).type === 'area'">
                  <div class="flex-1 px-1">
                    <svg class="w-full h-full" viewBox="0 0 200 80" preserveAspectRatio="none">
                      <polygon
                        v-if="(region.component.data as ChartData).type === 'area'"
                        :points="`0,80 ${getLinePoints((region.component.data as ChartData).datasets[0].data, 200, 80)} 200,80`"
                        fill="rgba(245,158,11,0.1)"
                      />
                      <polyline
                        v-for="(ds, dsi) in (region.component.data as ChartData).datasets"
                        :key="dsi"
                        fill="none"
                        :stroke="dsi === 0 ? '#F59E0B' : '#71717A'"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        :points="getLinePoints(ds.data, 200, 80)"
                        :opacity="0.8"
                      />
                    </svg>
                  </div>
                </template>

                <!-- Pie / Doughnut -->
                <template v-else-if="(region.component.data as ChartData).type === 'pie' || (region.component.data as ChartData).type === 'doughnut'">
                  <div class="flex-1 flex items-center justify-center">
                    <div
                      class="w-20 h-20 rounded-full relative"
                      :style="{
                        background: (() => {
                          const data = (region.component!.data as ChartData).datasets[0].data
                          const total = data.reduce((a: number, b: number) => a + b, 0) || 1
                          const colors = (region.component!.data as ChartData).datasets[0].backgroundColor ?? ['#F59E0B','#FBBF24','#D97706','#92400E']
                          let pct = 0
                          return 'conic-gradient(' + data.map((v: number, i: number) => {
                            const start = pct; pct += (v / total) * 100
                            return `${colors[i % colors.length]} ${start}% ${pct}%`
                          }).join(', ') + ')'
                        })()
                      }"
                    >
                      <div
                        v-if="(region.component.data as ChartData).type === 'doughnut'"
                        class="absolute inset-0 m-auto w-10 h-10 rounded-full"
                        :style="{ background: 'var(--surface-elevated)' }"
                      />
                    </div>
                  </div>
                  <div class="flex flex-wrap justify-center gap-x-2 gap-y-0.5 mt-1">
                    <span v-for="(label, i) in (region.component.data as ChartData).labels" :key="i"
                      class="text-[8px] font-mono text-muted-foreground/50 flex items-center gap-0.5">
                      <span class="w-1.5 h-1.5 rounded-full"
                        :style="{ backgroundColor: ((region.component.data as ChartData).datasets[0].backgroundColor ?? ['#F59E0B','#FBBF24','#D97706'])[i % 3] }" />
                      {{ label }}
                    </span>
                  </div>
                </template>

                <!-- Fallback bar -->
                <template v-else>
                  <div class="flex-1 flex items-end gap-1.5 px-1">
                    <div
                      v-for="(val, i) in getBarHeights((region.component.data as ChartData).datasets[0].data)"
                      :key="i"
                      class="flex-1 rounded-t"
                      :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.4)', minHeight: '3px' }"
                    />
                  </div>
                </template>
              </template>

              <!-- Table component -->
              <template v-else-if="region.component.type === 'table'">
                <div class="flex items-center gap-2 mb-2">
                  <Table2 :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">Table</span>
                </div>
                <div class="flex-1 overflow-auto">
                  <table class="w-full text-[9px]">
                    <thead>
                      <tr class="border-b border-border">
                        <th
                          v-for="h in (region.component.data as TableData).headers.slice(0, 5)"
                          :key="h"
                          class="text-left py-1 px-1.5 font-mono text-muted-foreground/60 font-medium"
                        >{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, ri) in (region.component.data as TableData).rows.slice(0, 4)"
                        :key="ri"
                        class="border-b border-border/40"
                      >
                        <td
                          v-for="(cell, ci) in row.slice(0, 5)"
                          :key="ci"
                          class="py-1 px-1.5 text-foreground/60"
                        >{{ cell }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>

              <!-- Text component -->
              <template v-else-if="region.component.type === 'text'">
                <div class="flex items-center gap-2 mb-2">
                  <FileText :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">Text</span>
                </div>
                <p class="text-[10px] text-muted-foreground leading-relaxed whitespace-pre-line line-clamp-6">
                  {{ (region.component.data as { content: string }).content }}
                </p>
              </template>
            </div>
          </div>
        </div>

        <!-- Slide-level commentary (below canvas) -->
        <div v-if="slide.commentary" class="w-full max-w-4xl mx-auto mt-3 px-1">
          <div class="flex items-center gap-1.5 mb-1">
            <FileText :size="10" :stroke-width="1.5" class="text-muted-foreground/40" />
            <span class="text-[9px] font-mono uppercase tracking-wider text-muted-foreground/40">Commentary</span>
          </div>
          <p class="text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-3">
            {{ slide.commentary }}
          </p>
        </div>
      </div>
    </template>
  </div>
</template>
