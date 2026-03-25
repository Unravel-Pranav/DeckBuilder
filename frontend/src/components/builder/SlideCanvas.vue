<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import EmptyState from '@/components/shared/EmptyState.vue'
import { mockChartData, mockTableData } from '@/lib/mockData'
import type { ChartData, TableData } from '@/types'
import {
  BarChart3,
  Table2,
  FileText,
  PenTool,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const slide = computed(() => slidesStore.activeSlide)

const layoutConfig = computed(() => {
  if (!slide.value) return null
  const configs: Record<string, { grid: string; areas: string[] }> = {
    'chart-commentary': { grid: 'grid-cols-5', areas: ['col-span-3', 'col-span-2'] },
    'table-commentary': { grid: 'grid-cols-5', areas: ['col-span-3', 'col-span-2'] },
    'full-chart': { grid: 'grid-cols-1', areas: ['col-span-1'] },
    'full-table': { grid: 'grid-cols-1', areas: ['col-span-1'] },
    mixed: { grid: 'grid-cols-2', areas: ['col-span-1', 'col-span-1'] },
    'commentary-only': { grid: 'grid-cols-1', areas: ['col-span-1'] },
  }
  return configs[slide.value.layout] ?? configs['chart-commentary']
})

const hasChart = computed(() =>
  ['chart-commentary', 'full-chart', 'mixed'].includes(slide.value?.layout ?? ''),
)
const hasTable = computed(() =>
  ['table-commentary', 'full-table', 'mixed'].includes(slide.value?.layout ?? ''),
)
const hasCommentary = computed(() =>
  ['chart-commentary', 'table-commentary', 'commentary-only'].includes(slide.value?.layout ?? ''),
)

const chartComponent = computed(() =>
  slide.value?.components.find((c) => c.type === 'chart') ?? null,
)
const tableComponent = computed(() =>
  slide.value?.components.find((c) => c.type === 'table') ?? null,
)

const chartData = computed<ChartData>(() => {
  const c = chartComponent.value
  if (c?.type === 'chart') return c.data
  return mockChartData.revenue
})
const tableData = computed<TableData>(() => {
  const c = tableComponent.value
  if (c?.type === 'table') return c.data
  return mockTableData.financials
})
const chartType = computed(() => chartData.value.type ?? 'bar')

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
      <!-- Slide title -->
      <div class="px-6 py-3 border-b border-border">
        <input
          :value="slide.title"
          class="bg-transparent text-lg font-display font-semibold tracking-tight outline-none w-full placeholder:text-muted-foreground/50"
          placeholder="Slide title..."
          @input="(e) => { if (slide) slide.title = (e.target as HTMLInputElement).value }"
        />
      </div>

      <!-- Canvas area -->
      <div class="flex-1 p-6 overflow-y-auto">
        <div
          class="w-full max-w-4xl mx-auto aspect-[16/9] rounded-xl border border-border bg-[var(--preview-surface)] p-6 flex flex-col"
        >
          <div class="flex-1 grid gap-4" :class="layoutConfig?.grid">

            <!-- CHART AREA -->
            <div
              v-if="hasChart"
              class="rounded-lg border border-border bg-[var(--glass-bg)] p-4 flex flex-col"
              :class="layoutConfig?.areas[0]"
            >
              <div class="flex items-center gap-2 mb-3">
                <BarChart3 :size="14" :stroke-width="1.5" class="text-amber-500" />
                <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  {{ chartType }} chart
                </span>
              </div>

              <!-- Bar chart -->
              <template v-if="chartType === 'bar'">
                <div class="flex-1 flex items-end gap-2 px-2">
                  <div
                    v-for="(val, i) in getBarHeights(chartData.datasets[0].data)"
                    :key="i"
                    class="flex-1 rounded-t transition-all duration-500"
                    :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.6)', minHeight: '4px' }"
                  />
                </div>
                <div class="flex justify-between mt-2 px-1">
                  <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/70">
                    {{ label }}
                  </span>
                </div>
              </template>

              <!-- Line / Area chart -->
              <template v-else-if="chartType === 'line' || chartType === 'area'">
                <div class="flex-1 px-1">
                  <svg class="w-full h-full" viewBox="0 0 200 80" preserveAspectRatio="none">
                    <polygon
                      v-if="chartType === 'area'"
                      :points="`0,80 ${getLinePoints(chartData.datasets[0].data, 200, 80)} 200,80`"
                      fill="rgba(245,158,11,0.1)"
                    />
                    <polyline
                      v-for="(ds, dsi) in chartData.datasets"
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
                <div class="flex justify-between mt-1 px-1">
                  <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/70">
                    {{ label }}
                  </span>
                </div>
              </template>

              <!-- Pie / Doughnut chart -->
              <template v-else-if="chartType === 'pie' || chartType === 'doughnut'">
                <div class="flex-1 flex items-center justify-center">
                  <div
                    class="w-24 h-24 rounded-full relative"
                    :style="{
                      background: (() => {
                        const data = chartData.datasets[0].data
                        const total = data.reduce((a, b) => a + b, 0) || 1
                        const colors = chartData.datasets[0].backgroundColor ?? ['#F59E0B', '#FBBF24', '#D97706', '#92400E']
                        let pct = 0
                        return 'conic-gradient(' + data.map((v, i) => {
                          const start = pct
                          pct += (v / total) * 100
                          return `${colors[i % colors.length]} ${start}% ${pct}%`
                        }).join(', ') + ')'
                      })(),
                    }"
                  >
                    <div
                      v-if="chartType === 'doughnut'"
                      class="absolute inset-0 m-auto w-12 h-12 rounded-full bg-[var(--preview-surface-deep)]"
                    />
                  </div>
                </div>
                <div class="flex flex-wrap justify-center gap-x-3 gap-y-1 mt-2">
                  <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/70 flex items-center gap-1">
                    <span
                      class="w-1.5 h-1.5 rounded-full"
                      :style="{ backgroundColor: (chartData.datasets[0].backgroundColor ?? ['#F59E0B', '#FBBF24', '#D97706'])[i % 3] }"
                    />
                    {{ label }}
                  </span>
                </div>
              </template>

              <!-- Fallback -->
              <template v-else>
                <div class="flex-1 flex items-end gap-2 px-2">
                  <div
                    v-for="(val, i) in getBarHeights(chartData.datasets[0].data)"
                    :key="i"
                    class="flex-1 rounded-t transition-all"
                    :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.4)', minHeight: '4px' }"
                  />
                </div>
              </template>
            </div>

            <!-- TABLE AREA -->
            <div
              v-if="hasTable"
              class="rounded-lg border border-border bg-[var(--glass-bg)] p-4 flex flex-col"
              :class="hasChart ? layoutConfig?.areas[1] : layoutConfig?.areas[0]"
            >
              <div class="flex items-center gap-2 mb-3">
                <Table2 :size="14" :stroke-width="1.5" class="text-amber-500" />
                <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Table</span>
              </div>

              <div class="flex-1 overflow-auto">
                <table class="w-full text-[10px]">
                  <thead>
                    <tr class="border-b border-border">
                      <th
                        v-for="h in tableData.headers.slice(0, 5)"
                        :key="h"
                        class="text-left py-1.5 px-2 font-mono text-muted-foreground font-medium"
                      >
                        {{ h }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, i) in tableData.rows.slice(0, 4)"
                      :key="i"
                      class="border-b border-border"
                    >
                      <td
                        v-for="(cell, j) in row.slice(0, 5)"
                        :key="j"
                        class="py-1.5 px-2 text-muted-foreground"
                      >
                        {{ cell }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- COMMENTARY / TEXT AREA -->
            <div
              v-if="hasCommentary"
              class="rounded-lg border border-border bg-[var(--glass-bg)] p-4 flex flex-col"
              :class="hasChart || hasTable ? layoutConfig?.areas[1] : layoutConfig?.areas[0]"
            >
              <div class="flex items-center gap-2 mb-3">
                <FileText :size="14" :stroke-width="1.5" class="text-amber-500" />
                <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Commentary</span>
              </div>
              <div class="flex-1">
                <p class="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                  {{ slide.commentary || (slide.components.find(c => c.type === 'text')?.type === 'text' ? (slide.components.find(c => c.type === 'text') as any)?.data?.content : '') || 'No commentary yet. Use the right panel to add data and generate commentary.' }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
