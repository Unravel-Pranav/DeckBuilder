<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePresentationStore } from '@/stores/presentation'
import { useSlidesStore } from '@/stores/slides'
import { useAiStore } from '@/stores/ai'
import { useUiStore } from '@/stores/ui'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Download,
  CheckCircle2,
  Share2,
  Edit3,
  Plus,
  Clock,
  FileText,
  Layers,
  Copy,
} from 'lucide-vue-next'

const router = useRouter()
const presentationStore = usePresentationStore()
const slidesStore = useSlidesStore()
const aiStore = useAiStore()
const uiStore = useUiStore()

const isDownloading = ref(false)

const versions = ref([
  { id: '1', label: 'Version 3 — Current', date: 'Mar 21, 2026 · 2:15 PM', isCurrent: true },
  { id: '2', label: 'Version 2', date: 'Mar 21, 2026 · 1:30 PM', isCurrent: false },
  { id: '3', label: 'Version 1 — Initial', date: 'Mar 21, 2026 · 12:45 PM', isCurrent: false },
])

async function downloadPPT() {
  isDownloading.value = true
  await new Promise((r) => setTimeout(r, 1500))
  isDownloading.value = false
}

function editPresentation() {
  router.push('/builder')
}

function createNew() {
  presentationStore.$reset()
  slidesStore.$reset()
  aiStore.$reset()
  uiStore.$reset()
  router.push('/create')
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-4xl mx-auto">
    <!-- Success header -->
    <div class="text-center mb-12">
      <div
        class="w-20 h-20 rounded-2xl bg-emerald-500/15 flex items-center justify-center mx-auto mb-6 shadow-[0_0_40px_rgba(16,185,129,0.15)]"
      >
        <CheckCircle2 :size="40" :stroke-width="1.5" class="text-emerald-400" />
      </div>
      <h2 class="text-3xl md:text-4xl font-display font-bold tracking-tight mb-3">
        Presentation Ready
      </h2>
      <p class="text-zinc-500 text-sm max-w-md mx-auto">
        Your presentation has been generated successfully. Download it or make further edits.
      </p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <!-- Presentation info -->
      <GlassCard class="md:col-span-2">
        <div class="flex items-start gap-4 mb-6">
          <div class="w-12 h-12 rounded-xl bg-amber-500/15 flex items-center justify-center flex-shrink-0">
            <FileText :size="24" :stroke-width="1.5" class="text-amber-500" />
          </div>
          <div>
            <h3 class="font-display font-semibold text-lg tracking-tight">
              {{ presentationStore.presentationName }}
            </h3>
            <p class="text-xs text-zinc-500 mt-0.5">
              {{ slidesStore.sections.length }} sections · {{ slidesStore.totalSlideCount }} slides
            </p>
          </div>
          <Badge
            variant="secondary"
            class="ml-auto text-[10px] bg-emerald-500/15 text-emerald-400 rounded-full px-2.5"
          >
            Complete
          </Badge>
        </div>

        <!-- Section summary -->
        <div class="space-y-2 mb-6">
          <p class="text-[10px] font-mono uppercase tracking-wider text-zinc-600 mb-2">Sections</p>
          <div
            v-for="section in slidesStore.sections"
            :key="section.id"
            class="flex items-center gap-3 py-2 px-3 rounded-lg bg-white/[0.02]"
          >
            <Layers :size="14" :stroke-width="1.5" class="text-zinc-600 flex-shrink-0" />
            <span class="text-sm text-zinc-400 flex-1">{{ section.name }}</span>
            <span class="text-[10px] font-mono text-zinc-600">{{ section.slides.length }} slides</span>
          </div>
        </div>

        <Separator class="bg-[rgba(255,255,255,0.06)] my-6" />

        <!-- Actions -->
        <div class="flex flex-wrap gap-3">
          <Button
            class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 font-medium h-12 px-8 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:shadow-[0_0_40px_rgba(245,158,11,0.5)] transition-all duration-200 active:scale-[0.98]"
            :disabled="isDownloading"
            @click="downloadPPT"
          >
            <Download :size="18" :stroke-width="2" class="mr-2" />
            {{ isDownloading ? 'Preparing...' : 'Download PPT' }}
          </Button>

          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] text-zinc-300 hover:bg-white/5 rounded-xl h-12"
            @click="editPresentation"
          >
            <Edit3 :size="16" :stroke-width="1.5" class="mr-2" />
            Edit
          </Button>

          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] text-zinc-300 hover:bg-white/5 rounded-xl h-12"
          >
            <Share2 :size="16" :stroke-width="1.5" class="mr-2" />
            Share
          </Button>

          <Button
            variant="outline"
            class="border-[rgba(255,255,255,0.15)] text-zinc-300 hover:bg-white/5 rounded-xl h-12"
          >
            <Copy :size="16" :stroke-width="1.5" class="mr-2" />
            Duplicate
          </Button>
        </div>
      </GlassCard>

      <!-- Version history -->
      <GlassCard>
        <div class="flex items-center gap-2 mb-4">
          <Clock :size="14" :stroke-width="1.5" class="text-zinc-500" />
          <h4 class="text-xs font-mono uppercase tracking-wider text-zinc-500">Versions</h4>
        </div>

        <div class="space-y-2">
          <button
            v-for="version in versions"
            :key="version.id"
            class="w-full text-left py-2.5 px-3 rounded-lg transition-all duration-200"
            :class="
              version.isCurrent
                ? 'bg-amber-500/10 border border-amber-500/20'
                : 'bg-white/[0.02] border border-transparent hover:bg-white/[0.04]'
            "
          >
            <p
              class="text-xs font-medium"
              :class="version.isCurrent ? 'text-amber-500' : 'text-zinc-400'"
            >
              {{ version.label }}
            </p>
            <p class="text-[10px] text-zinc-600 mt-0.5">{{ version.date }}</p>
          </button>
        </div>
      </GlassCard>
    </div>

    <!-- Create new -->
    <div class="text-center pt-6 border-t border-[rgba(255,255,255,0.06)]">
      <Button
        variant="outline"
        class="border-[rgba(255,255,255,0.15)] text-zinc-400 hover:text-zinc-200 hover:bg-white/5 rounded-xl h-11"
        @click="createNew"
      >
        <Plus :size="16" :stroke-width="1.5" class="mr-2" />
        Create Another Presentation
      </Button>
    </div>
  </div>
</template>
