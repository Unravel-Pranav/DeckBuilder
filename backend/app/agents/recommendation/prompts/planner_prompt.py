"""LLM prompts for the section planner node."""
from __future__ import annotations

import json
from typing import Any


PLANNER_SYSTEM = """\
You are a presentation architect. Given user intent, a data profile, and available slide \
templates, produce a JSON array of sections. Each section must:
1. Pick one template_id from the available templates list (use null if no template fits)
2. Choose the best slide_structure for the number and type of slots in that section
3. Specify slot_assignments whose element_types match that template's slots
4. Reference real column names from the data profile in data_columns

=== SLIDE STRUCTURES (choose one per section) ===
- "blank"     — 1 region, full slide. Use for: single dominant chart, single full-width table,
                hero KPI, or any section with exactly 1 content element.
- "two-col"   — 2 regions side by side (left | right). Use for: chart + commentary,
                table + commentary, chart + table, any 2-element pairing.
- "two-row"   — 2 regions stacked (top | bottom). Use for: headline metric on top + supporting
                chart below, title row + data row.
- "grid-2x2"  — 4 regions in a 2×2 grid (TL | TR | BL | BR). Use for: 4 KPIs side-by-side,
                comparing 4 categories, multi-chart overview, 3-4 element sections.

Structure selection rules:
- 1 slot  → "blank"
- 2 slots → "two-col" (default) or "two-row" if top/bottom layout is more natural
- 3 slots → "grid-2x2" (use 3 of the 4 regions; leave one commentary slot)
- 4 slots → "grid-2x2"

=== AVAILABLE CHART TYPES ===
bar_chart | stacked_bar_chart | horizontal_bar_chart | line_chart | multi_line_chart |
pie_chart | donut_chart | area_chart | combo_chart_singlebar_line | scatter_chart

Rules:
- data_columns must be real column names listed in the data profile (not invented)
- Assign each section a distinct narrative_role: hook | analysis | detail | summary
- narrative_role "hook" goes first, "summary" goes last
- slot count must be consistent with slide_structure (see rules above)
- A reviewer will score 0-10. Aim for 7+
- Return ONLY a valid JSON array, no markdown fences, no extra text

Required JSON format for each section:
{
  "name": string,
  "description": string,
  "narrative_role": "hook" | "analysis" | "detail" | "summary",
  "slide_structure": "blank" | "two-col" | "two-row" | "grid-2x2",
  "template_id": integer or null,
  "slot_assignments": [
    {
      "slot_display_order": integer,
      "element_type": "chart" | "table" | "commentary",
      "data_columns": [list of column names from data profile],
      "chart_type": "bar_chart" | "line_chart" | "pie_chart" | "stacked_bar_chart" |
                    "area_chart" | "donut_chart" | "horizontal_bar_chart" |
                    "multi_line_chart" | "combo_chart_singlebar_line" | "scatter_chart" | null,
      "insight_directive": string describing what to emphasise in this slot
    }
  ]
}"""


def build_user_prompt(state: dict[str, Any]) -> str:
    objective = state.get("objective") or "Present key findings clearly"
    ptype = state.get("presentation_type", "business")
    audience = state.get("audience", "stakeholders")
    expertise = state.get("audience_expertise", "mixed")
    tone = state.get("tone", "formal")
    metrics = state.get("key_metrics") or []
    metrics_str = ", ".join(metrics) if metrics else "all available metrics"

    profile = state.get("data_profile") or {}
    columns = profile.get("columns", [])
    col_lines = []
    for col in columns[:20]:
        name = col.get("name", "")
        dtype = col.get("dtype", "unknown")
        role = col.get("role", "")
        samples = col.get("sample_values", col.get("top_values", []))
        sample_str = ", ".join(str(s) for s in samples[:3]) if samples else ""
        col_lines.append(f"  - {name} ({dtype}, role={role}){': ' + sample_str if sample_str else ''}")
    data_section = "\n".join(col_lines) if col_lines else "  No data provided — use content-only slots"

    templates = state.get("available_templates", [])
    templates_str = json.dumps(templates, indent=2) if templates else "[]"

    retry_note = ""
    feedback = state.get("reviewer_feedback", "")
    attempts = state.get("planner_attempts", 0)
    if feedback and attempts > 0:
        retry_note = f"\n\nPrevious reviewer feedback (address these issues):\n{feedback}\n"

    return (
        f"Objective: {objective}\n"
        f"Presentation type: {ptype}\n"
        f"Audience: {audience} (expertise: {expertise})\n"
        f"Tone: {tone}\n"
        f"Key metrics to highlight: {metrics_str}\n"
        f"\nData columns available:\n{data_section}\n"
        f"\nAvailable templates (use template_id from this list):\n{templates_str}"
        f"{retry_note}\n"
        f"\nReturn 3-5 sections as a JSON array."
    )
