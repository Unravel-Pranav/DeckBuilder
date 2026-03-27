import type { ChartData, TableData, SlideComponent, ChartType } from '@/types'

// ─── Data Type Detection ───

export type DetectedDataType = 'chart' | 'table' | 'text' | 'unknown'

export interface DetectionResult {
  type: DetectedDataType
  confidence: number
  chartType?: ChartType
  errors: string[]
}

const VALID_CHART_TYPES = new Set<ChartType>(['bar', 'pie', 'line', 'doughnut', 'area', 'scatter'])

export function detectDataType(raw: unknown): DetectionResult {
  if (typeof raw === 'string') {
    return { type: 'text', confidence: 1, errors: [] }
  }

  if (typeof raw !== 'object' || raw === null) {
    return { type: 'unknown', confidence: 0, errors: ['Input is not an object or string'] }
  }

  const obj = raw as Record<string, unknown>

  const explicitType = typeof obj.type === 'string' && VALID_CHART_TYPES.has(obj.type as ChartType)
    ? (obj.type as ChartType)
    : undefined

  if (Array.isArray(obj.headers) && Array.isArray(obj.rows)) {
    return { type: 'table', confidence: 0.95, errors: [] }
  }

  if (Array.isArray(obj.labels) && Array.isArray(obj.values)) {
    const chartType = explicitType ?? inferChartType(obj.values as number[], obj.labels as string[])
    return { type: 'chart', confidence: 0.9, chartType, errors: [] }
  }

  if (Array.isArray(obj.x_axis) && Array.isArray(obj.y_axis)) {
    const chartType = explicitType ?? inferChartType(obj.y_axis as number[], obj.x_axis as string[])
    return { type: 'chart', confidence: 0.95, chartType, errors: [] }
  }

  if (Array.isArray(obj.series)) {
    const chartType = explicitType ?? inferSeriesChartType(obj)
    return { type: 'chart', confidence: 0.85, chartType, errors: [] }
  }

  if (typeof obj.content === 'string' || typeof obj.text === 'string') {
    return { type: 'text', confidence: 0.8, errors: [] }
  }

  return { type: 'unknown', confidence: 0, errors: ['Could not determine data type'] }
}

function inferSeriesChartType(obj: Record<string, unknown>): ChartType {
  const series = obj.series as Array<{ data?: number[] }>
  const labels = (obj.x_axis ?? obj.labels) as string[] | undefined
  const pointCount = labels?.length ?? series[0]?.data?.length ?? 0

  if (series.length >= 2 || pointCount > 6) return 'line'
  return 'bar'
}

function inferChartType(values: number[], labels?: (string | number)[]): ChartType {
  const allNonNegative = values.every((v) => v >= 0)
  const labelsAreNumeric = labels != null && labels.every((l) => !isNaN(Number(l)))

  if (labelsAreNumeric && values.length >= 3) return 'scatter'

  if (!labelsAreNumeric && allNonNegative && values.length >= 2 && values.length <= 6) {
    const sum = values.reduce((a, b) => a + b, 0)
    const looksLikeProportions = (sum > 90 && sum < 110) || (sum > 0.9 && sum < 1.1)
    if (looksLikeProportions) return 'pie'
  }

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

  if (series) {
    if (!Array.isArray(series)) {
      errors.push('"series" must be an array of { label, data } objects')
    } else {
      const labelCount = Array.isArray(labels) ? (labels as unknown[]).length : null
      for (let i = 0; i < series.length; i++) {
        const entry = series[i] as Record<string, unknown> | null
        if (!entry || typeof entry !== 'object') {
          errors.push(`series[${i}] must be an object with "label" and "data"`)
          continue
        }
        if (!Array.isArray(entry.data)) {
          errors.push(`series[${i}] is missing a "data" array`)
        } else {
          if (!(entry.data as unknown[]).every((v) => typeof v === 'number')) {
            errors.push(`series[${i}].data must contain only numbers`)
          }
          if (labelCount != null && (entry.data as unknown[]).length !== labelCount) {
            warnings.push(`series[${i}].data length (${(entry.data as unknown[]).length}) doesn't match label count (${labelCount})`)
          }
        }
      }
    }
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
