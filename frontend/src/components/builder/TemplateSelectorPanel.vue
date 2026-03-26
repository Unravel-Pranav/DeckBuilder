<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useDeckTemplateStore } from '@/stores/deckTemplate'
import { useDragDrop } from '@/composables/useDragDrop'
import { chartTemplates, tableTemplates, textTemplates } from '@/lib/mockData'
import { fetchTemplateSlides, type UploadedSlideInfo } from '@/lib/api'
import type { SlideTemplate, ChartData, TableData, SlideComponent, SlidePreviewData, UploadedSlideData } from '@/types'
import {
  BarChart3,
  TrendingUp,
  PieChart,
  Table2,
  FileText,
  Check,
  Info,
  Copy,
  GripVertical,
  Upload,
  Loader2,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()
const deckTemplateStore = useDeckTemplateStore()
const { startDrag, endDrag } = useDragDrop()
const activeCategory = ref<'chart' | 'table' | 'text' | 'uploaded'>('chart')

const uploadedSlides = ref<UploadedSlideInfo[]>([])
const uploadedLoading = ref(false)

const filteredTemplates = computed(() => {
  if (activeCategory.value === 'chart') return chartTemplates
  if (activeCategory.value === 'table') return tableTemplates
  if (activeCategory.value === 'uploaded') return [] as SlideTemplate[]
  return textTemplates
})

onMounted(async () => {
  if (deckTemplateStore.selectedTemplateId) {
    await loadUploadedSlides()
  }
})

async function loadUploadedSlides() {
  const id = deckTemplateStore.selectedTemplateId
  if (!id) return
  uploadedLoading.value = true
  try {
    uploadedSlides.value = await fetchTemplateSlides(id)
  } catch {
    uploadedSlides.value = []
  } finally {
    uploadedLoading.value = false
  }
}

const appliedTemplateIds = computed(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return new Set<string>()
  return new Set(
    slide.regions
      .map((r) => r.component?.templateId)
      .filter(Boolean),
  )
})

const chartTypeIcons: Record<string, typeof BarChart3> = {
  bar: BarChart3,
  line: TrendingUp,
  pie: PieChart,
  doughnut: PieChart,
  area: TrendingUp,
  scatter: BarChart3,
}

function isChartData(data: ChartData | TableData | string | SlidePreviewData): data is ChartData {
  return typeof data === 'object' && data !== null && 'datasets' in data
}

function isTableData(data: ChartData | TableData | string | SlidePreviewData): data is TableData {
  return typeof data === 'object' && data !== null && 'headers' in data
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

  slidesStore.setRegionComponent(
    slidesStore.activeSlideId,
    slidesStore.activeRegionIndex,
    component,
  )
}

function copySchema(hint: string) {
  navigator.clipboard.writeText(hint)
}

function onTemplateDragStart(event: DragEvent, template: SlideTemplate) {
  if (template.category === 'slide') return

  let component: Omit<SlideComponent, 'id'>

  if (template.category === 'chart' && isChartData(template.previewData)) {
    component = { type: 'chart', templateId: template.id, data: template.previewData, config: {} }
  } else if (template.category === 'table' && isTableData(template.previewData)) {
    component = { type: 'table', templateId: template.id, data: template.previewData, config: {} }
  } else if (template.category === 'text' && typeof template.previewData === 'string') {
    component = { type: 'text', templateId: template.id, data: { content: template.previewData }, config: { format: 'paragraph' as const } }
  } else {
    return
  }

  startDrag(event, {
    componentType: component.type,
    component,
    label: template.name,
  })
}

function applyUploadedSlide(slide: UploadedSlideInfo) {
  if (!slidesStore.activeSlideId || !deckTemplateStore.selectedTemplateId) return

  const data: UploadedSlideData = {
    templateId: deckTemplateStore.selectedTemplateId,
    slideIndex: slide.index,
    title: slide.title,
    layoutName: slide.layout_name,
  }
  const component: SlideComponent = {
    id: crypto.randomUUID(),
    type: 'uploaded_slide',
    templateId: `uploaded-${data.templateId}-${data.slideIndex}`,
    data,
    config: {},
  }
  slidesStore.setRegionComponent(
    slidesStore.activeSlideId,
    slidesStore.activeRegionIndex,
    component,
  )
}

function onUploadedSlideDragStart(event: DragEvent, slide: UploadedSlideInfo) {
  if (!deckTemplateStore.selectedTemplateId) return
  const data: UploadedSlideData = {
    templateId: deckTemplateStore.selectedTemplateId,
    slideIndex: slide.index,
    title: slide.title,
    layoutName: slide.layout_name,
  }
  startDrag(event, {
    componentType: 'uploaded_slide',
    component: { type: 'uploaded_slide' as const, templateId: `uploaded-${data.templateId}-${data.slideIndex}`, data, config: {} },
    label: slide.title,
  })
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <p class="text-xs text-muted-foreground mb-3">
        Pick a template to populate this slide's component. The schema hint shows the expected data format.
      </p>

      <!-- Category filter -->
      <div class="flex gap-1 p-1 rounded-lg bg-foreground/[0.03]">
        <button
          v-for="cat in [
            { id: 'chart' as const, label: 'Charts', icon: BarChart3 },
            { id: 'table' as const, label: 'Tables', icon: Table2 },
            { id: 'text' as const, label: 'Text', icon: FileText },
            ...(deckTemplateStore.selectedTemplateId
              ? [{ id: 'uploaded' as const, label: 'Uploaded', icon: Upload }]
              : []),
          ]"
          :key="cat.id"
          class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[11px] font-medium transition-all duration-200"
          :class="activeCategory === cat.id ? 'bg-amber-500/10 text-amber-500' : 'text-muted-foreground hover:text-foreground/80'"
          @click="activeCategory = cat.id"
        >
          <component :is="cat.icon" :size="12" :stroke-width="1.5" />
          {{ cat.label }}
        </button>
      </div>
    </div>

    <!-- Uploaded slide cards -->
    <div v-if="activeCategory === 'uploaded'" class="space-y-2">
      <div v-if="uploadedLoading" class="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
        <Loader2 :size="14" class="animate-spin text-amber-500" />
        Loading slides…
      </div>
      <div v-else-if="uploadedSlides.length === 0" class="text-xs text-muted-foreground/70 py-4 text-center">
        No uploaded template found. Upload a .pptx first.
      </div>
      <div
        v-for="slide in uploadedSlides"
        :key="slide.index"
        class="group/card rounded-lg border p-3 transition-all duration-200 cursor-pointer"
        :class="
          appliedTemplateIds.has(`uploaded-${deckTemplateStore.selectedTemplateId}-${slide.index}`)
            ? 'border-amber-500/30 bg-amber-500/10'
            : 'border-border bg-foreground/[0.02] hover:border-[color:var(--glass-border-hover)] hover:bg-foreground/[0.04]'
        "
        draggable="true"
        @click="applyUploadedSlide(slide)"
        @dragstart="onUploadedSlideDragStart($event, slide)"
        @dragend="endDrag"
      >
        <div class="flex items-start gap-2.5 relative">
          <div class="absolute -left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/card:opacity-50 transition-opacity cursor-grab">
            <GripVertical :size="10" class="text-muted-foreground" />
          </div>
          <div
            class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            :class="appliedTemplateIds.has(`uploaded-${deckTemplateStore.selectedTemplateId}-${slide.index}`) ? 'bg-amber-500/20' : 'bg-foreground/5'"
          >
            <Upload
              :size="14"
              :stroke-width="1.5"
              :class="appliedTemplateIds.has(`uploaded-${deckTemplateStore.selectedTemplateId}-${slide.index}`) ? 'text-amber-500' : 'text-muted-foreground'"
            />
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5">
              <p
                class="text-xs font-medium truncate"
                :class="appliedTemplateIds.has(`uploaded-${deckTemplateStore.selectedTemplateId}-${slide.index}`) ? 'text-amber-500' : 'text-foreground/80'"
              >
                Slide {{ slide.index + 1 }}: {{ slide.title }}
              </p>
              <Check
                v-if="appliedTemplateIds.has(`uploaded-${deckTemplateStore.selectedTemplateId}-${slide.index}`)"
                :size="12"
                :stroke-width="2.5"
                class="text-amber-500 flex-shrink-0"
              />
            </div>
            <p class="text-[10px] text-muted-foreground/70 line-clamp-2 mt-0.5">{{ slide.layout_name }} &middot; {{ slide.shape_count }} shapes</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Template cards -->
    <div v-else class="space-y-2">
      <div
        v-for="tmpl in filteredTemplates"
        :key="tmpl.id"
        class="group/card rounded-lg border p-3 transition-all duration-200 cursor-pointer"
        :class="
          appliedTemplateIds.has(tmpl.id)
            ? 'border-amber-500/30 bg-amber-500/10'
            : 'border-border bg-foreground/[0.02] hover:border-[color:var(--glass-border-hover)] hover:bg-foreground/[0.04]'
        "
        draggable="true"
        @click="applyTemplate(tmpl)"
        @dragstart="onTemplateDragStart($event, tmpl)"
        @dragend="endDrag"
      >
        <div class="flex items-start gap-2.5 relative">
          <!-- Drag grip -->
          <div class="absolute -left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/card:opacity-50 transition-opacity cursor-grab">
            <GripVertical :size="10" class="text-muted-foreground" />
          </div>

          <!-- Icon -->
          <div
            class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            :class="appliedTemplateIds.has(tmpl.id) ? 'bg-amber-500/20' : 'bg-foreground/5'"
          >
            <component
              :is="tmpl.chartType ? (chartTypeIcons[tmpl.chartType] ?? BarChart3) : (tmpl.category === 'table' ? Table2 : FileText)"
              :size="14"
              :stroke-width="1.5"
              :class="appliedTemplateIds.has(tmpl.id) ? 'text-amber-500' : 'text-muted-foreground'"
            />
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5">
              <p
                class="text-xs font-medium truncate"
                :class="appliedTemplateIds.has(tmpl.id) ? 'text-amber-500' : 'text-foreground/80'"
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
            <p class="text-[10px] text-muted-foreground/70 line-clamp-2 mt-0.5">{{ tmpl.description }}</p>
          </div>
        </div>

        <!-- Schema hint -->
        <div
          v-if="appliedTemplateIds.has(tmpl.id)"
          class="mt-2.5 p-2 rounded bg-[var(--preview-surface)] border border-border"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-[9px] font-mono uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1">
              <Info :size="8" :stroke-width="1.5" />
              Schema
            </span>
            <button
              class="text-[9px] text-muted-foreground/70 hover:text-amber-500 transition-colors flex items-center gap-0.5"
              @click.stop="copySchema(tmpl.schemaHint)"
            >
              <Copy :size="8" :stroke-width="1.5" />
              Copy
            </button>
          </div>
          <pre class="text-[9px] font-mono text-muted-foreground whitespace-pre-wrap break-all">{{ tmpl.schemaHint }}</pre>
        </div>
      </div>
    </div>

    <!-- Helper text -->
    <p class="text-[10px] text-muted-foreground/50 text-center pt-2">
      Click to apply or drag into a region. Switch to the Data tab to customize values.
    </p>
  </div>
</template>
