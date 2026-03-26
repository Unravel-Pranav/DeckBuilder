import { ref, readonly } from 'vue'
import type { SlideComponent } from '@/types'

export interface DragPayload {
  componentType: 'chart' | 'table' | 'text' | 'uploaded_slide'
  component: SlideComponent | Omit<SlideComponent, 'id'>
  label: string
  /** Set when dragging an existing component between regions (internal move) */
  sourceRegionIndex?: number
}

const _isDragging = ref(false)
const _payload = ref<DragPayload | null>(null)
const _hoverRegionIndex = ref<number | null>(null)

export function useDragDrop() {
  function startDrag(event: DragEvent, data: DragPayload) {
    _isDragging.value = true
    _payload.value = data
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = data.sourceRegionIndex != null ? 'move' : 'copy'
      event.dataTransfer.setData('application/x-deckbuilder', 'drag')
    }
  }

  function endDrag() {
    _isDragging.value = false
    _payload.value = null
    _hoverRegionIndex.value = null
  }

  function setHoverRegion(index: number | null) {
    _hoverRegionIndex.value = index
  }

  function consumePayload(): DragPayload | null {
    const data = _payload.value
    _isDragging.value = false
    _payload.value = null
    _hoverRegionIndex.value = null
    return data
  }

  return {
    isDragging: readonly(_isDragging),
    hoverRegionIndex: readonly(_hoverRegionIndex),
    payload: readonly(_payload),
    startDrag,
    endDrag,
    setHoverRegion,
    consumePayload,
  }
}
