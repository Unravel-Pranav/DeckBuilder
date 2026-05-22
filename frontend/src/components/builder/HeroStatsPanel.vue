<script setup lang="ts">
import { usePresentationStore } from '@/stores/presentation'
import { TrendingUp, TrendingDown, Minus, Hash } from 'lucide-vue-next'
import type { TrendDirection } from '@/types'

const store = usePresentationStore()

const trends: { id: TrendDirection; icon: typeof TrendingUp; label: string }[] = [
  { id: 'up',      icon: TrendingUp,   label: 'Up' },
  { id: 'down',    icon: TrendingDown, label: 'Down' },
  { id: 'neutral', icon: Minus,        label: 'Flat' },
]
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center gap-2 p-2 rounded-lg bg-amber-500/[0.06] border border-amber-500/10">
      <Hash :size="12" :stroke-width="1.5" class="text-amber-500 flex-shrink-0" />
      <p class="text-[10px] text-amber-500/80 leading-snug">
        These values appear on the cover slide. Leave blank to use auto-calculated defaults from your data.
      </p>
    </div>

    <div
      v-for="stat in store.heroFields"
      :key="stat.key"
      class="p-3 rounded-lg border border-border bg-[var(--glass-bg)] space-y-2"
    >
      <!-- Label row -->
      <input
        :value="stat.label"
        class="w-full bg-transparent text-[11px] font-medium text-foreground/80 outline-none border-b border-border/40 pb-1 placeholder:text-muted-foreground/40 focus:border-amber-500/40"
        placeholder="Label (e.g. Vacancy Rate)"
        @input="store.updateHeroField(stat.key, 'label', ($event.target as HTMLInputElement).value)"
      />

      <div class="flex items-center gap-2">
        <!-- Value input -->
        <input
          :value="stat.value"
          class="flex-1 h-8 bg-foreground/[0.04] border border-border rounded-lg px-2.5 text-sm font-mono text-foreground/90 outline-none placeholder:text-muted-foreground/30 focus:border-amber-500/50"
          placeholder="e.g. 8.2%"
          @input="store.updateHeroField(stat.key, 'value', ($event.target as HTMLInputElement).value)"
        />

        <!-- Trend selector -->
        <div class="flex gap-1">
          <button
            v-for="t in trends"
            :key="t.id"
            class="w-7 h-8 flex items-center justify-center rounded-lg border transition-all duration-150"
            :class="
              stat.trend === t.id
                ? t.id === 'up'
                  ? 'bg-green-500/15 border-green-500/30 text-green-400'
                  : t.id === 'down'
                  ? 'bg-red-500/15 border-red-500/30 text-red-400'
                  : 'bg-foreground/[0.06] border-border text-muted-foreground'
                : 'border-border/50 text-muted-foreground/40 hover:border-border hover:text-muted-foreground/70'
            "
            :title="t.label"
            @click="store.updateHeroField(stat.key, 'trend', t.id)"
          >
            <component :is="t.icon" :size="12" :stroke-width="2" />
          </button>
        </div>
      </div>
    </div>

    <p class="text-[10px] text-muted-foreground/50 text-center">
      Trend arrows are rendered on the cover slide of the generated PPT.
    </p>
  </div>
</template>
