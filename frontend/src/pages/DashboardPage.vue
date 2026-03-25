<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePresentationStore } from '@/stores/presentation'
import { useSlidesStore } from '@/stores/slides'
import { useAiStore } from '@/stores/ai'
import { useUiStore } from '@/stores/ui'
import { mockPresentations } from '@/lib/mockData'
import GlassCard from '@/components/shared/GlassCard.vue'
import EmptyState from '@/components/shared/EmptyState.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Plus,
  FileText,
  Clock,
  BarChart3,
  Briefcase,
  GraduationCap,
  Sparkles,
} from 'lucide-vue-next'

const router = useRouter()
const presentationStore = usePresentationStore()
const slidesStore = useSlidesStore()
const aiStore = useAiStore()
const uiStore = useUiStore()

const typeIcons = {
  financial: BarChart3,
  business: Briefcase,
  research: GraduationCap,
  custom: Sparkles,
} as const

const statusColors = {
  draft: 'text-muted-foreground bg-muted',
  generating: 'text-amber-500 bg-amber-500/15',
  complete: 'text-emerald-400 bg-emerald-500/15',
} as const

onMounted(() => {
  presentationStore.setRecentPresentations(mockPresentations)
})

function createNew() {
  presentationStore.$reset()
  slidesStore.$reset()
  aiStore.$reset()
  uiStore.$reset()
  router.push('/create')
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10">
      <div>
        <h2 class="text-3xl md:text-4xl font-display font-bold tracking-tight mb-2">
          Your Presentations
        </h2>
        <p class="text-muted-foreground text-sm">
          Create AI-powered presentations in minutes
        </p>
      </div>

      <Button
        class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-11 px-6 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98]"
        @click="createNew"
      >
        <Plus :size="18" :stroke-width="2" class="mr-2" />
        New Presentation
      </Button>
    </div>

    <!-- Presentations grid -->
    <div
      v-if="presentationStore.recentPresentations.length > 0"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
    >
      <GlassCard
        v-for="pres in presentationStore.recentPresentations"
        :key="pres.id"
        hoverable
        @click="router.push('/builder')"
      >
        <!-- Card header -->
        <div class="flex items-start justify-between mb-4">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--accent-muted)' }"
          >
            <component
              :is="typeIcons[pres.intent.type]"
              :size="20"
              :stroke-width="1.5"
              class="text-amber-500"
            />
          </div>
          <Badge
            variant="secondary"
            class="text-[10px] font-mono uppercase tracking-wider rounded-full px-2.5 py-0.5"
            :class="statusColors[pres.status]"
          >
            {{ pres.status }}
          </Badge>
        </div>

        <!-- Card body -->
        <h3 class="font-display font-semibold text-base tracking-tight mb-1.5 line-clamp-1">
          {{ pres.name }}
        </h3>
        <p class="text-xs text-muted-foreground mb-4 capitalize">
          {{ pres.intent.type }} · {{ pres.intent.tone }}
        </p>

        <!-- Card footer -->
        <div class="flex items-center gap-4 text-[11px] text-muted-foreground/70 font-mono">
          <span class="flex items-center gap-1">
            <FileText :size="12" :stroke-width="1.5" />
            {{ pres.sections.length }} sections
          </span>
          <span class="flex items-center gap-1">
            <Clock :size="12" :stroke-width="1.5" />
            {{ formatDate(pres.updatedAt) }}
          </span>
        </div>
      </GlassCard>

      <!-- Create new card -->
      <button
        class="group flex flex-col items-center justify-center rounded-xl border border-dashed border-border hover:border-amber-500/30 bg-transparent hover:bg-[var(--accent-muted)] min-h-[200px] transition-all duration-300"
        @click="createNew"
      >
        <div
          class="w-12 h-12 rounded-xl bg-muted group-hover:bg-amber-500/15 flex items-center justify-center mb-3 transition-all duration-300"
        >
          <Plus
            :size="24"
            :stroke-width="1.5"
            class="text-muted-foreground/70 group-hover:text-amber-500 transition-colors duration-300"
          />
        </div>
        <span class="text-sm text-muted-foreground/70 group-hover:text-muted-foreground transition-colors font-medium">
          Create New
        </span>
      </button>
    </div>

    <!-- Empty state -->
    <EmptyState
      v-else
      :icon="FileText"
      title="No presentations yet"
      description="Create your first AI-powered presentation to get started."
    >
      <Button
        class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-11 px-6 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200"
        @click="createNew"
      >
        <Plus :size="18" :stroke-width="2" class="mr-2" />
        Create Presentation
      </Button>
    </EmptyState>
  </div>
</template>
