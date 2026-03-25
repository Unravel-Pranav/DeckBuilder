<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useDragDrop } from '@/composables/useDragDrop'
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
  BarChart3,
  PieChart,
  Table2,
  TrendingUp,
  GripVertical,
} from 'lucide-vue-next'

const iconMap: Record<string, any> = {
  BarChart3,
  PieChart,
  Table2,
  TrendingUp,
}

const slidesStore = useSlidesStore()
const { startDrag, endDrag } = useDragDrop()

const jsonInput = ref('')
const csvInput = ref('')
const validationErrors = ref<string[]>([])
const validationWarnings = ref<string[]>([])
const validationState = ref<'idle' | 'valid' | 'invalid' | 'schema-error'>('idle')
const activeTab = ref<'json' | 'csv'>('json')

const dataPatterns = [
  { id: 'revenue', icon: 'BarChart3', label: 'Quarterly Revenue (Chart)', data: { x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], y_axis: [120, 150, 180, 210], label: 'Revenue ($M)' } },
  { id: 'market-share', icon: 'PieChart', label: 'Market Share (Pie)', data: { labels: ['Company A', 'Company B', 'Others'], values: [45, 30, 25] } },
  { id: 'financials', icon: 'Table2', label: 'Financial Summary (Table)', data: { headers: ['Metric', 'Current', '% Change'], rows: [['Revenue', '$45.2M', '+12%'], ['EBITDA', '$18.1M', '+8%'], ['Net Margin', '40%', '+2pp']] } },
  { id: 'user-growth', icon: 'TrendingUp', label: 'Monthly Users (Line)', data: { x_axis: ['Jan', 'Feb', 'Mar', 'Apr'], y_axis: [5000, 6200, 7500, 9100], label: 'Active Users' } },
]

function parseCSV(csv: string) {
  const delimiter = csv.includes('\t') ? '\t' : ','
  const lines = csv.trim().split('\n')
  if (lines.length < 2) return null
  const headers = lines[0].split(delimiter).map((h) => h.trim())
  const rows = lines.slice(1).map((line) => line.split(delimiter).map((c) => c.trim()))
  return { headers, rows }
}

function convertCSVToChart(csv: any) {
  if (csv.headers.length >= 2) {
    const x_axis = csv.rows.map((r: any) => r[0])
    const y_values = csv.rows.map((r: any) => parseFloat(r[1]) || 0)
    return { x_axis, y_axis: y_values, label: csv.headers[1] || 'Value' }
  }
  return null
}

function processCSVInput() {
  const csv = parseCSV(csvInput.value)
  if (!csv) {
    validationErrors.value = ['Invalid CSV format (requires at least a header row and one data row)']
    return
  }

  if (csv.headers.length === 2) {
    const chartData = convertCSVToChart(csv)
    if (chartData) {
      jsonInput.value = JSON.stringify(chartData, null, 2)
      activeTab.value = 'json'
    }
  } else {
    jsonInput.value = JSON.stringify(csv, null, 2)
    activeTab.value = 'json'
  }
}

const activeRegionLabel = computed(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return ''
  const idx = slidesStore.activeRegionIndex
  const region = slide.regions[idx]
  if (!region) return ''
  const labels = ['Full Slide', 'Left', 'Right', 'Top', 'Bottom', 'Top Left', 'Top Right', 'Bottom Left', 'Bottom Right']
  const structureLabels: Record<string, string[]> = {
    'blank': ['Full Slide'],
    'two-col': ['Left', 'Right'],
    'two-row': ['Top', 'Bottom'],
    'grid-2x2': ['Top Left', 'Top Right', 'Bottom Left', 'Bottom Right'],
  }
  return (structureLabels[slide.structure] ?? labels)[idx] ?? `Region ${idx + 1}`
})

const dominantType = computed<'chart' | 'table' | 'text'>(() => {
  const region = slidesStore.activeRegion
  if (!region?.component) return 'chart'
  if (region.component.type === 'chart') return 'chart'
  if (region.component.type === 'table') return 'table'
  return 'chart'
})

const currentChartType = computed<ChartType>(() => {
  const region = slidesStore.activeRegion
  if (!region?.component || region.component.type !== 'chart') return 'bar'
  return region.component.data.type
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

  try {
    const parsed = JSON.parse(jsonInput.value) as Record<string, unknown>
    const detected = detectDataType(parsed)

    let component: SlideComponent | null = null

    if (detected.type === 'chart' || (detected.type === 'unknown' && dominantType.value === 'chart')) {
      const chartData = mapDataToChartComponent(parsed, detected.chartType ?? currentChartType.value)
      component = { id: crypto.randomUUID(), type: 'chart', data: chartData, config: {} }
    } else if (detected.type === 'table' || (detected.type === 'unknown' && dominantType.value === 'table')) {
      const tableData = mapDataToTableComponent(parsed)
      component = { id: crypto.randomUUID(), type: 'table', data: tableData, config: {} }
    }

    if (component) {
      slidesStore.setRegionComponent(
        slidesStore.activeSlideId!,
        slidesStore.activeRegionIndex,
        component,
      )
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

function onPatternDragStart(event: DragEvent, pattern: typeof dataPatterns[number]) {
  const d = pattern.data as Record<string, unknown>
  let component: Omit<SlideComponent, 'id'>

  if ('headers' in d && 'rows' in d) {
    component = {
      type: 'table',
      data: { headers: d.headers as string[], rows: d.rows as string[][] },
      config: {},
    }
  } else if ('labels' in d && 'values' in d) {
    component = {
      type: 'chart',
      data: {
        type: 'pie' as const,
        labels: d.labels as string[],
        datasets: [{ label: 'Share', data: d.values as number[] }],
      },
      config: {},
    }
  } else if ('x_axis' in d && 'y_axis' in d) {
    const chartType = pattern.icon === 'TrendingUp' ? 'line' as const : 'bar' as const
    component = {
      type: 'chart',
      data: {
        type: chartType,
        labels: d.x_axis as string[],
        datasets: [{ label: (d.label as string) ?? 'Value', data: d.y_axis as number[] }],
      },
      config: {},
    }
  } else {
    return
  }

  startDrag(event, {
    componentType: component.type,
    component,
    label: pattern.label,
  })
}
</script>

<template>
  <div class="space-y-4">
    <!-- Active region indicator -->
    <div class="flex items-center gap-2 p-2 rounded-lg bg-foreground/[0.03]">
      <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70">Region:</span>
      <Badge
        variant="secondary"
        class="text-[10px] rounded-full px-2 bg-amber-500/10 text-amber-500"
      >
        {{ activeRegionLabel }}
      </Badge>
      <Badge
        v-if="slidesStore.activeRegion?.component"
        variant="secondary"
        class="text-[10px] rounded-full px-2 capitalize bg-foreground/5 text-muted-foreground"
      >
        {{ dominantType }} {{ dominantType === 'chart' ? `(${currentChartType})` : '' }}
      </Badge>
      <span v-else class="text-[10px] text-muted-foreground/50">Empty</span>
    </div>

    <!-- Tab selector -->
    <div class="flex gap-1 p-1 rounded-lg bg-foreground/[0.03]">
      <button
        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all duration-200"
        :class="activeTab === 'json' ? 'bg-amber-500/10 text-amber-500' : 'text-muted-foreground hover:text-foreground/80'"
        @click="activeTab = 'json'"
      >
        <Code2 :size="12" :stroke-width="1.5" />
        JSON
      </button>
      <button
        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all duration-200"
        :class="activeTab === 'csv' ? 'bg-amber-500/10 text-amber-500' : 'text-muted-foreground hover:text-foreground/80'"
        @click="activeTab = 'csv'"
      >
        <Upload :size="12" :stroke-width="1.5" />
        CSV Upload
      </button>
    </div>

    <!-- JSON input -->
    <div v-if="activeTab === 'json'" class="space-y-4">
      <!-- Quick Patterns -->
      <div class="space-y-2">
        <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 px-1">Quick Templates</span>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="pattern in dataPatterns"
            :key="pattern.id"
            class="flex items-center gap-2 p-2 rounded-lg bg-foreground/[0.03] border border-border hover:bg-foreground/[0.06] hover:border-amber-500/30 transition-all text-left group cursor-grab active:cursor-grabbing"
            draggable="true"
            @click="jsonInput = JSON.stringify(pattern.data, null, 2)"
            @dragstart="onPatternDragStart($event, pattern)"
            @dragend="endDrag"
          >
            <component :is="iconMap[pattern.icon]" :size="12" :stroke-width="1.5" class="text-muted-foreground group-hover:text-amber-500" />
            <span class="text-[10px] text-muted-foreground group-hover:text-foreground/80 truncate flex-1">{{ pattern.label }}</span>
            <GripVertical :size="10" class="text-muted-foreground/30 group-hover:text-muted-foreground/60 flex-shrink-0 transition-colors" />
          </button>
        </div>
      </div>

      <!-- Schema prompt -->
      <div class="p-3 rounded-lg bg-foreground/[0.02] border border-border">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            {{ dominantType === 'table' ? 'Table' : 'Chart' }} Schema
          </span>
          <div class="flex gap-1">
            <button class="text-[10px] text-muted-foreground/70 hover:text-amber-500 transition-colors flex items-center gap-1" @click="copySchema">
              <Copy :size="10" :stroke-width="1.5" /> Copy
            </button>
            <button class="text-[10px] text-muted-foreground/70 hover:text-amber-500 transition-colors ml-2" @click="loadExample">
              Use Example
            </button>
          </div>
        </div>
        <pre class="text-[10px] font-mono text-muted-foreground/70 whitespace-pre-wrap max-h-24 overflow-y-auto">{{ schemaExample }}</pre>
      </div>

      <!-- Editor -->
      <div>
        <div class="flex items-center justify-between mb-1.5">
          <Label class="text-xs text-muted-foreground">Data JSON</Label>
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
          class="font-mono text-xs bg-[var(--glass-bg)] border-border rounded-lg resize-vertical max-h-[40vh] overflow-y-auto placeholder:text-muted-foreground/50"
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
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        @click="applyData"
      >
        Apply Data
      </Button>
    </div>

    <!-- CSV upload -->
    <div v-else class="space-y-4">
      <div class="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 mb-3">
        <p class="text-[10px] text-amber-500">
          <strong>Tip:</strong> Paste your spreadsheet data below. Two columns (Name, Value) will be mapped to a Chart. Three or more will be mapped to a Table.
        </p>
      </div>

      <Textarea
        v-model="csvInput"
        rows="8"
        class="font-mono text-xs bg-[var(--glass-bg)] border-border rounded-lg resize-vertical max-h-[40vh] overflow-y-auto placeholder:text-muted-foreground/50"
        placeholder="Month,Revenue&#10;Jan,100&#10;Feb,150&#10;Mar,200"
      />

      <Button
        :disabled="!csvInput.trim()"
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        @click="processCSVInput"
      >
        Transform to Data
      </Button>

      <div class="mt-4 pt-4 border-t border-border text-center">
        <Upload :size="24" :stroke-width="1.5" class="mx-auto mb-2 text-muted-foreground/50 opacity-50" />
        <p class="text-[10px] text-muted-foreground/70">File upload integration coming soon</p>
      </div>
    </div>
  </div>
</template>
