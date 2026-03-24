<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Upload,
  FileCheck,
  AlertTriangle,
  Loader2,
  ArrowRight,
  BarChart3,
  Table2,
  Type,
  Image,
  Link,
  CheckCircle2,
} from 'lucide-vue-next'
import type { UploadedTemplate } from '@/types'

const router = useRouter()
const uiStore = useUiStore()

const uploadState = ref<'idle' | 'uploading' | 'validating' | 'valid' | 'invalid'>('idle')
const uploadedTemplate = ref<UploadedTemplate | null>(null)

const placeholderIcons = {
  chart: BarChart3,
  table: Table2,
  text: Type,
  image: Image,
} as const

const dataFields = [
  'revenue_chart',
  'cost_breakdown',
  'market_share',
  'summary_table',
  'title_text',
  'commentary_text',
  'logo_image',
]

function handleDrop(e: DragEvent) {
  e.preventDefault()
  const file = e.dataTransfer?.files[0]
  if (file) processUpload(file)
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) processUpload(file)
}

async function processUpload(file: File) {
  uploadState.value = 'uploading'
  await new Promise((r) => setTimeout(r, 1200))

  uploadState.value = 'validating'
  await new Promise((r) => setTimeout(r, 1500))

  // Mock validated result
  uploadedTemplate.value = {
    id: crypto.randomUUID(),
    fileName: file.name,
    placeholders: [
      { id: '1', shapeLabel: 'Main Chart Area', boundField: null, type: 'chart', x: 5, y: 15, width: 55, height: 65 },
      { id: '2', shapeLabel: 'Data Table', boundField: null, type: 'table', x: 62, y: 15, width: 33, height: 40 },
      { id: '3', shapeLabel: 'Title Text', boundField: null, type: 'text', x: 5, y: 3, width: 90, height: 10 },
      { id: '4', shapeLabel: 'Commentary Box', boundField: null, type: 'text', x: 62, y: 58, width: 33, height: 22 },
      { id: '5', shapeLabel: 'Logo', boundField: null, type: 'image', x: 85, y: 3, width: 10, height: 10 },
    ],
    status: 'valid',
  }
  uploadState.value = 'valid'
}

function bindField(placeholderId: string, field: string) {
  if (!uploadedTemplate.value) return
  const ph = uploadedTemplate.value.placeholders.find((p) => p.id === placeholderId)
  if (ph) ph.boundField = field
}

function handleContinue() {
  uiStore.completeStep('upload')
  uiStore.setCurrentStep('preview')
  router.push('/preview')
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-5xl mx-auto">
    <div class="mb-8">
      <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight mb-1">
        Upload Template
      </h2>
      <p class="text-sm text-zinc-500">
        Upload a custom PPT template. We'll detect editable regions and let you bind data fields.
      </p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- Left: Upload + Status -->
      <div class="space-y-6">
        <!-- Upload zone -->
        <div
          class="border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 cursor-pointer"
          :class="
            uploadState === 'valid'
              ? 'border-emerald-500/30 bg-emerald-500/5'
              : uploadState === 'invalid'
                ? 'border-red-500/30 bg-red-500/5'
                : 'border-zinc-800 hover:border-amber-500/30 hover:bg-[var(--accent-muted)]'
          "
          @dragover.prevent
          @drop="handleDrop"
          @click="($refs.fileInput as HTMLInputElement)?.click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".ppt,.pptx"
            class="hidden"
            @change="handleFileSelect"
          />

          <!-- Upload states -->
          <template v-if="uploadState === 'idle'">
            <Upload :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-zinc-600" />
            <p class="text-sm text-zinc-400 font-medium mb-1">Drop your PPT template here</p>
            <p class="text-xs text-zinc-600">Supports .ppt and .pptx files</p>
          </template>

          <template v-else-if="uploadState === 'uploading'">
            <Loader2 :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-amber-500 animate-spin" />
            <p class="text-sm text-amber-500 font-medium">Uploading...</p>
          </template>

          <template v-else-if="uploadState === 'validating'">
            <Loader2 :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-amber-500 animate-spin" />
            <p class="text-sm text-amber-500 font-medium mb-1">Validating template...</p>
            <p class="text-xs text-zinc-600">Detecting placeholders and structure</p>
          </template>

          <template v-else-if="uploadState === 'valid'">
            <FileCheck :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-emerald-400" />
            <p class="text-sm text-emerald-400 font-medium mb-1">Template validated</p>
            <p class="text-xs text-zinc-500">{{ uploadedTemplate?.fileName }}</p>
          </template>

          <template v-else>
            <AlertTriangle :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-red-400" />
            <p class="text-sm text-red-400 font-medium mb-1">Invalid template</p>
            <p class="text-xs text-zinc-600">Template must contain populatable placeholders</p>
          </template>
        </div>

        <!-- Validation results -->
        <GlassCard v-if="uploadedTemplate" padding="p-4">
          <h4 class="text-xs font-mono uppercase tracking-wider text-zinc-500 mb-3">
            Detected Placeholders
          </h4>
          <div class="space-y-2">
            <div
              v-for="ph in uploadedTemplate.placeholders"
              :key="ph.id"
              class="flex items-center gap-3 py-2 px-3 rounded-lg bg-white/[0.02]"
            >
              <component
                :is="placeholderIcons[ph.type]"
                :size="14"
                :stroke-width="1.5"
                class="text-amber-500 flex-shrink-0"
              />
              <span class="text-xs text-zinc-400 flex-1">{{ ph.shapeLabel }}</span>
              <Badge
                variant="secondary"
                class="text-[9px] bg-white/5 text-zinc-500 rounded-full px-2"
              >
                {{ ph.type }}
              </Badge>
              <CheckCircle2
                v-if="ph.boundField"
                :size="12"
                :stroke-width="2"
                class="text-emerald-400"
              />
            </div>
          </div>
        </GlassCard>
      </div>

      <!-- Right: Mapping UI -->
      <div v-if="uploadedTemplate" class="space-y-6">
        <!-- Visual slide preview -->
        <GlassCard padding="p-4">
          <h4 class="text-xs font-mono uppercase tracking-wider text-zinc-500 mb-3">
            Template Layout
          </h4>
          <div class="aspect-[16/9] rounded-lg bg-[rgba(10,10,15,0.6)] border border-[rgba(255,255,255,0.06)] relative overflow-hidden">
            <div
              v-for="ph in uploadedTemplate.placeholders"
              :key="ph.id"
              class="absolute border rounded transition-all duration-200 flex items-center justify-center"
              :class="
                ph.boundField
                  ? 'border-amber-500/40 bg-amber-500/10'
                  : 'border-zinc-700 bg-zinc-900/50 hover:border-zinc-600'
              "
              :style="{
                left: `${ph.x}%`,
                top: `${ph.y}%`,
                width: `${ph.width}%`,
                height: `${ph.height}%`,
              }"
            >
              <div class="text-center">
                <component
                  :is="placeholderIcons[ph.type]"
                  :size="14"
                  :stroke-width="1.5"
                  :class="ph.boundField ? 'text-amber-500' : 'text-zinc-600'"
                  class="mx-auto mb-0.5"
                />
                <p class="text-[8px] font-mono" :class="ph.boundField ? 'text-amber-500' : 'text-zinc-700'">
                  {{ ph.boundField ?? ph.shapeLabel }}
                </p>
              </div>
            </div>
          </div>
        </GlassCard>

        <!-- Field binding -->
        <GlassCard padding="p-4">
          <div class="flex items-center gap-2 mb-4">
            <Link :size="14" :stroke-width="1.5" class="text-amber-500" />
            <h4 class="text-xs font-mono uppercase tracking-wider text-zinc-500">
              Bind Data Fields
            </h4>
          </div>
          <div class="space-y-3">
            <div
              v-for="ph in uploadedTemplate.placeholders"
              :key="ph.id"
              class="flex items-center gap-3"
            >
              <span class="text-xs text-zinc-400 flex-1 truncate">{{ ph.shapeLabel }}</span>
              <Select
                :model-value="ph.boundField ?? ''"
                @update:model-value="bindField(ph.id, $event as string)"
              >
                <SelectTrigger class="w-40 h-8 text-xs bg-[rgba(26,26,36,0.6)] border-[rgba(255,255,255,0.06)] rounded-lg">
                  <SelectValue placeholder="Select field" />
                </SelectTrigger>
                <SelectContent class="bg-[#12121A] border-[rgba(255,255,255,0.08)]">
                  <SelectItem v-for="field in dataFields" :key="field" :value="field" class="text-xs">
                    {{ field }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </GlassCard>

        <div class="flex justify-end">
          <Button
            class="bg-amber-500 text-[#0A0A0F] hover:bg-amber-400 font-medium h-11 px-6 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98]"
            @click="handleContinue"
          >
            Continue to Preview
            <ArrowRight :size="16" :stroke-width="2" class="ml-1.5" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
