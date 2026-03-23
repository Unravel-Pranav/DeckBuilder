<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { chartTemplates, tableTemplates, textTemplates } from '@/lib/mockData'
import type { SlideTemplate, ChartData, TableData, SlideComponent } from '@/types'
import { Badge } from '@/components/ui/badge'
import {
  BarChart3,
  TrendingUp,
  PieChart,
  Table2,
  FileText,
  Check,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const activeCategory = ref<'chart' | 'table' | 'text'>('chart')

const categories = [
  { id: 'chart' as const, label: 'Charts', icon: BarChart3, count: chartTemplates.length },
  { id: 'table' as const, label: 'Tables', icon: Table2, count: tableTemplates.length },
  { id: 'text' as const, label: 'Text', icon: FileText, count: textTemplates.length },
]

const filteredTemplates = computed(() => {
  if (activeCategory.value === 'chart') return chartTemplates
  if (activeCategory.value === 'table') return tableTemplates
  return textTemplates
})

const appliedTemplateIds = computed(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return new Set<string>()
  return new Set(slide.components.map((c) => c.templateId).filter(Boolean))
})

const chartTypeIcons: Record<string, typeof BarChart3> = {
  bar: BarChart3,
  line: TrendingUp,
  pie: PieChart,
  doughnut: PieChart,
  area: TrendingUp,
  scatter: BarChart3,
}

function isChartData(data: ChartData | TableData | string): data is ChartData {
  return typeof data === 'object' && 'datasets' in data
}

function isTableData(data: ChartData | TableData | string): data is TableData {
  return typeof data === 'object' && 'headers' in data
}

function applyTemplate(template: SlideTemplate) {
  if (!slidesStore.activeSlideId || template.category === 'slide') return

  let component: SlideComponent

  if (template.category === 'chart' && isChartData(template.previewData)) {
    component = { id: crypto.randomUUID(), type: 'chart', templateId: template.id, data: template.previewData, config: {} }
  } else if (template.category === 'table' && isTableData(template.previewData)) {
    component = { id: crypto.randomUUID(), type: 'table', templateId: template.id, data: template.previewData, config: {} }
  } else if (template.category === 'text' && typeof template.previewData === 'string') {
    component = { id: crypto.randomUUID(), type: 'text', templateId: template.id, data: { content: template.previewData }, config: { format: 'paragraph' } }
  } else {
    return
  }

  const slide = slidesStore.activeSlide
  if (!slide) return

  const existingIndex = slide.components.findIndex((c) => c.type === template.category)
  if (existingIndex >= 0) {
    const updated = [...slide.components]
    updated[existingIndex] = component
    slidesStore.updateSlideComponents(slidesStore.activeSlideId, updated)
  } else {
    slidesStore.updateSlideComponents(slidesStore.activeSlideId, [
      ...slide.components,
      component,
    ])
  }
}

function getBarHeights(data: number[]): number[] {
  const max = Math.max(...data)
  return data.map((v) => (max > 0 ? (v / max) * 100 : 0))
}
</script>

<template>
  <div class="border-b border-[rgba(255,255,255,0.06)]">
    <!-- Category tabs -->
    <div class="flex items-center gap-1 px-4 pt-2 pb-0">
      <span class="text-[10px] font-mono uppercase tracking-wider text-zinc-600 mr-2 flex-shrink-0">Template</span>
      <button
        v-for="cat in categories"
        :key="cat.id"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-[11px] font-medium transition-all duration-200 border border-b-0"
        :class="
          activeCategory === cat.id
            ? 'bg-[rgba(26,26,36,0.6)] text-amber-500 border-[rgba(255,255,255,0.08)]'
            : 'text-zinc-500 hover:text-zinc-300 border-transparent'
        "
        @click="activeCategory = cat.id"
      >
        <component :is="cat.icon" :size="12" :stroke-width="1.5" />
        {{ cat.label }}
        <span class="text-[9px] text-zinc-600 font-mono">{{ cat.count }}</span>
      </button>
    </div>

    <!-- Template grid -->
    <div class="px-4 py-3 overflow-x-auto">
      <div class="flex gap-3" style="min-width: max-content">
        <button
          v-for="tmpl in filteredTemplates"
          :key="tmpl.id"
          class="group relative flex-shrink-0 w-44 rounded-lg border p-3 text-left transition-all duration-200"
          :class="
            appliedTemplateIds.has(tmpl.id)
              ? 'border-amber-500/30 bg-amber-500/10 shadow-[0_0_15px_rgba(245,158,11,0.1)]'
              : 'border-[rgba(255,255,255,0.06)] bg-[rgba(26,26,36,0.3)] hover:border-[rgba(255,255,255,0.12)] hover:bg-[rgba(26,26,36,0.5)]'
          "
          @click="applyTemplate(tmpl)"
        >
          <!-- Applied checkmark -->
          <div
            v-if="appliedTemplateIds.has(tmpl.id)"
            class="absolute top-2 right-2 w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center"
          >
            <Check :size="10" :stroke-width="3" class="text-[#0A0A0F]" />
          </div>

          <!-- Mini preview -->
          <div class="h-16 mb-2 rounded bg-[rgba(10,10,15,0.5)] border border-[rgba(255,255,255,0.04)] flex items-end p-1.5 overflow-hidden">
            <!-- Chart mini preview -->
            <template v-if="tmpl.category === 'chart' && isChartData(tmpl.previewData)">
              <template v-if="tmpl.chartType === 'bar'">
                <div class="flex items-end gap-0.5 w-full h-full">
                  <div
                    v-for="(val, i) in getBarHeights(tmpl.previewData.datasets[0].data)"
                    :key="i"
                    class="flex-1 rounded-t-sm transition-all"
                    :style="{ height: `${val}%`, backgroundColor: appliedTemplateIds.has(tmpl.id) ? 'rgba(245,158,11,0.7)' : 'rgba(245,158,11,0.35)', minHeight: '2px' }"
                  />
                </div>
              </template>
              <template v-else-if="tmpl.chartType === 'line'">
                <svg class="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
                  <polyline
                    v-for="(ds, dsi) in tmpl.previewData.datasets"
                    :key="dsi"
                    fill="none"
                    :stroke="dsi === 0 ? '#F59E0B' : '#71717A'"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    :points="ds.data.map((v, i) => `${(i / (ds.data.length - 1)) * 100},${40 - (v / Math.max(...ds.data)) * 36}`).join(' ')"
                    :opacity="appliedTemplateIds.has(tmpl.id) ? 0.9 : 0.5"
                  />
                </svg>
              </template>
              <template v-else-if="tmpl.chartType === 'pie' || tmpl.chartType === 'doughnut'">
                <div class="w-full h-full flex items-center justify-center">
                  <div
                    class="w-10 h-10 rounded-full"
                    :style="{
                      background: `conic-gradient(#F59E0B 0% ${tmpl.previewData.datasets[0].data[0]}%, #FBBF24 ${tmpl.previewData.datasets[0].data[0]}% ${tmpl.previewData.datasets[0].data[0] + (tmpl.previewData.datasets[0].data[1] ?? 0)}%, #D97706 ${tmpl.previewData.datasets[0].data[0] + (tmpl.previewData.datasets[0].data[1] ?? 0)}% 100%)`,
                      opacity: appliedTemplateIds.has(tmpl.id) ? 0.9 : 0.5,
                    }"
                  >
                    <div
                      v-if="tmpl.chartType === 'doughnut'"
                      class="w-5 h-5 rounded-full bg-[rgba(10,10,15,0.9)] mt-2.5 ml-2.5"
                    />
                  </div>
                </div>
              </template>
              <template v-else>
                <svg class="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
                  <polygon
                    :points="`0,40 ${tmpl.previewData.datasets[0].data.map((v, i) => `${(i / (tmpl.previewData as ChartData).datasets[0].data.length * 1) * 100},${40 - (v / Math.max(...(tmpl.previewData as ChartData).datasets[0].data)) * 36}`).join(' ')} 100,40`"
                    fill="rgba(245,158,11,0.15)"
                    stroke="#F59E0B"
                    stroke-width="1.5"
                    :opacity="appliedTemplateIds.has(tmpl.id) ? 0.9 : 0.5"
                  />
                </svg>
              </template>
            </template>

            <!-- Table mini preview -->
            <template v-else-if="tmpl.category === 'table' && isTableData(tmpl.previewData)">
              <div class="w-full space-y-1">
                <div class="flex gap-1">
                  <div
                    v-for="(h, i) in (tmpl.previewData as TableData).headers.slice(0, 3)"
                    :key="i"
                    class="flex-1 h-1.5 rounded-sm"
                    :style="{ backgroundColor: appliedTemplateIds.has(tmpl.id) ? 'rgba(245,158,11,0.5)' : 'rgba(245,158,11,0.2)' }"
                  />
                </div>
                <div v-for="r in 3" :key="r" class="flex gap-1">
                  <div
                    v-for="c in Math.min((tmpl.previewData as TableData).headers.length, 3)"
                    :key="c"
                    class="flex-1 h-1 rounded-sm bg-zinc-800"
                  />
                </div>
              </div>
            </template>

            <!-- Text mini preview -->
            <template v-else>
              <div class="w-full space-y-1 py-1">
                <div class="h-1 w-full rounded-sm" :style="{ backgroundColor: appliedTemplateIds.has(tmpl.id) ? 'rgba(245,158,11,0.3)' : 'rgba(255,255,255,0.08)' }" />
                <div class="h-1 w-3/4 rounded-sm bg-zinc-800" />
                <div class="h-1 w-5/6 rounded-sm bg-zinc-800" />
                <div class="h-1 w-2/3 rounded-sm bg-zinc-800" />
              </div>
            </template>
          </div>

          <!-- Info -->
          <p class="text-[11px] font-medium truncate" :class="appliedTemplateIds.has(tmpl.id) ? 'text-amber-500' : 'text-zinc-300'">
            {{ tmpl.name }}
          </p>
          <p class="text-[9px] text-zinc-600 line-clamp-1 mt-0.5">{{ tmpl.description }}</p>

          <!-- Chart type badge -->
          <Badge
            v-if="tmpl.chartType"
            variant="secondary"
            class="mt-1.5 text-[8px] bg-white/5 text-zinc-500 rounded-full px-1.5 py-0 inline-flex items-center gap-0.5 border-none"
          >
            <component :is="chartTypeIcons[tmpl.chartType] ?? BarChart3" :size="8" :stroke-width="1.5" />
            {{ tmpl.chartType }}
          </Badge>
        </button>
      </div>
    </div>
  </div>
</template>
