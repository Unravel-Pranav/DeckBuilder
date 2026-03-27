<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useDragDrop } from '@/composables/useDragDrop'
import { STRUCTURE_BY_ID } from '@/lib/layoutDefinitions'
import EmptyState from '@/components/shared/EmptyState.vue'
import type { ChartData, TableData, UploadedSlideData, SlideRegion, SlideComponent } from '@/types'
import {
  BarChart3,
  Table2,
  FileText,
  PenTool,
  TrendingUp,
  Plus,
  GripVertical,
  Upload,
} from 'lucide-vue-next'

const emit = defineEmits<{
  'commentary-click': []
  'region-click': [componentType: string | null]
}>()

const slidesStore = useSlidesStore()
const slide = computed(() => slidesStore.activeSlide)
const { isDragging, hoverRegionIndex, payload, startDrag, endDrag, setHoverRegion, consumePayload } = useDragDrop()

function regionDynamicClass(ri: number): string {
  if (isDragging.value) {
    if (hoverRegionIndex.value === ri) {
      return 'border-amber-500 bg-amber-500/10 shadow-[0_0_20px_rgba(245,158,11,0.15)] ring-2 ring-amber-500/20 scale-[1.01]'
    }
    return 'border-dashed border-amber-500/30 bg-amber-500/[0.02]'
  }
  if (slidesStore.activeRegionIndex === ri) {
    return 'border-amber-500/40 bg-amber-500/[0.04] shadow-[0_0_12px_rgba(245,158,11,0.08)]'
  }
  return 'border-border/60 hover:border-border bg-[var(--glass-bg)]'
}

function onDragEnter(regionIndex: number) {
  setHoverRegion(regionIndex)
}

function onGridDragLeave(event: DragEvent) {
  const grid = event.currentTarget as HTMLElement
  const related = event.relatedTarget as Node | null
  if (!related || !grid.contains(related)) {
    setHoverRegion(null)
  }
}

function onRegionDragStart(event: DragEvent, ri: number, region: SlideRegion) {
  if (!region.component) {
    event.preventDefault()
    return
  }
  startDrag(event, {
    componentType: region.component.type,
    component: region.component,
    label: `Move ${region.component.type}`,
    sourceRegionIndex: ri,
  })
}

function onDrop(targetIndex: number) {
  const data = consumePayload()
  if (!data || !slide.value) return

  if (data.sourceRegionIndex != null) {
    const sourceIndex = data.sourceRegionIndex
    if (sourceIndex === targetIndex) return

    const targetComponent = slide.value.regions[targetIndex].component
    const sourceComponent = data.component as SlideComponent

    slidesStore.setRegionComponent(slide.value.id, targetIndex, sourceComponent)
    if (targetComponent) {
      slidesStore.setRegionComponent(slide.value.id, sourceIndex, targetComponent)
    } else {
      slidesStore.clearRegion(slide.value.id, sourceIndex)
    }
  } else {
    const component = {
      ...data.component,
      id: crypto.randomUUID(),
    } as SlideComponent
    slidesStore.setRegionComponent(slide.value.id, targetIndex, component)
  }

  slidesStore.setActiveRegion(targetIndex)
}

const structureDef = computed(() => {
  const id = slide.value?.structure ?? 'blank'
  return STRUCTURE_BY_ID[id] ?? STRUCTURE_BY_ID['blank']
})

const gridClass = computed(() => structureDef.value?.gridClass ?? 'grid-cols-1')

function selectRegion(index: number) {
  slidesStore.setActiveRegion(index)
  const region = slide.value?.regions[index]
  emit('region-click', region?.component?.type ?? null)
}

const CHART_COLORS = ['#F59E0B', '#71717A', '#3B82F6', '#10B981', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4']

function getBarHeights(data: number[]): number[] {
  const max = Math.max(...data, 1)
  return data.map((v) => (v / max) * 100)
}

function getMultiBarMax(datasets: { data: number[] }[]): number {
  let max = 1
  for (const ds of datasets) {
    for (const v of ds.data) {
      if (v > max) max = v
    }
  }
  return max
}

function getLinePoints(data: number[], width: number, height: number): string {
  if (data.length < 2) return ''
  const max = Math.max(...data, 1)
  return data
    .map((v, i) => `${(i / (data.length - 1)) * width},${height - (v / max) * (height - 4)}`)
    .join(' ')
}

function getScatterPoints(data: number[], labels: string[]): { x: number; y: number }[] {
  if (data.length === 0) return []
  const xVals = labels.map(Number)
  const xMin = Math.min(...xVals)
  const xMax = Math.max(...xVals, xMin + 1)
  const yMax = Math.max(...data, 1)
  return data.map((v, i) => ({
    x: ((xVals[i] - xMin) / (xMax - xMin)) * 190 + 5,
    y: 76 - (v / yMax) * 72,
  }))
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
      <div class="flex-1 p-6 overflow-y-auto" @click.self="emit('region-click', null)">
        <div
          class="w-full max-w-4xl mx-auto aspect-[16/9] rounded-xl border border-border p-4 grid gap-3"
          :class="gridClass"
          :style="{ background: 'var(--preview-surface-deep)' }"
          @dragleave="onGridDragLeave"
        >
          <!-- Render each region -->
          <div
            v-for="(region, ri) in slide.regions"
            :key="region.id"
            class="group relative rounded-lg border-2 transition-all duration-200 cursor-pointer flex flex-col overflow-hidden"
            :class="regionDynamicClass(ri)"
            :draggable="!!region.component"
            @click="selectRegion(ri)"
            @dragstart="onRegionDragStart($event, ri, region)"
            @dragend="endDrag"
            @dragenter.prevent="onDragEnter(ri)"
            @dragover.prevent
            @drop.prevent="onDrop(ri)"
          >
            <!-- Drop indicator overlay -->
            <div
              v-if="isDragging && hoverRegionIndex === ri"
              class="absolute inset-0 flex items-center justify-center rounded-lg z-10 pointer-events-none"
            >
              <div class="flex flex-col items-center gap-1 px-3 py-2 rounded-lg bg-amber-500/15 backdrop-blur-sm">
                <Plus :size="16" :stroke-width="2" class="text-amber-500" />
                <span class="text-[10px] font-mono font-medium text-amber-500">{{ payload?.label ?? 'Drop here' }}</span>
              </div>
            </div>

            <!-- Drag handle (visible on hover when region has content) -->
            <div
              v-if="region.component && !isDragging"
              class="absolute top-2 right-2 opacity-0 group-hover:opacity-60 transition-opacity z-10 cursor-grab"
            >
              <GripVertical :size="12" class="text-muted-foreground" />
            </div>

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

                <!-- Bar (supports multi-series grouped bars) -->
                <template v-if="(region.component.data as ChartData).type === 'bar'">
                  <div class="flex-1 flex items-end gap-1.5 px-1">
                    <div
                      v-for="(_, labelIdx) in (region.component.data as ChartData).labels"
                      :key="labelIdx"
                      class="flex-1 flex items-end gap-px"
                    >
                      <div
                        v-for="(ds, dsi) in (region.component.data as ChartData).datasets"
                        :key="dsi"
                        class="flex-1 rounded-t transition-all duration-500"
                        :style="{
                          height: `${(ds.data[labelIdx] / getMultiBarMax((region.component.data as ChartData).datasets)) * 100}%`,
                          backgroundColor: CHART_COLORS[dsi % CHART_COLORS.length] + '80',
                          minHeight: '3px',
                        }"
                      />
                    </div>
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
                      <template v-for="(ds, dsi) in (region.component.data as ChartData).datasets" :key="dsi">
                        <polygon
                          v-if="(region.component.data as ChartData).type === 'area'"
                          :points="`0,80 ${getLinePoints(ds.data, 200, 80)} 200,80`"
                          :fill="CHART_COLORS[dsi % CHART_COLORS.length] + '18'"
                        />
                        <polyline
                          fill="none"
                          :stroke="CHART_COLORS[dsi % CHART_COLORS.length]"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          :points="getLinePoints(ds.data, 200, 80)"
                          :opacity="0.8"
                        />
                      </template>
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
                          const colors = (region.component!.data as ChartData).datasets[0].backgroundColor ?? CHART_COLORS
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
                        :style="{ backgroundColor: ((region.component.data as ChartData).datasets[0].backgroundColor ?? CHART_COLORS)[i % CHART_COLORS.length] }" />
                      {{ label }}
                    </span>
                  </div>
                </template>

                <!-- Scatter -->
                <template v-else-if="(region.component.data as ChartData).type === 'scatter'">
                  <div class="flex-1 px-1">
                    <svg class="w-full h-full" viewBox="0 0 200 80" preserveAspectRatio="none">
                      <circle
                        v-for="(pt, pi) in getScatterPoints((region.component.data as ChartData).datasets[0].data, (region.component.data as ChartData).labels)"
                        :key="pi"
                        :cx="pt.x"
                        :cy="pt.y"
                        r="3"
                        fill="#F59E0B"
                        opacity="0.7"
                      />
                    </svg>
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

              <!-- Uploaded slide component -->
              <template v-else-if="region.component.type === 'uploaded_slide'">
                <div class="flex items-center gap-2 mb-2">
                  <Upload :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">Uploaded Slide</span>
                </div>
                <div class="flex-1 flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-amber-500/20 bg-amber-500/[0.03] p-3">
                  <div class="w-12 h-12 rounded-lg bg-amber-500/10 flex items-center justify-center">
                    <span class="text-xl font-bold text-amber-500/60">{{ (region.component.data as UploadedSlideData).slideIndex + 1 }}</span>
                  </div>
                  <p class="text-[10px] font-medium text-foreground/70 text-center truncate max-w-full">
                    {{ (region.component.data as UploadedSlideData).title }}
                  </p>
                  <p class="text-[8px] text-muted-foreground/50 font-mono">
                    {{ (region.component.data as UploadedSlideData).layoutName }}
                  </p>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- Slide-level commentary (below canvas) -->
        <div
          v-if="slide.commentary"
          class="w-full max-w-4xl mx-auto mt-3 px-1 cursor-pointer rounded-lg p-2 -m-1 transition-colors hover:bg-amber-500/[0.04]"
          @click="emit('commentary-click')"
        >
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
