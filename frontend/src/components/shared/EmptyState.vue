<script setup lang="ts">
import type { Component } from 'vue'

interface Props {
  icon?: Component
  title: string
  description?: string
}

defineProps<Props>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
    <div
      v-if="icon"
      class="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center mb-6"
    >
      <component :is="icon" :size="28" :stroke-width="1.5" class="text-amber-500" />
    </div>
    <h3 class="text-xl font-display font-semibold tracking-tight mb-2">
      {{ title }}
    </h3>
    <p v-if="description" class="text-sm text-zinc-500 max-w-sm">
      {{ description }}
    </p>
    <div class="mt-6">
      <slot />
    </div>
  </div>
</template>
