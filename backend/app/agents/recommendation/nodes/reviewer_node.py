"""reviewer_node — LLM critic that scores the recommendation plan 0-10."""
from __future__ import annotations

import json
from typing import Any

from app.services.ai_service import _chat, _get_client
from app.utils.logger import logger
from ..prompts.reviewer_prompt import REVIEWER_SYSTEM, build_user_prompt


def _heuristic_score(state: dict[str, Any]) -> tuple[int, str]:
    """Quick rule-based fallback scorer when no LLM is available."""
    plan = state.get("recommendation_plan", [])
    if not plan:
        return 2, "No sections generated."

    profile = state.get("data_profile") or {}
    known_cols = {c.get("name", "").lower() for c in profile.get("columns", [])}
    templates = state.get("available_templates", [])
    valid_ids = {t.get("id") for t in templates if t.get("id") is not None}

    score = 5
    issues = []

    roles = [s.get("narrative_role") for s in plan]
    if len(set(roles)) < len(roles):
        score -= 2
        issues.append("duplicate narrative roles")

    for sec in plan:
        tid = sec.get("template_id")
        if tid is not None and valid_ids and tid not in valid_ids:
            score -= 1
            issues.append(f"invalid template_id {tid}")
            break

        for slot in sec.get("slot_assignments", []):
            for col in slot.get("data_columns", []):
                if known_cols and col.lower() not in known_cols:
                    score -= 1
                    issues.append(f"unknown column '{col}'")
                    break

    score = max(0, min(10, score))
    feedback = "; ".join(issues) if issues else "Plan looks reasonable."
    return score, feedback


def _clean_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


async def reviewer_node(state: dict[str, Any]) -> dict[str, Any]:
    steps = [*(state.get("steps_completed") or []), "reviewer"]

    if not _get_client():
        score, feedback = _heuristic_score(state)
        logger.info("reviewer_node (heuristic): score=%d", score)
        return {"reviewer_score": score, "reviewer_feedback": feedback, "steps_completed": steps}

    try:
        user_prompt = build_user_prompt(state)
        raw = await _chat(REVIEWER_SYSTEM, user_prompt)
        cleaned = _clean_json(raw)
        result = json.loads(cleaned)
        score = int(result.get("score", 5))
        feedback = str(result.get("feedback", ""))
        score = max(0, min(10, score))
        logger.info("reviewer_node: score=%d feedback=%s", score, feedback[:80])
        return {"reviewer_score": score, "reviewer_feedback": feedback, "steps_completed": steps}
    except Exception as exc:  # noqa: BLE001
        logger.warning("reviewer_node LLM call failed: %s — using heuristic", exc)
        score, feedback = _heuristic_score(state)
        return {"reviewer_score": score, "reviewer_feedback": feedback, "steps_completed": steps}
