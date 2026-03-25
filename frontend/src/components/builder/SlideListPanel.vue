<script setup lang="ts">
import { ref } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useTemplatesStore } from '@/stores/templates'
import { STRUCTURE_REGISTRY } from '@/lib/layoutDefinitions'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Plus,
  FileText,
  Square,
  Columns2,
  Rows2,
  Grid2x2,
  PanelTop,
  SplitSquareVertical,
  CalendarCheck,
  Users,
  Clock,
  Presentation,
} from 'lucide-vue-next'
import type { SlideStructure, SlideTemplate, SlidePreviewData, SlideComponent } from '@/types'
import { createRegions } from '@/types'

const slidesStore = useSlidesStore()
const templatesStore = useTemplatesStore()

const showAddDialog = ref(false)
const addToSectionId = ref<string | null>(null)

const STRUCTURE_ICONS: Record<SlideStructure, typeof Square> = {
  'blank': Square,
  'two-col': Columns2,
  'two-row': Rows2,
  'grid-2x2': Grid2x2,
}

const STRUCTURE_LABELS: Record<SlideStructure, string> = {
  'blank': 'Blank',
  'two-col': 'V-Split',
  'two-row': 'H-Split',
  'grid-2x2': '2×2',
}

const slideKindIcons: Record<string, typeof PanelTop> = {
  title: PanelTop,
  'section-divider': SplitSquareVertical,
  closing: CalendarCheck,
  team: Users,
  timeline: Clock,
  content: FileText,
  blank: Square,
}

function openAddDialog(sectionId: string) {
  addToSectionId.value = sectionId
  showAddDialog.value = true
}

function addWithStructure(structure: SlideStructure) {
  if (!addToSectionId.value) return
  slidesStore.addSlide(addToSectionId.value, structure)
  showAddDialog.value = false
}

function addFromTemplate(tmpl: SlideTemplate) {
  if (!addToSectionId.value) return
  const sectionId = addToSectionId.value
  const structure = tmpl.defaultStructure ?? 'blank'

  slidesStore.addSlide(sectionId, structure)

  const slide = slidesStore.activeSlide
  if (!slide) return

  slide.title = tmpl.name
  if (tmpl.defaultComponents?.length) {
    const comps = tmpl.defaultComponents.map((c) => ({ ...c, id: crypto.randomUUID() })) as SlideComponent[]
    for (let i = 0; i < Math.min(comps.length, slide.regions.length); i++) {
      slide.regions[i].component = comps[i]
    }
  }
  const textComp = tmpl.defaultComponents?.find((c) => c.type === 'text')
  if (textComp && 'data' in textComp && (textComp.data as any)?.content) {
    slide.commentary = (textComp.data as any).content
    slide.commentarySource = 'manual'
  }

  showAddDialog.value = false
}

function isSlidePreviewData(data: unknown): data is SlidePreviewData {
  return typeof data === 'object' && data !== null && 'elements' in data
}
</script>

<template>
  <div class="flex flex-col h-full border-r border-border" :style="{ background: 'var(--surface-elevated)' }">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-border">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-mono uppercase tracking-wider text-muted-foreground">Slides</h3>
        <span class="text-[10px] font-mono text-muted-foreground/70">{{ slidesStore.totalSlideCount }}</span>
      </div>
    </div>

    <!-- Scrollable list -->
    <ScrollArea class="flex-1">
      <div class="p-3 space-y-4">
        <div v-for="section in slidesStore.sections" :key="section.id">
          <!-- Section label -->
          <p class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 mb-2 px-1 truncate">
            {{ section.name }}
          </p>

          <!-- Slide thumbnails -->
          <div class="space-y-1.5">
            <button
              v-for="slide in section.slides"
              :key="slide.id"
              class="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-all duration-200"
              :class="
                slidesStore.activeSlideId === slide.id
                  ? 'bg-amber-500/10 border border-amber-500/20 shadow-[0_0_12px_rgba(245,158,11,0.1)]'
                  : 'bg-foreground/[0.03] border border-transparent hover:bg-foreground/[0.06] hover:border-border'
              "
              @click="slidesStore.setActiveSlide(slide.id)"
            >
              <div
                class="flex-shrink-0 w-10 h-7 rounded border flex items-center justify-center"
                :class="
                  slidesStore.activeSlideId === slide.id
                    ? 'border-amber-500/30 bg-amber-500/5'
                    : 'border-border bg-muted'
                "
              >
                <component
                  :is="STRUCTURE_ICONS[slide.structure] ?? FileText"
                  :size="10"
                  :stroke-width="1.5"
                  :class="slidesStore.activeSlideId === slide.id ? 'text-amber-500' : 'text-muted-foreground/50'"
                />
              </div>

              <div class="flex-1 min-w-0">
                <p
                  class="text-[11px] font-medium truncate"
                  :class="slidesStore.activeSlideId === slide.id ? 'text-amber-500' : 'text-muted-foreground'"
                >
                  {{ slide.title }}
                </p>
                <p class="text-[9px] font-mono text-muted-foreground/50 truncate">
                  {{ STRUCTURE_LABELS[slide.structure] ?? slide.structure }}
                  · {{ slide.regions.filter(r => r.component).length }}/{{ slide.regions.length }} filled
                </p>
              </div>
            </button>

            <!-- Add slide to section -->
            <button
              class="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-dashed border-border text-muted-foreground/50 hover:text-muted-foreground hover:border-border transition-all text-[11px]"
              @click="openAddDialog(section.id)"
            >
              <Plus :size="12" :stroke-width="1.5" />
              Add
            </button>
          </div>
        </div>
      </div>
    </ScrollArea>

    <!-- Add slide dialog -->
    <Dialog v-model:open="showAddDialog">
      <DialogContent class="bg-popover border-border rounded-xl max-w-md max-h-[70vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight">Add Slide</DialogTitle>
        </DialogHeader>

        <div class="flex-1 overflow-y-auto space-y-4 pr-1">
          <!-- Structure options -->
          <div>
            <p class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 mb-2 px-1">
              Choose Structure
            </p>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="def in STRUCTURE_REGISTRY"
                :key="def.id"
                class="flex items-center gap-3 p-3 rounded-lg border border-border bg-[var(--glass-bg)] hover:border-amber-500/30 hover:bg-amber-500/5 transition-all duration-200 text-left group"
                @click="addWithStructure(def.id)"
              >
                <div class="w-8 h-8 rounded-lg bg-foreground/5 group-hover:bg-amber-500/10 flex items-center justify-center flex-shrink-0 transition-colors">
                  <component
                    :is="STRUCTURE_ICONS[def.id]"
                    :size="14"
                    :stroke-width="1.5"
                    class="text-muted-foreground group-hover:text-amber-500 transition-colors"
                  />
                </div>
                <div>
                  <p class="text-xs font-medium text-foreground/80 group-hover:text-amber-500 transition-colors">{{ def.label }}</p>
                  <p class="text-[9px] text-muted-foreground/60">{{ def.regionCount }} region{{ def.regionCount > 1 ? 's' : '' }}</p>
                </div>
              </button>
            </div>
          </div>

          <!-- Slide templates -->
          <div>
            <p class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 mb-2 px-1">
              From Template
            </p>
            <div class="space-y-1.5">
              <button
                v-for="tmpl in templatesStore.getSlideTemplates()"
                :key="tmpl.id"
                class="w-full flex items-center gap-3 p-3 rounded-lg border border-border bg-[var(--glass-bg)] hover:border-[color:var(--glass-border-hover)] hover:bg-[var(--glass-bg-hover)] transition-all duration-200 text-left"
                @click="addFromTemplate(tmpl)"
              >
                <div class="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                  <component
                    :is="slideKindIcons[tmpl.slideKind ?? 'content'] ?? Presentation"
                    :size="16"
                    :stroke-width="1.5"
                    class="text-amber-500"
                  />
                </div>
                <div
                  class="flex-shrink-0 w-14 h-10 rounded border border-border bg-[var(--preview-surface)] relative overflow-hidden"
                >
                  <template v-if="isSlidePreviewData(tmpl.previewData)">
                    <div
                      v-for="(el, ei) in (tmpl.previewData as SlidePreviewData).elements.slice(0, 4)"
                      :key="ei"
                      class="absolute rounded-[1px]"
                      :class="
                        el.type === 'heading' ? 'bg-amber-500/25' :
                        el.type === 'accent-bar' ? 'bg-amber-500/40' :
                        el.type === 'divider' ? 'bg-muted-foreground/30' :
                        'bg-muted'
                      "
                      :style="{ left: `${el.x}%`, top: `${el.y}%`, width: `${el.w}%`, height: `${el.h}%` }"
                    />
                  </template>
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-xs font-medium text-foreground/80 truncate">{{ tmpl.name }}</p>
                  <p class="text-[10px] text-muted-foreground/70 line-clamp-1">{{ tmpl.description }}</p>
                </div>
              </button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
