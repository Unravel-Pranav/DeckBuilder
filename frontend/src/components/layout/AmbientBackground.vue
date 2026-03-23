<script setup lang="ts">
</script>

<template>
  <div class="fixed inset-0 -z-10 overflow-hidden pointer-events-none" aria-hidden="true">
    <!-- Primary amber orb — top center -->
    <div
      class="absolute -top-32 left-1/2 -translate-x-1/2 h-[400px] w-[600px] md:h-[600px] md:w-[900px] rounded-full opacity-[0.03]"
      style="background: radial-gradient(circle, #F59E0B 0%, transparent 70%); filter: blur(120px)"
    />

    <!-- Secondary orb — bottom right -->
    <div
      class="absolute -bottom-48 -right-32 h-[350px] w-[500px] md:h-[500px] md:w-[700px] rounded-full opacity-[0.02]"
      style="background: radial-gradient(circle, #F59E0B 0%, transparent 70%); filter: blur(150px)"
    />

    <!-- Subtle noise texture -->
    <div
      class="absolute inset-0 opacity-[0.015]"
      style="background-image: url(&quot;data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.5'/%3E%3C/svg%3E&quot;)"
    />

    <!-- Subtle grid -->
    <div
      class="absolute inset-0 opacity-[0.02]"
      style="background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px); background-size: 40px 40px"
    />
  </div>
</template>
