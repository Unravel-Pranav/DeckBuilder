<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSlidesStore } from '@/stores/slides'
import { usePresentationStore } from '@/stores/presentation'
import { useAiStore } from '@/stores/ai'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Sparkles,
  RefreshCw,
  PenLine,
  MessageSquare,
  Loader2,
  Database,
} from 'lucide-vue-next'

const slidesStore = useSlidesStore()
const presentationStore = usePresentationStore()
const aiStore = useAiStore()

const commentaryMode = ref<'ai' | 'prompt' | 'manual'>('ai')
const promptText = ref('')
const manualText = ref('')

const currentCommentary = computed(() => slidesStore.activeSlide?.commentary ?? '')

const sectionName = computed(() => slidesStore.activeSection?.name ?? '')

const dominantContext = computed(() => {
  const slide = slidesStore.activeSlide
  if (!slide) return 'default'
  const components = slide.regions.map((r) => r.component).filter(Boolean)
  if (components.find((c) => c!.type === 'chart')) return 'chart'
  if (components.find((c) => c!.type === 'table')) return 'table'
  if (components.find((c) => c!.type === 'text')) return 'text'
  return 'default'
})

const fullContext = computed(() => ({
  componentType: dominantContext.value as 'chart' | 'table' | 'text' | 'default',
  sectionName: sectionName.value,
  intentType: presentationStore.intent.type,
  intentTone: presentationStore.intent.tone,
  slideTitle: slidesStore.activeSlide?.title,
}))

watch([commentaryMode, () => slidesStore.activeSlideId], () => {
  if (commentaryMode.value === 'manual') {
    manualText.value = currentCommentary.value
  }
})

async function generateFromData() {
  if (!slidesStore.activeSlideId) return
  const text = await aiStore.generateCommentary(fullContext.value)
  slidesStore.updateSlideCommentary(slidesStore.activeSlideId, text, 'ai')
}

async function generateFromPrompt() {
  if (!slidesStore.activeSlideId || !promptText.value.trim()) return
  const text = await aiStore.generateCommentary(fullContext.value, promptText.value)
  slidesStore.updateSlideCommentary(slidesStore.activeSlideId, text, 'prompt')
}

function applyManual() {
  if (!slidesStore.activeSlideId) return
  slidesStore.updateSlideCommentary(slidesStore.activeSlideId, manualText.value, 'manual')
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

    <!-- Context indicator -->
    <div class="flex items-center gap-2 flex-wrap text-[9px] font-mono text-muted-foreground/70">
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ dominantContext }}</span>
      <span v-if="sectionName" class="px-1.5 py-0.5 rounded bg-foreground/5">{{ sectionName }}</span>
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ presentationStore.intent.type }}</span>
      <span class="px-1.5 py-0.5 rounded bg-foreground/5">{{ presentationStore.intent.tone }}</span>
    </div>

    <!-- Current commentary -->
    <div v-if="currentCommentary" class="p-3 rounded-lg bg-foreground/[0.02] border border-border">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Current Commentary</span>
        <span class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500">
          {{ slidesStore.activeSlide?.commentarySource }}
        </span>
      </div>
      <p class="text-xs text-muted-foreground leading-relaxed">{{ currentCommentary }}</p>
    </div>

    <!-- Data source preview -->
    <div v-if="dominantContext !== 'text' && dominantContext !== 'default'" class="p-3 rounded-lg bg-foreground/[0.01] border border-dashed border-border">
      <div class="flex items-center gap-2 mb-2">
        <Database :size="10" class="text-muted-foreground" />
        <span class="text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70">Reference Data</span>
      </div>
      <div v-if="slidesStore.activeSlide?.regions.some(r => r.component?.type === 'chart')" class="text-[10px] text-muted-foreground font-mono">
        {{ (slidesStore.activeSlide?.regions.find(r => r.component?.type === 'chart')?.component as any)?.data.labels.join(', ') }} ...
      </div>
      <div v-else-if="slidesStore.activeSlide?.regions.some(r => r.component?.type === 'table')" class="text-[10px] text-muted-foreground font-mono">
        {{ (slidesStore.activeSlide?.regions.find(r => r.component?.type === 'table')?.component as any)?.data.headers.join(' | ') }}
      </div>
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
