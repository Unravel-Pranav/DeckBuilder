<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Button } from '@/components/ui/button'
import {
  Upload,
  FileCheck,
  AlertTriangle,
  Loader2,
  ArrowRight,
  Download,
} from 'lucide-vue-next'
import {
  fetchDeckTemplates,
  uploadDeckTemplatePpt,
  deckTemplatePptDownloadUrl,
  type DeckTemplate,
} from '@/lib/api'
import { useDeckTemplateStore } from '@/stores/deckTemplate'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const deckTemplateStore = useDeckTemplateStore()

const deckTemplates = ref<DeckTemplate[]>([])
const templatesLoading = ref(true)
const templatesError = ref<string | null>(null)

const selectedTemplateId = ref<string>('')
const uploadState = ref<'idle' | 'uploading' | 'valid' | 'invalid'>('idle')
const uploadedFileName = ref<string | null>(null)
const serverTemplate = ref<DeckTemplate | null>(null)
const uploadError = ref<string | null>(null)

const selectedIdNum = computed(() => {
  const n = parseInt(selectedTemplateId.value, 10)
  return Number.isFinite(n) ? n : null
})

onMounted(async () => {
  templatesLoading.value = true
  templatesError.value = null
  try {
    const res = await fetchDeckTemplates()
    deckTemplates.value = res.items
    const q = route.query.templateId
    const fromQuery = typeof q === 'string' && q ? q : null
    if (fromQuery && res.items.some((t) => String(t.id) === fromQuery)) {
      selectedTemplateId.value = fromQuery
    } else if (res.items.length > 0) {
      selectedTemplateId.value = String(res.items[0].id)
    }
  } catch (e: unknown) {
    templatesError.value = e instanceof Error ? e.message : 'Failed to load templates'
  } finally {
    templatesLoading.value = false
  }
})

function handleDrop(e: DragEvent) {
  e.preventDefault()
  const file = e.dataTransfer?.files[0]
  if (file) void processUpload(file)
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) void processUpload(file)
}

async function processUpload(file: File) {
  uploadError.value = null
  serverTemplate.value = null
  uploadedFileName.value = file.name

  if (!selectedIdNum.value) {
    uploadState.value = 'invalid'
    uploadError.value = 'Select a template to attach this deck to.'
    return
  }

  if (!file.name.toLowerCase().endsWith('.pptx')) {
    uploadState.value = 'invalid'
    uploadError.value = 'Only .pptx files are accepted. Save as PowerPoint .pptx and try again.'
    return
  }

  uploadState.value = 'uploading'
  try {
    const updated = await uploadDeckTemplatePpt(selectedIdNum.value, file)
    serverTemplate.value = updated
    deckTemplateStore.setExportDeck(updated.id, updated.name)
    uploadState.value = 'valid'
  } catch (e: unknown) {
    uploadState.value = 'invalid'
    uploadError.value = e instanceof Error ? e.message : 'Upload failed'
  }
}

function openDownload() {
  const id = serverTemplate.value?.id ?? selectedIdNum.value
  if (!id) return
  window.open(deckTemplatePptDownloadUrl(id), '_blank', 'noopener,noreferrer')
}

function handleContinueToBuilder() {
  uiStore.completeStep('upload')
  uiStore.setCurrentStep('builder')
  router.push('/builder')
}

function handleContinueToPreview() {
  uiStore.completeStep('upload')
  uiStore.setCurrentStep('preview')
  router.push('/preview')
}

function resetUpload() {
  uploadState.value = 'idle'
  uploadedFileName.value = null
  serverTemplate.value = null
  uploadError.value = null
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-5xl mx-auto">
    <div class="mb-8">
      <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight mb-1">
        Upload template deck
      </h2>
      <p class="text-sm text-muted-foreground">
        The server validates your file as a real .pptx (readable, at least one slide), then saves it for
        this template record. After a successful upload, this deck is set as the base for exports (cover and theme)
        when you generate a PPT from Preview. Use Download stored .pptx to view the file.
      </p>
    </div>

    <GlassCard v-if="templatesLoading" padding="p-6" class="mb-6">
      <div class="flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 :size="18" class="animate-spin text-amber-500" />
        Loading templates…
      </div>
    </GlassCard>

    <GlassCard v-else-if="templatesError" padding="p-6" class="mb-6 border-red-500/20">
      <p class="text-sm text-red-400">{{ templatesError }}</p>
    </GlassCard>

    <template v-else>
      <GlassCard padding="p-4" class="mb-6">
        <label class="text-xs font-mono uppercase tracking-wider text-muted-foreground block mb-2">
          Template
        </label>
        <select
          v-model="selectedTemplateId"
          class="w-full max-w-md h-10 text-sm rounded-lg border border-border bg-[var(--glass-bg)] text-foreground px-3 outline-none focus:ring-1 focus:ring-amber-500/50"
        >
          <option disabled value="">
            Choose a template to attach the .pptx to
          </option>
          <option v-for="t in deckTemplates" :key="t.id" :value="String(t.id)">
            {{ t.name }} ({{ t.ppt_status }})
          </option>
        </select>
        <p v-if="deckTemplates.length === 0" class="text-xs text-muted-foreground mt-2">
          No templates in the database yet. Create one via the API or seed data first.
        </p>
      </GlassCard>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div class="space-y-6">
          <div
            class="border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 cursor-pointer"
            :class="
              uploadState === 'valid'
                ? 'border-emerald-500/30 bg-emerald-500/5'
                : uploadState === 'invalid'
                  ? 'border-red-500/30 bg-red-500/5'
                  : 'border-border hover:border-amber-500/30 hover:bg-[var(--accent-muted)]'
            "
            @dragover.prevent
            @drop="handleDrop"
            @click="($refs.fileInput as HTMLInputElement)?.click()"
          >
            <input
              ref="fileInput"
              type="file"
              accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
              class="hidden"
              @change="handleFileSelect"
            />

            <template v-if="uploadState === 'idle'">
              <Upload :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-muted-foreground/70" />
              <p class="text-sm text-muted-foreground font-medium mb-1">Drop your .pptx here or click to browse</p>
              <p class="text-xs text-muted-foreground/70">Only .pptx is supported</p>
            </template>

            <template v-else-if="uploadState === 'uploading'">
              <Loader2 :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-amber-500 animate-spin" />
              <p class="text-sm text-amber-500 font-medium mb-1">Uploading &amp; validating…</p>
              <p class="text-xs text-muted-foreground/70">Server checks the file before saving</p>
            </template>

            <template v-else-if="uploadState === 'valid'">
              <FileCheck :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-emerald-400" />
              <p class="text-sm text-emerald-400 font-medium mb-1">Saved</p>
              <p class="text-xs text-muted-foreground">{{ uploadedFileName }}</p>
              <Button variant="ghost" class="mt-3 text-xs text-muted-foreground" type="button" @click.stop="resetUpload">
                Upload another
              </Button>
            </template>

            <template v-else>
              <AlertTriangle :size="32" :stroke-width="1.5" class="mx-auto mb-4 text-red-400" />
              <p class="text-sm text-red-400 font-medium mb-1">Not saved</p>
              <p class="text-xs text-muted-foreground px-2">{{ uploadError }}</p>
              <Button variant="ghost" class="mt-3 text-xs text-muted-foreground" type="button" @click.stop="resetUpload">
                Try again
              </Button>
            </template>
          </div>
        </div>

        <div v-if="uploadState === 'valid' && serverTemplate" class="space-y-6">
          <GlassCard padding="p-4">
            <h4 class="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-3">
              Server response
            </h4>
            <dl class="space-y-2 text-xs text-muted-foreground">
              <div class="flex justify-between gap-4">
                <dt class="text-muted-foreground/70">Template</dt>
                <dd class="text-foreground/80 truncate">{{ serverTemplate.name }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-muted-foreground/70">PPT status</dt>
                <dd class="text-emerald-400/90">{{ serverTemplate.ppt_status }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-muted-foreground/70">Deck URL</dt>
                <dd class="truncate font-mono text-[10px] text-muted-foreground/70">{{ serverTemplate.ppt_url }}</dd>
              </div>
            </dl>
            <Button
              type="button"
              variant="outline"
              class="mt-4 w-full border-border text-foreground/80"
              @click="openDownload"
            >
              <Download :size="14" :stroke-width="1.5" class="mr-2" />
              Download stored .pptx
            </Button>
          </GlassCard>

          <div class="flex justify-end gap-3">
            <Button
              variant="outline"
              class="font-medium h-11 px-6 rounded-xl border-border text-foreground/80 transition-all duration-200 active:scale-[0.98]"
              @click="handleContinueToPreview"
            >
              Continue to Preview
              <ArrowRight :size="16" :stroke-width="2" class="ml-1.5" />
            </Button>
            <Button
              class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-11 px-6 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98]"
              @click="handleContinueToBuilder"
            >
              Use in Builder
              <ArrowRight :size="16" :stroke-width="2" class="ml-1.5" />
            </Button>
          </div>
        </div>
    </div>
    </template>
  </div>
</template>
