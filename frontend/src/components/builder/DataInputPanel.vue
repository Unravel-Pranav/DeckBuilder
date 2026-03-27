<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useDragDrop } from '@/composables/useDragDrop'
import { validateDataForChartType, validateTableSchema, mapDataToChartComponent, mapDataToTableComponent } from '@/lib/schema'
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
  Circle,
  Layers,
} from 'lucide-vue-next'

const iconMap: Record<string, any> = {
  BarChart3,
  PieChart,
  Table2,
  TrendingUp,
  Circle,
  Layers,
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
  { id: 'revenue', chartType: 'bar' as ChartType, componentType: 'chart' as const, icon: 'BarChart3', label: 'Bar — Quarterly Revenue', data: { x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], y_axis: [120, 150, 180, 210], label: 'Revenue ($M)' } },
  { id: 'user-growth', chartType: 'line' as ChartType, componentType: 'chart' as const, icon: 'TrendingUp', label: 'Line — Monthly Users', data: { type: 'line', x_axis: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], y_axis: [5000, 6200, 7500, 8100, 8900, 9100], label: 'Active Users' } },
  { id: 'multi-line', chartType: 'line' as ChartType, componentType: 'chart' as const, icon: 'TrendingUp', label: 'Multi-Line — Rev vs Profit', data: { type: 'line', x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], series: [{ label: 'Revenue', data: [120, 150, 180, 210] }, { label: 'Profit', data: [40, 55, 70, 90] }] } },
  { id: 'market-share', chartType: 'pie' as ChartType, componentType: 'chart' as const, icon: 'PieChart', label: 'Pie — Market Share', data: { labels: ['Company A', 'Company B', 'Others'], values: [45, 30, 25] } },
  { id: 'doughnut', chartType: 'doughnut' as ChartType, componentType: 'chart' as const, icon: 'Circle', label: 'Doughnut — Segments', data: { type: 'doughnut', labels: ['Product', 'Services', 'Licensing', 'Other'], values: [40, 30, 20, 10] } },
  { id: 'area', chartType: 'area' as ChartType, componentType: 'chart' as const, icon: 'Layers', label: 'Area — Growth Trend', data: { type: 'area', x_axis: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], y_axis: [200, 350, 480, 520, 680, 790], label: 'Cumulative Users' } },
  { id: 'financials', chartType: undefined, componentType: 'table' as const, icon: 'Table2', label: 'Table — Financial Summary', data: { headers: ['Metric', 'Current', '% Change'], rows: [['Revenue', '$45.2M', '+12%'], ['EBITDA', '$18.1M', '+8%'], ['Net Margin', '40%', '+2pp']] } },
]

const filteredPatterns = computed(() => {
  if (dominantType.value === 'table') {
    return dataPatterns.filter((p) => p.componentType === 'table')
  }
  return dataPatterns.filter((p) => p.componentType === 'chart')
})

function parseCSV(csv: string) {
  const delimiter = csv.includes('\t') ? '\t' : ','
  const lines = csv.trim().split('\n')
  if (lines.length < 2) return null
  const headers = lines[0].split(delimiter).map((h) => h.trim())
  const rows = lines.slice(1).map((line) => line.split(delimiter).map((c) => c.trim()))
  return { headers, rows }
}

function csvColumnsAreNumeric(csv: { headers: string[]; rows: string[][] }, fromCol: number): boolean {
  return csv.rows.every((row) =>
    row.slice(fromCol).every((cell) => cell === '' || !isNaN(parseFloat(cell)))
  )
}

function csvToTable(csv: { headers: string[]; rows: string[][] }) {
  return { headers: csv.headers, rows: csv.rows }
}

function csvToSingleSeries(csv: { headers: string[]; rows: string[][] }, chartType?: string) {
  const labels = csv.rows.map((r) => r[0])
  const values = csv.rows.map((r) => parseFloat(r[1]) || 0)
  const result: Record<string, unknown> = { x_axis: labels, y_axis: values, label: csv.headers[1] || 'Value' }
  if (chartType) result.type = chartType
  return result
}

function csvToPieFormat(csv: { headers: string[]; rows: string[][] }, chartType: 'pie' | 'doughnut') {
  return {
    type: chartType,
    labels: csv.rows.map((r) => r[0]),
    values: csv.rows.map((r) => parseFloat(r[1]) || 0),
  }
}

function csvToMultiSeries(csv: { headers: string[]; rows: string[][] }, chartType: string) {
  const x_axis = csv.rows.map((r) => r[0])
  const series = csv.headers.slice(1).map((header, colIdx) => ({
    label: header,
    data: csv.rows.map((r) => parseFloat(r[colIdx + 1]) || 0),
  }))
  return { type: chartType, x_axis, series }
}

function processCSVInput() {
  const csv = parseCSV(csvInput.value)
  if (!csv) {
    validationErrors.value = ['Invalid CSV format (requires at least a header row and one data row)']
    return
  }

  if (csv.headers.length < 2) {
    validationErrors.value = ['CSV needs at least 2 columns']
    return
  }

  const target = dominantType.value === 'table' ? 'table' : currentChartType.value
  const numericValues = csvColumnsAreNumeric(csv, 1)
  const colCount = csv.headers.length
  const chartLabel = target.charAt(0).toUpperCase() + target.slice(1)
  let result: Record<string, unknown>

  if (target === 'table') {
    result = csvToTable(csv)
  } else if (target === 'pie' || target === 'doughnut') {
    if (!numericValues) {
      validationErrors.value = [`${chartLabel} chart requires numeric value columns`]
      return
    }
    result = csvToPieFormat(csv, target)
  } else if (target === 'scatter') {
    if (!numericValues) {
      validationErrors.value = ['Scatter chart requires numeric value columns']
      return
    }
    result = csvToSingleSeries(csv, 'scatter')
  } else {
    if (!numericValues) {
      validationErrors.value = [`${chartLabel} chart requires numeric value columns`]
      return
    }
    if (colCount === 2) {
      result = csvToSingleSeries(csv, target)
    } else {
      result = csvToMultiSeries(csv, target)
    }
  }

  jsonInput.value = JSON.stringify(result, null, 2)
  activeTab.value = 'json'
  validationErrors.value = []
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

const isMultiSeries = computed(() => {
  const region = slidesStore.activeRegion
  if (!region?.component || region.component.type !== 'chart') return false
  return region.component.data.datasets.length > 1
})

const schemaExample = computed(() => {
  if (dominantType.value === 'table') {
    return JSON.stringify(
      { headers: ['Metric', 'Q1', 'Q2'], rows: [['Revenue', '$12M', '$18M'], ['Profit', '$5M', '$8M']] },
      null, 2,
    )
  }
  if (isMultiSeries.value) {
    return JSON.stringify(
      { type: currentChartType.value, x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], series: [{ label: 'Revenue', data: [100, 200, 150, 280] }, { label: 'Profit', data: [40, 80, 60, 120] }] },
      null, 2,
    )
  }
  const ct = currentChartType.value
  if (ct === 'pie' || ct === 'doughnut') {
    return JSON.stringify(
      { type: ct, labels: ['Segment A', 'Segment B', 'Other'], values: [45, 35, 20] },
      null, 2,
    )
  }
  return JSON.stringify(
    { type: ct, x_axis: ['Q1', 'Q2', 'Q3', 'Q4'], y_axis: [100, 200, 150, 280], label: 'Revenue ($M)' },
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

  let result
  if (dominantType.value === 'table') {
    result = validateTableSchema(parsed)
  } else {
    result = validateDataForChartType(parsed, currentChartType.value)
  }

  if (typeof (parsed as Record<string, unknown>)?.type === 'string' && dominantType.value === 'chart') {
    const dataType = (parsed as Record<string, unknown>).type as string
    if (dataType !== currentChartType.value) {
      result.warnings.push(`Data specifies type "${dataType}" but will be applied as ${currentChartType.value} chart`)
    }
  }

  validationErrors.value = result.errors
  validationWarnings.value = result.warnings
  validationState.value = result.valid ? 'valid' : 'schema-error'
})

function applyData() {
  if (validationState.value !== 'valid' || !slidesStore.activeSlideId) return

  try {
    const parsed = JSON.parse(jsonInput.value) as Record<string, unknown>
    let component: SlideComponent | null = null

    if (dominantType.value === 'chart') {
      const chartData = mapDataToChartComponent(parsed, currentChartType.value)
      component = { id: crypto.randomUUID(), type: 'chart', data: chartData, config: {} }
    } else if (dominantType.value === 'table') {
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

  if (pattern.componentType === 'table') {
    component = {
      type: 'table',
      data: { headers: d.headers as string[], rows: d.rows as string[][] },
      config: {},
    }
  } else {
    const mapped = mapDataToChartComponent(d, pattern.chartType!)
    component = { type: 'chart', data: mapped, config: {} }
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
            v-for="pattern in filteredPatterns"
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
      <div class="p-2 rounded-lg bg-foreground/[0.03]">
        <span class="text-[10px] font-mono text-muted-foreground/70">
          CSV will be converted to
          <span class="text-amber-500 font-medium">
            {{ dominantType === 'table' ? 'Table' : currentChartType.charAt(0).toUpperCase() + currentChartType.slice(1) + ' Chart' }}
          </span>
          format based on your selected template.
        </span>
      </div>

      <Textarea
        v-model="csvInput"
        rows="8"
        class="font-mono text-xs bg-[var(--glass-bg)] border-border rounded-lg resize-vertical max-h-[40vh] overflow-y-auto placeholder:text-muted-foreground/50"
        placeholder="Month,Revenue,Profit&#10;Jan,100,40&#10;Feb,150,55&#10;Mar,200,70"
      />

      <Button
        :disabled="!csvInput.trim()"
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        @click="processCSVInput"
      >
        Transform to {{ dominantType === 'table' ? 'Table' : currentChartType.charAt(0).toUpperCase() + currentChartType.slice(1) + ' Chart' }}
      </Button>
    </div>
  </div>
</template>
