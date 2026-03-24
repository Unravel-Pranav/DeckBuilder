<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTemplatesStore, type LibraryCategoryFilter } from '@/stores/templates'
import GlassCard from '@/components/shared/GlassCard.vue'
import EmptyState from '@/components/shared/EmptyState.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import type { BackendTemplate } from '@/lib/api'
import {
  Search,
  Upload,
  BarChart3,
  Table2,
  FileText,
  LayoutTemplate,
  Grid3x3,
  List,
  PanelTop,
  CalendarCheck,
  Copy,
} from 'lucide-vue-next'

const templatesStore = useTemplatesStore()

const showDetailDialog = ref(false)
const selectedBackendTemplate = ref<BackendTemplate | null>(null)

function openTemplateDetail(tmpl: BackendTemplate) {
  selectedBackendTemplate.value = tmpl
  showDetailDialog.value = true
}

function copyToClipboard(text: string) {
  void navigator.clipboard.writeText(text)
}

onMounted(() => {
  templatesStore.loadBackendTemplates()
})

const viewMode = ref<'grid' | 'list'>('grid')

const libraryFilterTabs: { id: LibraryCategoryFilter; label: string; icon: typeof BarChart3 }[] = [
  { id: 'all', label: 'All', icon: LayoutTemplate },
  { id: 'chart', label: 'Charts', icon: BarChart3 },
  { id: 'table', label: 'Tables', icon: Table2 },
  { id: 'front_page', label: 'Cover', icon: PanelTop },
  { id: 'base', label: 'Slide base', icon: LayoutTemplate },
  { id: 'last_page', label: 'Closing', icon: CalendarCheck },
  { id: 'other', label: 'Other', icon: FileText },
]

const pptCategoryIcons: Record<string, typeof BarChart3> = {
  chart: BarChart3,
  table: Table2,
  front_page: PanelTop,
  last_page: CalendarCheck,
  base: LayoutTemplate,
  other: FileText,
}

const pptCategoryColors: Record<string, string> = {
  chart: 'text-blue-400',
  table: 'text-emerald-400',
  front_page: 'text-amber-500',
  last_page: 'text-purple-400',
  base: 'text-zinc-400',
  other: 'text-zinc-500',
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function getBarHeights(data: number[]): number[] {
  const max = Math.max(...data)
  return data.map((v) => (max > 0 ? (v / max) * 100 : 0))
}

type PptPreviewKind = 'bar' | 'line' | 'pie' | 'horizontal' | 'slide-shell' | 'table' | 'generic'

function pptPreviewKind(tmpl: BackendTemplate): PptPreviewKind {
  const c = tmpl.category
  if (c === 'table') return 'table'
  if (c === 'front_page' || c === 'last_page' || c === 'base') return 'slide-shell'
  if (c !== 'chart') return 'generic'
  const ct = (tmpl.chart_type || '').toLowerCase()
  if (ct.includes('pie') || ct.includes('donut')) return 'pie'
  if (ct.includes('horizontal')) return 'horizontal'
  if (ct.includes('line') || ct.includes('combo')) return 'line'
  return 'bar'
}

const pptDemoBarData = [40, 65, 45, 80, 55, 70]
const pptDemoLineData = [12, 28, 22, 45, 38, 62]

function pptLinePoints(data: number[], heightScale = 1): string {
  const max = Math.max(...data)
  if (max <= 0) return ''
  return data
    .map((v, i) => `${(i / Math.max(data.length - 1, 1)) * 120},${50 - (v / max) * 44 * heightScale}`)
    .join(' ')
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
            Templates
          </h2>
        </div>
        <p class="text-sm text-zinc-500 ml-10">
          PowerPoint layouts registered with the PPT engine (server).
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
      </div>
    </div>

    <!-- Loading -->
    <div v-if="templatesStore.isLoadingBackend" class="flex flex-col items-center justify-center py-20">
      <div class="animate-spin w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full" />
      <span class="mt-4 text-sm text-zinc-500">Loading templates…</span>
    </div>

    <template v-else>
      <!-- Category filters -->
      <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-8">
        <GlassCard
          v-for="tab in libraryFilterTabs"
          :key="tab.id"
          :highlighted="templatesStore.libraryCategoryFilter === tab.id"
          hoverable
          padding="p-3"
          @click="templatesStore.setLibraryCategoryFilter(tab.id)"
        >
          <div class="flex items-center gap-2">
            <component
              :is="tab.icon"
              :size="14"
              :stroke-width="1.5"
              :class="templatesStore.libraryCategoryFilter === tab.id ? 'text-amber-500' : 'text-zinc-500'"
            />
            <span
              class="text-xs font-medium truncate"
              :class="templatesStore.libraryCategoryFilter === tab.id ? 'text-amber-500' : 'text-zinc-400'"
            >
              {{ tab.label }}
            </span>
          </div>
          <p
            class="text-xl font-display font-bold mt-1"
            :class="templatesStore.libraryCategoryFilter === tab.id ? 'text-amber-500' : 'text-zinc-300'"
          >
            {{ templatesStore.libraryCategoryCounts[tab.id] }}
          </p>
        </GlassCard>
      </div>

      <!-- Search + view -->
      <div class="flex items-center gap-3 mb-6">
        <div class="relative flex-1">
          <Search :size="16" :stroke-width="1.5" class="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
          <Input
            :model-value="templatesStore.searchQuery"
            placeholder="Search by name, filename, or chart/table type…"
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

      <EmptyState
        v-if="templatesStore.filteredLibraryTemplates.length === 0"
        :icon="LayoutTemplate"
        title="No templates found"
        :description="
          templatesStore.searchQuery
            ? 'Try a different search term.'
            : templatesStore.backendPptTemplates.length === 0
              ? 'The server returned no templates. Is the API running?'
              : 'Nothing matches this category filter.'
        "
      />

      <!-- Grid -->
      <div
        v-else-if="viewMode === 'grid'"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
      >
        <div
          v-for="tmpl in templatesStore.filteredLibraryTemplates"
          :key="tmpl.filename"
          class="group rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(26,26,36,0.6)] hover:border-amber-500/20 transition-all duration-300 overflow-hidden cursor-pointer hover:shadow-[0_0_20px_rgba(245,158,11,0.06)] active:scale-[0.99]"
          style="backdrop-filter: blur(8px)"
          role="button"
          tabindex="0"
          @click="openTemplateDetail(tmpl)"
          @keydown.enter.prevent="openTemplateDetail(tmpl)"
        >
          <div class="h-28 bg-[rgba(10,10,15,0.5)] flex items-center justify-center p-3 relative overflow-hidden">
            <Badge
              variant="secondary"
              class="absolute top-2 left-2 z-10 text-[8px] bg-amber-500/15 text-amber-500 border-amber-500/20 rounded-full px-1.5"
            >
              .pptx
            </Badge>
            <template v-if="pptPreviewKind(tmpl) === 'bar'">
              <div class="flex items-end gap-1 w-full h-full px-1 pt-2">
                <div
                  v-for="(val, i) in getBarHeights(pptDemoBarData)"
                  :key="i"
                  class="flex-1 rounded-t transition-all"
                  :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.5)', minHeight: '4px' }"
                />
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'line'">
              <svg class="w-full h-full" viewBox="0 0 120 50" preserveAspectRatio="none">
                <polyline
                  fill="none"
                  stroke="#F59E0B"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  :points="pptLinePoints(pptDemoLineData, 1)"
                  opacity="0.85"
                />
                <polyline
                  fill="none"
                  stroke="#71717A"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  :points="pptLinePoints(pptDemoLineData, 0.72)"
                  opacity="0.6"
                />
              </svg>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'pie'">
              <div class="relative w-16 h-16 flex items-center justify-center">
                <div
                  class="w-14 h-14 rounded-full"
                  :style="{
                    background: 'conic-gradient(#F59E0B 0% 42%, #FBBF24 42% 72%, #D97706 72% 100%)',
                    opacity: 0.75,
                  }"
                />
                <div
                  v-if="(tmpl.chart_type || '').toLowerCase().includes('donut')"
                  class="absolute w-7 h-7 rounded-full bg-[rgba(10,10,15,0.92)]"
                />
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'horizontal'">
              <div class="flex flex-col justify-center gap-1.5 w-full h-full px-2 py-1">
                <div v-for="row in 4" :key="row" class="flex items-center gap-2">
                  <div class="h-2 flex-1 rounded-sm bg-zinc-800/80" />
                  <div
                    class="h-2 rounded-sm bg-amber-500/50"
                    :style="{ width: `${[55, 72, 48, 65][row - 1]}%` }"
                  />
                </div>
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'table'">
              <div class="w-full space-y-1.5 px-1">
                <div class="flex gap-1.5">
                  <div v-for="i in 4" :key="i" class="flex-1 h-2 rounded-sm bg-amber-500/30" />
                </div>
                <div v-for="r in 3" :key="r" class="flex gap-1.5">
                  <div v-for="c in 4" :key="c" class="flex-1 h-1.5 rounded-sm bg-zinc-800" />
                </div>
              </div>

            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'slide-shell'">
              <div class="w-full h-full relative rounded-sm">
                <div class="absolute top-[8%] left-[6%] right-[6%] h-[8%] rounded-sm bg-amber-500/20" />
                <div class="absolute top-[22%] left-[6%] w-[55%] h-[4%] rounded-sm bg-zinc-700/80" />
                <div class="absolute top-[32%] left-[6%] w-[40%] h-[3%] rounded-sm bg-zinc-800/90" />
                <div
                  v-if="tmpl.category === 'base'"
                  class="absolute bottom-[12%] left-[6%] right-[6%] top-[42%] rounded border border-dashed border-zinc-700/60 bg-zinc-900/30"
                />
                <div
                  v-else
                  class="absolute bottom-[18%] left-[6%] right-[30%] h-[20%] rounded-sm bg-zinc-800/50"
                />
              </div>
            </template>
            <template v-else>
              <component
                :is="pptCategoryIcons[tmpl.category] ?? FileText"
                :size="28"
                :stroke-width="1"
                :class="pptCategoryColors[tmpl.category] ?? 'text-zinc-500'"
                style="opacity: 0.6"
              />
            </template>
          </div>
          <div class="p-3">
            <h4 class="text-xs font-medium text-zinc-300 truncate mb-0.5">{{ tmpl.name }}</h4>
            <div class="flex items-center gap-1.5 flex-wrap">
              <Badge variant="secondary" class="text-[8px] bg-white/5 text-zinc-500 border-none rounded-full px-1.5 capitalize">
                {{ tmpl.category.replace('_', ' ') }}
              </Badge>
              <Badge v-if="tmpl.chart_type" variant="secondary" class="text-[8px] bg-blue-500/10 text-blue-400 border-none rounded-full px-1.5">
                {{ tmpl.chart_type }}
              </Badge>
              <Badge v-if="tmpl.table_type" variant="secondary" class="text-[8px] bg-emerald-500/10 text-emerald-400 border-none rounded-full px-1.5">
                {{ tmpl.table_type }}
              </Badge>
            </div>
            <p class="text-[9px] font-mono text-zinc-700 mt-1.5">{{ tmpl.filename }} · {{ formatFileSize(tmpl.size) }}</p>
          </div>
        </div>
      </div>

      <!-- List -->
      <div v-else class="space-y-2">
        <div
          v-for="tmpl in templatesStore.filteredLibraryTemplates"
          :key="tmpl.filename"
          class="flex items-center gap-4 px-4 py-3 rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(26,26,36,0.6)] cursor-pointer hover:border-amber-500/25 transition-colors"
          style="backdrop-filter: blur(8px)"
          role="button"
          tabindex="0"
          @click="openTemplateDetail(tmpl)"
          @keydown.enter.prevent="openTemplateDetail(tmpl)"
        >
          <div class="w-28 h-16 rounded-lg bg-[rgba(10,10,15,0.5)] flex items-center justify-center overflow-hidden flex-shrink-0 relative p-1.5">
            <template v-if="pptPreviewKind(tmpl) === 'bar'">
              <div class="flex items-end gap-0.5 w-full h-full">
                <div
                  v-for="(val, i) in getBarHeights(pptDemoBarData)"
                  :key="i"
                  class="flex-1 rounded-t"
                  :style="{ height: `${val * 0.85}%`, backgroundColor: 'rgba(245, 158, 11, 0.5)', minHeight: '3px' }"
                />
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'line'">
              <svg class="w-full h-full" viewBox="0 0 120 50" preserveAspectRatio="none">
                <polyline
                  fill="none"
                  stroke="#F59E0B"
                  stroke-width="2"
                  :points="pptLinePoints(pptDemoLineData, 1)"
                  opacity="0.85"
                />
              </svg>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'pie'">
              <div
                class="w-10 h-10 rounded-full"
                :style="{
                  background: 'conic-gradient(#F59E0B 0% 42%, #FBBF24 42% 100%)',
                  opacity: 0.75,
                }"
              />
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'horizontal'">
              <div class="flex flex-col gap-1 w-full justify-center">
                <div v-for="row in 3" :key="row" class="flex gap-1 items-center">
                  <div class="h-1 flex-1 rounded-sm bg-zinc-800" />
                  <div class="h-1 w-1/2 rounded-sm bg-amber-500/50" />
                </div>
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'table'">
              <div class="w-full space-y-1">
                <div class="flex gap-1">
                  <div v-for="i in 3" :key="i" class="flex-1 h-1.5 rounded-sm bg-amber-500/30" />
                </div>
                <div v-for="r in 2" :key="r" class="flex gap-1">
                  <div v-for="c in 3" :key="c" class="flex-1 h-1 rounded-sm bg-zinc-800" />
                </div>
              </div>
            </template>
            <template v-else-if="pptPreviewKind(tmpl) === 'slide-shell'">
              <div class="w-full h-full relative">
                <div class="absolute inset-0 top-0 h-[20%] rounded-sm bg-amber-500/20" />
                <div class="absolute bottom-1 left-0 right-0 h-[35%] rounded-sm bg-zinc-800/40" />
              </div>
            </template>
            <component
              v-else
              :is="pptCategoryIcons[tmpl.category] ?? FileText"
              :size="22"
              :stroke-width="1"
              :class="pptCategoryColors[tmpl.category] ?? 'text-zinc-500'"
              class="opacity-60"
            />
          </div>
          <div class="flex-1 min-w-0">
            <h4 class="text-sm font-medium text-zinc-300 truncate">{{ tmpl.name }}</h4>
            <p class="text-[11px] font-mono text-zinc-600 truncate">{{ tmpl.filename }} · {{ formatFileSize(tmpl.size) }}</p>
          </div>
          <Badge variant="secondary" class="text-[9px] capitalize flex-shrink-0">
            {{ tmpl.category.replace('_', ' ') }}
          </Badge>
        </div>
      </div>

      <div v-if="templatesStore.backendError" class="mt-6 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs text-center">
        {{ templatesStore.backendError }} — ensure the API is reachable (e.g. localhost:8000).
      </div>
    </template>

    <!-- Template detail (backend .pptx metadata + preview) -->
    <Dialog v-model:open="showDetailDialog">
      <DialogContent
        v-if="selectedBackendTemplate"
        class="bg-[#12121A] border-[rgba(255,255,255,0.08)] rounded-xl max-w-lg"
      >
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight flex items-center gap-2">
            <component
              :is="pptCategoryIcons[selectedBackendTemplate.category] ?? FileText"
              :size="18"
              :stroke-width="1.5"
              class="text-amber-500"
            />
            {{ selectedBackendTemplate.name }}
          </DialogTitle>
          <DialogDescription class="text-xs text-zinc-500 text-left">
            Engine template file from the server (<code class="text-zinc-600">individual_templates</code>).
            The generator selects it when your deck JSON uses the matching chart or table type.
          </DialogDescription>
        </DialogHeader>

        <div class="h-44 rounded-lg bg-[rgba(10,10,15,0.5)] border border-[rgba(255,255,255,0.06)] flex items-center justify-center p-4 relative overflow-hidden">
          <template v-if="pptPreviewKind(selectedBackendTemplate) === 'bar'">
            <div class="flex items-end gap-1.5 w-full h-full px-2 pt-3">
              <div
                v-for="(val, i) in getBarHeights(pptDemoBarData)"
                :key="i"
                class="flex-1 rounded-t"
                :style="{ height: `${val}%`, backgroundColor: 'rgba(245, 158, 11, 0.55)', minHeight: '6px' }"
              />
            </div>
          </template>
          <template v-else-if="pptPreviewKind(selectedBackendTemplate) === 'line'">
            <svg class="w-full max-h-full" viewBox="0 0 120 50" preserveAspectRatio="none">
              <polyline
                fill="none"
                stroke="#F59E0B"
                stroke-width="2"
                stroke-linecap="round"
                :points="pptLinePoints(pptDemoLineData, 1)"
                opacity="0.85"
              />
              <polyline
                fill="none"
                stroke="#71717A"
                stroke-width="1.5"
                stroke-linecap="round"
                :points="pptLinePoints(pptDemoLineData, 0.72)"
                opacity="0.6"
              />
            </svg>
          </template>
          <template v-else-if="pptPreviewKind(selectedBackendTemplate) === 'pie'">
            <div class="relative w-24 h-24 flex items-center justify-center">
              <div
                class="w-[5.5rem] h-[5.5rem] rounded-full"
                :style="{
                  background: 'conic-gradient(#F59E0B 0% 42%, #FBBF24 42% 72%, #D97706 72% 100%)',
                  opacity: 0.8,
                }"
              />
              <div
                v-if="(selectedBackendTemplate.chart_type || '').toLowerCase().includes('donut')"
                class="absolute w-12 h-12 rounded-full bg-[rgba(10,10,15,0.92)]"
              />
            </div>
          </template>
          <template v-else-if="pptPreviewKind(selectedBackendTemplate) === 'horizontal'">
            <div class="flex flex-col justify-center gap-2 w-full h-full px-4">
              <div v-for="row in 4" :key="row" class="flex items-center gap-2">
                <div class="h-2.5 flex-1 rounded-sm bg-zinc-800/80" />
                <div
                  class="h-2.5 rounded-sm bg-amber-500/50"
                  :style="{ width: `${[55, 72, 48, 65][row - 1]}%` }"
                />
              </div>
            </div>
          </template>
          <template v-else-if="pptPreviewKind(selectedBackendTemplate) === 'table'">
            <div class="w-full space-y-2 px-2">
              <div class="flex gap-2">
                <div v-for="i in 4" :key="i" class="flex-1 h-2.5 rounded-sm bg-amber-500/30" />
              </div>
              <div v-for="r in 3" :key="r" class="flex gap-2">
                <div v-for="c in 4" :key="c" class="flex-1 h-2 rounded-sm bg-zinc-800" />
              </div>
            </div>
          </template>
          <template v-else-if="pptPreviewKind(selectedBackendTemplate) === 'slide-shell'">
            <div class="w-full h-full relative rounded-md">
              <div class="absolute top-[8%] left-[6%] right-[6%] h-[10%] rounded-sm bg-amber-500/20" />
              <div class="absolute top-[24%] left-[6%] w-[55%] h-[5%] rounded-sm bg-zinc-700/80" />
              <div class="absolute top-[36%] left-[6%] w-[40%] h-[4%] rounded-sm bg-zinc-800/90" />
              <div
                v-if="selectedBackendTemplate.category === 'base'"
                class="absolute bottom-[10%] left-[6%] right-[6%] top-[48%] rounded border border-dashed border-zinc-700/60 bg-zinc-900/30"
              />
              <div
                v-else
                class="absolute bottom-[16%] left-[6%] right-[28%] h-[22%] rounded-sm bg-zinc-800/50"
              />
            </div>
          </template>
          <template v-else>
            <component
              :is="pptCategoryIcons[selectedBackendTemplate.category] ?? FileText"
              :size="40"
              :stroke-width="1"
              :class="pptCategoryColors[selectedBackendTemplate.category] ?? 'text-zinc-500'"
              class="opacity-70"
            />
          </template>
        </div>

        <div class="space-y-2 py-2 text-sm">
          <div class="grid grid-cols-2 gap-2">
            <div class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">File</p>
              <p class="text-xs font-mono text-zinc-300 break-all">{{ selectedBackendTemplate.filename }}</p>
            </div>
            <div class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Size</p>
              <p class="text-xs text-zinc-300">{{ formatFileSize(selectedBackendTemplate.size) }}</p>
            </div>
            <div class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)]">
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Category</p>
              <p class="text-xs text-zinc-300 capitalize">{{ selectedBackendTemplate.category.replace('_', ' ') }}</p>
            </div>
            <div
              v-if="selectedBackendTemplate.chart_type"
              class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)] col-span-2"
            >
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Chart type (JSON)</p>
              <p class="text-xs text-zinc-300">{{ selectedBackendTemplate.chart_type }}</p>
            </div>
            <div
              v-if="selectedBackendTemplate.table_type"
              class="p-3 rounded-lg bg-white/[0.02] border border-[rgba(255,255,255,0.04)] col-span-2"
            >
              <p class="text-[9px] font-mono uppercase tracking-wider text-zinc-600 mb-1">Table type (JSON)</p>
              <p class="text-xs text-zinc-300">{{ selectedBackendTemplate.table_type }}</p>
            </div>
          </div>
          <p class="text-[11px] text-zinc-600 leading-relaxed">
            Illustration above is a quick category preview, not a pixel-perfect render of the .pptx slide.
          </p>
        </div>

        <DialogFooter class="gap-2 sm:gap-2">
          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] rounded-lg"
            @click="copyToClipboard(selectedBackendTemplate.filename)"
          >
            <Copy :size="14" :stroke-width="1.5" class="mr-1.5" />
            Copy filename
          </Button>
          <Button class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 rounded-lg" @click="showDetailDialog = false">
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
