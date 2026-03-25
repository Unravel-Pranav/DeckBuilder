<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Sortable } from 'sortablejs-vue3'
import type { SortableEvent } from 'sortablejs'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import GlassCard from '@/components/shared/GlassCard.vue'
import EmptyState from '@/components/shared/EmptyState.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  ArrowRight,
  GripVertical,
  Layers,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  FileText,
  PenLine,
} from 'lucide-vue-next'
import type { SlideStructure } from '@/types'
import { STRUCTURE_REGISTRY } from '@/lib/layoutDefinitions'

const router = useRouter()
const slidesStore = useSlidesStore()
const uiStore = useUiStore()

const expandedSections = ref<Set<string>>(new Set())
const showAddDialog = ref(false)
const newSectionName = ref('')
const newSectionDesc = ref('')

const editingSection = ref<string | null>(null)
const editName = ref('')

const showLayoutDialog = ref(false)
const pendingSectionId = ref<string | null>(null)

function toggleExpand(sectionId: string) {
  if (expandedSections.value.has(sectionId)) {
    expandedSections.value.delete(sectionId)
  } else {
    expandedSections.value.add(sectionId)
  }
}

function startEditing(sectionId: string, currentName: string) {
  editingSection.value = sectionId
  editName.value = currentName
}

function finishEditing(sectionId: string) {
  const section = slidesStore.sections.find((s) => s.id === sectionId)
  if (section && editName.value.trim()) {
    section.name = editName.value.trim()
  }
  editingSection.value = null
}

function addSection() {
  if (!newSectionName.value.trim()) return
  slidesStore.addSection(newSectionName.value.trim(), newSectionDesc.value.trim())
  newSectionName.value = ''
  newSectionDesc.value = ''
  showAddDialog.value = false
}

function openLayoutSelector(sectionId: string) {
  pendingSectionId.value = sectionId
  showLayoutDialog.value = true
}

function addSlideWithStructure(structure: SlideStructure) {
  if (pendingSectionId.value) {
    slidesStore.addSlide(pendingSectionId.value, structure)
  }
  showLayoutDialog.value = false
  pendingSectionId.value = null
}

function onSectionDragEnd(event: SortableEvent) {
  const { oldIndex, newIndex } = event
  if (oldIndex != null && newIndex != null && oldIndex !== newIndex) {
    const sections = [...slidesStore.sections]
    const [moved] = sections.splice(oldIndex, 1)
    sections.splice(newIndex, 0, moved)
    slidesStore.setSections(sections.map((s, i) => ({ ...s, order: i })))
  }
}

function onSlideDragEnd(sectionId: string, event: SortableEvent) {
  const { oldIndex, newIndex } = event
  if (oldIndex == null || newIndex == null || oldIndex === newIndex) return

  const section = slidesStore.sections.find((s) => s.id === sectionId)
  if (!section) return

  const slides = [...section.slides]
  const [moved] = slides.splice(oldIndex, 1)
  slides.splice(newIndex, 0, moved)
  section.slides = slides.map((s, i) => ({ ...s, order: i }))
}

function handleContinue() {
  uiStore.completeStep('sections')
  uiStore.setCurrentStep('builder')
  router.push('/builder')
}

const structureLabels: Record<string, string> = {
  'blank': 'Blank',
  'two-col': 'V-Split',
  'two-row': 'H-Split',
  'grid-2x2': '2×2 Grid',
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <div>
        <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight mb-1">
          Manage Sections
        </h2>
        <p class="text-sm text-muted-foreground">
          Drag sections and slides to reorder. Expand to manage individual slides.
        </p>
      </div>

      <Button
        variant="outline"
        class="border-border text-foreground/80 hover:bg-foreground/5 rounded-lg h-9 text-sm"
        @click="showAddDialog = true"
      >
        <Plus :size="14" :stroke-width="1.5" class="mr-1.5" />
        Add Section
      </Button>
    </div>

    <!-- Empty state -->
    <EmptyState
      v-if="slidesStore.sections.length === 0"
      :icon="Layers"
      title="No sections yet"
      description="Go back to AI Recommendations to generate sections, or add one manually."
    >
      <Button
        class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium rounded-xl"
        @click="showAddDialog = true"
      >
        <Plus :size="16" class="mr-1.5" />
        Add Section
      </Button>
    </EmptyState>

    <!-- Section list with drag-and-drop -->
    <div v-else class="space-y-3">
      <Sortable
        :list="slidesStore.sections"
        item-key="id"
        tag="div"
        class="space-y-3"
        :options="{
          animation: 250,
          handle: '.section-drag-handle',
          ghostClass: 'drag-ghost',
          chosenClass: 'drag-chosen',
        }"
        @end="onSectionDragEnd"
      >
        <template #item="{ element: section, index }">
          <GlassCard padding="p-0">
            <!-- Section header -->
            <div class="flex items-center gap-3 p-4">
              <!-- Drag handle -->
              <div class="flex items-center gap-1.5">
                <div class="section-drag-handle cursor-grab active:cursor-grabbing text-muted-foreground/50 hover:text-muted-foreground transition-colors p-0.5">
                  <GripVertical :size="16" :stroke-width="1.5" />
                </div>
                <button
                  class="p-1 rounded text-muted-foreground/70 hover:text-muted-foreground transition-colors"
                  @click="toggleExpand(section.id)"
                >
                  <component
                    :is="expandedSections.has(section.id) ? ChevronDown : ChevronRight"
                    :size="16"
                    :stroke-width="1.5"
                  />
                </button>
              </div>

              <!-- Section number -->
              <div
                class="flex-shrink-0 w-7 h-7 rounded-lg bg-amber-500/10 flex items-center justify-center text-[11px] font-mono text-amber-500 border border-amber-500/20"
              >
                {{ index + 1 }}
              </div>

              <!-- Name (editable) -->
              <div class="flex-1 min-w-0">
                <div v-if="editingSection === section.id" class="flex items-center gap-2">
                  <Input
                    v-model="editName"
                    class="h-8 text-sm bg-[var(--glass-bg)] border-amber-500/30 rounded-lg"
                    @keyup.enter="finishEditing(section.id)"
                    @blur="finishEditing(section.id)"
                  />
                </div>
                <div v-else class="group flex items-center gap-2 cursor-pointer" @click="startEditing(section.id, section.name)">
                  <h4 class="font-display font-semibold text-sm tracking-tight truncate">
                    {{ section.name }}
                  </h4>
                  <PenLine :size="12" :stroke-width="1.5" class="text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <p class="text-[11px] text-muted-foreground/70 truncate">
                  {{ section.description || 'No description' }} · {{ section.slides.length }} slides
                </p>
              </div>

              <!-- Delete -->
              <button
                class="p-1.5 rounded-lg text-muted-foreground/70 hover:text-red-400 hover:bg-red-500/10 transition-all"
                @click="slidesStore.removeSection(section.id)"
              >
                <Trash2 :size="14" :stroke-width="1.5" />
              </button>
            </div>

            <!-- Expanded slides list -->
            <Transition name="expand">
              <div
                v-if="expandedSections.has(section.id)"
                class="border-t border-border px-4 pb-4"
              >
                <div class="mt-3">
                  <Sortable
                    :list="section.slides"
                    item-key="id"
                    tag="div"
                    class="space-y-2"
                    :options="{
                      animation: 200,
                      handle: '.slide-drag-handle',
                      ghostClass: 'drag-ghost',
                    }"
                    @end="(e: SortableEvent) => onSlideDragEnd(section.id, e)"
                  >
                    <template #item="{ element: slide }">
                      <div class="flex items-center gap-3 py-2 px-3 rounded-lg bg-foreground/[0.02] hover:bg-foreground/[0.04] transition-colors">
                        <div class="slide-drag-handle cursor-grab active:cursor-grabbing text-muted-foreground/50 hover:text-muted-foreground transition-colors">
                          <GripVertical :size="14" :stroke-width="1.5" />
                        </div>
                        <FileText :size="14" :stroke-width="1.5" class="text-muted-foreground/70 flex-shrink-0" />
                        <span class="text-sm text-muted-foreground flex-1 truncate">{{ slide.title }}</span>
                        <span class="text-[10px] font-mono text-muted-foreground/70 bg-muted/50 px-2 py-0.5 rounded">
                          {{ structureLabels[slide.structure] ?? slide.structure }}
                        </span>
                        <button
                          class="p-1 rounded text-muted-foreground/50 hover:text-red-400 transition-colors"
                          @click="slidesStore.removeSlide(section.id, slide.id)"
                        >
                          <Trash2 :size="12" :stroke-width="1.5" />
                        </button>
                      </div>
                    </template>
                  </Sortable>

                  <!-- Add slide button -->
                  <button
                    class="flex items-center gap-2 w-full py-2 px-3 mt-2 rounded-lg border border-dashed border-border text-muted-foreground/70 hover:text-muted-foreground hover:border-border transition-all text-sm"
                    @click="openLayoutSelector(section.id)"
                  >
                    <Plus :size="14" :stroke-width="1.5" />
                    Add Slide
                  </button>
                </div>
              </div>
            </Transition>
          </GlassCard>
        </template>
      </Sortable>

      <!-- Continue -->
      <div class="flex justify-end pt-6">
        <Button
          class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-12 px-8 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98] text-base"
          @click="handleContinue"
        >
          Continue to Builder
          <ArrowRight :size="18" :stroke-width="2" class="ml-2" />
        </Button>
      </div>
    </div>

    <!-- Add Section Dialog -->
    <Dialog v-model:open="showAddDialog">
      <DialogContent class="bg-popover border-border rounded-xl max-w-md">
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight">Add New Section</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div>
            <label class="text-sm font-medium text-foreground/80 mb-1.5 block">Section Name</label>
            <Input
              v-model="newSectionName"
              placeholder="e.g., Market Analysis"
              class="h-11 bg-[var(--glass-bg)] border-border rounded-xl placeholder:text-muted-foreground/50"
            />
          </div>
          <div>
            <label class="text-sm font-medium text-foreground/80 mb-1.5 block">Description</label>
            <Input
              v-model="newSectionDesc"
              placeholder="Brief description of this section..."
              class="h-11 bg-[var(--glass-bg)] border-border rounded-xl placeholder:text-muted-foreground/50"
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            class="border-border rounded-lg"
            @click="showAddDialog = false"
          >
            Cancel
          </Button>
          <Button
            class="bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg"
            @click="addSection"
          >
            Add Section
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Structure Selector Dialog -->
    <Dialog v-model:open="showLayoutDialog">
      <DialogContent class="bg-popover border-border rounded-xl max-w-lg">
        <DialogHeader>
          <DialogTitle class="font-display tracking-tight">Choose Slide Structure</DialogTitle>
        </DialogHeader>
        <div class="grid grid-cols-2 gap-3 py-2">
          <button
            v-for="def in STRUCTURE_REGISTRY"
            :key="def.id"
            class="p-4 rounded-xl border border-border bg-[var(--glass-bg)] hover:border-amber-500/30 hover:bg-amber-500/5 transition-all duration-200 text-left group"
            @click="addSlideWithStructure(def.id)"
          >
            <h4 class="text-sm font-medium text-foreground/80 group-hover:text-amber-500 transition-colors mb-1">
              {{ def.label }}
            </h4>
            <p class="text-[10px] text-muted-foreground/70 leading-relaxed">{{ def.tooltip }}</p>
          </button>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            class="border-border rounded-lg"
            @click="showLayoutDialog = false"
          >
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.drag-ghost {
  opacity: 0.4;
}
.drag-chosen {
  box-shadow: 0 0 30px rgba(245, 158, 11, 0.15);
  border-radius: 12px;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 300ms ease;
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
.expand-enter-to,
.expand-leave-from {
  max-height: 600px;
}
</style>
