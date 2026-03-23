<script setup lang="ts">
import { useUiStore } from '@/stores/ui'
import { Check } from 'lucide-vue-next'

const uiStore = useUiStore()
</script>

<template>
  <div class="flex items-center gap-2 overflow-x-auto pb-1">
    <template v-for="(step, index) in uiStore.steps" :key="step.id">
      <!-- Step pill -->
      <div
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-200"
        :class="[
          step.isActive
            ? 'bg-amber-500/15 text-amber-500 border border-amber-500/30'
            : step.isCompleted
              ? 'bg-white/5 text-zinc-400 border border-transparent'
              : 'text-zinc-600 border border-transparent',
        ]"
      >
        <Check v-if="step.isCompleted" :size="12" :stroke-width="2" class="text-amber-500" />
        <span>{{ step.label }}</span>
      </div>

      <!-- Connector -->
      <div
        v-if="index < uiStore.steps.length - 1"
        class="w-4 h-px flex-shrink-0"
        :class="step.isCompleted ? 'bg-amber-500/30' : 'bg-zinc-800'"
      />
    </template>
  </div>
</template>
