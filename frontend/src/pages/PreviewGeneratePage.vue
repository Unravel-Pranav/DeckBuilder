<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSlidesStore } from '@/stores/slides'
import { useUiStore } from '@/stores/ui'
import { usePresentationStore } from '@/stores/presentation'
import { transformToBackendFormat, generatePPT, downloadFile } from '@/lib/api'
import { mockSections } from '@/lib/mockData'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Edit3,
  Loader2,
  CheckCircle2,
  BarChart3,
  Table2,
  FileText,
  Layers,
} from 'lucide-vue-next'

const router = useRouter()
const slidesStore = useSlidesStore()
const uiStore = useUiStore()
const presentationStore = usePresentationStore()

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

async function generatePPTAction() {
  if (!presentationStore.currentPresentation) {
    // For demo/dev purposes, if no presentation is set, we might want to create one
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
    // 1. Transform data
    const payload = transformToBackendFormat(
      presentationStore.currentPresentation!, 
      slidesStore.sections
    )
    console.log('Sending payload to backend:', payload)
    generateProgress.value = 30

    // 2. Call backend
    const result = await generatePPT(payload)
    generateProgress.value = 80

    if (result.success && result.file_id) {
      // 3. Trigger download
      downloadFile(result.file_id, result.filename)
      generateProgress.value = 100
      
      // 4. Update UI state
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

const layoutIcons: Record<string, typeof BarChart3> = {
  'chart-commentary': BarChart3,
  'table-commentary': Table2,
  'full-chart': BarChart3,
  'full-table': Table2,
  mixed: Layers,
  'commentary-only': FileText,
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
            class="aspect-[16/9] rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(10,10,15,0.8)] p-8 flex flex-col shadow-xl"
          >
            <h3 class="font-display font-bold text-xl tracking-tight mb-6">
              {{ currentSlide.title }}
            </h3>

            <div class="flex-1 flex items-center justify-center">
              <div class="text-center">
                <component
                  :is="layoutIcons[currentSlide.layout] ?? FileText"
                  :size="48"
                  :stroke-width="1"
                  class="mx-auto mb-4 text-amber-500/40"
                />
                <p class="text-sm text-zinc-500 max-w-md">
                  {{ currentSlide.commentary || 'Slide content preview — data and visuals will be rendered in the final PPT.' }}
                </p>
              </div>
            </div>

            <div class="flex items-center justify-between mt-4 pt-4 border-t border-[rgba(255,255,255,0.04)]">
              <span class="text-[10px] font-mono text-zinc-600">
                {{ sectionForSlide?.name }}
              </span>
              <span class="text-[10px] font-mono text-zinc-600">
                {{ currentSlideIndex + 1 }} / {{ allSlides.length }}
              </span>
            </div>
          </div>

          <!-- Navigation -->
          <div class="flex items-center justify-between mt-6">
            <Button
              variant="outline"
              class="border-[rgba(255,255,255,0.1)] text-zinc-400 hover:bg-white/5 rounded-lg h-9"
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
                    : 'bg-zinc-800 hover:bg-zinc-700'
                "
                @click="currentSlideIndex = idx"
              />
            </div>

            <Button
              variant="outline"
              class="border-[rgba(255,255,255,0.1)] text-zinc-400 hover:bg-white/5 rounded-lg h-9"
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
    <div class="w-72 flex-shrink-0 border-l border-[rgba(255,255,255,0.08)] flex flex-col" style="background: rgba(18, 18, 26, 0.9)">
      <div class="px-4 py-4 border-b border-[rgba(255,255,255,0.06)]">
        <h3 class="text-sm font-display font-semibold tracking-tight">Presentation Summary</h3>
      </div>

      <ScrollArea class="flex-1">
        <div class="p-4 space-y-4">
          <!-- Stats -->
          <div class="grid grid-cols-2 gap-3">
            <GlassCard padding="p-3">
              <p class="text-[10px] font-mono text-zinc-600 uppercase tracking-wider mb-1">Sections</p>
              <p class="text-lg font-display font-bold text-amber-500">{{ slidesStore.sections.length }}</p>
            </GlassCard>
            <GlassCard padding="p-3">
              <p class="text-[10px] font-mono text-zinc-600 uppercase tracking-wider mb-1">Slides</p>
              <p class="text-lg font-display font-bold text-amber-500">{{ allSlides.length }}</p>
            </GlassCard>
          </div>

          <!-- Section list -->
          <div>
            <p class="text-[10px] font-mono uppercase tracking-wider text-zinc-600 mb-2">Sections</p>
            <div class="space-y-1.5">
              <div
                v-for="section in slidesStore.sections"
                :key="section.id"
                class="flex items-center gap-2 py-2 px-3 rounded-lg bg-white/[0.02]"
              >
                <div class="w-5 h-5 rounded bg-amber-500/10 flex items-center justify-center text-[9px] font-mono text-amber-500">
                  {{ section.slides.length }}
                </div>
                <span class="text-xs text-zinc-400 truncate">{{ section.name }}</span>
              </div>
            </div>
          </div>

          <!-- Edit current -->
          <Button
            variant="outline"
            class="w-full border-[rgba(255,255,255,0.1)] text-zinc-400 hover:bg-white/5 rounded-lg h-9 text-xs"
            @click="editSlide"
          >
            <Edit3 :size="12" :stroke-width="1.5" class="mr-1.5" />
            Edit Current Slide
          </Button>
        </div>
      </ScrollArea>

      <!-- Generate button -->
      <div class="p-4 border-t border-[rgba(255,255,255,0.06)]">
        <Button
          class="w-full bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 font-medium h-12 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:shadow-[0_0_40px_rgba(245,158,11,0.5)] transition-all duration-200 active:scale-[0.98] text-sm"
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
        <div v-if="isGenerating" class="mt-3 h-1 rounded-full bg-zinc-800 overflow-hidden">
          <div
            class="h-full bg-amber-500 rounded-full transition-all duration-300"
            :style="{ width: `${generateProgress}%` }"
          />
        </div>
      </div>
    </div>
  </div>
</template>
