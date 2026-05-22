<script setup lang="ts">
import { ref, computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  BarChart3,
  Briefcase,
  GraduationCap,
  Sparkles,
  X,
} from 'lucide-vue-next'
import type { PresentationType, ToneType, AudienceExpertise } from '@/types'

const presentationStore = usePresentationStore()

const presentationTypes: { id: PresentationType; label: string; icon: typeof BarChart3; desc: string }[] = [
  { id: 'financial', label: 'Financial', icon: BarChart3, desc: 'Revenue, P&L, forecasts' },
  { id: 'business', label: 'Business', icon: Briefcase, desc: 'Strategy, operations, growth' },
  { id: 'research', label: 'Research', icon: GraduationCap, desc: 'Analysis, findings, data' },
  { id: 'custom', label: 'Custom', icon: Sparkles, desc: 'Build from scratch' },
]

const tones: { id: ToneType; label: string }[] = [
  { id: 'formal', label: 'Formal' },
  { id: 'analytical', label: 'Analytical' },
  { id: 'storytelling', label: 'Storytelling' },
]

const expertiseLevels: { id: AudienceExpertise; label: string; desc: string }[] = [
  { id: 'executive', label: 'Executive', desc: 'High-level, strategic focus' },
  { id: 'analyst', label: 'Analyst', desc: 'Detailed, data-heavy' },
  { id: 'mixed', label: 'Mixed', desc: 'Balanced depth' },
]

// Key metrics tag input
const metricInput = ref('')

const keyMetrics = computed(() => presentationStore.intent.keyMetrics ?? [])

function addMetric() {
  const val = metricInput.value.trim()
  if (!val) return
  const current = keyMetrics.value
  if (!current.includes(val)) {
    presentationStore.setKeyMetrics([...current, val])
  }
  metricInput.value = ''
}

function removeMetric(metric: string) {
  presentationStore.setKeyMetrics(keyMetrics.value.filter(m => m !== metric))
}

function onMetricKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    addMetric()
  }
}
</script>

<template>
  <div class="space-y-8">
    <!-- Presentation Type -->
    <div>
      <Label class="text-sm font-medium text-foreground/80 mb-3 block">Presentation Type</Label>
      <div class="grid grid-cols-2 gap-3">
        <button
          v-for="pt in presentationTypes"
          :key="pt.id"
          class="flex items-start gap-3 p-4 rounded-xl border transition-all duration-200 text-left"
          :class="
            presentationStore.intent.type === pt.id
              ? 'border-amber-500/30 bg-amber-500/10 shadow-[0_0_20px_rgba(245,158,11,0.1)]'
              : 'border-border bg-[var(--glass-bg)] hover:border-[color:var(--glass-border-hover)] hover:bg-[var(--glass-bg-hover)]'
          "
          @click="presentationStore.setType(pt.id)"
        >
          <div
            class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-200"
            :class="
              presentationStore.intent.type === pt.id
                ? 'bg-amber-500/20 text-amber-500'
                : 'bg-muted text-muted-foreground'
            "
          >
            <component :is="pt.icon" :size="18" :stroke-width="1.5" />
          </div>
          <div>
            <p
              class="text-sm font-medium transition-colors"
              :class="presentationStore.intent.type === pt.id ? 'text-amber-500' : 'text-foreground/80'"
            >
              {{ pt.label }}
            </p>
            <p class="text-[11px] text-muted-foreground/70 mt-0.5">{{ pt.desc }}</p>
          </div>
        </button>
      </div>
    </div>

    <!-- Target Audience -->
    <div>
      <Label for="audience" class="text-sm font-medium text-foreground/80 mb-2 block">
        Target Audience
      </Label>
      <Input
        id="audience"
        :model-value="presentationStore.intent.audience"
        placeholder="e.g., Board of Directors, Product Team, Investors..."
        class="h-11 bg-[var(--glass-bg)] border-border rounded-xl placeholder:text-muted-foreground/50 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20"
        @update:model-value="presentationStore.setAudience($event as string)"
      />
    </div>

    <!-- Audience Expertise -->
    <div>
      <Label class="text-sm font-medium text-foreground/80 mb-3 block">Audience Expertise</Label>
      <div class="flex gap-2">
        <button
          v-for="lvl in expertiseLevels"
          :key="lvl.id"
          class="flex-1 py-2.5 px-3 rounded-lg text-sm font-medium border transition-all duration-200 text-left"
          :class="
            (presentationStore.intent.audienceExpertise ?? 'mixed') === lvl.id
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-500'
              : 'border-border text-muted-foreground hover:text-foreground/80 hover:border-[color:var(--glass-border-hover)]'
          "
          @click="presentationStore.setAudienceExpertise(lvl.id)"
        >
          <span class="block">{{ lvl.label }}</span>
          <span class="text-[10px] opacity-60 mt-0.5 block">{{ lvl.desc }}</span>
        </button>
      </div>
    </div>

    <!-- Tone -->
    <div>
      <Label class="text-sm font-medium text-foreground/80 mb-3 block">Tone</Label>
      <div class="flex gap-2">
        <button
          v-for="tone in tones"
          :key="tone.id"
          class="flex-1 py-2.5 px-4 rounded-lg text-sm font-medium border transition-all duration-200"
          :class="
            presentationStore.intent.tone === tone.id
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-500'
              : 'border-border text-muted-foreground hover:text-foreground/80 hover:border-[color:var(--glass-border-hover)]'
          "
          @click="presentationStore.setTone(tone.id)"
        >
          {{ tone.label }}
        </button>
      </div>
    </div>

    <!-- Objective -->
    <div>
      <Label for="objective" class="text-sm font-medium text-foreground/80 mb-2 block">
        Objective
        <span class="text-muted-foreground/50 font-normal ml-1">(optional)</span>
      </Label>
      <textarea
        id="objective"
        :value="presentationStore.intent.objective ?? ''"
        placeholder="What is the single most important thing this presentation should convey?"
        rows="2"
        class="w-full bg-[var(--glass-bg)] border border-border rounded-xl px-3 py-2.5 text-sm placeholder:text-muted-foreground/50 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 resize-none outline-none"
        @input="presentationStore.setObjective(($event.target as HTMLTextAreaElement).value)"
      />
    </div>

    <!-- Key Metrics -->
    <div>
      <Label class="text-sm font-medium text-foreground/80 mb-2 block">
        Key Metrics
        <span class="text-muted-foreground/50 font-normal ml-1">(optional — press Enter to add)</span>
      </Label>
      <!-- Tags -->
      <div v-if="keyMetrics.length" class="flex flex-wrap gap-1.5 mb-2">
        <span
          v-for="m in keyMetrics"
          :key="m"
          class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-500 border border-amber-500/20"
        >
          {{ m }}
          <button class="hover:text-amber-300 transition-colors" @click="removeMetric(m)">
            <X :size="11" />
          </button>
        </span>
      </div>
      <Input
        v-model="metricInput"
        placeholder="e.g., Revenue, Occupancy Rate, EBITDA..."
        class="h-11 bg-[var(--glass-bg)] border-border rounded-xl placeholder:text-muted-foreground/50 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20"
        @keydown="onMetricKeydown"
        @blur="addMetric"
      />
    </div>
  </div>
</template>
