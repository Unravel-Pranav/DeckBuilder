# Data Ingestion & Minimal Intervention — Gap Analysis + Design

> Companion to: `agentic_architecture_+_mcp_6eabd3c7.plan.md`
> Status: **Proposed addendum — no code changes**

---

## 1. Problem Statement

The agentic architecture plan designs a pipeline that accepts a **text intent** and produces a PPT. But it assumes data already exists in the database (reports, templates, sections). Real users arrive in one of four ways:

| User Has | Current Plan Handles? | Gap |
|---|---|---|
| CSV/Excel + a prompt | **No** | No file upload, no parsing, no column-to-chart mapping |
| Just chart type preferences | **Partially** (overrides) | No skeleton/data-contract output, no "fill in your data" workflow |
| An idea, no data at all | **Yes** | Generates structure + generic content |
| An existing DB report | **Yes** | Fetches from DB, generates PPT |

The first two rows — which represent the **highest-value, most common** scenarios — are unsupported. This document designs the missing data ingestion layer and redefines each user flow end-to-end.

---

## 2. Gaps in the Current Plan

### Gap 1: No File Upload Path

There is no endpoint to accept CSV/Excel files. `AgentGenerateRequest.data_source` is referenced but `DataSourceConfig` is never defined. The `data_agent` only calls `data_tool.fetch_report_data()` and `data_tool.fetch_template_sections()` — both read from the database.

**Impact:** Users with their own data cannot use the agent pipeline at all. They must manually create a report in the DB first, defeating the purpose of an agentic system.

### Gap 2: No Data Profiling

Even if a file were accepted, nothing in the plan analyzes what the data *contains*. The planner agent generates sections from the text intent alone — it has no awareness of:
- How many columns exist and what they represent
- Whether the data is time-series, categorical, hierarchical, or flat
- What value ranges and distributions look like
- Which columns are suitable as chart axes vs. values vs. groupers

**Impact:** The planner generates generic section structures ("Overview", "Analysis", "Summary") instead of data-aware structures ("Regional Revenue Comparison by Quarter", "Growth Trend Analysis").

### Gap 3: No Column-to-Chart Mapping

`viz_tool.recommend_chart_type()` takes a `DataShapeInput` — but this is an abstract schema, not actual column metadata. There is no mechanism to say "map the 'Quarter' column to the X-axis, 'Revenue' to the Y-axis, and group by 'Region'."

**Impact:** Even with the right chart type selected, the PPT engine receives no data bindings. The generated charts would have placeholder or empty data.

### Gap 4: No Data-Driven Insights

`insight_tool.generate_commentary()` sends context to the LLM, but without real data, the commentary is generic ("Revenue showed strong growth in Q1"). With actual numbers, it could say "North region led with ₹8.9Cr in Q4, a 15.3% YoY increase — the highest across all regions."

**Impact:** Insights don't reference real figures, reducing presentation credibility and requiring manual editing.

### Gap 5: No Skeleton / Data-Contract Mode

A user who says "I want 3 bar charts and a pie chart" gets back a structure (via `structure_only` mode), but that structure has no information about what data each chart expects. There is no "data contract" — a specification like "this bar chart needs columns: [label: str, value: float, group: str]."

**Impact:** Users cannot easily bridge from the AI-generated structure to actual chart population. They still need to manually figure out what data goes where.

### Gap 6: `DataSourceConfig` Undefined

The plan references `data_source: DataSourceConfig | None` in `AgentGenerateRequest` but never defines the schema. This is the single field that would connect user-provided data to the pipeline, and it's a blank.

---

## 3. Proposed Additions

### 3.1 New Tools

#### `ingest_tool.py` — Parse + Profile

Accepts a file reference or inline data, returns a structured profile.

**Functions:**

```
parse_file(file_path: str, file_type: "csv" | "xlsx") -> ToolResult[ParsedData]
    - Uses pandas to read the file
    - Returns: row_count, column_count, raw preview (first 10 rows), parse warnings

profile_data(parsed_data: ParsedData) -> ToolResult[DataProfile]
    - For each column, detects:
        - data_type: numeric | categorical | temporal | text | percentage | currency | boolean
        - role: axis | value | grouper | label | identifier (heuristic-based)
        - stats: min, max, mean, median, std_dev, null_count, distinct_count
        - sample_values: first 5 unique values
    - Generates suggested_groupings: plausible (axis, grouper, value) combinations
    - Detects data patterns: is_time_series, has_hierarchy, is_comparison, is_distribution
```

**Why a separate tool (not inside data_agent):** Parsing and profiling are reusable — MCP clients, future API endpoints, and data validation flows all need them. Keeping them as registered tools means they're auto-exposed everywhere.

#### `mapping_tool.py` — Column-to-Chart Binding

Takes a `DataProfile` + target chart type → produces exact column-to-visual mappings.

**Functions:**

```
map_columns_to_chart(
    profile: DataProfile,
    chart_type: str,
    section_intent: str       # what this section is about, for disambiguation
) -> ToolResult[ChartDataMapping]
    
    Output:
        x_axis: ColumnRef       # which column maps to X
        y_axis: list[ColumnRef] # which column(s) map to Y (multi-series support)
        grouper: ColumnRef | None
        labels: ColumnRef | None
        filters: list[FilterSpec] | None   # e.g., "only Q1 data for this slide"
        data_slice: list[dict]              # the actual extracted data rows for this chart
        warnings: list[str]                 # e.g., "50+ categories truncated to top 10"

generate_data_contract(
    chart_type: str,
    section_structure: SectionDef
) -> ToolResult[DataContract]

    Output:
        chart_type: str
        required_columns: list[ColumnSpec]  # name, expected_type, role
        optional_columns: list[ColumnSpec]
        constraints: list[str]              # e.g., "max 8 categories for pie chart"
        example_data: list[dict]            # sample rows showing expected format
```

### 3.2 New Schemas

#### `DataSourceConfig` (fills the undefined gap)

```
class DataSourceConfig:
    source_type: "csv_upload" | "xlsx_upload" | "report_id" | "template_id" | "inline_json"
    
    # For file uploads (csv_upload, xlsx_upload)
    file_id: str | None              # returned by upload endpoint
    
    # For existing DB data
    report_id: int | None
    template_id: int | None
    
    # For inline data (small datasets passed directly)
    inline_data: list[dict] | None   # row-oriented: [{"Quarter": "Q1", "Revenue": 450000}, ...]
    
    # Optional: user hints about their data
    data_hints: DataHints | None
```

#### `DataHints` (user provides optional context about their data)

```
class DataHints:
    time_column: str | None          # "I know 'Date' is my time axis"
    value_columns: list[str] | None  # "Revenue and Profit are my metrics"  
    group_column: str | None         # "Region is how I want to split"
    currency: str | None             # "INR" — for formatting
    date_format: str | None          # "%Y-%m-%d" — for parsing ambiguous dates
```

When `DataHints` are provided, the profiler uses them instead of guessing. When absent, the profiler infers everything automatically.

#### `DataProfile` (output of profiling)

```
class DataProfile:
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    suggested_groupings: list[DataGrouping]
    data_patterns: DataPatterns
    preview: list[dict]              # first 5 rows for LLM context

class ColumnProfile:
    name: str
    data_type: "numeric" | "categorical" | "temporal" | "text" | "percentage" | "currency" | "boolean"
    role: "axis" | "value" | "grouper" | "label" | "identifier" | "unknown"
    stats: ColumnStats | None        # only for numeric/temporal
    distinct_count: int
    null_ratio: float
    sample_values: list[str]         # first 5 unique, stringified

class DataGrouping:
    axis: str                        # column name for X-axis
    grouper: str | None              # column name for grouping/series
    values: list[str]                # column name(s) for Y-axis
    recommended_chart: str           # best chart type for this grouping
    confidence: float                # 0.0 - 1.0

class DataPatterns:
    is_time_series: bool
    has_hierarchy: bool              # e.g., Region > City > Store
    is_comparison: bool              # e.g., Actual vs Budget
    is_distribution: bool            # e.g., age ranges, score buckets
    dominant_pattern: str            # the primary pattern detected
```

#### `DataContract` (skeleton mode output)

```
class DataContract:
    slide_index: int
    chart_type: str
    required_columns: list[ColumnSpec]
    optional_columns: list[ColumnSpec]
    constraints: list[str]
    example_data: list[dict]         # sample rows the user can replace

class ColumnSpec:
    name: str
    expected_type: str               # "numeric", "categorical", etc.
    role: str                        # "x_axis", "y_axis", "grouper", "label"
    description: str                 # human-readable: "The category labels for each bar"
```

### 3.3 New Mode: `skeleton`

Added to the existing mode literal:

```
mode: "full" | "structure_only" | "ppt_only" | "skeleton"
```

`skeleton` mode produces:
- A PPT file with chart layouts, titles, and placeholder/sample data
- A JSON manifest with `DataContract` per slide — tells the user exactly what data each chart needs
- No real data required as input — the system generates illustrative sample data

### 3.4 New Endpoint: File Upload

```
POST /api/v2/agent/upload
    Content-Type: multipart/form-data
    Body: file (CSV or XLSX)
    
    Response: { file_id: str, filename: str, row_count: int, columns: list[str] }
```

The file is stored temporarily (configurable TTL, default 1 hour). The `file_id` is passed in `AgentGenerateRequest.data_source.file_id`.

### 3.5 `AgentState` Additions

```
class AgentState(TypedDict, total=False):
    # ... existing fields from the plan ...
    
    # NEW: Data ingestion state
    raw_data_ref: str | None              # file_id or "inline"
    data_profile: DataProfile | None      # output of ingest/profile step
    data_mappings: list[ChartDataMapping] # output of mapping step (per section)
    data_contracts: list[DataContract]    # output in skeleton mode
```

### 3.6 Updated Pipeline Graph

```
     +----------+
     | ingest   |  (NEW — parse + profile; skipped if no file/inline data)
     +----+-----+
          |
     +----v-----+
     | planner  |  (receives DataProfile for data-aware section planning)
     +----+-----+
          |
     +----v-----+
     | data     |  (column-to-chart mapping from profile; OR DB fetch if report_id)
     +----+-----+
          |
    +-----+------+
    |            |
 +--v---+  +----v----+
 | viz  |  | insight |  (viz uses profile stats; insight uses real numbers)
 +--+---+  +----+----+
    |            |
    +-----+------+
          |
     +----v-----+
     |   ppt    |  (injects mapped data into chart JSON payloads)
     +----+-----+
          |
      [DONE / RETRY]
```

**Node conditions:**

| Node | Runs when | Skipped when |
|---|---|---|
| `ingest` | `data_source.source_type` is `csv_upload`, `xlsx_upload`, or `inline_json` | `report_id`, `template_id`, or no data source |
| `planner` | `mode` is `full`, `structure_only`, or `skeleton` | `mode` is `ppt_only` |
| `data` | `mode` is `full`, `ppt_only`, or `skeleton` | `mode` is `structure_only` |
| `viz` | `mode` is `full` or `skeleton`, and `overrides.skip_viz` is false | `overrides.skip_viz` or `mode` is `structure_only` |
| `insight` | `mode` is `full`, and `overrides.skip_insights` is false | `skeleton`, `structure_only`, or `overrides.skip_insights` |
| `ppt` | `mode` is `full`, `ppt_only`, or `skeleton`, and `dry_run` is false | `structure_only` or `dry_run` is true |

---

## 4. User Flows — End to End

### Flow A: CSV + Prompt (Fully Autonomous)

**User has:** A CSV file and a one-line description of what they want.

**Goal:** Complete, data-accurate PPT with zero further intervention.

**Example:**
```
Upload: quarterly_revenue.csv (columns: Quarter, Region, Revenue, Growth_Pct, Headcount)
Prompt: "Q1 2025 financial review for the board, formal tone"
Mode: full
```

**Step-by-step pipeline:**

```
Step 1 — UPLOAD
    User calls: POST /api/v2/agent/upload  (multipart, attaches CSV)
    System returns: { file_id: "f-abc123", row_count: 48, columns: ["Quarter","Region","Revenue","Growth_Pct","Headcount"] }

Step 2 — GENERATE REQUEST  
    User calls: POST /api/v2/agent/generate-ppt
    Body: {
        intent: "Q1 2025 financial review for the board",
        tone: "formal",
        audience: "board of directors",
        mode: "full",
        data_source: { source_type: "csv_upload", file_id: "f-abc123" }
    }
    System returns: { job_id: "j-xyz789", status: "pending" }

Step 3 — INGEST (automatic, background)
    Reads CSV from temp storage via file_id
    Parses with pandas → 48 rows, 5 columns
    Profiles each column:
        Quarter     → temporal,  role: axis,    distinct: [Q1-2024, Q2-2024, ..., Q4-2025]
        Region      → categorical, role: grouper, distinct: [North, South, East, West]
        Revenue     → currency,  role: value,   stats: {min: 1.2Cr, max: 8.9Cr, mean: 4.5Cr}
        Growth_Pct  → percentage, role: value,   stats: {min: -2.1%, max: 15.3%}
        Headcount   → numeric,   role: value,   stats: {min: 45, max: 312}
    Detects patterns: is_time_series=true, is_comparison=true (regions)
    Suggests groupings:
        1. Quarter × Region → Revenue  (grouped bar, confidence: 0.92)
        2. Quarter → Revenue, Growth_Pct  (combo chart, confidence: 0.87)
        3. Region → avg(Revenue)  (pie chart, confidence: 0.78)
        4. Quarter → Headcount by Region  (stacked area, confidence: 0.71)
    
    State updated: data_profile = DataProfile(...)

Step 4 — PLANNER (automatic, background)
    LLM receives: intent + DataProfile (column names, types, stats, suggested groupings)
    LLM generates a DATA-AWARE structure:
        Section 1: "Revenue Overview" — grouped bar — Quarter × Region → Revenue
        Section 2: "Growth Trajectory" — combo chart — Quarter → Revenue + Growth_Pct
        Section 3: "Regional Contribution" — pie chart — Region → sum(Revenue)
        Section 4: "Team Scaling" — stacked area — Quarter → Headcount by Region
        Section 5: "Key Takeaways" — commentary slide — summary insights
    
    Note: Without the DataProfile, the planner would generate generic sections like 
    "Financial Overview", "Analysis", "Conclusion" with no chart specificity.
    
    State updated: structure = PresentationStructure(sections=[...])

Step 5 — DATA AGENT (automatic, background)
    For each section, calls mapping_tool:
        Section 1: map(profile, "grouped_bar", "Revenue Overview")
            → x_axis: Quarter, grouper: Region, y_axis: Revenue
            → data_slice: [{Q1, North, 3.2Cr}, {Q1, South, 2.1Cr}, ...] (48 rows)
        Section 2: map(profile, "combo", "Growth Trajectory")
            → x_axis: Quarter, y_axis: [Revenue, Growth_Pct], dual_axis: true
            → data_slice: [{Q1, 12.5Cr total, 8.2%}, ...] (aggregated by quarter)
        ... and so on for each section
    
    State updated: sections_data = [...], data_mappings = [...]

Step 6 — VIZ AGENT (automatic, parallel)
    Validates chart selections against DataProfile stats:
        - Section 3 pie chart: 4 distinct regions → fine (≤8 categories)
        - If there were 25 regions → would override to horizontal bar
    Adjusts formatting: currency labels for Revenue, percentage labels for Growth_Pct
    
    State updated: viz_mappings = [...]

Step 7 — INSIGHT AGENT (automatic, parallel with viz)
    LLM receives: section structure + ACTUAL data slices
    Generates data-driven commentary:
        Section 1: "North region dominated with ₹8.9Cr in Q4-2025, while South 
                    showed the strongest quarter-over-quarter recovery at 12.1%."
        Section 2: "Revenue growth decelerated from 15.3% in Q1 to 7.8% in Q4, 
                    while absolute revenue continued climbing — suggesting market maturation."
        Section 5: "Key takeaway: ₹54Cr total annual revenue across regions, 
                    with North contributing 38% of the total. Headcount grew 22% 
                    but revenue grew only 11%, flagging efficiency considerations."
    
    Note: Without real data, these would be "Revenue showed positive trends in Q1" — useless.
    
    State updated: commentaries = {...}

Step 8 — PPT AGENT (automatic, background)
    Assembles final payload:
        - Each section → chart type + mapped data + commentary + formatting
        - Converts to the JSON shape that ppt_engine/pptx_builder.py expects
    Calls ppt_tool → PptService.generate_custom_ppt → generate_presentation
    
    State updated: ppt_result = {file_id: "ppt-001", path: "...", size: "2.4MB"}

Step 9 — JOB COMPLETE
    AgentJobModel updated: status=completed, ppt_file_id="ppt-001"

Step 10 — USER DOWNLOADS
    GET /api/v2/agent/jobs/j-xyz789 → { status: "completed", download_url: "/api/v2/agent/jobs/j-xyz789/download" }
    GET /api/v2/agent/jobs/j-xyz789/download → FileResponse (quarterly_review.pptx)
```

**Human intervention: ZERO.** One file upload, one sentence, one download.

---

### Flow B: Chart Types Only (Skeleton Mode)

**User has:** A rough idea of what chart types they want, no data yet.

**Goal:** Get a skeleton PPT with the right chart layouts and a data contract explaining what data each chart needs. User fills in data later via Build Slide.

**Example:**
```
Prompt: "Financial quarterly review"
Mode: skeleton
Overrides: { chart_layout: ["grouped_bar", "line", "pie", "table"] }
```

**Step-by-step pipeline:**

```
Step 1 — GENERATE REQUEST
    POST /api/v2/agent/generate-ppt
    Body: {
        intent: "Financial quarterly review",
        presentation_type: "financial",
        mode: "skeleton",
        overrides: {
            chart_layout: ["grouped_bar", "line", "pie", "table"]
        }
    }
    Returns: { job_id: "j-skel-001", status: "pending" }

Step 2 — INGEST: SKIPPED (no data source provided)

Step 3 — PLANNER
    LLM receives: intent + requested chart layout (4 charts)
    Generates sections matched to chart types:
        Section 1: "Revenue by Category" — grouped_bar
        Section 2: "Quarterly Trend" — line
        Section 3: "Market Share Distribution" — pie
        Section 4: "Detailed Metrics" — table
    
    State updated: structure = PresentationStructure(sections=[...])

Step 4 — DATA AGENT (skeleton path)
    No real data to fetch or map.
    Instead, calls mapping_tool.generate_data_contract() for each section:
    
    Section 1 — grouped_bar:
        DataContract {
            chart_type: "grouped_bar",
            required_columns: [
                { name: "category", type: "categorical", role: "x_axis", 
                  description: "The categories along the horizontal axis (e.g., Q1, Q2, Q3, Q4)" },
                { name: "value", type: "numeric", role: "y_axis",
                  description: "The numeric values for each bar (e.g., revenue in lakhs)" },
                { name: "group", type: "categorical", role: "grouper",
                  description: "The series grouping (e.g., Product Line A, Product Line B)" }
            ],
            constraints: ["Max 8 groups recommended", "Max 12 categories on X-axis"],
            example_data: [
                {"category": "Q1", "group": "Product A", "value": 450000},
                {"category": "Q1", "group": "Product B", "value": 320000},
                {"category": "Q2", "group": "Product A", "value": 510000},
                {"category": "Q2", "group": "Product B", "value": 380000}
            ]
        }
    
    Section 2 — line:
        DataContract {
            required_columns: [
                { name: "time_point", type: "temporal", role: "x_axis" },
                { name: "metric", type: "numeric", role: "y_axis" }
            ],
            optional_columns: [
                { name: "series", type: "categorical", role: "grouper",
                  description: "Optional: split into multiple lines" }
            ],
            constraints: ["Time points should be chronologically ordered"],
            example_data: [
                {"time_point": "Jan 2025", "metric": 1200000},
                {"time_point": "Feb 2025", "metric": 1350000}
            ]
        }
    
    ... similar for pie and table
    
    State updated: data_contracts = [DataContract(...), ...]

Step 5 — VIZ AGENT
    Validates chart types against constraints (all valid since user chose them).
    Assigns layout positioning, sizing, color palettes.
    
    State updated: viz_mappings = [...]

Step 6 — INSIGHT AGENT: SKIPPED (skeleton mode — no real data to comment on)

Step 7 — PPT AGENT (skeleton path)
    Builds PPT with:
        - Correct chart layouts and positioning
        - Placeholder/sample data from DataContract.example_data (charts render visually)
        - Titles and section headings from planner
        - Subtle "Sample Data" watermark or note on each chart slide
    Also outputs: skeleton_manifest.json with all DataContracts
    
    State updated: ppt_result = {file_id: "skel-001", manifest: [...]}

Step 8 — USER RECEIVES
    Response includes:
    {
        status: "completed",
        mode: "skeleton",
        download_url: "...",
        data_contracts: [
            { slide: 1, chart: "grouped_bar", required: ["category", "value", "group"], example: [...] },
            { slide: 2, chart: "line", required: ["time_point", "metric"], example: [...] },
            ...
        ]
    }
```

**What the user does next:**
1. Downloads the skeleton PPT — sees the visual layout with sample charts
2. Reads the `data_contracts` — knows exactly what columns each chart needs
3. Prepares their CSV matching the contract
4. Uses **Build Slide** (existing V1 flow) or re-submits via **Flow A** with `mode: "ppt_only"` and the CSV

**Human intervention: LOW.** User decides chart types. System handles layout, sizing, data contracts, sample rendering. User only needs to supply actual data in the specified format.

---

### Flow C: Prompt Only, No Data (Existing Plan — Works As-Is)

**User has:** Just an idea.

**Goal:** Get a structured presentation with AI-generated content and illustrative visuals.

**Example:**
```
Prompt: "Annual company performance review, executive audience"
Mode: full
No data_source, no overrides
```

**Step-by-step pipeline:**

```
Step 1 — GENERATE REQUEST
    POST /api/v2/agent/generate-ppt
    Body: {
        intent: "Annual company performance review",
        audience: "executives",
        tone: "formal",
        mode: "full"
    }

Step 2 — INGEST: SKIPPED (no data source)

Step 3 — PLANNER
    LLM generates structure purely from intent:
        Section 1: "Company Overview" — commentary slide
        Section 2: "Financial Highlights" — bar chart (illustrative)
        Section 3: "Operational Metrics" — table
        Section 4: "Strategic Initiatives" — commentary
        Section 5: "Outlook & Next Steps" — commentary
    
    Note: Without DataProfile, planner falls back to generic but reasonable sections.

Step 4 — DATA AGENT
    No file data, no report_id → checks for templates matching "annual performance"
    If template found → fetches template sections/elements from DB
    If nothing found → returns empty sections, flags "no_data" in state

Step 5 — VIZ AGENT
    With no real data profile → uses defaults:
        Bar chart → standard vertical bar with placeholder categories
        Table → generic metric table layout
    
Step 6 — INSIGHT AGENT
    LLM generates generic but contextually appropriate commentary:
        "This section presents the key financial highlights for the year..."
    Falls back to _fallback_commentary if LLM unavailable.

Step 7 — PPT AGENT
    Builds PPT with:
        - Section layouts and titles from planner
        - Illustrative/placeholder chart data
        - AI-generated commentary
    If no data at all → includes a "No data provided" indicator slide

Step 8 — USER RECEIVES
    Complete PPT with structure and placeholders. User replaces with real data.
```

**Human intervention: MEDIUM.** Good structure and layout, but data is placeholder. User must replace chart data manually.

---

### Flow D: Existing DB Report (Existing Plan — Works As-Is)

**User has:** A report already created in the system (via V1 API).

**Goal:** Generate a PPT from that report's data using the agent pipeline for smarter chart selection and insights.

**Example:**
```
Prompt: "Generate a board-ready version of this report"
Mode: full
data_source: { source_type: "report_id", report_id: 42 }
```

**Step-by-step pipeline:**

```
Step 1 — GENERATE REQUEST
    POST /api/v2/agent/generate-ppt
    Body: {
        intent: "Board-ready presentation from this report",
        mode: "full",
        data_source: { source_type: "report_id", report_id: 42 }
    }

Step 2 — INGEST: SKIPPED (report_id, not a file upload)

Step 3 — PLANNER
    LLM receives: intent + report metadata (title, section count, element types from DB)
    Generates structure tailored to the report's content.

Step 4 — DATA AGENT
    Calls data_tool.fetch_report_data(session, report_id=42)
    Returns: report with sections, elements, charts, tables — all from DB
    Maps existing data to the planned sections.

Step 5-8 — Same as full pipeline
    Viz selects chart types based on the element types already in the report.
    Insight generates commentary from the report's actual data.
    PPT builds the final file.
```

**Human intervention: ZERO** (assuming the report data is already good).

---

### Flow E: CSV + Skeleton Refinement (Two-Phase Workflow)

**User has:** A rough idea first, then data later. Wants to preview before committing.

**Goal:** Get structure approval first, then feed data for final generation.

**Phase 1 — Get skeleton:**
```
POST /api/v2/agent/generate-ppt
Body: {
    intent: "Quarterly sales analysis",
    mode: "skeleton",
    overrides: { chart_layout: ["bar", "line", "pie"] }
}
→ Returns: skeleton PPT + data_contracts
```

**Phase 2 — Upload data and generate final:**
```
POST /api/v2/agent/upload → file_id

POST /api/v2/agent/generate-ppt
Body: {
    intent: "Quarterly sales analysis",
    mode: "ppt_only",
    data_source: { source_type: "csv_upload", file_id: "..." },
    overrides: { 
        custom_sections: [sections from Phase 1 skeleton]
    }
}
→ Returns: final PPT with real data charts and AI insights
```

**Human intervention: LOW.** User reviews structure in Phase 1, provides data in Phase 2. No manual chart configuration.

---

## 5. Chart Type Selection Logic (Data-Driven)

When a `DataProfile` is available, `viz_tool` should use these rules instead of generic defaults:

| Data Pattern | Detected When | Recommended Chart | Confidence |
|---|---|---|---|
| Time series + 1 metric | 1 temporal axis + 1 numeric value | Line chart | 0.95 |
| Time series + 2+ metrics (same scale) | 1 temporal + multiple numeric, similar ranges | Multi-line chart | 0.90 |
| Time series + 2 metrics (different scales) | 1 temporal + 2 numeric, ranges differ >10x | Combo (bar + line, dual axis) | 0.88 |
| Categorical + 1 metric | 1 categorical (≤8 distinct) + 1 numeric | Bar chart | 0.90 |
| Categorical + 1 metric (≤5 categories) | Same but very few categories | Pie chart | 0.82 |
| Categorical + multiple metrics | 1 categorical + 2+ numeric | Grouped bar | 0.87 |
| Categorical × Categorical + 1 metric | 2 categorical + 1 numeric | Stacked bar or heatmap | 0.80 |
| Many categories (>12) | 1 categorical (>12 distinct) + 1 numeric | Horizontal bar (top N) | 0.85 |
| High-cardinality detail | 5+ columns, many rows | Table | 0.90 |
| Two numerics (no time) | 2 numeric columns, no temporal | Scatter plot | 0.75 |
| Single metric, no grouping | 1 numeric, no categories | KPI card / big number | 0.88 |

These are rule-based (no LLM needed). The profiler detects the pattern, and the rules map to chart type. The LLM in the planner can override if the intent suggests otherwise (e.g., user says "show me a pie chart" even if data has 20 categories — LLM respects intent but adds a warning).

---

## 6. Impact on Minimal Human Intervention

| Scenario | Without Data Ingestion | With Data Ingestion | Reduction |
|---|---|---|---|
| User has CSV + prompt | Not possible — must manually create DB report first, configure charts, write insights | Upload → one sentence → done | Manual steps: **~15 → 0** |
| User wants specific charts | Gets structure only, must figure out data format per chart | Gets skeleton + data contracts, just supplies matching CSV | Manual steps: **~10 → 2** |
| User iterates on structure | `structure_only` → manually reconfigure → try again | `skeleton` → review → upload data → `ppt_only` | Manual steps: **~8 → 3** |
| Insights quality | Generic "revenue showed growth" | "North led with ₹8.9Cr, up 15.3% YoY" | Manual editing: **~20 min → 0** |

---

## 7. New Dependencies

No additional packages required beyond what the plan already specifies:
- `pandas` — already a dependency, handles CSV/Excel parsing
- `numpy` — already a dependency, used for stats in profiling
- `openpyxl` — already a dependency, handles `.xlsx` reading
- `langgraph` — already planned
- `mcp` — already planned

The file upload endpoint uses FastAPI's built-in `UploadFile` — no extra dependency.

---

## 8. Summary of Changes to the Original Plan

| Original Plan Component | What Changes |
|---|---|
| `app/tools/` | Add `ingest_tool.py` and `mapping_tool.py` (2 new files) |
| `app/schemas/agent_schema.py` | Define `DataSourceConfig`, `DataHints`, add `"skeleton"` to mode |
| `app/schemas/tool_schema.py` | Add `DataProfile`, `ColumnProfile`, `DataGrouping`, `DataPatterns`, `ChartDataMapping`, `DataContract`, `ColumnSpec` |
| `app/agents/state.py` | Add `data_profile`, `data_mappings`, `data_contracts` to `AgentState` |
| `app/agents/orchestrator.py` | Add `ingest` node, wire conditional edge (runs only if file/inline data provided) |
| `app/agents/planner_agent.py` | Include `DataProfile` in LLM prompt context when available |
| `app/agents/data_agent.py` | Add column-to-chart mapping path alongside existing DB fetch path |
| `app/agents/insight_agent.py` | When real data present, include actual numbers in LLM prompt |
| `app/agents/ppt_agent.py` | Skeleton path: generate with sample data + output data contracts |
| `app/api/v2/agent_controller.py` | Add `POST /upload` endpoint, add `data_contracts` to response |
| `app/core/config.py` | Add `upload_dir`, `upload_ttl_seconds`, `max_upload_size_mb` |
| MCP tools | `ingest_tool` and `mapping_tool` auto-exposed via `TOOL_REGISTRY` |

Everything else from the original plan remains unchanged.
