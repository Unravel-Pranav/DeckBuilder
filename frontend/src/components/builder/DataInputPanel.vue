<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { validateSchema, mapDataToChartComponent, mapDataToTableComponent, detectDataType } from '@/lib/schema'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import type { SlideComponent, ChartType } from '@/types'
import {
  Code2,
  Upload,
  Check,
  AlertCircle,
  AlertTriangle,
  Copy,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()

const jsonInput = ref('')
const validationErrors = ref<string[]>([])
const validationWarnings = ref<string[]>([])
const validationState = ref<'idle' | 'valid' | 'invalid' | 'schema-error'>('idle')
const activeTab = ref<'json' | 'csv'>('json')

const dominantType = computed<'chart' | 'table' | 'text'>(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return 'chart'
  if (slide.components.find((c) => c.type === 'chart')) return 'chart'
  if (slide.components.find((c) => c.type === 'table')) return 'table'
  return 'chart'
})

const currentChartType = computed<ChartType>(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return 'bar'
  const chart = slide.components.find((c) => c.type === 'chart')
  if (chart?.type === 'chart') return chart.data.type
  return 'bar'
})

const schemaExample = computed(() => {
  if (dominantType.value === 'table') {
    return JSON.stringify(
      { headers: ['Metric', 'Q1', 'Q2'], rows: [['Revenue', '$12M', '$18M'], ['Profit', '$5M', '$8M']] },
      null, 2,
    )
  }
  return JSON.stringify(
    { x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], y_axis: [100, 200, 150, 280], label: 'Revenue ($M)' },
    null, 2,
  )
})

watch(jsonInput, (val) => {
  validationErrors.value = []
  validationWarnings.value = []

  if (!val.trim()) {
    validationState.value = 'idle'
    return
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(val)
  } catch {
    validationState.value = 'invalid'
    validationErrors.value = ['Invalid JSON syntax']
    return
  }

  const detected = detectDataType(parsed)
  const targetType = detected.type === 'chart' || detected.type === 'table' ? detected.type : dominantType.value
  const result = validateSchema(parsed, targetType)

  validationErrors.value = result.errors
  validationWarnings.value = result.warnings
  validationState.value = result.valid ? 'valid' : 'schema-error'
})

function applyData() {
  if (validationState.value !== 'valid' || !slidesStore.activeSlideId) return
  const slide = slidesStore.activeSlide
  if (!slide) return

  try {
    const parsed = JSON.parse(jsonInput.value) as Record<string, unknown>
    const detected = detectDataType(parsed)

    if (detected.type === 'chart' || (detected.type === 'unknown' && dominantType.value === 'chart')) {
      const chartData = mapDataToChartComponent(parsed, detected.chartType ?? currentChartType.value)
      const newChart: SlideComponent = {
        id: crypto.randomUUID(),
        type: 'chart',
        data: chartData,
        config: {},
      }
      const existing = slide.components.filter((c) => c.type !== 'chart')
      slidesStore.updateSlideComponents(slidesStore.activeSlideId!, [...existing, newChart])
    } else if (detected.type === 'table' || (detected.type === 'unknown' && dominantType.value === 'table')) {
      const tableData = mapDataToTableComponent(parsed)
      const newTable: SlideComponent = {
        id: crypto.randomUUID(),
        type: 'table',
        data: tableData,
        config: {},
      }
      const existing = slide.components.filter((c) => c.type !== 'table')
      slidesStore.updateSlideComponents(slidesStore.activeSlideId!, [...existing, newTable])
    }
  } catch {
    validationState.value = 'invalid'
  }
}

function loadExample() {
  jsonInput.value = schemaExample.value
}

function copySchema() {
  navigator.clipboard.writeText(schemaExample.value)
}
</script>

<template>
  <div class="space-y-4">
    <!-- Active data type -->
    <div class="flex items-center gap-2 p-2 rounded-lg bg-white/[0.03]">
      <span class="text-[10px] font-mono uppercase tracking-wider text-zinc-600">Editing:</span>
      <Badge
        variant="secondary"
        class="text-[10px] rounded-full px-2 capitalize"
        :class="dominantType === 'chart' ? 'bg-amber-500/10 text-amber-500' : 'bg-white/5 text-zinc-400'"
      >
        {{ dominantType }} {{ dominantType === 'chart' ? `(${currentChartType})` : '' }}
      </Badge>
    </div>

    <!-- Tab selector -->
    <div class="flex gap-1 p-1 rounded-lg bg-white/[0.03]">
      <button
        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all duration-200"
        :class="activeTab === 'json' ? 'bg-amber-500/10 text-amber-500' : 'text-zinc-500 hover:text-zinc-300'"
        @click="activeTab = 'json'"
      >
        <Code2 :size="12" :stroke-width="1.5" />
        JSON
      </button>
      <button
        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all duration-200"
        :class="activeTab === 'csv' ? 'bg-amber-500/10 text-amber-500' : 'text-zinc-500 hover:text-zinc-300'"
        @click="activeTab = 'csv'"
      >
        <Upload :size="12" :stroke-width="1.5" />
        CSV Upload
      </button>
    </div>

    <!-- JSON input -->
    <div v-if="activeTab === 'json'" class="space-y-3">
      <!-- Schema prompt -->
      <div class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
            {{ dominantType === 'table' ? 'Table' : 'Chart' }} Schema
          </span>
          <div class="flex gap-1">
            <button class="text-[10px] text-zinc-600 hover:text-amber-500 transition-colors flex items-center gap-1" @click="copySchema">
              <Copy :size="10" :stroke-width="1.5" /> Copy
            </button>
            <button class="text-[10px] text-zinc-600 hover:text-amber-500 transition-colors ml-2" @click="loadExample">
              Use Example
            </button>
          </div>
        </div>
        <pre class="text-[10px] font-mono text-zinc-600 whitespace-pre-wrap">{{ schemaExample }}</pre>
      </div>

      <!-- Editor -->
      <div>
        <div class="flex items-center justify-between mb-1.5">
          <Label class="text-xs text-zinc-400">Data JSON</Label>
          <Badge
            v-if="validationState !== 'idle'"
            variant="secondary"
            class="text-[9px] rounded-full px-2 py-0.5"
            :class="
              validationState === 'valid'
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-red-500/15 text-red-400'
            "
          >
            <component :is="validationState === 'valid' ? Check : AlertCircle" :size="10" :stroke-width="2" class="mr-0.5" />
            {{ validationState === 'valid' ? 'Valid' : validationState === 'schema-error' ? 'Schema error' : 'Invalid JSON' }}
          </Badge>
        </div>
        <Textarea
          v-model="jsonInput"
          rows="8"
          class="font-mono text-xs bg-[rgba(10,10,15,0.6)] border-[rgba(255,255,255,0.06)] rounded-lg resize-none placeholder:text-zinc-700"
          placeholder='Paste your JSON data here...'
        />
      </div>

      <!-- Validation errors -->
      <div v-if="validationErrors.length > 0" class="space-y-1">
        <p v-for="err in validationErrors" :key="err" class="flex items-start gap-1.5 text-[10px] text-red-400">
          <AlertCircle :size="10" :stroke-width="2" class="mt-0.5 flex-shrink-0" />
          {{ err }}
        </p>
      </div>
      <div v-if="validationWarnings.length > 0" class="space-y-1">
        <p v-for="warn in validationWarnings" :key="warn" class="flex items-start gap-1.5 text-[10px] text-amber-500">
          <AlertTriangle :size="10" :stroke-width="2" class="mt-0.5 flex-shrink-0" />
          {{ warn }}
        </p>
      </div>

      <Button
        :disabled="validationState !== 'valid'"
        class="w-full bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        @click="applyData"
      >
        Apply Data
      </Button>
    </div>

    <!-- CSV upload -->
    <div v-else class="space-y-3">
      <div class="border border-dashed border-zinc-800 hover:border-amber-500/30 rounded-xl p-8 text-center transition-all duration-300 cursor-pointer">
        <Upload :size="24" :stroke-width="1.5" class="mx-auto mb-3 text-zinc-600" />
        <p class="text-sm text-zinc-500">Drop a CSV file here or click to browse</p>
        <p class="text-[11px] text-zinc-700 mt-1">Coming soon — use JSON input for now</p>
      </div>
    </div>
  </div>
</template>
