<script setup lang="ts">
import { computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import EmptyState from '@/components/shared/EmptyState.vue'
import { mockChartData, mockTableData } from '@/lib/mockData'
import { LAYOUT_BY_ID } from '@/lib/layoutDefinitions'
import type { ChartData, TableData } from '@/types'
import {
  BarChart3,
  Table2,
  FileText,
  PenTool,
  TrendingUp,
  SeparatorHorizontal,
  Heading1,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()
const slide = computed(() => slidesStore.activeSlide)

const layoutDef = computed(() => {
  const id = slide.value?.layout ?? 'chart-commentary'
  return LAYOUT_BY_ID[id] ?? LAYOUT_BY_ID['chart-commentary']
})

const panels     = computed(() => layoutDef.value?.panels ?? {})
const gridClass  = computed(() => layoutDef.value?.gridClass ?? 'grid-cols-1')
const panelSpans = computed(() => layoutDef.value?.panelSpans ?? ['col-span-1'])

const hasChart      = computed(() => !!panels.value.chart)
const hasTable      = computed(() => !!panels.value.table)
const hasCommentary = computed(() => !!panels.value.commentary)
const hasKpi        = computed(() => !!panels.value.kpi)
const hasDivider    = computed(() => !!panels.value.divider)
const hasTitle      = computed(() => !!panels.value.title)

const isGridLayout = computed(() =>
  layoutDef.value?.category === 'grid' || layoutDef.value?.id === 'quadrant-2c',
)
const hasTwoTables = computed(() => layoutDef.value?.id === 'quadrant-2c2t')

const chartComponent = computed(() => slide.value?.components.find((c) => c.type === 'chart') ?? null)
const tableComponent = computed(() => slide.value?.components.find((c) => c.type === 'table') ?? null)

const chartData = computed<ChartData>(() => {
  const c = chartComponent.value
  return c?.type === 'chart' ? c.data : mockChartData.revenue
})
const tableData = computed<TableData>(() => {
  const c = tableComponent.value
  return c?.type === 'table' ? c.data : mockTableData.financials
})
const chartType = computed(() => chartData.value.type ?? 'bar')

const commentaryText = computed(() => {
  if (slide.value?.commentary) return slide.value.commentary
  const textComp = slide.value?.components.find((c) => c.type === 'text')
  if (textComp?.type === 'text') return (textComp as any).data?.content ?? ''
  return ''
})

const mockKpis = [
  { label: 'Total Value',    value: '$4.2B',   change: '+12%',  up: true  },
  { label: 'Vacancy Rate',   value: '5.3%',    change: '-0.4%', up: false },
  { label: 'Avg Rent / SF',  value: '$38.50',  change: '+8%',   up: true  },
  { label: 'Net Absorption', value: '2.1M SF', change: '+15%',  up: true  },
]

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
          class="w-full max-w-4xl mx-auto aspect-[16/9] rounded-xl border border-border p-6 flex flex-col"
          :style="{ background: 'var(--preview-surface-deep)' }"
        >

          <!-- ── SECTION DIVIDER ───────────────────────────────────── -->
          <template v-if="hasDivider">
            <div class="flex-1 flex flex-col items-center justify-center gap-4">
              <SeparatorHorizontal :size="32" :stroke-width="1" class="text-amber-500/40" />
              <h2 class="font-display font-bold text-2xl tracking-tight text-foreground">
                {{ slide.title || 'Section Title' }}
              </h2>
              <div class="w-16 h-px bg-amber-500/40" />
              <p class="text-xs text-muted-foreground font-mono uppercase tracking-widest">
                {{ commentaryText || 'Section sub-label' }}
              </p>
            </div>
          </template>

          <!-- ── KPI HIGHLIGHT ─────────────────────────────────────── -->
          <template v-else-if="hasKpi">
            <div class="flex items-center gap-2 mb-4">
              <TrendingUp :size="14" :stroke-width="1.5" class="text-amber-500" />
              <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">KPI Highlights</span>
            </div>
            <div class="flex-1 grid grid-cols-2 gap-3">
              <div
                v-for="kpi in mockKpis"
                :key="kpi.label"
                class="rounded-lg border border-border p-4 flex flex-col justify-between"
                :style="{ background: 'var(--glass-bg)' }"
              >
                <span class="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{{ kpi.label }}</span>
                <div>
                  <div class="text-2xl font-display font-bold text-foreground mt-1">{{ kpi.value }}</div>
                  <div
                    class="text-[10px] font-mono mt-0.5"
                    :class="kpi.up ? 'text-emerald-500' : 'text-red-500'"
                  >
                    {{ kpi.change }} vs prior period
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- ── TITLE LAYOUTS ─────────────────────────────────────── -->
          <template v-else-if="hasTitle">
            <div class="flex items-center gap-2 mb-3">
              <Heading1 :size="14" :stroke-width="1.5" class="text-amber-500" />
              <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Title Slide</span>
            </div>
            <div class="mb-4 pb-4 border-b border-border">
              <h2 class="font-display font-bold text-xl tracking-tight text-foreground">
                {{ slide.title || 'Slide Title' }}
              </h2>
            </div>
            <div class="flex-1 grid gap-4" :class="gridClass">
              <div
                v-if="hasChart"
                class="rounded-lg border border-border p-3 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="panelSpans[0]"
              >
                <div class="flex items-center gap-1.5 mb-2">
                  <BarChart3 :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">Chart</span>
                </div>
                <div class="flex-1 flex items-end gap-1 px-1">
                  <div
                    v-for="(val, i) in getBarHeights(chartData.datasets[0].data)"
                    :key="i"
                    class="flex-1 rounded-t"
                    :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.5)', minHeight: '3px' }"
                  />
                </div>
              </div>
              <div
                v-if="hasCommentary"
                class="rounded-lg border border-border p-3 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="hasChart ? panelSpans[1] : panelSpans[0]"
              >
                <div class="flex items-center gap-1.5 mb-2">
                  <FileText :size="12" :stroke-width="1.5" class="text-amber-500/70" />
                  <span class="text-[9px] font-mono text-muted-foreground/60">Body</span>
                </div>
                <p class="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                  {{ commentaryText || 'Add body text or commentary in the right panel.' }}
                </p>
              </div>
            </div>
          </template>

          <!-- ── STANDARD CHART / TABLE / COMMENTARY ───────────────── -->
          <template v-else>
            <div class="flex-1 grid gap-4" :class="gridClass">

              <!-- CHART PANEL 1 -->
              <div
                v-if="hasChart"
                class="rounded-lg border border-border p-4 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="panelSpans[0]"
              >
                <div class="flex items-center gap-2 mb-3">
                  <BarChart3 :size="14" :stroke-width="1.5" class="text-amber-500" />
                  <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    {{ isGridLayout ? 'Chart 1' : chartType + ' chart' }}
                  </span>
                </div>

                <!-- Bar -->
                <template v-if="chartType === 'bar'">
                  <div class="flex-1 flex items-end gap-2 px-2">
                    <div
                      v-for="(val, i) in getBarHeights(chartData.datasets[0].data)"
                      :key="i"
                      class="flex-1 rounded-t transition-all duration-500"
                      :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.6)', minHeight: '4px' }"
                    />
                  </div>
                  <div class="flex justify-between mt-2 px-1">
                    <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/60">{{ label }}</span>
                  </div>
                </template>

                <!-- Line / Area -->
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
                    <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/60">{{ label }}</span>
                  </div>
                </template>

                <!-- Pie / Doughnut -->
                <template v-else-if="chartType === 'pie' || chartType === 'doughnut'">
                  <div class="flex-1 flex items-center justify-center">
                    <div
                      class="w-24 h-24 rounded-full relative"
                      :style="{
                        background: (() => {
                          const data = chartData.datasets[0].data
                          const total = data.reduce((a, b) => a + b, 0) || 1
                          const colors = chartData.datasets[0].backgroundColor ?? ['#F59E0B','#FBBF24','#D97706','#92400E']
                          let pct = 0
                          return 'conic-gradient(' + data.map((v, i) => {
                            const start = pct; pct += (v / total) * 100
                            return `${colors[i % colors.length]} ${start}% ${pct}%`
                          }).join(', ') + ')'
                        })()
                      }"
                    >
                      <div
                        v-if="chartType === 'doughnut'"
                        class="absolute inset-0 m-auto w-12 h-12 rounded-full"
                        :style="{ background: 'var(--surface-elevated)' }"
                      />
                    </div>
                  </div>
                  <div class="flex flex-wrap justify-center gap-x-3 gap-y-1 mt-2">
                    <span v-for="(label, i) in chartData.labels" :key="i" class="text-[9px] font-mono text-muted-foreground/60 flex items-center gap-1">
                      <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: (chartData.datasets[0].backgroundColor ?? ['#F59E0B','#FBBF24','#D97706'])[i % 3] }" />
                      {{ label }}
                    </span>
                  </div>
                </template>

                <!-- Fallback bar -->
                <template v-else>
                  <div class="flex-1 flex items-end gap-2 px-2">
                    <div
                      v-for="(val, i) in getBarHeights(chartData.datasets[0].data)"
                      :key="i"
                      class="flex-1 rounded-t"
                      :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.4)', minHeight: '4px' }"
                    />
                  </div>
                </template>
              </div>

              <!-- CHART PANEL 2 (grid layouts) -->
              <div
                v-if="hasChart && isGridLayout"
                class="rounded-lg border border-border p-4 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="panelSpans[1] ?? 'col-span-1'"
              >
                <div class="flex items-center gap-2 mb-3">
                  <BarChart3 :size="14" :stroke-width="1.5" class="text-amber-500" />
                  <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Chart 2</span>
                </div>
                <div class="flex-1 flex items-end gap-2 px-2">
                  <div
                    v-for="(val, i) in getBarHeights([...chartData.datasets[0].data].reverse())"
                    :key="i"
                    class="flex-1 rounded-t"
                    :style="{ height: `${val}%`, backgroundColor: 'rgba(245,158,11,0.35)', minHeight: '4px' }"
                  />
                </div>
              </div>

              <!-- TABLE PANEL 1 -->
              <div
                v-if="hasTable"
                class="rounded-lg border border-border p-4 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="hasChart && !isGridLayout ? panelSpans[1] : (isGridLayout ? (panelSpans[2] ?? 'col-span-1') : panelSpans[0])"
              >
                <div class="flex items-center gap-2 mb-3">
                  <Table2 :size="14" :stroke-width="1.5" class="text-amber-500" />
                  <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    {{ hasTwoTables ? 'Table 1' : 'Table' }}
                  </span>
                </div>
                <div class="flex-1 overflow-auto">
                  <table class="w-full text-[10px]">
                    <thead>
                      <tr class="border-b border-border">
                        <th
                          v-for="h in tableData.headers.slice(0, 5)"
                          :key="h"
                          class="text-left py-1.5 px-2 font-mono text-muted-foreground/70 font-medium"
                        >{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, ri) in tableData.rows.slice(0, 4)"
                        :key="ri"
                        class="border-b border-border/50"
                      >
                        <td
                          v-for="(cell, ci) in row.slice(0, 5)"
                          :key="ci"
                          class="py-1.5 px-2 text-foreground/70"
                        >{{ cell }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- TABLE PANEL 2 (quadrant-2c2t) -->
              <div
                v-if="hasTwoTables"
                class="rounded-lg border border-border p-4 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="panelSpans[3] ?? 'col-span-1'"
              >
                <div class="flex items-center gap-2 mb-3">
                  <Table2 :size="14" :stroke-width="1.5" class="text-amber-500" />
                  <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Table 2</span>
                </div>
                <div class="flex-1 overflow-auto">
                  <table class="w-full text-[10px]">
                    <thead>
                      <tr class="border-b border-border">
                        <th
                          v-for="h in tableData.headers.slice(0, 5)"
                          :key="h"
                          class="text-left py-1.5 px-2 font-mono text-muted-foreground/70 font-medium"
                        >{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, ri) in tableData.rows.slice(0, 4)"
                        :key="ri"
                        class="border-b border-border/50"
                      >
                        <td
                          v-for="(cell, ci) in row.slice(0, 5)"
                          :key="ci"
                          class="py-1.5 px-2 text-foreground/70"
                        >{{ cell }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- COMMENTARY PANEL -->
              <div
                v-if="hasCommentary"
                class="rounded-lg border border-border p-4 flex flex-col"
                :style="{ background: 'var(--glass-bg)' }"
                :class="
                  isGridLayout
                    ? (panelSpans[3] ?? 'col-span-1')
                    : (hasChart || hasTable ? panelSpans[1] : panelSpans[0])
                "
              >
                <div class="flex items-center gap-2 mb-3">
                  <FileText :size="14" :stroke-width="1.5" class="text-amber-500" />
                  <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Commentary</span>
                </div>
                <div class="flex-1">
                  <p class="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                    {{ commentaryText || 'No commentary yet. Use the right panel to add data and generate commentary.' }}
                  </p>
                </div>
              </div>

            </div>
          </template>

        </div>
      </div>
    </template>
  </div>
</template>
