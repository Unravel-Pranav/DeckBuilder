import type { ChartData, TableData, SlideComponent, DataSchema, ChartType } from '@/types'

// ─── Data Type Detection ───

export type DetectedDataType = 'chart' | 'table' | 'text' | 'unknown'

export interface DetectionResult {
  type: DetectedDataType
  confidence: number
  chartType?: ChartType
  errors: string[]
}

export function detectDataType(raw: unknown): DetectionResult {
  if (typeof raw === 'string') {
    return { type: 'text', confidence: 1, errors: [] }
  }

  if (typeof raw !== 'object' || raw === null) {
    return { type: 'unknown', confidence: 0, errors: ['Input is not an object or string'] }
  }

  const obj = raw as Record<string, unknown>

  if (Array.isArray(obj.headers) && Array.isArray(obj.rows)) {
    return { type: 'table', confidence: 0.95, errors: [] }
  }

  if (Array.isArray(obj.labels) && Array.isArray(obj.values)) {
    const chartType = inferChartType(obj.values as number[])
    return { type: 'chart', confidence: 0.9, chartType, errors: [] }
  }

  if (Array.isArray(obj.x_axis) && Array.isArray(obj.y_axis)) {
    const chartType = inferChartType(obj.y_axis as number[])
    return { type: 'chart', confidence: 0.95, chartType, errors: [] }
  }

  if (Array.isArray(obj.series)) {
    return { type: 'chart', confidence: 0.85, chartType: 'bar', errors: [] }
  }

  if (typeof obj.content === 'string' || typeof obj.text === 'string') {
    return { type: 'text', confidence: 0.8, errors: [] }
  }

  return { type: 'unknown', confidence: 0, errors: ['Could not determine data type'] }
}

function inferChartType(values: number[]): ChartType {
  if (values.length <= 5 && values.every((v) => v >= 0)) return 'pie'
  if (values.length > 8) return 'line'
  return 'bar'
}

// ─── Schema Validation ───

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export function validateChartSchema(data: unknown): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (typeof data !== 'object' || data === null) {
    return { valid: false, errors: ['Data must be a JSON object'], warnings }
  }

  const obj = data as Record<string, unknown>

  const labels = obj.x_axis ?? obj.labels
  const values = obj.y_axis ?? obj.values
  const series = obj.series

  if (!labels && !series) {
    errors.push('Missing required field: "x_axis" (or "labels")')
  } else if (labels && !Array.isArray(labels)) {
    errors.push('"x_axis" / "labels" must be an array of strings')
  }

  if (!values && !series) {
    errors.push('Missing required field: "y_axis" (or "values" or "series")')
  } else if (values && !Array.isArray(values)) {
    errors.push('"y_axis" / "values" must be an array of numbers')
  } else if (values && Array.isArray(values)) {
    if (!values.every((v) => typeof v === 'number')) {
      errors.push('All values in "y_axis" must be numbers')
    }
    if (Array.isArray(labels) && values.length !== (labels as unknown[]).length) {
      warnings.push(`Label count (${(labels as unknown[]).length}) doesn't match value count (${values.length})`)
    }
  }

  if (series && !Array.isArray(series)) {
    errors.push('"series" must be an array of { label, data } objects')
  }

  return { valid: errors.length === 0, errors, warnings }
}

export function validateTableSchema(data: unknown): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (typeof data !== 'object' || data === null) {
    return { valid: false, errors: ['Data must be a JSON object'], warnings }
  }

  const obj = data as Record<string, unknown>

  if (!Array.isArray(obj.headers)) {
    errors.push('Missing required field: "headers" (array of strings)')
  } else {
    if (!obj.headers.every((h: unknown) => typeof h === 'string')) {
      errors.push('All headers must be strings')
    }
  }

  if (!Array.isArray(obj.rows)) {
    errors.push('Missing required field: "rows" (array of arrays)')
  } else {
    if (!obj.rows.every((r: unknown) => Array.isArray(r))) {
      errors.push('Each row must be an array')
    }
    if (Array.isArray(obj.headers)) {
      const colCount = (obj.headers as unknown[]).length
      const badRows = (obj.rows as unknown[][]).filter((r) => r.length !== colCount)
      if (badRows.length > 0) {
        warnings.push(`${badRows.length} row(s) have mismatched column count (expected ${colCount})`)
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings }
}

export function validateSchema(data: unknown, expectedType: 'chart' | 'table' | 'text'): ValidationResult {
  if (expectedType === 'chart') return validateChartSchema(data)
  if (expectedType === 'table') return validateTableSchema(data)
  return { valid: true, errors: [], warnings: [] }
}

// ─── Data → Component Mapping ───

export function mapDataToChartComponent(
  raw: Record<string, unknown>,
  chartType: ChartType = 'bar',
): Omit<ChartData, 'type'> & { type: ChartType } {
  const labels = (raw.x_axis ?? raw.labels ?? []) as string[]

  if (Array.isArray(raw.series)) {
    const datasets = (raw.series as Array<{ label?: string; data?: number[] }>).map((s) => ({
      label: s.label ?? 'Series',
      data: s.data ?? [],
    }))
    return { type: chartType, labels, datasets }
  }

  const values = (raw.y_axis ?? raw.values ?? []) as number[]
  return {
    type: chartType,
    labels,
    datasets: [{ label: (raw.label as string) ?? 'Data', data: values }],
  }
}

export function mapDataToTableComponent(raw: Record<string, unknown>): TableData {
  return {
    headers: (raw.headers as string[]) ?? [],
    rows: (raw.rows as string[][]) ?? [],
  }
}

// ─── Fallback Strategy ───

export function getSafeFallback(type: 'chart' | 'table' | 'text'): SlideComponent {
  if (type === 'chart') {
    return {
      id: crypto.randomUUID(),
      type: 'chart',
      data: {
        type: 'bar',
        labels: ['No Data'],
        datasets: [{ label: 'Fallback', data: [0] }],
      },
      config: {},
    }
  }

  if (type === 'table') {
    return {
      id: crypto.randomUUID(),
      type: 'table',
      data: { headers: ['—'], rows: [['No data available']] },
      config: {},
    }
  }

  return {
    id: crypto.randomUUID(),
    type: 'text',
    data: { content: 'No content yet.' },
    config: { format: 'paragraph' },
  }
}

export function ensureSafeRender(component: SlideComponent): SlideComponent {
  if (component.type === 'chart') {
    const c = component
    if (!c.data?.datasets?.length || !c.data?.labels?.length) {
      return getSafeFallback('chart')
    }
  }
  if (component.type === 'table') {
    const c = component
    if (!c.data?.headers?.length) {
      return getSafeFallback('table')
    }
  }
  return component
}
