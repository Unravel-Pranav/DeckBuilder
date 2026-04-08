<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { usePresentationStore } from '@/stores/presentation'
import { useAiStore } from '@/stores/ai'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sparkles,
  RefreshCw,
  PenLine,
  MessageSquare,
  Loader2,
  Database,
  BarChart3,
  Table2,
} from 'lucide-vue-next'
import type { ChartComponent, TableComponent } from '@/types'
import { REGION_LABELS } from '@/types'

const slidesStore = useSlidesStore()
const presentationStore = usePresentationStore()
const aiStore = useAiStore()

const commentaryMode = ref<'ai' | 'prompt' | 'manual'>('ai')
const promptText = ref('')
const manualText = ref('')
const selectedElementId = ref<string | null>(null)

const activeRegionId = computed(() => slidesStore.activeRegion?.id ?? null)

const activeRegionLabel = computed(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return ''
  const labels = REGION_LABELS[slide.structure] ?? []
  return labels[slidesStore.activeRegionIndex] ?? `Region ${slidesStore.activeRegionIndex + 1}`
})

const currentCommentary = computed(() => {
  const slide = slidesStore.activeSlide
  const regionId = activeRegionId.value
  if (!slide || !regionId) return ''
  const rc = slide.regionCommentary?.[regionId]
  if (rc) return rc.text
  return slide.commentary ?? ''
})

const currentCommentarySource = computed(() => {
  const slide = slidesStore.activeSlide
  const regionId = activeRegionId.value
  if (!slide || !regionId) return 'manual'
  const rc = slide.regionCommentary?.[regionId]
  if (rc) return rc.source
  return slide.commentarySource ?? 'manual'
})

const sectionName = computed(() => slidesStore.activeSection?.name ?? '')

interface DataElement {
  id: string
  label: string
  subtitle: string
  type: 'chart' | 'table'
  component: ChartComponent | TableComponent
}

const dataElements = computed<DataElement[]>(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return []

  const elements: DataElement[] = []
  let chartIdx = 0
  let tableIdx = 0

  for (const region of slide.regions) {
    const comp = region.component
    if (!comp) continue

    if (comp.type === 'chart') {
      chartIdx++
      const chartComp = comp as ChartComponent
      const typeName = chartComp.data.type
        ? `${chartComp.data.type.charAt(0).toUpperCase()}${chartComp.data.type.slice(1)}`
        : 'Chart'
      const datasetNames = chartComp.data.datasets.map((ds) => ds.label).filter(Boolean)
      const subtitle = datasetNames.length > 0
        ? datasetNames.join(', ')
        : chartComp.data.labels.slice(0, 3).join(', ') + (chartComp.data.labels.length > 3 ? '…' : '')
      elements.push({
        id: comp.id,
        label: `${typeName} Chart ${chartIdx}`,
        subtitle,
        type: 'chart',
        component: chartComp,
      })
    } else if (comp.type === 'table') {
      tableIdx++
      const tableComp = comp as TableComponent
      const subtitle = tableComp.data.headers.slice(0, 3).join(', ') + (tableComp.data.headers.length > 3 ? '…' : '')
      elements.push({
        id: comp.id,
        label: `Table ${tableIdx}`,
        subtitle: `${tableComp.data.rows.length} rows · ${subtitle}`,
        type: 'table',
        component: tableComp,
      })
    }
  }
  return elements
})

const selectedElement = computed(() =>
  dataElements.value.find((e) => e.id === selectedElementId.value) ?? null,
)

function resetPanelState() {
  promptText.value = ''

  const slide = slidesStore.activeSlide
  const regionId = activeRegionId.value
  if (slide && regionId) {
    const rc = slide.regionCommentary?.[regionId]
    if (rc?.boundElementId && dataElements.value.find((e) => e.id === rc.boundElementId)) {
      selectedElementId.value = rc.boundElementId
    } else {
      selectedElementId.value = dataElements.value[0]?.id ?? null
    }
    manualText.value = rc?.text ?? ''
  } else {
    selectedElementId.value = dataElements.value[0]?.id ?? null
    manualText.value = ''
  }
}

watch(
  [() => slidesStore.activeSlideId, () => slidesStore.activeRegionIndex],
  () => resetPanelState(),
  { immediate: true },
)

watch(dataElements, (els) => {
  if (selectedElementId.value && !els.find((e) => e.id === selectedElementId.value)) {
    selectedElementId.value = els[0]?.id ?? null
  }
})

watch(commentaryMode, (mode) => {
  if (mode === 'manual') {
    manualText.value = currentCommentary.value
  }
})

const dominantContext = computed(() => {
  if (selectedElement.value) return selectedElement.value.type
  const slide = slidesStore.activeSlide
  if (!slide) return 'default'
  const components = slide.regions.map((r) => r.component).filter(Boolean)
  if (components.find((c) => c!.type === 'chart')) return 'chart'
  if (components.find((c) => c!.type === 'table')) return 'table'
  if (components.find((c) => c!.type === 'text')) return 'text'
  return 'default'
})

function extractElementData(el: DataElement | null): Record<string, unknown> | undefined {
  if (!el) return undefined
  if (el.type === 'chart') {
    const d = (el.component as ChartComponent).data
    return { type: d.type, labels: d.labels, datasets: d.datasets.map((ds) => ({ label: ds.label, data: ds.data })) }
  }
  if (el.type === 'table') {
    const d = (el.component as TableComponent).data
    return { headers: d.headers, rows: d.rows }
  }
  return undefined
}

const fullContext = computed(() => ({
  componentType: dominantContext.value as 'chart' | 'table' | 'text' | 'default',
  sectionName: sectionName.value,
  intentType: presentationStore.intent.type,
  intentTone: presentationStore.intent.tone,
  slideTitle: slidesStore.activeSlide?.title,
  slideId: slidesStore.activeSlideId ?? undefined,
  elementId: selectedElement.value?.id,
  elementType: selectedElement.value?.type,
  elementData: extractElementData(selectedElement.value),
  presentationName: presentationStore.presentationName,
}))

async function generateFromData() {
  if (!slidesStore.activeSlideId) return
  const text = await aiStore.generateCommentary(fullContext.value)
  slidesStore.updateSlideCommentary(
    slidesStore.activeSlideId, text, 'ai',
    activeRegionId.value ?? undefined,
    selectedElement.value?.id,
  )
}

async function generateFromPrompt() {
  if (!slidesStore.activeSlideId || !promptText.value.trim()) return
  const text = await aiStore.generateCommentary(fullContext.value, promptText.value)
  slidesStore.updateSlideCommentary(
    slidesStore.activeSlideId, text, 'prompt',
    activeRegionId.value ?? undefined,
    selectedElement.value?.id,
  )
}

function applyManual() {
  if (!slidesStore.activeSlideId) return
  slidesStore.updateSlideCommentary(
    slidesStore.activeSlideId, manualText.value, 'manual',
    activeRegionId.value ?? undefined,
  )
}
</script>

<template>
  <div class="space-y-4">
    <!-- Mode selector -->
    <div class="flex gap-1 p-1 rounded-lg bg-foreground/[0.03]">
      <button
        v-for="mode in [
          { id: 'ai' as const, label: 'AI Generate', icon: Sparkles },
          { id: 'prompt' as const, label: 'From Prompt', icon: MessageSquare },
          { id: 'manual' as const, label: 'Manual', icon: PenLine },
        ]"
        :key="mode.id"
        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[11px] font-medium transition-all duration-200"
        :class="commentaryMode === mode.id ? 'bg-amber-500/10 text-amber-500' : 'text-muted-foreground hover:text-foreground/80'"
        @click="commentaryMode = mode.id"
      >
        <component :is="mode.icon" :size="12" :stroke-width="1.5" />
        {{ mode.label }}
      </button>
    </div>

    <!-- Active region indicator -->
    <div class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-amber-500/5 border border-amber-500/15">
      <div class="w-1.5 h-1.5 rounded-full bg-amber-500" />
      <span class="text-[10px] font-medium text-amber-500/90">Editing: {{ activeRegionLabel }}</span>
    </div>

    <!-- Context indicator -->
    <div class="flex items-center gap-2 flex-wrap text-[9px] font-mono text-muted-foreground/70">
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ dominantContext }}</span>
      <span v-if="sectionName" class="px-1.5 py-0.5 rounded bg-foreground/5">{{ sectionName }}</span>
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ presentationStore.intent.type }}</span>
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ presentationStore.intent.tone }}</span>
    </div>

    <!-- Data Source Selector -->
    <div v-if="dataElements.length > 0" class="space-y-2">
      <div class="flex items-center gap-2">
        <Database :size="12" class="text-muted-foreground" />
        <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70">Data Source</span>
      </div>
      <Select v-model="selectedElementId">
        <SelectTrigger class="h-auto min-h-9 py-1.5 bg-[var(--glass-bg)] border-border rounded-lg text-xs">
          <div v-if="selectedElement" class="flex items-center gap-2 text-left min-w-0">
            <BarChart3 v-if="selectedElement.type === 'chart'" :size="12" class="text-amber-500 flex-shrink-0" />
            <Table2 v-else :size="12" class="text-blue-400 flex-shrink-0" />
            <div class="min-w-0">
              <div class="text-xs font-medium truncate">{{ selectedElement.label }}</div>
              <div class="text-[10px] text-muted-foreground/60 truncate">{{ selectedElement.subtitle }}</div>
            </div>
          </div>
          <SelectValue v-else placeholder="Select data source" />
        </SelectTrigger>
        <SelectContent class="bg-popover border-border">
          <SelectItem
            v-for="el in dataElements"
            :key="el.id"
            :value="el.id"
          >
            <div class="flex items-center gap-2">
              <BarChart3 v-if="el.type === 'chart'" :size="12" class="text-amber-500 flex-shrink-0" />
              <Table2 v-else :size="12" class="text-blue-400 flex-shrink-0" />
              <div class="min-w-0">
                <span class="text-xs">{{ el.label }}</span>
                <span class="text-[10px] text-muted-foreground/60 ml-1.5">{{ el.subtitle }}</span>
              </div>
            </div>
          </SelectItem>
        </SelectContent>
      </Select>

      <!-- Selected data preview -->
      <div v-if="selectedElement" class="p-2.5 rounded-lg bg-foreground/[0.02] border border-dashed border-border">
        <template v-if="selectedElement.type === 'chart'">
          <div class="text-[10px] text-muted-foreground font-mono space-y-0.5">
            <div class="text-amber-500/80">{{ (selectedElement.component as any).data.type }} chart</div>
            <div>Labels: {{ (selectedElement.component as any).data.labels.join(', ') }}</div>
            <div v-for="ds in (selectedElement.component as any).data.datasets" :key="ds.label">
              {{ ds.label }}: {{ ds.data.join(', ') }}
            </div>
          </div>
        </template>
        <template v-else>
          <div class="text-[10px] text-muted-foreground font-mono space-y-0.5">
            <div class="text-blue-400/80">table ({{ (selectedElement.component as any).data.rows.length }} rows)</div>
            <div>{{ (selectedElement.component as any).data.headers.join(' | ') }}</div>
          </div>
        </template>
      </div>
    </div>

    <div v-else class="p-2.5 rounded-lg bg-foreground/[0.02] border border-dashed border-border text-center">
      <p class="text-[10px] text-muted-foreground/60">No chart or table data on this slide. Commentary will be generated from context only.</p>
    </div>

    <!-- Current commentary -->
    <div v-if="currentCommentary" class="p-3 rounded-lg bg-foreground/[0.02] border border-border">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Current Commentary</span>
        <span class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500">
          {{ currentCommentarySource }}
        </span>
      </div>
      <p class="text-xs text-muted-foreground leading-relaxed">{{ currentCommentary }}</p>
    </div>

    <!-- AI Generate -->
    <div v-if="commentaryMode === 'ai'" class="space-y-3">
      <p class="text-xs text-muted-foreground">
        AI will analyze the slide's {{ dominantContext }} data in the context of
        <span class="text-foreground/80">{{ sectionName || 'this section' }}</span>
        and generate {{ presentationStore.intent.tone }} commentary.
      </p>
      <Button
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        :disabled="aiStore.isGeneratingCommentary"
        @click="generateFromData"
      >
        <Loader2 v-if="aiStore.isGeneratingCommentary" :size="14" class="mr-1.5 animate-spin" />
        <Sparkles v-else :size="14" :stroke-width="1.5" class="mr-1.5" />
        {{ aiStore.isGeneratingCommentary ? 'Generating...' : 'Generate Commentary' }}
      </Button>

      <Button
        v-if="currentCommentary"
        variant="outline"
        class="w-full border-border text-muted-foreground hover:bg-foreground/5 rounded-lg h-9 text-sm"
        :disabled="aiStore.isGeneratingCommentary"
        @click="generateFromData"
      >
        <RefreshCw :size="12" :stroke-width="1.5" class="mr-1.5" />
        Regenerate
      </Button>
    </div>

    <!-- Prompt-based -->
    <div v-else-if="commentaryMode === 'prompt'" class="space-y-3">
      <Textarea
        v-model="promptText"
        rows="3"
        class="text-xs bg-[var(--glass-bg)] border-border rounded-lg resize-none placeholder:text-muted-foreground/50"
        placeholder="Describe what the commentary should focus on..."
      />
      <Button
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        :disabled="!promptText.trim() || aiStore.isGeneratingCommentary"
        @click="generateFromPrompt"
      >
        <Loader2 v-if="aiStore.isGeneratingCommentary" :size="14" class="mr-1.5 animate-spin" />
        <Sparkles v-else :size="14" :stroke-width="1.5" class="mr-1.5" />
        {{ aiStore.isGeneratingCommentary ? 'Generating...' : 'Generate from Prompt' }}
      </Button>
    </div>

    <!-- Manual -->
    <div v-else class="space-y-3">
      <Textarea
        v-model="manualText"
        rows="6"
        class="text-xs bg-[var(--glass-bg)] border-border rounded-lg resize-none placeholder:text-muted-foreground/50"
        placeholder="Write or paste your commentary..."
      />
      <Button
        class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        :disabled="!manualText.trim()"
        @click="applyManual"
      >
        Apply Commentary
      </Button>
    </div>
  </div>
</template>
