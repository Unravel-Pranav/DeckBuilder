"""LLM prompts for the reviewer/critic node."""
from __future__ import annotations

import json
from typing import Any


REVIEWER_SYSTEM = """\
You are a strict quality reviewer for presentation plans.
Score the plan 0-10 based on these criteria:
- Sections have distinct narrative roles (hook→analysis→detail→summary): +2
- data_columns reference real available column names: +3
- template_id values are valid (from the provided template list or null): +2
- Plan clearly addresses the stated objective: +2
- Sections form a logical story arc: +1

Deduct heavily for: invented column names, duplicate narrative roles, missing slot_assignments.

Return ONLY valid JSON with no markdown fences:
{"score": integer, "feedback": "specific issues and how to fix them"}"""


def build_user_prompt(state: dict[str, Any]) -> str:
    objective = state.get("objective") or "Present key findings clearly"

    profile = state.get("data_profile") or {}
    column_names = [c.get("name", "") for c in profile.get("columns", [])]

    templates = state.get("available_templates", [])
    valid_ids = [t.get("id") for t in templates if t.get("id") is not None]

    plan = state.get("recommendation_plan", [])
    plan_str = json.dumps(plan, indent=2)

    return (
        f"Objective: {objective}\n\n"
        f"Available column names: {column_names}\n\n"
        f"Valid template IDs: {valid_ids}\n\n"
        f"Plan to review:\n{plan_str}"
    )
