<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import { usePresentationStore } from '@/stores/presentation'
import { useDeckTemplateStore } from '@/stores/deckTemplate'
import { transformToBackendFormat, generatePPT, downloadFile, deckTemplatePptDownloadUrl } from '@/lib/api'
import { mockSections } from '@/lib/mockData'
import { STRUCTURE_BY_ID, CATEGORY_LABELS } from '@/lib/layoutDefinitions'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Edit3,
  Loader2,
  BarChart3,
  Table2,
  FileText,
  Columns2,
  Rows3,
  Grid2x2,
} from 'lucide-vue-next'

const router = useRouter()
const slidesStore = useSlidesStore()
const uiStore = useUiStore()
const presentationStore = usePresentationStore()
const deckTemplateStore = useDeckTemplateStore()

const currentSlideIndex = ref(0)
const isGenerating = ref(false)
const generateProgress = ref(0)
const errorMessage = ref<string | null>(null)

onMounted(() => {
  if (slidesStore.sections.length === 0) {
    slidesStore.setSections(mockSections)
  }
})

const allSlides = computed(() => slidesStore.allSlides)
const currentSlide = computed(() => allSlides.value[currentSlideIndex.value])
const sectionForSlide = computed(() => {
  if (!currentSlide.value) return null
  return slidesStore.sections.find((s) =>
    s.slides.some((sl) => sl.id === currentSlide.value!.id),
  )
})

function prevSlide() {
  if (currentSlideIndex.value > 0) currentSlideIndex.value--
}

function nextSlide() {
  if (currentSlideIndex.value < allSlides.value.length - 1) currentSlideIndex.value++
}

function editSlide() {
  if (currentSlide.value) {
    slidesStore.setActiveSlide(currentSlide.value.id)
    uiStore.setCurrentStep('builder')
    router.push('/builder')
  }
}

function openExportDeckFile() {
  const id = deckTemplateStore.selectedTemplateId
  if (id == null) return
  window.open(deckTemplatePptDownloadUrl(id), '_blank', 'noopener,noreferrer')
}

async function generatePPTAction() {
  if (!presentationStore.currentPresentation) {
    if (slidesStore.sections.length > 0) {
        presentationStore.createPresentation("Manual Presentation")
    } else {
        errorMessage.value = "No presentation data available."
        return
    }
  }

  isGenerating.value = true
  generateProgress.value = 10
  errorMessage.value = null

  try {
    const payload = transformToBackendFormat(
      presentationStore.currentPresentation!,
      slidesStore.sections,
      deckTemplateStore.selectedTemplateId,
    )
    console.log('Sending payload to backend:', payload)
    generateProgress.value = 30

    const result = await generatePPT(payload)
    generateProgress.value = 80

    if (result.success && result.file_id) {
      downloadFile(result.file_id, result.filename)
      generateProgress.value = 100
      uiStore.completeStep('preview')
      uiStore.setCurrentStep('output')
      router.push('/output')
    } else {
      throw new Error(result.message || 'Failed to generate PPT')
    }
  } catch (err: any) {
    console.error('Generation failed:', err)
    errorMessage.value = err.message || 'An unexpected error occurred'
  } finally {
    isGenerating.value = false
  }
}

const currentStructureDef = computed(() =>
  currentSlide.value ? STRUCTURE_BY_ID[currentSlide.value.structure] : null,
)
const currentStructureLabel = computed(() =>
  currentStructureDef.value ? CATEGORY_LABELS[currentStructureDef.value.id] ?? currentStructureDef.value.label : '',
)

const structureIcons: Record<string, typeof BarChart3> = {
  'blank':    FileText,
  'two-col':  Columns2,
  'two-row':  Rows3,
  'grid-2x2': Grid2x2,
}
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)]">
    <!-- Main preview area -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Slide viewer -->
      <div class="flex-1 flex items-center justify-center p-8">
        <div v-if="currentSlide" class="w-full max-w-4xl">
          <!-- Error alert -->
          <div v-if="errorMessage" class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-xs text-center">
            {{ errorMessage }}
          </div>

          <!-- Slide card -->
          <div
            class="aspect-[16/9] rounded-xl border border-border bg-[var(--preview-surface)] p-8 flex flex-col shadow-xl"
          >
            <h3 class="font-display font-bold text-xl tracking-tight mb-6">
              {{ currentSlide.title }}
            </h3>

            <div class="flex-1 flex items-center justify-center">
              <div class="text-center">
                <div class="flex items-center justify-center gap-2 mb-1">
                  <span
                    v-if="currentStructureLabel"
                    class="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/60 border border-border rounded px-1.5 py-0.5"
                  >{{ currentStructureLabel }}</span>
                  <span class="text-[9px] font-mono text-muted-foreground/50">
                    {{ currentSlide.regions.filter(r => r.component).length }}/{{ currentSlide.regions.length }} regions filled
                  </span>
                </div>
                <component
                  :is="structureIcons[currentSlide.structure] ?? FileText"
                  :size="48"
                  :stroke-width="1"
                  class="mx-auto mb-4 mt-2 text-amber-500/40"
                />
                <p class="text-sm text-muted-foreground max-w-md">
                  {{ currentSlide.commentary || 'Slide content preview — data and visuals will be rendered in the final PPT.' }}
                </p>
              </div>
            </div>

            <div class="flex items-center justify-between mt-4 pt-4 border-t border-border">
              <span class="text-[10px] font-mono text-muted-foreground/70">
                {{ sectionForSlide?.name }}
              </span>
              <span class="text-[10px] font-mono text-muted-foreground/70">
                {{ currentSlideIndex + 1 }} / {{ allSlides.length }}
              </span>
            </div>
          </div>

          <!-- Navigation -->
          <div class="flex items-center justify-between mt-6">
            <Button
              variant="outline"
              class="border-border text-muted-foreground hover:bg-foreground/5 rounded-lg h-9"
              :disabled="currentSlideIndex === 0"
              @click="prevSlide"
            >
              <ArrowLeft :size="16" :stroke-width="1.5" class="mr-1.5" />
              Previous
            </Button>

            <div class="flex items-center gap-1.5">
              <div
                v-for="(_, idx) in allSlides"
                :key="idx"
                class="w-2 h-2 rounded-full transition-all duration-200 cursor-pointer"
                :class="
                  idx === currentSlideIndex
                    ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'
                    : 'bg-muted hover:bg-muted-foreground/30'
                "
                @click="currentSlideIndex = idx"
              />
            </div>

            <Button
              variant="outline"
              class="border-border text-muted-foreground hover:bg-foreground/5 rounded-lg h-9"
              :disabled="currentSlideIndex === allSlides.length - 1"
              @click="nextSlide"
            >
              Next
              <ArrowRight :size="16" :stroke-width="1.5" class="ml-1.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- Right sidebar: Summary -->
    <div class="w-72 flex-shrink-0 border-l border-border flex flex-col" :style="{ background: 'var(--surface-elevated)' }">
      <div class="px-4 py-4 border-b border-border">
        <h3 class="text-sm font-display font-semibold tracking-tight">Presentation Summary</h3>
      </div>

      <ScrollArea class="flex-1">
        <div class="p-4 space-y-4">
          <div class="rounded-lg border border-border p-3 bg-[var(--preview-surface)]">
            <p class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2">
              Export base deck
            </p>
            <template v-if="deckTemplateStore.selectedTemplateId != null">
              <p class="text-xs text-foreground/80 truncate" :title="deckTemplateStore.selectedTemplateName ?? ''">
                {{ deckTemplateStore.selectedTemplateName }}
              </p>
              <div class="flex flex-wrap gap-2 mt-2">
                <Button size="sm" variant="outline" class="h-8 text-xs" @click="openExportDeckFile">
                  View .pptx
                </Button>
                <Button size="sm" variant="ghost" class="h-8 text-xs text-muted-foreground" @click="deckTemplateStore.clearExportDeck()">
                  Clear
                </Button>
              </div>
            </template>
            <template v-else>
              <p class="text-xs text-muted-foreground">
                Built-in theme only. Upload a deck and it becomes the export base automatically, or pick one under Templates.
              </p>
              <Button size="sm" variant="outline" class="h-8 text-xs mt-2 w-full" @click="router.push('/templates')">
                Manage decks
              </Button>
            </template>
          </div>
          <!-- Stats -->
          <div class="grid grid-cols-2 gap-3">
            <GlassCard padding="p-3">
              <p class="text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider mb-1">Sections</p>
              <p class="text-lg font-display font-bold text-amber-500">{{ slidesStore.sections.length }}</p>
            </GlassCard>
            <GlassCard padding="p-3">
              <p class="text-[10px] font-mono text-muted-foreground/70 uppercase tracking-wider mb-1">Slides</p>
              <p class="text-lg font-display font-bold text-amber-500">{{ allSlides.length }}</p>
            </GlassCard>
          </div>

          <!-- Section list -->
          <div>
            <p class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70 mb-2">Sections</p>
            <div class="space-y-1.5">
              <div
                v-for="section in slidesStore.sections"
                :key="section.id"
                class="flex items-center gap-2 py-2 px-3 rounded-lg bg-foreground/[0.02]"
              >
                <div class="w-5 h-5 rounded bg-amber-500/10 flex items-center justify-center text-[9px] font-mono text-amber-500">
                  {{ section.slides.length }}
                </div>
                <span class="text-xs text-muted-foreground truncate">{{ section.name }}</span>
              </div>
            </div>
          </div>

          <!-- Edit current -->
          <Button
            variant="outline"
            class="w-full border-border text-muted-foreground hover:bg-foreground/5 rounded-lg h-9 text-xs"
            @click="editSlide"
          >
            <Edit3 :size="12" :stroke-width="1.5" class="mr-1.5" />
            Edit Current Slide
          </Button>
        </div>
      </ScrollArea>

      <!-- Generate button -->
      <div class="p-4 border-t border-border">
        <Button
          class="w-full bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-12 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:shadow-[0_0_40px_rgba(245,158,11,0.5)] transition-all duration-200 active:scale-[0.98] text-sm"
          :disabled="isGenerating"
          @click="generatePPTAction"
        >
          <template v-if="isGenerating">
            <Loader2 :size="16" class="mr-2 animate-spin" />
            Generating... {{ generateProgress }}%
          </template>
          <template v-else>
            <Download :size="16" :stroke-width="2" class="mr-2" />
            Generate PPT
          </template>
        </Button>

        <!-- Progress bar -->
        <div v-if="isGenerating" class="mt-3 h-1 rounded-full bg-muted overflow-hidden">
          <div
            class="h-full bg-amber-500 rounded-full transition-all duration-300"
            :style="{ width: `${generateProgress}%` }"
          />
        </div>
      </div>
    </div>
  </div>
</template>
