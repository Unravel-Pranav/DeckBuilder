<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTemplatesStore } from '@/stores/templates'
import GlassCard from '@/components/shared/GlassCard.vue'
import EmptyState from '@/components/shared/EmptyState.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import type { SlideTemplate, ChartData, TableData, ChartType, SlidePreviewData } from '@/types'
import type { FilterCategory } from '@/stores/templates'
import {
  Search,
  Plus,
  Upload,
  BarChart3,
  TrendingUp,
  PieChart,
  Table2,
  FileText,
  LayoutTemplate,
  Eye,
  Copy,
  Trash2,
  X,
  Info,
  Sparkles,
  Grid3x3,
  List,
  Presentation,
  PanelTop,
  SplitSquareVertical,
  CalendarCheck,
  Users,
  Clock,
  Columns2,
  Quote,
  Hash,
  Square,
} from 'lucide-vue-next'

const templatesStore = useTemplatesStore()

const viewMode = ref<'grid' | 'list'>('grid')
const showDetailDialog = ref(false)
const showCreateDialog = ref(false)
const selectedTemplate = ref<SlideTemplate | null>(null)

// Create form state
const newTemplate = ref({
  name: '',
  category: 'chart' as 'chart' | 'table' | 'text',
  chartType: 'bar' as ChartType,
  description: '',
  schemaHint: '',
  dataJson: '',
})

const chartTypeIcons: Record<string, typeof BarChart3> = {
  bar: BarChart3,
  line: TrendingUp,
  pie: PieChart,
  doughnut: PieChart,
  area: TrendingUp,
  scatter: BarChart3,
}

const slideKindIcons: Record<string, typeof BarChart3> = {
  title: PanelTop,
  'section-divider': SplitSquareVertical,
  closing: CalendarCheck,
  agenda: FileText,
  team: Users,
  timeline: Clock,
  comparison: Columns2,
  quote: Quote,
  kpi: Hash,
  content: FileText,
  blank: Square,
}

const filterTabs: { id: FilterCategory; label: string; icon: typeof BarChart3 }[] = [
  { id: 'all', label: 'All', icon: LayoutTemplate },
  { id: 'slide', label: 'Slides', icon: Presentation },
  { id: 'chart', label: 'Charts', icon: BarChart3 },
  { id: 'table', label: 'Tables', icon: Table2 },
  { id: 'text', label: 'Text', icon: FileText },
  { id: 'custom', label: 'My Templates', icon: Sparkles },
]

function isChartData(data: ChartData | TableData | string | SlidePreviewData): data is ChartData {
  return typeof data === 'object' && 'datasets' in data
}

function isTableData(data: ChartData | TableData | string | SlidePreviewData): data is TableData {
  return typeof data === 'object' && 'headers' in data
}

function isSlidePreviewData(data: ChartData | TableData | string | SlidePreviewData): data is SlidePreviewData {
  return typeof data === 'object' && 'elements' in data
}

function viewTemplate(tmpl: SlideTemplate) {
  selectedTemplate.value = tmpl
  showDetailDialog.value = true
}

function getBarHeights(data: number[]): number[] {
  const max = Math.max(...data)
  return data.map((v) => (max > 0 ? (v / max) * 100 : 0))
}

function isCustom(id: string): boolean {
  return id.startsWith('custom-')
}

function createTemplate() {
  const { name, category, chartType, description, schemaHint, dataJson } = newTemplate.value
  if (!name.trim() || !description.trim()) return

  let previewData: ChartData | TableData | string | SlidePreviewData = ''

  if (category === 'slide') {
    const slideKind = (newTemplate.value as any).slideKind ?? 'content'
    previewData = {
      title: name,
      elements: [
        { type: 'heading', label: name, x: 10, y: 30, w: 80, h: 12 },
        { type: 'subheading', label: description, x: 10, y: 48, w: 60, h: 6 },
        { type: 'accent-bar', label: '', x: 10, y: 58, w: 20, h: 1 },
      ],
    } as SlidePreviewData
    templatesStore.addCustomTemplate({
      name: name.trim(),
      category: 'slide',
      slideKind,
      description: description.trim(),
      previewData,
      schemaHint: schemaHint.trim() || 'Custom slide template',
      defaultLayout: 'commentary-only',
      defaultComponents: [
        { type: 'text', textContent: dataJson.trim() || name },
      ],
    })
    newTemplate.value = { name: '', category: 'chart', chartType: 'bar', description: '', schemaHint: '', dataJson: '' }
    showCreateDialog.value = false
    return
  } else if (category === 'chart') {
    try {
      const parsed = JSON.parse(dataJson)
      previewData = {
        type: chartType,
        labels: parsed.x_axis ?? parsed.labels ?? ['A', 'B', 'C'],
        datasets: [{
          label: parsed.label ?? name,
          data: parsed.y_axis ?? parsed.values ?? [30, 50, 40],
          ...(chartType === 'pie' || chartType === 'doughnut'
            ? { backgroundColor: ['#F59E0B', '#FBBF24', '#D97706'] }
            : { borderColor: '#F59E0B' }),
        }],
      } as ChartData
    } catch {
      previewData = {
        type: chartType,
        labels: ['A', 'B', 'C', 'D'],
        datasets: [{ label: name, data: [30, 50, 40, 60] }],
      } as ChartData
    }
  } else if (category === 'table') {
    try {
      const parsed = JSON.parse(dataJson)
      previewData = {
        headers: parsed.headers ?? ['Col 1', 'Col 2', 'Col 3'],
        rows: parsed.rows ?? [['--', '--', '--']],
      } as TableData
    } catch {
      previewData = {
        headers: ['Column 1', 'Column 2', 'Column 3'],
        rows: [['Data', 'Data', 'Data']],
      } as TableData
    }
  } else {
    previewData = dataJson.trim() || 'Custom text template content'
  }

  templatesStore.addCustomTemplate({
    name: name.trim(),
    category,
    chartType: category === 'chart' ? chartType : undefined,
    description: description.trim(),
    previewData,
    schemaHint: schemaHint.trim() || 'Custom schema',
  })

  newTemplate.value = { name: '', category: 'chart', chartType: 'bar', description: '', schemaHint: '', dataJson: '' }
  showCreateDialog.value = false
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <div>
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center">
            <LayoutTemplate :size="16" :stroke-width="1.5" class="text-amber-500" />
          </div>
          <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight">
            Template Library
          </h2>
        </div>
        <p class="text-sm text-zinc-500 ml-10">
          Browse, create, and manage slide templates for your presentations.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          class="border-[rgba(255,255,255,0.15)] text-zinc-300 hover:bg-white/5 rounded-lg h-9 text-sm"
          @click="$router.push('/templates/upload')"
        >
          <Upload :size="14" :stroke-width="1.5" class="mr-1.5" />
          Upload PPT
        </Button>
        <Button
          class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 font-medium rounded-lg h-9 text-sm shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98]"
          @click="showCreateDialog = true"
        >
          <Plus :size="14" :stroke-width="2" class="mr-1.5" />
          Create Template
        </Button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-8">
      <GlassCard
        v-for="tab in filterTabs"
        :key="tab.id"
        :highlighted="templatesStore.activeFilter === tab.id"
        hoverable
        padding="p-3"
        @click="templatesStore.setFilter(tab.id)"
      >
        <div class="flex items-center gap-2">
          <component :is="tab.icon" :size="14" :stroke-width="1.5" :class="templatesStore.activeFilter === tab.id ? 'text-amber-500' : 'text-zinc-500'" />
          <span class="text-xs font-medium" :class="templatesStore.activeFilter === tab.id ? 'text-amber-500' : 'text-zinc-400'">
            {{ tab.label }}
          </span>
        </div>
        <p class="text-xl font-display font-bold mt-1" :class="templatesStore.activeFilter === tab.id ? 'text-amber-500' : 'text-zinc-300'">
          {{ templatesStore.templateCounts[tab.id] }}
        </p>
      </GlassCard>
    </div>

    <!-- Search + View toggle -->
    <div class="flex items-center gap-3 mb-6">
      <div class="relative flex-1">
        <Search :size="16" :stroke-width="1.5" class="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
        <Input
          :model-value="templatesStore.searchQuery"
          placeholder="Search templates by name, type, or description..."
          class="pl-10 h-10 bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-xl placeholder:text-zinc-600 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20"
          @update:model-value="templatesStore.setSearch($event as string)"
        />
      </div>
      <div class="flex rounded-lg border border-[rgba(255,255,255,0.08)] overflow-hidden">
        <button
          class="p-2 transition-colors"
          :class="viewMode === 'grid' ? 'bg-amber-500/10 text-amber-500' : 'text-zinc-600 hover:text-zinc-400'"
          @click="viewMode = 'grid'"
        >
          <Grid3x3 :size="16" :stroke-width="1.5" />
        </button>
        <button
          class="p-2 transition-colors"
          :class="viewMode === 'list' ? 'bg-amber-500/10 text-amber-500' : 'text-zinc-600 hover:text-zinc-400'"
          @click="viewMode = 'list'"
        >
          <List :size="16" :stroke-width="1.5" />
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <EmptyState
      v-if="templatesStore.filteredTemplates.length === 0"
      :icon="LayoutTemplate"
      title="No templates found"
      :description="templatesStore.searchQuery ? 'Try a different search term.' : 'Create your first custom template.'"
    >
      <Button
        class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 font-medium rounded-xl"
        @click="showCreateDialog = true"
      >
        <Plus :size="16" class="mr-1.5" />
        Create Template
      </Button>
    </EmptyState>

    <!-- Grid view -->
    <div
      v-else-if="viewMode === 'grid'"
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
    >
      <div
        v-for="tmpl in templatesStore.filteredTemplates"
        :key="tmpl.id"
        class="group rounded-xl border p-0 overflow-hidden transition-all duration-300 cursor-pointer"
        :class="isCustom(tmpl.id)
          ? 'border-amber-500/15 bg-[rgba(26,26,36,0.6)] hover:border-amber-500/30 hover:shadow-[0_0_20px_rgba(245,158,11,0.1)]'
          : 'border-[rgba(255,255,255,0.08)] bg-[rgba(26,26,36,0.6)] hover:border-[rgba(255,255,255,0.15)]'"
        style="backdrop-filter: blur(8px)"
        @click="viewTemplate(tmpl)"
      >
        <!-- Preview area -->
        <div class="h-28 bg-[rgba(10,10,15,0.5)] flex items-center justify-center p-4 relative">
          <!-- Custom badge -->
          <Badge
            v-if="isCustom(tmpl.id)"
            variant="secondary"
            class="absolute top-2 left-2 text-[8px] bg-amber-500/15 text-amber-500 border-amber-500/20 rounded-full px-1.5"
          >
            Custom
          </Badge>

          <!-- Actions overlay -->
          <div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              class="p-1.5 rounded-lg bg-[rgba(26,26,36,0.8)] text-zinc-400 hover:text-amber-500 transition-colors"
              title="Duplicate"
              @click.stop="templatesStore.duplicateTemplate(tmpl.id)"
            >
              <Copy :size="12" :stroke-width="1.5" />
            </button>
            <button
              v-if="isCustom(tmpl.id)"
              class="p-1.5 rounded-lg bg-[rgba(26,26,36,0.8)] text-zinc-400 hover:text-red-400 transition-colors"
              title="Delete"
              @click.stop="templatesStore.removeCustomTemplate(tmpl.id)"
            >
              <Trash2 :size="12" :stroke-width="1.5" />
            </button>
          </div>

          <!-- Chart preview -->
          <template v-if="tmpl.category === 'chart' && isChartData(tmpl.previewData)">
            <template v-if="tmpl.chartType === 'bar'">
              <div class="flex items-end gap-1 w-full h-full px-2">
                <div
                  v-for="(val, i) in getBarHeights(tmpl.previewData.datasets[0].data)"
                  :key="i"
                  class="flex-1 rounded-t transition-all"
                  :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.5)', minHeight: '4px' }"
                />
              </div>
            </template>
            <template v-else-if="tmpl.chartType === 'line' || tmpl.chartType === 'area'">
              <svg class="w-full h-full" viewBox="0 0 120 50" preserveAspectRatio="none">
                <polyline
                  v-if="tmpl.chartType === 'area'"
                  fill="rgba(245,158,11,0.1)"
                  stroke="none"
                  :points="`0,50 ${tmpl.previewData.datasets[0].data.map((v, i) => `${(i / (tmpl.previewData as ChartData).datasets[0].data.length - 1) * 120},${50 - (v / Math.max(...(tmpl.previewData as ChartData).datasets[0].data)) * 44}`).join(' ')} 120,50`"
                />
                <polyline
                  v-for="(ds, dsi) in tmpl.previewData.datasets"
                  :key="dsi"
                  fill="none"
                  :stroke="dsi === 0 ? '#F59E0B' : '#71717A'"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  :points="ds.data.map((v, i) => `${(i / (ds.data.length - 1)) * 120},${50 - (v / Math.max(...ds.data)) * 44}`).join(' ')"
                  opacity="0.7"
                />
              </svg>
            </template>
            <template v-else>
              <div
                class="w-20 h-20 rounded-full"
                :style="{
                  background: `conic-gradient(#F59E0B 0% ${tmpl.previewData.datasets[0].data[0]}%, #FBBF24 ${tmpl.previewData.datasets[0].data[0]}% ${tmpl.previewData.datasets[0].data[0] + (tmpl.previewData.datasets[0].data[1] ?? 0)}%, #D97706 ${tmpl.previewData.datasets[0].data[0] + (tmpl.previewData.datasets[0].data[1] ?? 0)}% 100%)`,
                  opacity: 0.6,
                }"
              >
                <div v-if="tmpl.chartType === 'doughnut'" class="w-10 h-10 rounded-full bg-[rgba(10,10,15,0.9)] mt-5 ml-5" />
              </div>
            </template>
          </template>

          <!-- Table preview -->
          <template v-else-if="tmpl.category === 'table' && isTableData(tmpl.previewData)">
            <div class="w-full space-y-1.5 px-2">
              <div class="flex gap-1.5">
                <div v-for="i in Math.min((tmpl.previewData as TableData).headers.length, 4)" :key="i" class="flex-1 h-2 rounded-sm bg-amber-500/30" />
              </div>
              <div v-for="r in Math.min((tmpl.previewData as TableData).rows.length, 3)" :key="r" class="flex gap-1.5">
                <div v-for="c in Math.min((tmpl.previewData as TableData).headers.length, 4)" :key="c" class="flex-1 h-1.5 rounded-sm bg-zinc-800" />
              </div>
            </div>
          </template>

          <!-- Slide preview -->
          <template v-else-if="tmpl.category === 'slide' && isSlidePreviewData(tmpl.previewData)">
            <div class="w-full h-full relative">
              <div
                v-for="(el, ei) in (tmpl.previewData as SlidePreviewData).elements.slice(0, 6)"
                :key="ei"
                class="absolute rounded-sm"
                :class="
                  el.type === 'heading' ? 'bg-amber-500/25' :
                  el.type === 'subheading' ? 'bg-amber-500/15' :
                  el.type === 'accent-bar' ? 'bg-amber-500/40' :
                  el.type === 'divider' ? 'bg-zinc-600' :
                  el.type === 'image-placeholder' ? 'bg-zinc-700/40 border border-dashed border-zinc-700' :
                  'bg-zinc-800'
                "
                :style="{ left: `${el.x}%`, top: `${el.y}%`, width: `${el.w}%`, height: `${el.h}%` }"
              />
            </div>
          </template>

          <!-- Text preview -->
          <template v-else>
            <div class="w-full space-y-1.5 px-2">
              <div class="h-2 w-4/5 rounded-sm bg-amber-500/20" />
              <div class="h-1.5 w-full rounded-sm bg-zinc-800" />
              <div class="h-1.5 w-3/4 rounded-sm bg-zinc-800" />
              <div class="h-1.5 w-5/6 rounded-sm bg-zinc-800" />
            </div>
          </template>
        </div>

        <!-- Card info -->
        <div class="p-3">
          <div class="flex items-center gap-2 mb-1">
            <h4 class="text-xs font-medium text-zinc-300 truncate flex-1">{{ tmpl.name }}</h4>
            <Badge
              variant="secondary"
              class="text-[8px] bg-white/5 text-zinc-500 border-none rounded-full px-1.5 flex-shrink-0"
            >
              {{ tmpl.category }}
            </Badge>
          </div>
          <p class="text-[10px] text-zinc-600 line-clamp-2">{{ tmpl.description }}</p>
          <div v-if="tmpl.chartType" class="mt-1.5 flex items-center gap-1">
            <component :is="chartTypeIcons[tmpl.chartType] ?? BarChart3" :size="10" :stroke-width="1.5" class="text-zinc-600" />
            <span class="text-[9px] font-mono text-zinc-600 capitalize">{{ tmpl.chartType }}</span>
          </div>
          <div v-else-if="tmpl.slideKind" class="mt-1.5 flex items-center gap-1">
            <component :is="slideKindIcons[tmpl.slideKind] ?? Presentation" :size="10" :stroke-width="1.5" class="text-zinc-600" />
            <span class="text-[9px] font-mono text-zinc-600 capitalize">{{ tmpl.slideKind.replace('-', ' ') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- List view -->
    <div v-else class="space-y-2">
      <div
        v-for="tmpl in templatesStore.filteredTemplates"
        :key="tmpl.id"
        class="group flex items-center gap-4 px-4 py-3 rounded-xl border transition-all duration-200 cursor-pointer"
        :class="isCustom(tmpl.id)
          ? 'border-amber-500/15 bg-[rgba(26,26,36,0.6)] hover:border-amber-500/30'
          : 'border-[rgba(255,255,255,0.08)] bg-[rgba(26,26,36,0.6)] hover:border-[rgba(255,255,255,0.15)]'"
        style="backdrop-filter: blur(8px)"
        @click="viewTemplate(tmpl)"
      >
        <!-- Icon -->
        <div
          class="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
          :class="isCustom(tmpl.id) ? 'bg-amber-500/15' : 'bg-white/5'"
        >
          <component
            :is="tmpl.chartType ? (chartTypeIcons[tmpl.chartType] ?? BarChart3) : tmpl.slideKind ? (slideKindIcons[tmpl.slideKind] ?? Presentation) : (tmpl.category === 'table' ? Table2 : FileText)"
            :size="18"
            :stroke-width="1.5"
            :class="isCustom(tmpl.id) ? 'text-amber-500' : 'text-zinc-500'"
          />
        </div>

        <!-- Info -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <h4 class="text-sm font-medium text-zinc-300 truncate">{{ tmpl.name }}</h4>
            <Badge v-if="isCustom(tmpl.id)" variant="secondary" class="text-[8px] bg-amber-500/15 text-amber-500 border-amber-500/20 rounded-full px-1.5">
              Custom
            </Badge>
          </div>
          <p class="text-xs text-zinc-600 truncate">{{ tmpl.description }}</p>
        </div>

        <!-- Meta -->
        <Badge variant="secondary" class="text-[9px] bg-white/5 text-zinc-500 border-none rounded-full px-2 capitalize flex-shrink-0">
          {{ tmpl.category }}
        </Badge>
        <Badge v-if="tmpl.chartType" variant="secondary" class="text-[9px] bg-white/5 text-zinc-500 border-none rounded-full px-2 capitalize flex-shrink-0">
          {{ tmpl.chartType }}
        </Badge>
        <Badge v-else-if="tmpl.slideKind" variant="secondary" class="text-[9px] bg-amber-500/10 text-amber-500/70 border-none rounded-full px-2 capitalize flex-shrink-0">
          {{ tmpl.slideKind.replace('-', ' ') }}
        </Badge>

        <!-- Actions -->
        <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button
            class="p-1.5 rounded-lg text-zinc-500 hover:text-amber-500 hover:bg-white/5 transition-colors"
            @click.stop="viewTemplate(tmpl)"
          >
            <Eye :size="14" :stroke-width="1.5" />
          </button>
          <button
            class="p-1.5 rounded-lg text-zinc-500 hover:text-amber-500 hover:bg-white/5 transition-colors"
            @click.stop="templatesStore.duplicateTemplate(tmpl.id)"
          >
            <Copy :size="14" :stroke-width="1.5" />
          </button>
          <button
            v-if="isCustom(tmpl.id)"
            class="p-1.5 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            @click.stop="templatesStore.removeCustomTemplate(tmpl.id)"
          >
            <Trash2 :size="14" :stroke-width="1.5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Detail Dialog -->
    <Dialog v-model:open="showDetailDialog">
      <DialogContent
        v-if="selectedTemplate"
        class="bg-[#12121A] border-[rgba(255,255,255,0.08)] rounded-xl max-w-lg"
      >
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight flex items-center gap-2">
            <component
              :is="selectedTemplate.chartType ? (chartTypeIcons[selectedTemplate.chartType] ?? BarChart3) : (selectedTemplate.category === 'table' ? Table2 : FileText)"
              :size="18"
              :stroke-width="1.5"
              class="text-amber-500"
            />
            {{ selectedTemplate.name }}
          </DialogTitle>
          <DialogDescription class="text-xs text-zinc-500">
            {{ selectedTemplate.description }}
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4 py-2">
          <!-- Preview -->
          <div class="h-40 rounded-lg bg-[rgba(10,10,15,0.5)] border border-[rgba(255,255,255,0.06)] flex items-center justify-center p-6">
            <template v-if="selectedTemplate.category === 'chart' && isChartData(selectedTemplate.previewData)">
              <template v-if="selectedTemplate.chartType === 'bar'">
                <div class="flex items-end gap-2 w-full h-full px-4">
                  <div
                    v-for="(val, i) in getBarHeights(selectedTemplate.previewData.datasets[0].data)"
                    :key="i"
                    class="flex-1 rounded-t transition-all"
                    :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.6)', minHeight: '4px' }"
                  />
                </div>
              </template>
              <template v-else>
                <svg class="w-full h-full" viewBox="0 0 140 60" preserveAspectRatio="none">
                  <polyline
                    v-for="(ds, dsi) in selectedTemplate.previewData.datasets"
                    :key="dsi"
                    fill="none"
                    :stroke="dsi === 0 ? '#F59E0B' : '#71717A'"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    :points="ds.data.map((v, i) => `${(i / (ds.data.length - 1)) * 140},${60 - (v / Math.max(...ds.data)) * 52}`).join(' ')"
                  />
                </svg>
              </template>
            </template>
            <template v-else-if="selectedTemplate.category === 'table' && isTableData(selectedTemplate.previewData)">
              <table class="w-full text-xs">
                <thead>
                  <tr class="border-b border-[rgba(255,255,255,0.08)]">
                    <th v-for="h in (selectedTemplate.previewData as TableData).headers" :key="h" class="text-left py-1.5 px-2 font-mono text-amber-500/70 font-medium text-[10px]">
                      {{ h }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in (selectedTemplate.previewData as TableData).rows" :key="i" class="border-b border-[rgba(255,255,255,0.04)]">
                    <td v-for="(cell, j) in row" :key="j" class="py-1.5 px-2 text-zinc-400 text-[10px]">{{ cell }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
            <template v-else-if="selectedTemplate.category === 'slide' && isSlidePreviewData(selectedTemplate.previewData)">
              <div class="w-full h-full relative rounded-lg overflow-hidden bg-[rgba(10,10,15,0.3)]">
                <div
                  v-for="(el, ei) in (selectedTemplate.previewData as SlidePreviewData).elements"
                  :key="ei"
                  class="absolute rounded-sm flex items-center justify-center"
                  :class="
                    el.type === 'heading' ? 'bg-amber-500/20' :
                    el.type === 'subheading' ? 'bg-amber-500/10' :
                    el.type === 'accent-bar' ? 'bg-amber-500/40' :
                    el.type === 'divider' ? 'bg-zinc-600' :
                    el.type === 'image-placeholder' ? 'bg-zinc-800/60 border border-dashed border-zinc-700' :
                    el.type === 'list' ? 'bg-transparent' :
                    'bg-zinc-800/40'
                  "
                  :style="{ left: `${el.x}%`, top: `${el.y}%`, width: `${el.w}%`, height: `${el.h}%` }"
                >
                  <span
                    v-if="el.label && el.type !== 'divider' && el.type !== 'accent-bar'"
                    class="text-[7px] text-zinc-500 truncate px-1 whitespace-pre-line text-center leading-tight"
                  >
                    {{ el.label.slice(0, 40) }}
                  </span>
                </div>
              </div>
            </template>
            <template v-else>
              <p class="text-xs text-zinc-400 leading-relaxed whitespace-pre-line">{{ selectedTemplate.previewData }}</p>
            </template>
          </div>

          <!-- Metadata -->
          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Category</p>
              <p class="text-xs text-zinc-300 capitalize">{{ selectedTemplate.category }}</p>
            </div>
            <div v-if="selectedTemplate.chartType" class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Chart Type</p>
              <p class="text-xs text-zinc-300 capitalize">{{ selectedTemplate.chartType }}</p>
            </div>
            <div v-else-if="selectedTemplate.slideKind" class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Slide Kind</p>
              <p class="text-xs text-zinc-300 capitalize">{{ selectedTemplate.slideKind.replace('-', ' ') }}</p>
            </div>
            <div :class="selectedTemplate.chartType ? 'col-span-2' : ''" class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <div class="flex items-center justify-between mb-1">
                <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600">Schema Hint</p>
                <button
                  class="text-[9px] text-zinc-600 hover:text-amber-500 transition-colors flex items-center gap-0.5"
                  @click="navigator.clipboard.writeText(selectedTemplate!.schemaHint)"
                >
                  <Copy :size="8" :stroke-width="1.5" />
                  Copy
                </button>
              </div>
              <pre class="text-[10px] font-mono text-zinc-500 whitespace-pre-wrap break-all">{{ selectedTemplate.schemaHint }}</pre>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] rounded-lg"
            @click="templatesStore.duplicateTemplate(selectedTemplate!.id); showDetailDialog = false"
          >
            <Copy :size="14" :stroke-width="1.5" class="mr-1.5" />
            Duplicate
          </Button>
          <Button
            class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 rounded-lg"
            @click="showDetailDialog = false"
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Create Template Dialog -->
    <Dialog v-model:open="showCreateDialog">
      <DialogContent class="bg-[#12121A] border-[rgba(255,255,255,0.08)] rounded-xl max-w-lg">
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight">Create Custom Template</DialogTitle>
          <DialogDescription class="text-xs text-zinc-500">
            Define a reusable slide component template with preview data and schema.
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4 py-2 max-h-[60vh] overflow-y-auto pr-1">
          <!-- Name -->
          <div>
            <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">Template Name</Label>
            <Input
              v-model="newTemplate.name"
              placeholder="e.g., Revenue Waterfall Chart"
              class="h-10 bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg placeholder:text-zinc-600"
            />
          </div>

          <!-- Category + Chart type -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">Category</Label>
              <Select v-model="newTemplate.category">
                <SelectTrigger class="h-10 bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent class="bg-[#12121A] border-[rgba(255,255,255,0.08)]">
                  <SelectItem value="slide">Slide</SelectItem>
                  <SelectItem value="chart">Chart</SelectItem>
                  <SelectItem value="table">Table</SelectItem>
                  <SelectItem value="text">Text</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-if="newTemplate.category === 'chart'">
              <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">Chart Type</Label>
              <Select v-model="newTemplate.chartType">
                <SelectTrigger class="h-10 bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent class="bg-[#12121A] border-[rgba(255,255,255,0.08)]">
                  <SelectItem value="bar">Bar</SelectItem>
                  <SelectItem value="line">Line</SelectItem>
                  <SelectItem value="pie">Pie</SelectItem>
                  <SelectItem value="doughnut">Doughnut</SelectItem>
                  <SelectItem value="area">Area</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-else-if="newTemplate.category === 'slide'">
              <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">Slide Kind</Label>
              <Select v-model="(newTemplate as any).slideKind" default-value="content">
                <SelectTrigger class="h-10 bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg">
                  <SelectValue placeholder="Select kind" />
                </SelectTrigger>
                <SelectContent class="bg-[#12121A] border-[rgba(255,255,255,0.08)]">
                  <SelectItem value="title">Title Page</SelectItem>
                  <SelectItem value="section-divider">Section Divider</SelectItem>
                  <SelectItem value="agenda">Agenda</SelectItem>
                  <SelectItem value="closing">Closing</SelectItem>
                  <SelectItem value="team">Team</SelectItem>
                  <SelectItem value="timeline">Timeline</SelectItem>
                  <SelectItem value="comparison">Comparison</SelectItem>
                  <SelectItem value="quote">Quote / Stat</SelectItem>
                  <SelectItem value="content">General Content</SelectItem>
                  <SelectItem value="blank">Blank</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <!-- Description -->
          <div>
            <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">Description</Label>
            <Textarea
              v-model="newTemplate.description"
              rows="2"
              placeholder="What this template is best used for..."
              class="text-sm bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg resize-none placeholder:text-zinc-600"
            />
          </div>

          <!-- Schema hint -->
          <div>
            <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">
              Schema Hint
              <span class="text-zinc-600 font-normal">(shown to users as data format guide)</span>
            </Label>
            <Textarea
              v-model="newTemplate.schemaHint"
              rows="2"
              placeholder='e.g., { "x_axis": [...], "y_axis": [...] }'
              class="text-xs font-mono bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg resize-none placeholder:text-zinc-600"
            />
          </div>

          <!-- Sample data -->
          <div>
            <Label class="text-sm font-medium text-zinc-300 mb-1.5 block">
              Sample Data
              <span class="text-zinc-600 font-normal">(JSON for charts/tables, plain text for text)</span>
            </Label>
            <Textarea
              v-model="newTemplate.dataJson"
              rows="4"
              :placeholder="newTemplate.category === 'chart'
                ? '{ &quot;x_axis&quot;: [&quot;Q1&quot;, &quot;Q2&quot;], &quot;y_axis&quot;: [100, 200], &quot;label&quot;: &quot;Revenue&quot; }'
                : newTemplate.category === 'table'
                  ? '{ &quot;headers&quot;: [&quot;Col1&quot;, &quot;Col2&quot;], &quot;rows&quot;: [[&quot;A&quot;, &quot;B&quot;]] }'
                  : 'Your template text content...'"
              class="text-xs font-mono bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.08)] rounded-lg resize-none placeholder:text-zinc-600"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] rounded-lg"
            @click="showCreateDialog = false"
          >
            Cancel
          </Button>
          <Button
            class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 rounded-lg"
            :disabled="!newTemplate.name.trim() || !newTemplate.description.trim()"
            @click="createTemplate"
          >
            Create Template
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
