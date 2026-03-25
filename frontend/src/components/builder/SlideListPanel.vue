<script setup lang="ts">
import { ref } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { useTemplatesStore } from '@/stores/templates'
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
  PanelTop,
  SplitSquareVertical,
  CalendarCheck,
  Users,
  Clock,
  Columns2,
  Quote,
  Square,
  Presentation,
} from 'lucide-vue-next'
import type { LayoutType, SlideTemplate, SlidePreviewData, SlideComponent } from '@/types'

const slidesStore = useSlidesStore()
const templatesStore = useTemplatesStore()

const showAddDialog = ref(false)
const addToSectionId = ref<string | null>(null)

const slideKindIcons: Record<string, typeof PanelTop> = {
  title: PanelTop,
  'section-divider': SplitSquareVertical,
  closing: CalendarCheck,
  agenda: FileText,
  team: Users,
  timeline: Clock,
  comparison: Columns2,
  quote: Quote,
  kpi: Plus,
  content: FileText,
  blank: Square,
}

function openAddDialog(sectionId: string) {
  addToSectionId.value = sectionId
  showAddDialog.value = true
}

function addBlankSlide() {
  if (!addToSectionId.value) return
  slidesStore.addSlide(addToSectionId.value, 'chart-commentary' as LayoutType)
  showAddDialog.value = false
}

function addFromTemplate(tmpl: SlideTemplate) {
  if (!addToSectionId.value) return
  const sectionId = addToSectionId.value
  const layout = tmpl.defaultLayout ?? 'commentary-only'

  slidesStore.addSlide(sectionId, layout)

  const slide = slidesStore.activeSlide
  if (!slide) return

  slide.title = tmpl.name
  if (tmpl.defaultComponents?.length) {
    slidesStore.updateSlideComponents(
      slide.id,
      tmpl.defaultComponents.map((c) => ({ ...c, id: crypto.randomUUID() })) as SlideComponent[],
    )
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
                <FileText
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
                <p class="text-[9px] font-mono text-muted-foreground/50 truncate">{{ slide.layout }}</p>
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

    <!-- Add slide dialog (template picker) -->
    <Dialog v-model:open="showAddDialog">
      <DialogContent class="bg-popover border-border rounded-xl max-w-md max-h-[70vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight">Add Slide</DialogTitle>
        </DialogHeader>

        <div class="flex-1 overflow-y-auto space-y-4 pr-1">
          <!-- Blank slide option -->
          <button
            class="w-full flex items-center gap-3 p-3 rounded-lg border border-dashed border-border hover:border-amber-500/30 hover:bg-amber-500/5 transition-all duration-200 text-left"
            @click="addBlankSlide"
          >
            <div class="w-10 h-10 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
              <Plus :size="18" :stroke-width="1.5" class="text-muted-foreground" />
            </div>
            <div>
              <p class="text-sm font-medium text-foreground/80">Blank Slide</p>
              <p class="text-[10px] text-muted-foreground/70">Start from scratch with Chart + Text layout</p>
            </div>
          </button>

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
                <!-- Slide kind icon -->
                <div class="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                  <component
                    :is="slideKindIcons[tmpl.slideKind ?? 'content'] ?? Presentation"
                    :size="16"
                    :stroke-width="1.5"
                    class="text-amber-500"
                  />
                </div>

                <!-- Mini preview -->
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
