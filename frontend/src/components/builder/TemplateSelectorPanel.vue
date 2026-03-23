<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { chartTemplates, tableTemplates, textTemplates } from '@/lib/mockData'
import type { SlideTemplate, ChartData, TableData, SlideComponent } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  BarChart3,
  TrendingUp,
  PieChart,
  Table2,
  FileText,
  Check,
  Info,
  Copy,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()
const activeCategory = ref<'chart' | 'table' | 'text'>('chart')

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

function copySchema(hint: string) {
  navigator.clipboard.writeText(hint)
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <p class="text-xs text-zinc-400 mb-3">
        Pick a template to populate this slide's component. The schema hint shows the expected data format.
      </p>

      <!-- Category filter -->
      <div class="flex gap-1 p-1 rounded-lg bg-white/[0.03]">
        <button
          v-for="cat in [
            { id: 'chart' as const, label: 'Charts', icon: BarChart3 },
            { id: 'table' as const, label: 'Tables', icon: Table2 },
            { id: 'text' as const, label: 'Text', icon: FileText },
          ]"
          :key="cat.id"
          class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[11px] font-medium transition-all duration-200"
          :class="activeCategory === cat.id ? 'bg-amber-500/10 text-amber-500' : 'text-zinc-500 hover:text-zinc-300'"
          @click="activeCategory = cat.id"
        >
          <component :is="cat.icon" :size="12" :stroke-width="1.5" />
          {{ cat.label }}
        </button>
      </div>
    </div>

    <!-- Template cards -->
    <div class="space-y-2">
      <div
        v-for="tmpl in filteredTemplates"
        :key="tmpl.id"
        class="rounded-lg border p-3 transition-all duration-200 cursor-pointer"
        :class="
          appliedTemplateIds.has(tmpl.id)
            ? 'border-amber-500/30 bg-amber-500/10'
            : 'border-[rgba(255,255,255,0.06)] bg-white/[0.02] hover:border-[rgba(255,255,255,0.12)] hover:bg-white/[0.04]'
        "
        @click="applyTemplate(tmpl)"
      >
        <div class="flex items-start gap-2.5">
          <!-- Icon -->
          <div
            class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            :class="appliedTemplateIds.has(tmpl.id) ? 'bg-amber-500/20' : 'bg-white/5'"
          >
            <component
              :is="tmpl.chartType ? (chartTypeIcons[tmpl.chartType] ?? BarChart3) : (tmpl.category === 'table' ? Table2 : FileText)"
              :size="14"
              :stroke-width="1.5"
              :class="appliedTemplateIds.has(tmpl.id) ? 'text-amber-500' : 'text-zinc-500'"
            />
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5">
              <p
                class="text-xs font-medium truncate"
                :class="appliedTemplateIds.has(tmpl.id) ? 'text-amber-500' : 'text-zinc-300'"
              >
                {{ tmpl.name }}
              </p>
              <Check
                v-if="appliedTemplateIds.has(tmpl.id)"
                :size="12"
                :stroke-width="2.5"
                class="text-amber-500 flex-shrink-0"
              />
            </div>
            <p class="text-[10px] text-zinc-600 line-clamp-2 mt-0.5">{{ tmpl.description }}</p>
          </div>
        </div>

        <!-- Schema hint (collapsed by default, shown for applied templates) -->
        <div
          v-if="appliedTemplateIds.has(tmpl.id)"
          class="mt-2.5 p-2 rounded bg-[rgba(10,10,15,0.5)] border border-[rgba(255,255,255,0.04)]"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 flex items-center gap-1">
              <Info :size="8" :stroke-width="1.5" />
              Schema
            </span>
            <button
              class="text-[9px] text-zinc-600 hover:text-amber-500 transition-colors flex items-center gap-0.5"
              @click.stop="copySchema(tmpl.schemaHint)"
            >
              <Copy :size="8" :stroke-width="1.5" />
              Copy
            </button>
          </div>
          <pre class="text-[9px] font-mono text-zinc-500 whitespace-pre-wrap break-all">{{ tmpl.schemaHint }}</pre>
        </div>
      </div>
    </div>

    <!-- Helper text -->
    <p class="text-[10px] text-zinc-700 text-center pt-2">
      Click a template to apply it. Switch to the Data tab to customize values.
    </p>
  </div>
</template>
