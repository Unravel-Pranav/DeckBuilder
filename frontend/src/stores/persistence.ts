/**
 * Pinia persistence plugin — saves/restores selected stores to sessionStorage.
 *
 * Why sessionStorage over localStorage:
 *   - Scoped to the tab → multiple presentations in parallel tabs stay isolated
 *   - Cleared automatically when the tab closes (no stale orphans)
 *   - Still survives in-tab navigation and full page reloads
 *
 * The `PresentationIntent.referenceFile` (a `File` object) is non-serialisable;
 * we strip it on save and restore it as `null`.
 */

import type { PiniaPluginContext } from 'pinia'
import { watch, toRaw } from 'vue'

const STORAGE_PREFIX = 'autodeck:draft:'

const PERSISTED_STORES = new Set([
  'presentation',
  'slides',
  'ui',
  'ai',
])

function storageKey(storeId: string): string {
  return `${STORAGE_PREFIX}${storeId}`
}

function serialize(storeId: string, state: Record<string, unknown>): string {
  const raw = toRaw(state)

  if (storeId === 'presentation') {
    const copy = { ...raw }
    if (copy.intent && typeof copy.intent === 'object') {
      copy.intent = { ...(copy.intent as Record<string, unknown>), referenceFile: null }
    }
    if (copy.currentPresentation && typeof copy.currentPresentation === 'object') {
      const pres = copy.currentPresentation as Record<string, unknown>
      if (pres.intent && typeof pres.intent === 'object') {
        pres.intent = { ...(pres.intent as Record<string, unknown>), referenceFile: null }
      }
    }
    return JSON.stringify(copy)
  }

  if (storeId === 'ui') {
    const copy = { ...raw }
    if (copy.completedSteps instanceof Set) {
      copy.completedSteps = [...copy.completedSteps]
    }
    return JSON.stringify(copy)
  }

  return JSON.stringify(raw)
}

function deserialize(storeId: string, json: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(json)
    if (storeId === 'ui' && Array.isArray(parsed.completedSteps)) {
      parsed.completedSteps = new Set(parsed.completedSteps)
    }
    return parsed
  } catch {
    return null
  }
}

export function piniaSessionPersistence({ store }: PiniaPluginContext): void {
  if (!PERSISTED_STORES.has(store.$id)) return

  const key = storageKey(store.$id)
  const saved = sessionStorage.getItem(key)
  if (saved) {
    const restored = deserialize(store.$id, saved)
    if (restored) {
      store.$patch(restored)
    }
  }

  watch(
    () => store.$state,
    (state) => {
      try {
        sessionStorage.setItem(key, serialize(store.$id, state))
      } catch {
        // quota exceeded — silently skip
      }
    },
    { deep: true },
  )

  const originalReset = store.$reset?.bind(store)
  if (originalReset) {
    store.$reset = () => {
      originalReset()
      sessionStorage.removeItem(key)
    }
  }
}

/**
 * Clears all draft keys from sessionStorage. Called by `$reset()` flows
 * (e.g. "Create New" on OutputPage) so every store starts fresh.
 */
export function clearAllDraftStorage(): void {
  const keysToRemove: string[] = []
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i)
    if (k?.startsWith(STORAGE_PREFIX)) keysToRemove.push(k)
  }
  keysToRemove.forEach((k) => sessionStorage.removeItem(k))
}
