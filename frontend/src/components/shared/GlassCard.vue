<script setup lang="ts">
interface Props {
  hoverable?: boolean
  highlighted?: boolean
  padding?: string
}

withDefaults(defineProps<Props>(), {
  hoverable: false,
  highlighted: false,
  padding: 'p-6',
})
</script>

<template>
  <div
    class="rounded-xl border transition-all duration-300"
    :class="[
      padding,
      highlighted
        ? 'border-amber-500/20 shadow-[0_0_0_1px_rgba(245,158,11,0.2),0_0_30px_rgba(245,158,11,0.15)]'
        : 'border-border',
      hoverable &&
        'cursor-pointer hover:border-[color:var(--glass-border-hover)] hover:scale-[1.02] hover:shadow-lg',
    ]"
    :style="{ background: 'var(--glass-bg)', backdropFilter: 'blur(8px)' }"
  >
    <slot />
  </div>
</template>
