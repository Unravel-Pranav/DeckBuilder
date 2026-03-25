<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { usePresentationStore } from '@/stores/presentation'
import { useUiStore } from '@/stores/ui'
import { useTheme } from '@/composables/useTheme'
import { Menu, Bell, Settings, Sun, Moon } from 'lucide-vue-next'

const route = useRoute()
const presentationStore = usePresentationStore()
const uiStore = useUiStore()
const { isDark, toggleTheme } = useTheme()

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    dashboard: 'Dashboard',
    create: 'Create Presentation',
    recommendations: 'AI Recommendations',
    sections: 'Section Manager',
    builder: 'Slide Builder',
    templates: 'Templates',
    'template-upload': 'Upload Template',
    preview: 'Preview & Generate',
    output: 'Your Presentation',
  }
  return titles[route.name as string] ?? 'DeckBuilder'
})

const showPresentationName = computed(() =>
  route.name !== 'dashboard' && presentationStore.currentPresentation,
)
</script>

<template>
  <header
    class="sticky top-0 z-30 flex items-center justify-between h-16 px-6 border-b border-border"
    :style="{ backgroundColor: 'var(--topbar-bg)', backdropFilter: 'blur(12px)' }"
  >
    <div class="flex items-center gap-4">
      <!-- Mobile menu toggle -->
      <button
        class="md:hidden p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-colors"
        @click="uiStore.toggleSidebar()"
      >
        <Menu :size="20" :stroke-width="1.5" />
      </button>

      <div>
        <h1 class="text-lg font-display font-semibold tracking-tight">
          {{ pageTitle }}
        </h1>
        <p v-if="showPresentationName" class="text-xs text-muted-foreground font-mono tracking-wide">
          {{ presentationStore.presentationName }}
        </p>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <!-- Theme toggle -->
      <button
        class="p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-all duration-200"
        :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
        @click="() => toggleTheme()"
      >
        <Sun v-if="isDark" :size="18" :stroke-width="1.5" />
        <Moon v-else :size="18" :stroke-width="1.5" />
      </button>

      <button
        class="p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-all duration-200"
      >
        <Bell :size="18" :stroke-width="1.5" />
      </button>
      <button
        class="p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-all duration-200"
      >
        <Settings :size="18" :stroke-width="1.5" />
      </button>

      <!-- User avatar -->
      <div
        class="w-8 h-8 rounded-full bg-gradient-to-br from-amber-500/20 to-amber-600/20 border border-amber-500/20 flex items-center justify-center ml-2"
      >
        <span class="text-xs font-medium text-amber-500">U</span>
      </div>
    </div>
  </header>
</template>
