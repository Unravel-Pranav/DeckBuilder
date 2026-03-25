/**
 * layoutDefinitions.ts
 *
 * Single source of truth for structural slide layouts.
 *
 * Layouts are purely structural (grid arrangements).
 * Content (chart, table, text, KPI) is added into regions independently.
 */

import type { SlideStructure } from '@/types'

// ─── Structural Definition ────────────────────────────────────────────────────

export interface StructureDefinition {
  id: SlideStructure
  label: string
  tooltip: string
  regionCount: number
  regionLabels: string[]
  gridClass: string
  /** Backend layout_preference string for generation */
  backendPreference: string
}

export const STRUCTURE_REGISTRY: StructureDefinition[] = [
  {
    id: 'blank',
    label: 'Blank',
    tooltip: 'Full slide — one region for any content',
    regionCount: 1,
    regionLabels: ['Full Slide'],
    gridClass: 'grid-cols-1',
    backendPreference: 'Full Width',
  },
  {
    id: 'two-col',
    label: 'Vertical Split',
    tooltip: 'Left and right sections',
    regionCount: 2,
    regionLabels: ['Left', 'Right'],
    gridClass: 'grid-cols-2',
    backendPreference: 'Content (2x2 Grid)',
  },
  {
    id: 'two-row',
    label: 'Horizontal Split',
    tooltip: 'Top and bottom sections',
    regionCount: 2,
    regionLabels: ['Top', 'Bottom'],
    gridClass: 'grid-cols-1 grid-rows-2',
    backendPreference: 'Content (2x2 Grid)',
  },
  {
    id: 'grid-2x2',
    label: '2×2 Grid',
    tooltip: 'Four equal quadrants',
    regionCount: 4,
    regionLabels: ['Top Left', 'Top Right', 'Bottom Left', 'Bottom Right'],
    gridClass: 'grid-cols-2 grid-rows-2',
    backendPreference: 'Content (2x2 Grid)',
  },
]

// ─── Derived Lookups ──────────────────────────────────────────────────────────

export const STRUCTURE_BY_ID: Record<string, StructureDefinition> = Object.fromEntries(
  STRUCTURE_REGISTRY.map((s) => [s.id, s]),
)

export function getBackendPreference(structureId: string): string {
  return STRUCTURE_BY_ID[structureId]?.backendPreference ?? 'Content (2x2 Grid)'
}

// ─── Legacy re-exports (used by api.ts and preview page) ─────────────────────

/** @deprecated Use STRUCTURE_BY_ID */
export type LayoutCategory = 'full_width' | 'two_column' | 'grid' | 'title' | 'kpi' | 'section'

/** @deprecated */
export const LAYOUT_BY_ID: Record<string, StructureDefinition> = STRUCTURE_BY_ID

/** @deprecated */
export const CATEGORY_LABELS: Record<string, string> = {
  blank: 'Blank',
  'two-col': 'Vertical Split',
  'two-row': 'Horizontal Split',
  'grid-2x2': '2×2 Grid',
}
