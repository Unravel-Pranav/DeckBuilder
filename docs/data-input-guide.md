# Data Input Guide — Charts, Graphs & Tables

How to populate data for each visual component in the Slide Builder.

---

## How It Works

1. Select a slide from the left panel
2. Click on a **region** in the canvas that has a chart, table, or text component
3. The **right sidebar** opens automatically with the appropriate tab (Data or Text)
4. Paste JSON or CSV data, or use a Quick Template
5. Click **Apply Data**

There are two input methods: **JSON** (primary) and **CSV** (converted to JSON before applying).

---

## JSON Schemas by Component Type

Every chart JSON optionally accepts a `"type"` field to force a specific chart type.
Valid types: `bar`, `line`, `pie`, `doughnut`, `area`, `scatter`.
If omitted, the system auto-detects the best chart type from the data shape.

### Bar Chart

```json
{
  "x_axis": ["Q1", "Q2", "Q3", "Q4"],
  "y_axis": [120, 150, 180, 210],
  "label": "Revenue ($M)"
}
```

| Field    | Type       | Required | Description                  |
|----------|------------|----------|------------------------------|
| `x_axis` | `string[]` | Yes      | Category labels              |
| `y_axis` | `number[]` | Yes      | Values (must match x_axis length) |
| `label`  | `string`   | No       | Series name (defaults to "Data") |

Auto-detected when: ≤8 data points, labels are not numeric, values don't sum to ~100.

### Multi-Series Bar Chart

```json
{
  "type": "bar",
  "x_axis": ["Q1", "Q2", "Q3", "Q4"],
  "series": [
    { "label": "Revenue", "data": [120, 150, 180, 210] },
    { "label": "Expenses", "data": [80, 95, 110, 130] }
  ]
}
```

Renders grouped bars side-by-side per category.

### Line Chart (Single Series)

```json
{
  "type": "line",
  "x_axis": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
  "y_axis": [5000, 6200, 7500, 8100, 8900, 9100],
  "label": "Active Users"
}
```

Auto-detected when: >8 data points. Use `"type": "line"` to force with fewer points.

### Multi-Line Chart

```json
{
  "type": "line",
  "x_axis": ["Q1", "Q2", "Q3", "Q4"],
  "series": [
    { "label": "Revenue", "data": [120, 150, 180, 210] },
    { "label": "Profit", "data": [40, 55, 70, 90] }
  ]
}
```

| Field    | Type       | Required | Description                        |
|----------|------------|----------|------------------------------------|
| `x_axis` | `string[]` | Yes      | Shared x-axis labels               |
| `series` | `array`    | Yes      | Array of `{ label, data }` objects |

Each `series` entry:

| Field  | Type       | Required | Description                          |
|--------|------------|----------|--------------------------------------|
| `label`| `string`   | No       | Series name (defaults to "Series")   |
| `data` | `number[]` | Yes      | Values (should match x_axis length)  |

Auto-detected as `line` when: series has 2+ entries, or 6+ data points.

### Pie Chart

```json
{
  "labels": ["Company A", "Company B", "Others"],
  "values": [45, 30, 25]
}
```

| Field    | Type       | Required | Description        |
|----------|------------|----------|--------------------|
| `labels` | `string[]` | Yes      | Slice names        |
| `values` | `number[]` | Yes      | Slice values       |

Auto-detected when: 2–6 non-negative values that sum to approximately 100.

### Doughnut Chart

```json
{
  "type": "doughnut",
  "labels": ["Product", "Services", "Licensing", "Other"],
  "values": [40, 30, 20, 10]
}
```

Same schema as pie. The `"type": "doughnut"` field is required — without it, the system infers `pie`.

### Area Chart

```json
{
  "type": "area",
  "x_axis": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
  "y_axis": [200, 350, 480, 520, 680, 790],
  "label": "Cumulative Users"
}
```

Same schema as line chart. Use `"type": "area"` to get the filled area rendering.
Also supports multi-series via the `series` array (each series gets its own fill).

### Scatter Chart

```json
{
  "type": "scatter",
  "x_axis": ["10", "20", "30", "40", "50"],
  "y_axis": [15, 28, 35, 42, 55],
  "label": "Correlation"
}
```

Auto-detected when: labels are numeric (e.g. `"10"`, `"20"`).
Use `"type": "scatter"` to force with non-numeric labels.

### Table

```json
{
  "headers": ["Metric", "Current", "% Change"],
  "rows": [
    ["Revenue", "$45.2M", "+12%"],
    ["EBITDA", "$18.1M", "+8%"],
    ["Net Margin", "40%", "+2pp"]
  ]
}
```

| Field     | Type         | Required | Description                        |
|-----------|--------------|----------|------------------------------------|
| `headers` | `string[]`   | Yes      | Column header names                |
| `rows`    | `string[][]` | Yes      | Each row is an array of cell values |

Auto-detected when input has both `headers` and `rows` arrays.

---

## Alternative Field Names

The system accepts aliases for convenience:

| Primary field | Alias      | Used by          |
|---------------|------------|------------------|
| `x_axis`      | `labels`   | All chart types  |
| `y_axis`      | `values`   | Single-series charts |

You can use either. `labels`/`values` is shorter for pie/doughnut. `x_axis`/`y_axis` is clearer for bar/line.

---

## CSV Input

Paste CSV or tab-separated data in the **CSV Upload** tab.

Before clicking **Transform**, pick a target type using the **Convert To** selector:
`Auto | Bar | Line | Area | Pie | Doughnut | Scatter | Table`

The first column is always treated as **labels/categories**. All other columns must be **numeric** for chart types (the system validates this and shows an error if not).

---

### Auto (default)

The system decides based on data shape:

| CSV shape | Result |
|-----------|--------|
| 2 numeric columns | Single-series bar chart |
| 3+ numeric columns | Multi-line chart |
| Non-numeric value columns | Table |

---

### Bar Chart

**Single series** (2 columns):

```
Quarter,Revenue
Q1,120
Q2,150
Q3,180
Q4,210
```

**Grouped bars** (3+ columns — each column becomes a bar group):

```
Quarter,Revenue,Expenses
Q1,120,80
Q2,150,95
Q3,180,110
Q4,210,130
```

---

### Line Chart

**Single line** (2 columns):

```
Month,Users
Jan,5000
Feb,6200
Mar,7500
Apr,8100
```

**Multi-line** (3+ columns — each column becomes a separate line):

```
Month,Revenue,Profit,Expenses
Jan,100,40,60
Feb,150,55,95
Mar,200,70,130
Apr,250,90,160
```

---

### Area Chart

Same CSV format as Line. Select **Area** to get the filled rendering.

**Single area** (2 columns):

```
Month,Cumulative Users
Jan,200
Feb,550
Mar,1030
Apr,1550
```

**Multi-area** (3+ columns):

```
Month,Signups,Churns
Jan,200,20
Feb,350,45
Mar,480,60
Apr,520,55
```

---

### Pie Chart

Use a 2-column CSV — first column is slice labels, second is values:

```
Segment,Share
Company A,45
Company B,30
Others,25
```

Converts to: `{ "type": "pie", "labels": [...], "values": [...] }`

---

### Doughnut Chart

Same format as Pie. Select **Doughnut** instead:

```
Category,Percentage
Product,40
Services,30
Licensing,20
Other,10
```

Converts to: `{ "type": "doughnut", "labels": [...], "values": [...] }`

---

### Scatter Chart

2-column CSV where both columns represent numeric axes:

```
Temperature,Sales
10,15
20,28
30,35
40,42
50,55
```

Converts to: `{ "type": "scatter", "x_axis": [...], "y_axis": [...] }`

---

### Table

Select **Table** to force any CSV into a table, even if the values are numeric:

```
Metric,Current,Change
Revenue,$45.2M,+12%
EBITDA,$18.1M,+8%
Net Margin,40%,+2pp
```

Converts to: `{ "headers": [...], "rows": [[...], ...] }`

Non-numeric CSVs in **Auto** mode also produce a table automatically.

---

### CSV Rules Summary

| Target type | Columns needed | Value columns | Output format |
|-------------|----------------|---------------|---------------|
| **Auto**    | 2+             | Numeric → chart, else → table | Varies |
| **Bar**     | 2 (single) or 3+ (grouped) | Numeric required | `x_axis`/`y_axis` or `x_axis`/`series` |
| **Line**    | 2 (single) or 3+ (multi) | Numeric required | `x_axis`/`y_axis` or `x_axis`/`series` |
| **Area**    | 2 (single) or 3+ (multi) | Numeric required | `x_axis`/`y_axis` or `x_axis`/`series` |
| **Pie**     | 2              | Numeric required | `labels`/`values` |
| **Doughnut**| 2              | Numeric required | `labels`/`values` |
| **Scatter** | 2              | Numeric required | `x_axis`/`y_axis` |
| **Table**   | 2+             | Any            | `headers`/`rows` |

---

## Quick Templates

The Data panel includes pre-built quick templates you can click or drag onto the canvas:

| Template                    | Type      | Format                  |
|-----------------------------|-----------|-------------------------|
| Bar — Quarterly Revenue     | `bar`     | `x_axis` / `y_axis`    |
| Line — Monthly Users        | `line`    | `x_axis` / `y_axis`    |
| Multi-Line — Rev vs Profit  | `line`    | `x_axis` / `series`    |
| Pie — Market Share          | `pie`     | `labels` / `values`    |
| Doughnut — Segments         | `doughnut`| `labels` / `values`    |
| Area — Growth Trend         | `area`    | `x_axis` / `y_axis`    |
| Table — Financial Summary   | `table`   | `headers` / `rows`     |

Click a template to load its JSON into the editor. Drag it directly onto a canvas region to apply instantly.

---

## Validation

The system validates your JSON in real-time as you type:

- **Green badge** — Valid, ready to apply
- **Red badge** — Errors found (missing fields, wrong types)
- **Amber warnings** — Non-critical issues (length mismatches)

### Common Validation Errors

| Error | Fix |
|-------|-----|
| `Invalid JSON syntax` | Check for missing commas, brackets, or quotes |
| `Missing required field: "x_axis"` | Add `x_axis` or `labels` array |
| `Missing required field: "y_axis"` | Add `y_axis`, `values`, or `series` array |
| `All values in "y_axis" must be numbers` | Remove quotes from numeric values |
| `series[N] is missing a "data" array` | Each series entry needs `{ "label": "...", "data": [...] }` |
| `Missing required field: "headers"` | Table data needs a `headers` string array |
| `Each row must be an array` | Each entry in `rows` must be `["cell1", "cell2"]` |

---

## Auto-Detection Summary

When `"type"` is omitted, the system infers the chart type:

| Data shape | Inferred type |
|------------|---------------|
| `headers` + `rows` | Table |
| `labels`/`values` summing to ~100, 2–6 items | Pie |
| Numeric labels (e.g. `"10"`, `"20"`) | Scatter |
| `series` with 2+ entries | Line |
| `series` with 1 entry, ≤6 points | Bar |
| Single `y_axis` with >8 points | Line |
| Single `y_axis` with ≤8 points | Bar |

To override auto-detection, add `"type": "line"` (or any valid type) to your JSON.
