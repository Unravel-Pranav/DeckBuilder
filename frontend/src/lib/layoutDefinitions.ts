/**
 * layoutDefinitions.ts
 *
 * Single source of truth for every layout in the system.
 *
 * Adding a new layout:
 *  1. Add the id to `LayoutCategory` (if it's a new category) and to `LayoutType` in presentation.ts
 *  2. Add a `LayoutDefinition` entry here
 *  3. The rest of the system (api, selector, canvas, preview) reads from this file automatically
 */

// ─── Category ─────────────────────────────────────────────────────────────────

/**
 * layout_category groups related layouts and drives:
 * - visual grouping in LayoutSelector
 * - backend layout_preference resolution
 * - SlideCanvas render strategy
 */
export type LayoutCategory =
  | 'full_width'   // Single element spans full slide
  | 'two_column'   // Two side-by-side panels
  | 'grid'         // Full 2×2 four-quadrant grid
  | 'title'        // Title / intro slide
  | 'kpi'          // KPI / highlight numbers
  | 'section'      // Section divider

// ─── Definition ───────────────────────────────────────────────────────────────

export interface LayoutDefinition {
  /** Unique id — must match LayoutType in presentation.ts */
  id: string
  /** Display label shown in the selector */
  label: string
  /** Short tooltip */
  tooltip: string
  /** Category used for grouping and backend logic */
  category: LayoutCategory
  /** String sent to backend as layout_preference */
  backendPreference: string
  /**
   * When true, tables in this layout render ALL rows without truncation
   * (render_full_table flag sent to backend)
   */
  fullTableMode?: boolean
  /**
   * Explicit quadrant positions for each component slot.
   * 0=Top-Left, 1=Top-Right, 2=Bottom-Left, 3=Bottom-Right
   * undefined = let backend smart-sort by content type
   */
  quadrantPositions?: (number | null)[]
  /**
   * Which panels are visible in the canvas preview.
   * Drives hasChart / hasTable / hasCommentary / hasKpi / hasDivider flags.
   */
  panels: {
    chart?: boolean
    table?: boolean
    commentary?: boolean
    kpi?: boolean
    divider?: boolean
    title?: boolean
  }
  /** CSS grid class for SlideCanvas */
  gridClass: string
  /** Per-panel col-span classes in order: [chart?, table?, commentary?] */
  panelSpans: string[]
}

// ─── Master Registry ──────────────────────────────────────────────────────────

export const LAYOUT_REGISTRY: LayoutDefinition[] = [
  // ── Full-Width ──────────────────────────────────────────────────────────────
  {
    id: 'full-chart',
    label: 'Chart',
    tooltip: 'Single chart, full slide width',
    category: 'full_width',
    backendPreference: 'Full Width',
    panels: { chart: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },
  {
    id: 'full-table',
    label: 'Table',
    tooltip: 'Single table — all rows shown (no truncation)',
    category: 'full_width',
    backendPreference: 'Full Width',
    fullTableMode: true,
    panels: { table: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },
  {
    id: 'commentary-only',
    label: 'Text Only',
    tooltip: 'Commentary / text block, full width',
    category: 'full_width',
    backendPreference: 'Full Width',
    panels: { commentary: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },

  // ── Two-Column ──────────────────────────────────────────────────────────────
  {
    id: 'chart-commentary',
    label: 'Chart + Text',
    tooltip: 'Chart on the left, commentary on the right',
    category: 'two_column',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1],
    panels: { chart: true, commentary: true },
    gridClass: 'grid-cols-5',
    panelSpans: ['col-span-3', 'col-span-2'],
  },
  {
    id: 'table-commentary',
    label: 'Table + Text',
    tooltip: 'Table on the left, commentary on the right',
    category: 'two_column',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1],
    panels: { table: true, commentary: true },
    gridClass: 'grid-cols-5',
    panelSpans: ['col-span-3', 'col-span-2'],
  },
  {
    id: 'quadrant-2c',
    label: '2 Charts',
    tooltip: 'Two charts side-by-side',
    category: 'two_column',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1],
    panels: { chart: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1'],
  },
  {
    id: 'quadrant-1c1t',
    label: 'Chart + Table',
    tooltip: 'Chart on the left, table on the right',
    category: 'two_column',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1],
    panels: { chart: true, table: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1'],
  },

  // ── Grid (4-Quadrant) ───────────────────────────────────────────────────────
  {
    id: 'mixed',
    label: 'Auto Mixed',
    tooltip: 'Auto-ordered: charts → tables → commentary across 4 quadrants',
    category: 'grid',
    backendPreference: 'Content (2x2 Grid)',
    panels: { chart: true, table: true, commentary: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1', 'col-span-1', 'col-span-1'],
  },
  {
    id: 'quadrant-2c1t1text',
    label: '2C + Table + Text',
    tooltip: '2 Charts (top) · Table (bottom-left) · Commentary (bottom-right)',
    category: 'grid',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1, 2, 3],
    panels: { chart: true, table: true, commentary: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1', 'col-span-1', 'col-span-1'],
  },
  {
    id: 'quadrant-2c2t',
    label: '2C + 2 Tables',
    tooltip: '2 Charts (top) · 2 Tables (bottom) — all rows shown',
    category: 'grid',
    backendPreference: 'Content (2x2 Grid)',
    fullTableMode: true,
    quadrantPositions: [0, 1, 2, 3],
    panels: { chart: true, table: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1', 'col-span-1', 'col-span-1'],
  },

  // ── Title ───────────────────────────────────────────────────────────────────
  {
    id: 'title-content',
    label: 'Title + Content',
    tooltip: 'Bold title with supporting text/body content below',
    category: 'title',
    backendPreference: 'Full Width',
    panels: { title: true, commentary: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },
  {
    id: 'title-2col',
    label: 'Title + 2-Col',
    tooltip: 'Bold title with two content columns below',
    category: 'title',
    backendPreference: 'Content (2x2 Grid)',
    quadrantPositions: [0, 1],
    panels: { title: true, chart: true, commentary: true },
    gridClass: 'grid-cols-2',
    panelSpans: ['col-span-1', 'col-span-1'],
  },

  // ── KPI ─────────────────────────────────────────────────────────────────────
  {
    id: 'kpi-highlight',
    label: 'KPI Highlight',
    tooltip: 'Large KPI numbers with supporting context — ideal for first slides',
    category: 'kpi',
    backendPreference: 'Full Width',
    panels: { kpi: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },

  // ── Section ─────────────────────────────────────────────────────────────────
  {
    id: 'section-divider',
    label: 'Section Divider',
    tooltip: 'Visual section break slide with title and optional sub-label',
    category: 'section',
    backendPreference: 'Full Width',
    panels: { divider: true },
    gridClass: 'grid-cols-1',
    panelSpans: ['col-span-1'],
  },
]

// ─── Derived Lookups (generated once, used everywhere) ───────────────────────

/** Fast O(1) lookup by layout id */
export const LAYOUT_BY_ID: Record<string, LayoutDefinition> = Object.fromEntries(
  LAYOUT_REGISTRY.map((l) => [l.id, l]),
)

/** Grouped by category for the selector */
export const LAYOUTS_BY_CATEGORY: Record<LayoutCategory, LayoutDefinition[]> = {
  full_width: [],
  two_column: [],
  grid: [],
  title: [],
  kpi: [],
  section: [],
}
for (const def of LAYOUT_REGISTRY) {
  LAYOUTS_BY_CATEGORY[def.category].push(def)
}

/** Backend preference string for a given layout id */
export function getBackendPreference(layoutId: string): string {
  return LAYOUT_BY_ID[layoutId]?.backendPreference ?? 'Content (2x2 Grid)'
}

/** Category label shown in LayoutSelector */
export const CATEGORY_LABELS: Record<LayoutCategory, string> = {
  full_width: 'Full Width',
  two_column: '2-Column',
  grid: '4-Quadrant',
  title: 'Title',
  kpi: 'KPI',
  section: 'Section',
}
