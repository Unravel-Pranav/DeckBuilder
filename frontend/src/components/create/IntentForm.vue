<script setup lang="ts">
import { usePresentationStore } from '@/stores/presentation'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  BarChart3,
  Briefcase,
  GraduationCap,
  Sparkles,
  Upload,
} from 'lucide-vue-next'
import type { PresentationType, ToneType, FontStyle, ColorScheme } from '@/types'

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

function handleFileDrop(e: DragEvent) {
  e.preventDefault()
  const file = e.dataTransfer?.files[0]
  if (file && (file.name.endsWith('.pptx') || file.name.endsWith('.ppt'))) {
    presentationStore.setReferenceFile(file)
  }
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) presentationStore.setReferenceFile(file)
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

    <!-- Design Preferences -->
    <div class="grid grid-cols-2 gap-4">
      <div>
        <Label class="text-sm font-medium text-foreground/80 mb-2 block">Font Style</Label>
        <Select
          :model-value="presentationStore.intent.designPreferences.fontStyle"
          @update:model-value="presentationStore.setDesignPreferences({ ...presentationStore.intent.designPreferences, fontStyle: $event as FontStyle })"
        >
          <SelectTrigger class="h-11 bg-[var(--glass-bg)] border-border rounded-xl">
            <SelectValue placeholder="Select style" />
          </SelectTrigger>
          <SelectContent class="bg-popover border-border">
            <SelectItem value="modern">Modern</SelectItem>
            <SelectItem value="corporate">Corporate</SelectItem>
            <SelectItem value="minimal">Minimal</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label class="text-sm font-medium text-foreground/80 mb-2 block">Color Scheme</Label>
        <Select
          :model-value="presentationStore.intent.designPreferences.colorScheme"
          @update:model-value="presentationStore.setDesignPreferences({ ...presentationStore.intent.designPreferences, colorScheme: $event as ColorScheme })"
        >
          <SelectTrigger class="h-11 bg-[var(--glass-bg)] border-border rounded-xl">
            <SelectValue placeholder="Select scheme" />
          </SelectTrigger>
          <SelectContent class="bg-popover border-border">
            <SelectItem value="dark">Dark</SelectItem>
            <SelectItem value="light">Light</SelectItem>
            <SelectItem value="brand">Brand-based</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <!-- Reference Upload -->
    <div>
      <Label class="text-sm font-medium text-foreground/80 mb-2 block">
        Reference PPT
        <span class="text-muted-foreground/70 font-normal">(optional)</span>
      </Label>
      <div
        class="border border-dashed border-border hover:border-amber-500/30 rounded-xl p-8 text-center transition-all duration-300 cursor-pointer"
        :class="presentationStore.intent.referenceFile ? 'bg-amber-500/5 border-amber-500/20' : ''"
        @dragover.prevent
        @drop="handleFileDrop"
        @click="($refs.fileInput as HTMLInputElement)?.click()"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".ppt,.pptx"
          class="hidden"
          @change="handleFileSelect"
        />
        <Upload :size="24" :stroke-width="1.5" class="mx-auto mb-3 text-muted-foreground/70" />
        <p v-if="presentationStore.intent.referenceFile" class="text-sm text-amber-500 font-medium">
          {{ presentationStore.intent.referenceFile.name }}
        </p>
        <template v-else>
          <p class="text-sm text-muted-foreground">Drop a .pptx file here or click to browse</p>
          <p class="text-[11px] text-muted-foreground/50 mt-1">AI will analyze the structure and style</p>
        </template>
      </div>
    </div>
  </div>
</template>
