"""planner_node — LLM generates template-aware section recommendations."""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.services.ai_service import _chat, _get_client
from app.utils.logger import logger
from ..prompts.planner_prompt import PLANNER_SYSTEM, build_user_prompt

_FALLBACK_SECTIONS = [
    {
        "name": "Executive Summary",
        "description": "High-level overview of key findings",
        "narrative_role": "hook",
        "template_id": None,
        "slot_assignments": [
            {"slot_display_order": 0, "element_type": "chart", "data_columns": [], "chart_type": "bar_chart", "insight_directive": "Highlight top metrics"},
            {"slot_display_order": 1, "element_type": "commentary", "data_columns": [], "chart_type": None, "insight_directive": "Summarise key takeaway"},
        ],
    },
    {
        "name": "Detailed Analysis",
        "description": "In-depth breakdown of data patterns",
        "narrative_role": "analysis",
        "template_id": None,
        "slot_assignments": [
            {"slot_display_order": 0, "element_type": "chart", "data_columns": [], "chart_type": "bar_chart", "insight_directive": "Show trends or comparisons"},
            {"slot_display_order": 1, "element_type": "commentary", "data_columns": [], "chart_type": None, "insight_directive": "Explain key drivers"},
        ],
    },
    {
        "name": "Data Table",
        "description": "Tabular view of underlying data",
        "narrative_role": "detail",
        "template_id": None,
        "slot_assignments": [
            {"slot_display_order": 0, "element_type": "table", "data_columns": [], "chart_type": None, "insight_directive": "Show raw data"},
        ],
    },
    {
        "name": "Key Takeaways",
        "description": "Strategic conclusions and next steps",
        "narrative_role": "summary",
        "template_id": None,
        "slot_assignments": [
            {"slot_display_order": 0, "element_type": "commentary", "data_columns": [], "chart_type": None, "insight_directive": "State conclusions clearly"},
        ],
    },
]


def _inject_real_columns(sections: list[dict], profile: dict) -> list[dict]:
    """If LLM returned empty data_columns, fill with real columns from the profile."""
    cols = [c.get("name", "") for c in profile.get("columns", []) if c.get("name")]
    numeric = [c.get("name", "") for c in profile.get("columns", []) if c.get("role") in ("y_axis", "measure", "numeric")]
    non_numeric = [c.get("name", "") for c in profile.get("columns", []) if c.get("role") not in ("y_axis", "measure", "numeric") and c.get("name")]

    for sec in sections:
        for slot in sec.get("slot_assignments", []):
            if slot.get("data_columns"):
                continue
            if slot["element_type"] == "commentary":
                continue
            if slot["element_type"] == "table":
                slot["data_columns"] = cols[:4] if cols else []
            else:
                x_candidates = non_numeric[:1] or cols[:1]
                y_candidates = numeric[:2] or cols[1:3]
                slot["data_columns"] = x_candidates + y_candidates
    return sections


def _clean_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    attempts = (state.get("planner_attempts") or 0) + 1
    steps = [*(state.get("steps_completed") or []), "planner"]

    if not _get_client():
        logger.warning("planner_node: no LLM client — using fallback plan")
        plan = _FALLBACK_SECTIONS[:]
        if state.get("data_profile"):
            plan = _inject_real_columns(plan, state["data_profile"])
        return {"recommendation_plan": plan, "planner_attempts": attempts, "steps_completed": steps}

    try:
        user_prompt = build_user_prompt(state)
        raw = await _chat(PLANNER_SYSTEM, user_prompt)
        cleaned = _clean_json(raw)
        plan = json.loads(cleaned)
        if not isinstance(plan, list):
            raise ValueError("Expected JSON array")

        # Normalise: ensure required keys exist
        normalised = []
        for sec in plan:
            slots = []
            for slot in sec.get("slot_assignments", []):
                slots.append({
                    "slot_display_order": int(slot.get("slot_display_order", len(slots))),
                    "element_type": slot.get("element_type", "chart"),
                    "data_columns": slot.get("data_columns") or [],
                    "chart_type": slot.get("chart_type"),
                    "insight_directive": slot.get("insight_directive", ""),
                })
            normalised.append({
                "name": sec.get("name", f"Section {len(normalised)+1}"),
                "description": sec.get("description", ""),
                "narrative_role": sec.get("narrative_role", "analysis"),
                "template_id": sec.get("template_id"),
                "slot_assignments": slots,
            })

        if state.get("data_profile"):
            normalised = _inject_real_columns(normalised, state["data_profile"])

        logger.info("planner_node: generated %d sections (attempt %d)", len(normalised), attempts)
        return {"recommendation_plan": normalised, "planner_attempts": attempts, "steps_completed": steps}

    except Exception as exc:  # noqa: BLE001
        logger.warning("planner_node LLM call failed (attempt %d): %s", attempts, exc)
        plan = _FALLBACK_SECTIONS[:]
        if state.get("data_profile"):
            plan = _inject_real_columns(plan, state["data_profile"])
        return {"recommendation_plan": plan, "planner_attempts": attempts, "steps_completed": steps}
