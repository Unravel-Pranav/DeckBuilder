<script setup lang="ts">
import { ref } from 'vue'
import type { SectionRecommendation } from '@/types'
import GlassCard from '@/components/shared/GlassCard.vue'
import { Badge } from '@/components/ui/badge'
import {
  ChevronDown,
  ChevronUp,
  Check,
  X,
  BarChart3,
  Table2,
  FileText,
  Layers,
  GripVertical,
} from 'lucide-vue-next'

interface Props {
  section: SectionRecommendation
  index: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  toggle: [id: string]
  remove: [id: string]
}>()

const expanded = ref(false)

const templateTypeIcons = {
  'chart-heavy': BarChart3,
  'table-heavy': Table2,
  commentary: FileText,
  mixed: Layers,
} as const
</script>

<template>
  <GlassCard
    :highlighted="section.accepted"
    class="relative group"
  >
    <div class="flex items-start gap-3">
      <!-- Drag handle -->
      <div class="drag-handle flex-shrink-0 pt-0.5 cursor-grab active:cursor-grabbing text-muted-foreground/50 hover:text-muted-foreground transition-colors">
        <GripVertical :size="16" :stroke-width="1.5" />
      </div>

      <!-- Content -->
      <div class="flex-1 min-w-0">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="text-[10px] font-mono text-muted-foreground/70 bg-muted px-1.5 py-0.5 rounded">
                {{ index + 1 }}
              </span>
              <h4 class="font-display font-semibold text-sm tracking-tight">
                {{ section.name }}
              </h4>
            </div>
            <p class="text-xs text-muted-foreground line-clamp-2">{{ section.description }}</p>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-1.5 flex-shrink-0">
            <button
              class="p-1.5 rounded-lg transition-all duration-200"
              :class="
                section.accepted
                  ? 'bg-amber-500/15 text-amber-500 hover:bg-amber-500/25'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              "
              @click="emit('toggle', section.id)"
            >
              <Check :size="14" :stroke-width="2" />
            </button>
            <button
              class="p-1.5 rounded-lg bg-muted text-muted-foreground/70 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
              @click="emit('remove', section.id)"
            >
              <X :size="14" :stroke-width="2" />
            </button>
          </div>
        </div>

        <!-- Templates preview -->
        <div class="mt-3 flex flex-wrap gap-2">
          <Badge
            v-for="tmpl in section.suggestedTemplates"
            :key="tmpl.id"
            variant="secondary"
            class="text-[10px] bg-foreground/5 text-muted-foreground border border-border rounded-md px-2 py-1 flex items-center gap-1"
          >
            <component
              :is="templateTypeIcons[tmpl.type]"
              :size="10"
              :stroke-width="1.5"
            />
            {{ tmpl.name }}
          </Badge>
        </div>

        <!-- Expandable templates detail -->
        <button
          class="mt-3 flex items-center gap-1 text-[11px] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
          @click="expanded = !expanded"
        >
          <component :is="expanded ? ChevronUp : ChevronDown" :size="12" :stroke-width="1.5" />
          {{ expanded ? 'Hide' : 'Show' }} template details
        </button>

        <Transition name="expand">
          <div v-if="expanded" class="mt-3 space-y-2">
            <div
              v-for="tmpl in section.suggestedTemplates"
              :key="tmpl.id"
              class="p-3 rounded-lg bg-foreground/[0.03] border border-border"
            >
              <div class="flex items-center gap-2 mb-1">
                <component
                  :is="templateTypeIcons[tmpl.type]"
                  :size="14"
                  :stroke-width="1.5"
                  class="text-amber-500"
                />
                <span class="text-xs font-medium">{{ tmpl.name }}</span>
                <Badge
                  variant="secondary"
                  class="text-[9px] bg-foreground/5 text-muted-foreground border-none ml-auto rounded-full"
                >
                  {{ tmpl.layout }}
                </Badge>
              </div>
              <p class="text-[11px] text-muted-foreground/70">{{ tmpl.previewDescription }}</p>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </GlassCard>
</template>

<style scoped>
.expand-enter-active,
.expand-leave-active {
  transition: all 300ms ease;
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
.expand-enter-to,
.expand-leave-from {
  max-height: 500px;
}
</style>
