"""data_profile_node — profile the uploaded data for the LLM prompt."""
from __future__ import annotations

from typing import Any

from app.tools.ingest_tool import profile_data
from app.utils.logger import logger


async def data_profile_node(state: dict[str, Any]) -> dict[str, Any]:
    data_source = state.get("data_source")

    if not data_source:
        return {"data_profile": {"columns": [], "row_count": 0, "column_count": 0}}

    src_type = data_source.get("source_type", "")
    try:
        if src_type in {"csv_upload", "xlsx_upload"}:
            file_id = data_source.get("file_id", "")
            filename = data_source.get("filename", "")
            if not file_id or not filename:
                raise ValueError("file_id and filename required for upload sources")
            res = await profile_data(file_id=file_id, filename=filename)
            if not res.success:
                raise RuntimeError(res.error or "profile_data failed")
            raw_profile = res.data or {}
        elif src_type == "inline_json":
            import pandas as pd
            from app.tools.ingest_tool import _profile_dataframe  # noqa: PLC0415
            rows = data_source.get("inline_data") or []
            if not rows:
                raise ValueError("inline_json requires non-empty inline_data")
            df = pd.DataFrame(rows)
            profile_obj = _profile_dataframe(df)
            raw_profile = profile_obj.model_dump()
        else:
            raw_profile = {"columns": [], "row_count": 0, "column_count": 0}

        columns_for_llm = _simplify_columns(raw_profile)
        raw_profile["columns"] = columns_for_llm
        logger.info("data_profile_node: %d columns profiled", len(columns_for_llm))
        return {"data_profile": raw_profile}

    except Exception as exc:  # noqa: BLE001
        logger.warning("data_profile_node failed: %s", exc)
        return {"data_profile": {"columns": [], "row_count": 0, "column_count": 0}}


def _simplify_columns(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert DataProfile column representation to a flat list for the LLM."""
    cols = raw.get("columns", [])
    if not cols:
        return []
    simplified = []
    for col in cols:
        if isinstance(col, dict):
            stats = col.get("stats") or {}
            simplified.append({
                "name": col.get("name", ""),
                "dtype": col.get("dtype", "unknown"),
                "role": col.get("role", ""),
                "sample_values": stats.get("top_values", [])[:5] if stats else [],
            })
    return simplified
