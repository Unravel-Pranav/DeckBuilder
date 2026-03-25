<script setup lang="ts">
import { useRouter } from 'vue-router'
import { usePresentationStore } from '@/stores/presentation'
import { useUiStore } from '@/stores/ui'
import { useAiStore } from '@/stores/ai'
import IntentForm from '@/components/create/IntentForm.vue'
import AiSuggestionPanel from '@/components/create/AiSuggestionPanel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ArrowRight, Loader2 } from 'lucide-vue-next'
import { ref } from 'vue'

const router = useRouter()
const presentationStore = usePresentationStore()
const uiStore = useUiStore()
const aiStore = useAiStore()

const presentationName = ref('')
const isSubmitting = ref(false)

async function handleContinue() {
  if (isSubmitting.value) return
  isSubmitting.value = true

  try {
    const name = presentationName.value.trim() || 'Untitled Presentation'
    presentationStore.createPresentation(name)
    uiStore.completeStep('create')
    uiStore.setCurrentStep('recommendations')

    await aiStore.fetchRecommendations()
    router.push('/recommendations')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="px-6 md:px-8 lg:px-12 py-8 md:py-12 max-w-6xl mx-auto">
    <div class="grid grid-cols-1 lg:grid-cols-5 gap-8 lg:gap-12">
      <!-- Left: Form -->
      <div class="lg:col-span-3 space-y-8">
        <div>
          <h2 class="text-2xl md:text-3xl font-display font-bold tracking-tight mb-2">
            Define Your Presentation
          </h2>
          <p class="text-sm text-muted-foreground">
            Tell us about your presentation and we'll recommend the best structure.
          </p>
        </div>

        <!-- Name input -->
        <div>
          <Label for="name" class="text-sm font-medium text-foreground/80 mb-2 block">
            Presentation Name
          </Label>
          <Input
            id="name"
            v-model="presentationName"
            placeholder="e.g., Q4 2025 Financial Review"
            class="h-11 bg-[var(--glass-bg)] border-border rounded-xl placeholder:text-muted-foreground/50 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20"
          />
        </div>

        <IntentForm />

        <div class="pt-4">
          <Button
            :disabled="isSubmitting"
            class="bg-amber-500 text-[#09090B] hover:bg-amber-400 font-medium h-12 px-8 rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] transition-all duration-200 active:scale-[0.98] text-base disabled:opacity-60"
            @click="handleContinue"
          >
            <Loader2 v-if="isSubmitting" :size="18" class="mr-2 animate-spin" />
            {{ isSubmitting ? 'Analyzing...' : 'Continue' }}
            <ArrowRight v-if="!isSubmitting" :size="18" :stroke-width="2" class="ml-2" />
          </Button>
        </div>
      </div>

      <!-- Right: AI Suggestions -->
      <div class="lg:col-span-2">
        <AiSuggestionPanel />
      </div>
    </div>
  </div>
</template>
