import { toast } from 'vue-sonner'

/**
 * Surfaces API and network failures to the user via toast notifications.
 */
export function notifyApiError(err: unknown, context: string): void {
  const message =
    err instanceof Error ? err.message : typeof err === 'string' ? err : 'An unexpected error occurred'
  toast.error(context, { description: message })
}

export function useApiError() {
  return { notifyApiError }
}
