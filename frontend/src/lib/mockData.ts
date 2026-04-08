import type { Presentation, Section, Slide, ChartData, TableData, SlideTemplate, SlidePreviewData, SlideComponent, SlideStructure } from '@/types'
import { createRegions } from '@/types'

export const mockChartData: Record<string, ChartData> = {
  revenue: {
    type: 'bar',
    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    datasets: [
      {
        label: 'Revenue ($M)',
        data: [12.5, 18.3, 23.1, 19.7],
        backgroundColor: ['#F59E0B', '#FBBF24', '#F59E0B', '#D97706'],
      },
    ],
  },
  trends: {
    type: 'line',
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [
      {
        label: 'Users',
        data: [1200, 1900, 3000, 5000, 4800, 6100],
        borderColor: '#F59E0B',
      },
      {
        label: 'Active Sessions',
        data: [800, 1400, 2200, 3500, 3200, 4800],
        borderColor: '#71717A',
      },
    ],
  },
  distribution: {
    type: 'pie',
    labels: ['Product A', 'Product B', 'Product C', 'Product D'],
    datasets: [
      {
        label: 'Market Share',
        data: [35, 25, 22, 18],
        backgroundColor: ['#F59E0B', '#FBBF24', '#D97706', '#92400E'],
      },
    ],
  },
}

export const mockTableData: Record<string, TableData> = {
  competitors: {
    headers: ['Company', 'Revenue', 'Growth', 'Market Share', 'Rating'],
    rows: [
      ['Acme Corp', '$45.2M', '+23%', '35%', 'A+'],
      ['Beta Inc', '$32.1M', '+18%', '25%', 'A'],
      ['Gamma Ltd', '$28.7M', '+12%', '22%', 'B+'],
      ['Delta Co', '$21.3M', '+8%', '18%', 'B'],
    ],
  },
  financials: {
    headers: ['Metric', 'Q1', 'Q2', 'Q3', 'Q4'],
    rows: [
      ['Revenue', '$12.5M', '$18.3M', '$23.1M', '$19.7M'],
      ['COGS', '$5.2M', '$7.1M', '$8.9M', '$7.8M'],
      ['Gross Profit', '$7.3M', '$11.2M', '$14.2M', '$11.9M'],
      ['Op. Expenses', '$4.1M', '$4.5M', '$4.8M', '$4.3M'],
      ['Net Income', '$3.2M', '$6.7M', '$9.4M', '$7.6M'],
    ],
  },
}

export const chartTemplates: SlideTemplate[] = [
  {
    id: 'tmpl-bar-basic',
    name: 'Bar Chart — Basic',
    category: 'chart',
    chartType: 'bar',
    description: 'Standard vertical bar chart for comparing categories or time periods.',
    previewData: {
      type: 'bar',
      labels: ['Q1', 'Q2', 'Q3', 'Q4'],
      datasets: [{ label: 'Value', data: [40, 65, 50, 80] }],
    },
    schemaHint: '{ "x_axis": ["Q1", "Q2", ...], "y_axis": [100, 200, ...], "label": "Revenue" }',
  },
  {
    id: 'tmpl-bar-stacked',
    name: 'Stacked Bar Chart',
    category: 'chart',
    chartType: 'bar',
    description: 'Stacked bars to show composition across categories.',
    previewData: {
      type: 'bar',
      labels: ['Q1', 'Q2', 'Q3', 'Q4'],
      datasets: [
        { label: 'Product A', data: [20, 30, 25, 40] },
        { label: 'Product B', data: [15, 25, 20, 30] },
      ],
    },
    schemaHint: '{ "x_axis": [...], "series": [{ "label": "A", "data": [...] }, ...] }',
  },
  {
    id: 'tmpl-line-trend',
    name: 'Line Chart — Trend',
    category: 'chart',
    chartType: 'line',
    description: 'Line chart for showing trends over time. Supports multiple series.',
    previewData: {
      type: 'line',
      labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May'],
      datasets: [{ label: 'Growth', data: [10, 25, 40, 35, 60], borderColor: '#F59E0B' }],
    },
    schemaHint: '{ "x_axis": ["Jan", ...], "y_axis": [10, 25, ...], "label": "Growth" }',
  },
  {
    id: 'tmpl-line-multi',
    name: 'Multi-Line Comparison',
    category: 'chart',
    chartType: 'line',
    description: 'Compare multiple data series with overlaid lines.',
    previewData: {
      type: 'line',
      labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May'],
      datasets: [
        { label: 'This Year', data: [20, 35, 50, 45, 70], borderColor: '#F59E0B' },
        { label: 'Last Year', data: [15, 20, 30, 28, 45], borderColor: '#71717A' },
      ],
    },
    schemaHint: '{ "x_axis": [...], "series": [{ "label": "A", "data": [...] }, ...] }',
  },
  {
    id: 'tmpl-pie-basic',
    name: 'Pie Chart — Distribution',
    category: 'chart',
    chartType: 'pie',
    description: 'Show proportional distribution across categories.',
    previewData: {
      type: 'pie',
      labels: ['Segment A', 'Segment B', 'Segment C'],
      datasets: [{ label: 'Share', data: [45, 30, 25], backgroundColor: ['#F59E0B', '#FBBF24', '#D97706'] }],
    },
    schemaHint: '{ "labels": ["A", "B", ...], "values": [45, 30, ...] }',
  },
  {
    id: 'tmpl-doughnut',
    name: 'Doughnut Chart',
    category: 'chart',
    chartType: 'doughnut',
    description: 'Hollow pie chart with center area for a KPI or label.',
    previewData: {
      type: 'doughnut',
      labels: ['Complete', 'Remaining'],
      datasets: [{ label: 'Progress', data: [72, 28], backgroundColor: ['#F59E0B', '#1A1A24'] }],
    },
    schemaHint: '{ "labels": ["Done", "Remaining"], "values": [72, 28] }',
  },
  {
    id: 'tmpl-area',
    name: 'Area Chart',
    category: 'chart',
    chartType: 'area',
    description: 'Filled line chart to emphasize volume over time.',
    previewData: {
      type: 'area',
      labels: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6'],
      datasets: [{ label: 'Volume', data: [100, 250, 180, 320, 290, 410], borderColor: '#F59E0B' }],
    },
    schemaHint: '{ "x_axis": ["W1", ...], "y_axis": [100, 250, ...], "label": "Volume" }',
  },
]

export const tableTemplates: SlideTemplate[] = [
  {
    id: 'tmpl-table-basic',
    name: 'Data Table — Basic',
    category: 'table',
    description: 'Clean data table with headers and rows. Good for financial data.',
    previewData: {
      headers: ['Metric', 'Value', 'Change'],
      rows: [['Revenue', '$45.2M', '+12%'], ['Profit', '$18.1M', '+8%'], ['Margin', '40%', '+2pp']],
    },
    schemaHint: '{ "headers": ["Col1", ...], "rows": [["val", ...], ...] }',
  },
  {
    id: 'tmpl-table-comparison',
    name: 'Comparison Matrix',
    category: 'table',
    description: 'Side-by-side comparison table for competitors, products, or options.',
    previewData: {
      headers: ['Feature', 'Option A', 'Option B', 'Option C'],
      rows: [['Price', '$99', '$149', '$199'], ['Users', '10', '50', 'Unlimited'], ['Support', 'Email', 'Priority', '24/7']],
    },
    schemaHint: '{ "headers": ["Feature", "A", "B"], "rows": [[...], ...] }',
  },
  {
    id: 'tmpl-table-financial',
    name: 'Financial Statement',
    category: 'table',
    description: 'P&L, balance sheet, or cash flow format with period columns.',
    previewData: {
      headers: ['Line Item', 'Q1', 'Q2', 'Q3', 'Q4'],
      rows: [['Revenue', '$12M', '$18M', '$23M', '$20M'], ['COGS', '$5M', '$7M', '$9M', '$8M'], ['Net', '$7M', '$11M', '$14M', '$12M']],
    },
    schemaHint: '{ "headers": ["Item", "Q1", ...], "rows": [["Revenue", "$12M", ...], ...] }',
  },
  {
    id: 'tmpl-table-kpi',
    name: 'KPI Scorecard',
    category: 'table',
    description: 'Key performance indicators with targets, actuals, and status.',
    previewData: {
      headers: ['KPI', 'Target', 'Actual', 'Status'],
      rows: [['Revenue', '$50M', '$45M', 'At Risk'], ['NPS', '70', '75', 'On Track'], ['Churn', '<5%', '3.2%', 'Exceeding']],
    },
    schemaHint: '{ "headers": ["KPI", "Target", "Actual", "Status"], "rows": [...] }',
  },
]

export const textTemplates: SlideTemplate[] = [
  {
    id: 'tmpl-text-insights',
    name: 'Key Insights',
    category: 'text',
    description: 'Bullet-point insights with supporting commentary.',
    previewData: '• Market share grew 12% YoY driven by expansion into new segments\n• Customer acquisition cost decreased by 18% through channel optimization\n• Strategic partnerships contributed $8.5M in incremental revenue',
    schemaHint: 'Plain text or markdown bullets',
  },
  {
    id: 'tmpl-text-narrative',
    name: 'Narrative Block',
    category: 'text',
    description: 'Paragraph-style commentary for executive summaries or conclusions.',
    previewData: 'The analysis reveals strong momentum across core business lines, with particularly notable performance in the enterprise segment. Growth drivers include improved conversion rates and expanded product adoption among existing customers.',
    schemaHint: 'Plain text paragraph',
  },
  {
    id: 'tmpl-text-callout',
    name: 'Callout / Highlight',
    category: 'text',
    description: 'Large callout number or stat with supporting context.',
    previewData: '$45.2M\nTotal Revenue — Up 23% YoY',
    schemaHint: 'Main stat + supporting text',
  },
]

export const slideTemplates: SlideTemplate[] = [
  {
    id: 'tmpl-slide-title',
    name: 'Title Page',
    category: 'slide',
    slideKind: 'title',
    description: 'Opening title slide with presentation name, subtitle, date, and author.',
    previewData: {
      title: 'Presentation Title',
      subtitle: 'Subtitle or tagline goes here',
      elements: [
        { type: 'accent-bar', label: '', x: 0, y: 0, w: 100, h: 3 },
        { type: 'heading', label: 'Presentation Title', x: 10, y: 30, w: 80, h: 15 },
        { type: 'subheading', label: 'Subtitle or tagline', x: 10, y: 48, w: 60, h: 6 },
        { type: 'divider', label: '', x: 10, y: 58, w: 20, h: 1 },
        { type: 'body', label: 'Author Name  ·  Date  ·  Company', x: 10, y: 65, w: 50, h: 5 },
        { type: 'image-placeholder', label: 'Logo', x: 80, y: 75, w: 12, h: 12 },
      ],
      accentPosition: 'top',
    } as SlidePreviewData,
    schemaHint: '{ "title": "...", "subtitle": "...", "author": "...", "date": "...", "company": "..." }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Presentation Title\n\nSubtitle or tagline goes here\n\nAuthor Name · March 2026 · Company' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-section-divider',
    name: 'Section Divider',
    category: 'slide',
    slideKind: 'section-divider',
    description: 'Full-bleed section break slide with section number and title.',
    previewData: {
      title: 'Section Title',
      subtitle: '01',
      elements: [
        { type: 'accent-bar', label: '', x: 0, y: 45, w: 100, h: 2 },
        { type: 'body', label: '01', x: 10, y: 25, w: 15, h: 12 },
        { type: 'heading', label: 'Section Title', x: 10, y: 52, w: 70, h: 12 },
        { type: 'subheading', label: 'Brief description of this section', x: 10, y: 67, w: 60, h: 5 },
      ],
      accentPosition: 'center',
    } as SlidePreviewData,
    schemaHint: '{ "number": "01", "title": "...", "description": "..." }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: '01\n\nSection Title\n\nBrief description of what this section covers.' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-agenda',
    name: 'Agenda / Contents',
    category: 'slide',
    slideKind: 'agenda',
    description: 'Table of contents or agenda slide listing all sections.',
    previewData: {
      title: 'Agenda',
      elements: [
        { type: 'heading', label: 'Agenda', x: 8, y: 8, w: 40, h: 10 },
        { type: 'divider', label: '', x: 8, y: 20, w: 15, h: 1 },
        { type: 'list', label: '01  Executive Summary\n02  Market Overview\n03  Financial Analysis\n04  Key Insights\n05  Next Steps', x: 8, y: 28, w: 55, h: 55 },
        { type: 'accent-bar', label: '', x: 70, y: 15, w: 1, h: 70 },
        { type: 'body', label: 'Duration: 45 min', x: 75, y: 40, w: 20, h: 8 },
      ],
      accentPosition: 'left',
    } as SlidePreviewData,
    schemaHint: '{ "items": [{ "number": "01", "title": "..." }, ...], "duration": "45 min" }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Agenda\n\n01  Executive Summary\n02  Market Overview\n03  Financial Analysis\n04  Key Insights\n05  Next Steps' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-closing',
    name: 'Thank You / Closing',
    category: 'slide',
    slideKind: 'closing',
    description: 'Final slide with thank you message, contact info, and call to action.',
    previewData: {
      title: 'Thank You',
      subtitle: 'Questions?',
      elements: [
        { type: 'heading', label: 'Thank You', x: 15, y: 25, w: 70, h: 15 },
        { type: 'subheading', label: 'Questions & Discussion', x: 25, y: 43, w: 50, h: 6 },
        { type: 'divider', label: '', x: 40, y: 55, w: 20, h: 1 },
        { type: 'body', label: 'name@company.com  ·  +1 (555) 123-4567', x: 20, y: 62, w: 60, h: 5 },
        { type: 'image-placeholder', label: 'Logo', x: 42, y: 75, w: 16, h: 12 },
      ],
      accentPosition: 'center',
    } as SlidePreviewData,
    schemaHint: '{ "heading": "Thank You", "subtitle": "Questions?", "email": "...", "phone": "..." }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Thank You\n\nQuestions & Discussion\n\nname@company.com · +1 (555) 123-4567' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-team',
    name: 'Team / About Us',
    category: 'slide',
    slideKind: 'team',
    description: 'Team introduction slide with member cards showing photo, name, and role.',
    previewData: {
      title: 'Our Team',
      elements: [
        { type: 'heading', label: 'Our Team', x: 8, y: 8, w: 40, h: 10 },
        { type: 'divider', label: '', x: 8, y: 20, w: 15, h: 1 },
        { type: 'image-placeholder', label: 'Photo', x: 8, y: 30, w: 18, h: 25 },
        { type: 'body', label: 'Jane Doe\nCEO', x: 8, y: 58, w: 18, h: 10 },
        { type: 'image-placeholder', label: 'Photo', x: 30, y: 30, w: 18, h: 25 },
        { type: 'body', label: 'John Smith\nCTO', x: 30, y: 58, w: 18, h: 10 },
        { type: 'image-placeholder', label: 'Photo', x: 52, y: 30, w: 18, h: 25 },
        { type: 'body', label: 'Alex Chen\nCFO', x: 52, y: 58, w: 18, h: 10 },
        { type: 'image-placeholder', label: 'Photo', x: 74, y: 30, w: 18, h: 25 },
        { type: 'body', label: 'Sam Lee\nCOO', x: 74, y: 58, w: 18, h: 10 },
      ],
    } as SlidePreviewData,
    schemaHint: '{ "members": [{ "name": "...", "role": "...", "photo?": "url" }, ...] }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Our Team\n\nJane Doe — CEO\nJohn Smith — CTO\nAlex Chen — CFO\nSam Lee — COO' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-timeline',
    name: 'Timeline / Milestones',
    category: 'slide',
    slideKind: 'timeline',
    description: 'Horizontal timeline showing key milestones or project phases.',
    previewData: {
      title: 'Key Milestones',
      elements: [
        { type: 'heading', label: 'Key Milestones', x: 8, y: 8, w: 50, h: 10 },
        { type: 'accent-bar', label: '', x: 8, y: 45, w: 84, h: 2 },
        { type: 'icon-row', label: 'Q1\nResearch', x: 8, y: 32, w: 15, h: 25 },
        { type: 'icon-row', label: 'Q2\nPrototype', x: 30, y: 32, w: 15, h: 25 },
        { type: 'icon-row', label: 'Q3\nLaunch', x: 52, y: 32, w: 15, h: 25 },
        { type: 'icon-row', label: 'Q4\nScale', x: 74, y: 32, w: 15, h: 25 },
        { type: 'body', label: 'Initial market research and validation', x: 8, y: 62, w: 15, h: 15 },
        { type: 'body', label: 'Build MVP and run pilot tests', x: 30, y: 62, w: 15, h: 15 },
        { type: 'body', label: 'Public launch and marketing push', x: 52, y: 62, w: 15, h: 15 },
        { type: 'body', label: 'Expand to new markets', x: 74, y: 62, w: 15, h: 15 },
      ],
    } as SlidePreviewData,
    schemaHint: '{ "milestones": [{ "period": "Q1", "title": "...", "description": "..." }, ...] }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Key Milestones\n\nQ1 — Research: Initial market research and validation\nQ2 — Prototype: Build MVP and run pilot tests\nQ3 — Launch: Public launch and marketing push\nQ4 — Scale: Expand to new markets' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-comparison',
    name: 'Comparison / vs.',
    category: 'slide',
    slideKind: 'comparison',
    description: 'Side-by-side comparison of two options, strategies, or scenarios.',
    previewData: {
      title: 'Option A vs Option B',
      elements: [
        { type: 'heading', label: 'Option A vs Option B', x: 15, y: 5, w: 70, h: 8 },
        { type: 'divider', label: '', x: 50, y: 18, w: 0.5, h: 70 },
        { type: 'subheading', label: 'Option A', x: 10, y: 18, w: 35, h: 6 },
        { type: 'list', label: '✓ Lower cost\n✓ Faster deploy\n✗ Less scalable', x: 10, y: 28, w: 35, h: 45 },
        { type: 'subheading', label: 'Option B', x: 55, y: 18, w: 35, h: 6 },
        { type: 'list', label: '✓ More scalable\n✓ Better long-term\n✗ Higher upfront cost', x: 55, y: 28, w: 35, h: 45 },
        { type: 'accent-bar', label: '', x: 10, y: 80, w: 80, h: 1 },
        { type: 'body', label: 'Recommendation: Option B for long-term growth', x: 10, y: 84, w: 80, h: 5 },
      ],
    } as SlidePreviewData,
    schemaHint: '{ "title": "A vs B", "optionA": { "name": "...", "pros": [...], "cons": [...] }, "optionB": {...}, "recommendation": "..." }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: 'Option A vs Option B\n\nOption A:\n✓ Lower cost\n✓ Faster deployment\n✗ Less scalable\n\nOption B:\n✓ More scalable\n✓ Better long-term value\n✗ Higher upfront cost\n\nRecommendation: Option B for long-term growth' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-quote',
    name: 'Quote / Key Stat',
    category: 'slide',
    slideKind: 'quote',
    description: 'Highlight a powerful quote, testimonial, or key statistic.',
    previewData: {
      title: '"Innovation distinguishes between a leader and a follower."',
      subtitle: '— Steve Jobs',
      elements: [
        { type: 'accent-bar', label: '', x: 15, y: 30, w: 3, h: 30 },
        { type: 'heading', label: '"Innovation distinguishes\nbetween a leader\nand a follower."', x: 22, y: 28, w: 65, h: 25 },
        { type: 'body', label: '— Steve Jobs', x: 22, y: 58, w: 30, h: 5 },
      ],
      accentPosition: 'left',
    } as SlidePreviewData,
    schemaHint: '{ "quote": "...", "attribution": "— Author Name" }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: '"Innovation distinguishes between a leader and a follower."\n\n— Steve Jobs' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-big-number',
    name: 'Big Number / KPI',
    category: 'slide',
    slideKind: 'kpi',
    description: 'Feature a large stat or KPI with supporting context.',
    previewData: {
      title: '$45.2M',
      subtitle: 'Total Revenue — Up 23% YoY',
      elements: [
        { type: 'heading', label: '$45.2M', x: 20, y: 25, w: 60, h: 20 },
        { type: 'subheading', label: 'Total Revenue', x: 25, y: 50, w: 50, h: 6 },
        { type: 'accent-bar', label: '', x: 40, y: 60, w: 20, h: 1 },
        { type: 'body', label: 'Up 23% Year-over-Year · Exceeded target by $5.2M', x: 15, y: 66, w: 70, h: 5 },
      ],
      accentPosition: 'center',
    } as SlidePreviewData,
    schemaHint: '{ "value": "$45.2M", "label": "Total Revenue", "context": "Up 23% YoY" }',
    defaultStructure: 'blank',
    defaultComponents: [
      { type: 'text', data: { content: '$45.2M\n\nTotal Revenue\nUp 23% Year-over-Year · Exceeded target by $5.2M' }, config: { format: 'paragraph' } },
    ],
  },
  {
    id: 'tmpl-slide-blank',
    name: 'Blank Canvas',
    category: 'slide',
    slideKind: 'blank',
    description: 'Empty slide — build from scratch with any layout and components.',
    previewData: {
      title: '',
      elements: [],
    } as SlidePreviewData,
    schemaHint: 'No schema — add components manually',
    defaultStructure: 'blank',
    defaultComponents: [],
  },
]

export const allTemplates: SlideTemplate[] = [
  ...chartTemplates,
  ...tableTemplates,
  ...textTemplates,
  ...slideTemplates,
]

function buildMockSlides(sectionName: string): Slide[] {
  const chartRegions = createRegions('two-col')
  chartRegions[0].component = {
    id: crypto.randomUUID(),
    type: 'chart',
    data: mockChartData.revenue,
    config: {},
  }
  chartRegions[1].component = {
    id: crypto.randomUUID(),
    type: 'text',
    data: { content: 'Key highlights and analysis for this section.' },
    config: { format: 'paragraph' },
  } as SlideComponent

  const tableRegions = createRegions('two-col')
  tableRegions[0].component = {
    id: crypto.randomUUID(),
    type: 'table',
    data: mockTableData.competitors,
    config: {},
  }

  const slides: Slide[] = [
    {
      id: crypto.randomUUID(),
      title: `${sectionName} — Overview`,
      structure: 'two-col',
      regions: chartRegions,
      commentary:
        'This section provides a comprehensive overview of the key metrics and trends observed during the reporting period.',
      commentarySource: 'ai',
      regionCommentary: {},
      order: 0,
    },
    {
      id: crypto.randomUUID(),
      title: `${sectionName} — Details`,
      structure: 'two-col',
      regions: tableRegions,
      commentary:
        'Detailed breakdown of performance metrics across key dimensions.',
      commentarySource: 'ai',
      regionCommentary: {},
      order: 1,
    },
  ]
  return slides
}

export const mockSections: Section[] = [
  {
    id: crypto.randomUUID(),
    name: 'Executive Summary',
    description: 'High-level overview of key findings and recommendations',
    slides: buildMockSlides('Executive Summary'),
    order: 0,
    recommendedTemplateIds: ['tmpl-bar-basic', 'tmpl-table-basic'],
  },
  {
    id: crypto.randomUUID(),
    name: 'Market Overview',
    description: 'Current market landscape and competitive positioning',
    slides: buildMockSlides('Market Overview'),
    order: 1,
    recommendedTemplateIds: ['tmpl-line-trend', 'tmpl-table-comparison'],
  },
  {
    id: crypto.randomUUID(),
    name: 'Financial Analysis',
    description: 'Revenue, costs, profitability, and projections',
    slides: buildMockSlides('Financial Analysis'),
    order: 2,
    recommendedTemplateIds: ['tmpl-bar-stacked', 'tmpl-table-financial'],
  },
  {
    id: crypto.randomUUID(),
    name: 'Key Insights',
    description: 'Strategic recommendations based on data analysis',
    slides: buildMockSlides('Key Insights'),
    order: 3,
    recommendedTemplateIds: ['tmpl-text-insights', 'tmpl-text-callout'],
  },
]

export const mockPresentations: Presentation[] = [
  {
    id: crypto.randomUUID(),
    name: 'Q4 2025 Financial Review',
    intent: {
      type: 'financial',
      audience: 'Board of Directors',
      tone: 'formal',
      designPreferences: { fontStyle: 'corporate', colorScheme: 'dark' },
      referenceFile: null,
    },
    sections: mockSections,
    createdAt: '2026-03-15T10:30:00Z',
    updatedAt: '2026-03-18T14:22:00Z',
    status: 'complete',
  },
  {
    id: crypto.randomUUID(),
    name: 'Market Expansion Strategy',
    intent: {
      type: 'business',
      audience: 'Leadership Team',
      tone: 'storytelling',
      designPreferences: { fontStyle: 'modern', colorScheme: 'dark' },
      referenceFile: null,
    },
    sections: [],
    createdAt: '2026-03-12T09:15:00Z',
    updatedAt: '2026-03-12T09:15:00Z',
    status: 'draft',
  },
  {
    id: crypto.randomUUID(),
    name: 'Product Analytics Deep Dive',
    intent: {
      type: 'research',
      audience: 'Product Team',
      tone: 'analytical',
      designPreferences: { fontStyle: 'minimal', colorScheme: 'dark' },
      referenceFile: null,
    },
    sections: [],
    createdAt: '2026-03-08T16:45:00Z',
    updatedAt: '2026-03-10T11:30:00Z',
    status: 'draft',
  },
]
