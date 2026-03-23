<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import GlassCard from '@/components/shared/GlassCard.vue'
import {
  Sparkles,
  BarChart3,
  PieChart,
  TrendingUp,
  Table2,
  FileText,
  Palette,
} from 'lucide-vue-next'

const presentationStore = usePresentationStore()
const isThinking = ref(false)

const suggestions = computed(() => {
  const type = presentationStore.intent.type
  const tone = presentationStore.intent.tone

  const sectionMap: Record<string, string[]> = {
    financial: ['Executive Summary', 'Revenue Analysis', 'Cost Breakdown', 'Financial Projections', 'Key Takeaways'],
    business: ['Executive Summary', 'Market Overview', 'Strategy & Goals', 'Action Plan', 'Next Steps'],
    research: ['Introduction', 'Methodology', 'Key Findings', 'Data Analysis', 'Conclusions'],
    custom: ['Overview', 'Main Content', 'Supporting Data', 'Summary'],
  }

  const chartMap: Record<string, string[]> = {
    financial: ['Bar Charts', 'Line Graphs', 'Pie Charts'],
    business: ['Bar Charts', 'Org Charts', 'Timeline'],
    research: ['Scatter Plots', 'Line Graphs', 'Heat Maps'],
    custom: ['Bar Charts', 'Tables'],
  }

  const toneLabel: Record<string, string> = {
    formal: 'Professional, data-driven language',
    analytical: 'Deep-dive analysis with insights',
    storytelling: 'Narrative flow with visual emphasis',
  }

  return {
    sections: sectionMap[type] ?? sectionMap.custom,
    charts: chartMap[type] ?? chartMap.custom,
    toneDesc: toneLabel[tone] ?? toneLabel.formal,
    slideCount: type === 'financial' ? '12-15' : type === 'business' ? '10-12' : '8-10',
  }
})

watch(
  () => presentationStore.intent.type,
  () => {
    isThinking.value = true
    setTimeout(() => (isThinking.value = false), 800)
  },
)
</script>

<template>
  <GlassCard highlighted class="sticky top-24">
    <!-- Header -->
    <div class="flex items-center gap-2 mb-6">
      <div
        class="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center"
      >
        <Sparkles :size="16" :stroke-width="1.5" class="text-amber-500" />
      </div>
      <div>
        <h3 class="text-sm font-display font-semibold tracking-tight">AI Suggestions</h3>
        <p class="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">Recommended Setup</p>
      </div>

      <!-- Thinking indicator -->
      <div
        v-if="isThinking"
        class="ml-auto flex items-center gap-1.5"
      >
        <div class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        <span class="text-[10px] text-amber-500 font-mono">Analyzing...</span>
      </div>
    </div>

    <Transition name="fade" mode="out-in">
      <div :key="presentationStore.intent.type" class="space-y-5">
        <!-- Suggested sections -->
        <div>
          <div class="flex items-center gap-2 mb-2">
            <FileText :size="14" :stroke-width="1.5" class="text-zinc-500" />
            <span class="text-[11px] font-mono uppercase tracking-wider text-zinc-500">Sections</span>
          </div>
          <div class="space-y-1.5">
            <div
              v-for="(section, i) in suggestions.sections"
              :key="section"
              class="flex items-center gap-2.5 py-1.5 px-3 rounded-lg bg-white/[0.03] text-sm text-zinc-300"
            >
              <span class="text-[10px] text-zinc-600 font-mono w-4 text-right">{{ i + 1 }}</span>
              <span>{{ section }}</span>
            </div>
          </div>
        </div>

        <!-- Suggested charts -->
        <div>
          <div class="flex items-center gap-2 mb-2">
            <BarChart3 :size="14" :stroke-width="1.5" class="text-zinc-500" />
            <span class="text-[11px] font-mono uppercase tracking-wider text-zinc-500">Chart Types</span>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="chart in suggestions.charts"
              :key="chart"
              class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20"
            >
              {{ chart }}
            </span>
          </div>
        </div>

        <!-- Tone & Style -->
        <div>
          <div class="flex items-center gap-2 mb-2">
            <Palette :size="14" :stroke-width="1.5" class="text-zinc-500" />
            <span class="text-[11px] font-mono uppercase tracking-wider text-zinc-500">Tone & Style</span>
          </div>
          <p class="text-sm text-zinc-400">{{ suggestions.toneDesc }}</p>
        </div>

        <!-- Slide estimate -->
        <div class="pt-3 border-t border-[rgba(255,255,255,0.06)]">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-mono text-zinc-500 uppercase tracking-wider">Est. Slides</span>
            <span class="text-sm font-display font-semibold text-amber-500">{{ suggestions.slideCount }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </GlassCard>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 300ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
