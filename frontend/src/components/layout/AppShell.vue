<script setup lang="ts">
import { useUiStore } from '@/stores/ui'
import AmbientBackground from './AmbientBackground.vue'
import AppSidebar from './AppSidebar.vue'
import TopBar from './TopBar.vue'

const uiStore = useUiStore()
</script>

<template>
  <div class="min-h-screen bg-background">
    <AmbientBackground />
    <AppSidebar />

    <div
      class="transition-all duration-300"
      :class="uiStore.sidebarCollapsed ? 'ml-16' : 'ml-64'"
    >
      <TopBar />
      <main class="relative">
        <slot />
      </main>
    </div>
  </div>
</template>
