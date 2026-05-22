<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { useRouter } from 'vue-router'
import { Sortable } from 'sortablejs-vue3'
import type { SortableEvent } from 'sortablejs'
import { useAiStore } from '@/stores/ai'
import { useSlidesStore } from '@/stores/slides'
import { usePresentationStore } from '@/stores/presentation'
import { useUiStore } from '@/stores/ui'
import { generateStructure } from '@/lib/api'
import { buildSectionsFromOutline } from '@/lib/structureMapper'
import SectionCard from '@/components/recommendations/SectionCard.vue'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import {
  ArrowRight,
  Sparkles,
  CheckCheck,
  Plus,
  Loader2,
  ShieldCheck,
} from 'lucide-vue-next'

import { useAutoSave } from '@/composables/useAutoSave'

const router = useRouter()
const aiStore = useAiStore()
const slidesStore = useSlidesStore()
const presentationStore = usePresentationStore()
const uiStore = useUiStore()
const { autoSaveFireAndForget } = useAutoSave()

const acceptedCount = computed(() => {
  if (!aiStore.recommendation) return 0
  return aiStore.recommendation.sections.filter((s) => s.accepted).length
})

const canContinue = computed(() => acceptedCount.value > 0)

onMounted(async () => {
  if (!aiStore.recommendation) {
    // Try the richer agent plan first; fall back to legacy endpoint on failure
    try {
      await aiStore.generatePlan({
        presentationType: presentationStore.intent.type,
        audience: presentationStore.intent.audience,
        tone: presentationStore.intent.tone,
        objective: presentationStore.intent.objective,
        keyMetrics: presentationStore.intent.keyMetrics,
        audienceExpertise: presentationStore.intent.audienceExpertise,
        dataSource: null,
      })
    } catch {
      await aiStore.fetchRecommendations(
        presentationStore.intent.type,
        presentationStore.intent.audience,
        presentationStore.intent.tone,
      )
    }
  }
})

function acceptAllSections() {
  aiStore.acceptAll()
}

function addCustomSection() {
  aiStore.addCustomSection({
    id: crypto.randomUUID(),
    name: 'Custom Section',
    description: 'Add your own content section',
    suggestedTemplates: [],
    accepted: true,
  })
}

function onDragEnd(event: SortableEvent) {
  const { oldIndex, newIndex } = event
  if (oldIndex != null && newIndex != null && oldIndex !== newIndex) {
    aiStore.reorderSections(oldIndex, newIndex)
  }
}

const isContinuing = ref(false)

async function handleContinue() {
  if (!aiStore.recommendation || isContinuing.value) return

  const acceptedSections = aiStore.recommendation.sections.filter((s) => s.accepted)
  if (acceptedSections.length === 0) {
    toast.warning('Accept at least one section to continue')
    return
  }

  isContinuing.value = true
  try {
    const sections = await buildSectionsFromOutline(
      (secs, intent) => generateStructure(secs, intent),
      presentationStore.intent,
      acceptedSections,
    )
    slidesStore.setSections(sections)
    uiStore.completeStep('recommendations')
    uiStore.setCurrentStep('sections')
    autoSaveFireAndForget()
    router.push('/sections')
  } finally {
    isContinuing.value = false
  }
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <div>
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center">
            <Sparkles :size="16" :stroke-width="1.5" class="text-amber-500" />
          </div>
          <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight">
            AI Outline
          </h2>
        </div>
        <p class="text-sm text-muted-foreground ml-10">
          Review, reorder, and accept sections for your presentation outline. Drag to reorder.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          class="border-border text-foreground/80 hover:bg-foreground/5 rounded-lg h-9 text-sm"
          @click="acceptAllSections"
        >
          <CheckCheck :size="14" :stroke-width="1.5" class="mr-1.5" />
          Accept All
        </Button>
        <Button
          variant="outline"
          class="border-border text-foreground/80 hover:bg-foreground/5 rounded-lg h-9 text-sm"
          @click="addCustomSection"
        >
          <Plus :size="14" :stroke-width="1.5" class="mr-1.5" />
          Add Section
        </Button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="aiStore.isLoading || aiStore.isGeneratingPlan" class="flex flex-col items-center py-24">
      <Loader2 :size="32" :stroke-width="1.5" class="text-amber-500 animate-spin mb-4" />
      <p class="text-sm text-muted-foreground font-mono">
        {{ aiStore.isGeneratingPlan ? 'Running recommendation agent...' : 'Analyzing your intent...' }}
      </p>
      <p class="text-xs text-muted-foreground/50 mt-2">This may take 15-30 seconds...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="aiStore.error && !aiStore.recommendation" class="flex flex-col items-center py-24">
      <p class="text-sm text-red-400 mb-4">{{ aiStore.error }}</p>
      <Button
        class="bg-amber-500 text-[#09090B] hover:bg-amber-400 rounded-lg h-9 text-sm font-medium"
        @click="aiStore.fetchRecommendations(presentationStore.intent.type, presentationStore.intent.audience, presentationStore.intent.tone)"
      >
        Retry
      </Button>
    </div>

    <!-- Section cards with drag-and-drop -->
    <div v-else-if="aiStore.recommendation" class="space-y-4">
      <Sortable
        :list="aiStore.recommendation.sections"
        item-key="id"
        tag="div"
        class="space-y-4"
        :options="{
          animation: 250,
          handle: '.drag-handle',
          ghostClass: 'drag-ghost',
          chosenClass: 'drag-chosen',
        }"
        @end="onDragEnd"
      >
        <template #item="{ element, index }">
          <SectionCard
            :section="element"
            :index="index"
            @toggle="aiStore.toggleSectionAccepted($event)"
            @remove="aiStore.removeSectionRecommendation($event)"
          />
        </template>
      </Sortable>

      <!-- Reviewer confidence badge (agent plan only) -->
      <GlassCard v-if="aiStore.agentPlan" padding="p-4" class="mt-6 border-amber-500/10">
        <div class="flex items-start gap-3">
          <ShieldCheck :size="16" :stroke-width="1.5" class="text-amber-500 flex-shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-medium text-amber-500">AI Confidence</span>
              <span
                class="text-xs font-bold px-2 py-0.5 rounded-full"
                :class="
                  aiStore.agentPlan.reviewer_score >= 7
                    ? 'bg-green-500/15 text-green-400'
                    : aiStore.agentPlan.reviewer_score >= 5
                    ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-red-500/15 text-red-400'
                "
              >
                {{ aiStore.agentPlan.reviewer_score }}/10
              </span>
              <span class="text-[10px] text-muted-foreground/50">
                ({{ aiStore.agentPlan.planner_attempts }} attempt{{ aiStore.agentPlan.planner_attempts !== 1 ? 's' : '' }})
              </span>
            </div>
            <p class="text-[11px] text-muted-foreground/70 leading-relaxed">
              {{ aiStore.agentPlan.reviewer_feedback || 'Plan generated with template-aware recommendations.' }}
            </p>
            <p
              v-if="aiStore.agentPlan.bound_sections?.length"
              class="text-[11px] text-amber-500/70 mt-1"
            >
              {{ aiStore.agentPlan.bound_sections.length }} sections pre-built with chart data — edit freely in the builder.
            </p>
          </div>
        </div>
      </GlassCard>

      <!-- AI style note -->
      <GlassCard padding="p-4" class="mt-3">
        <div class="flex items-center gap-3">
          <Sparkles :size="16" :stroke-width="1.5" class="text-amber-500 flex-shrink-0" />
          <div>
            <p class="text-xs text-muted-foreground">
              <span class="text-amber-500 font-medium">Suggested style:</span>
              {{ aiStore.recommendation.suggestedStyle }}
            </p>
            <p class="text-[11px] text-muted-foreground/70 mt-0.5">
              Recommended chart types:
              {{ aiStore.recommendation.suggestedChartTypes.join(', ') }}
            </p>
          </div>
        </div>
      </GlassCard>

      <p
        v-if="acceptedCount === 0"
        class="text-sm text-muted-foreground text-center pt-4"
      >
        Accept at least one section to continue.
      </p>

      <div class="flex justify-end pt-6">
        <Button
          class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-12 px-8 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98] text-base"
          :disabled="!canContinue || isContinuing"
          @click="handleContinue"
        >
          {{ isContinuing ? 'Building outline...' : 'Continue to Sections' }}
          <ArrowRight :size="18" :stroke-width="2" class="ml-2" />
        </Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drag-ghost {
  opacity: 0.4;
}
.drag-chosen {
  box-shadow: 0 0 30px rgba(245, 158, 11, 0.15);
}
</style>
