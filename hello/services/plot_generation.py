from __future__ import annotations

from typing import Any


async def build_plots(section: str, data: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a plot specification for the frontend.

    Supported types: bar, line, area, combo, pie, donut, stacked-bar, table, none.
    Heuristics are based on section name and data shape.
    """
    key = (section or "").lower()
    # If table-like data
    if (
        data
        and isinstance(data[0], dict)
        and {"metric", "current"}.issubset(set(data[0].keys()))
    ):
        # Provide a basic table spec
        return {
            "type": "table",
            "columns": ["metric", "current", "previous", "change"],
            "rows": data,
        }

    # Time-series chart from quarters
    x = [row.get("quarter") for row in data if isinstance(row, dict)]
    y1 = [row.get("net_absorption") for row in data if isinstance(row, dict)]
    y2 = [row.get("vacancy_rate") for row in data if isinstance(row, dict)]

    def line_spec():
        return {
            "type": "line",
            "x": x,
            "series": [{"name": "Net Absorption", "data": y1}],
        }

    def bar_spec(stacked: bool = False):
        spec: dict[str, Any] = {
            "type": "bar",
            "x": x,
            "series": [{"name": "Net Absorption", "data": y1}],
        }
        if stacked:
            spec["stacked"] = True
        return spec

    def area_spec():
        return {
            "type": "area",
            "x": x,
            "series": [{"name": "Net Absorption", "data": y1}],
        }

    def combo_spec():
        return {
            "type": "combo",
            "x": x,
            "series": [
                {"name": "Net Absorption", "type": "bar", "data": y1},
                {"name": "Vacancy Rate", "type": "line", "yAxis": "right", "data": y2},
            ],
            "yAxis": {"left": {"label": "Absorption"}, "right": {"label": "Vacancy %"}},
        }

    def pie_spec(donut: bool = False):
        # derive categories from first few rows
        parts: list[dict[str, Any]] = []
        for row in data[:6]:
            if isinstance(row, dict):
                name = row.get("metric") or row.get("quarter") or "Slice"
                val = row.get("net_absorption") or row.get("current") or 1
                parts.append(
                    {
                        "name": str(name),
                        "value": float(str(val).strip("%$ ").replace(",", "") or 0),
                    }
                )
        return {"type": "donut" if donut else "pie", "parts": parts}

    if (
        key.startswith("chart")
        or "chart" in key
        or "overview" in key
        or "absorption" in key
    ):
        if "line" in key:
            return line_spec()
        if "area" in key:
            return area_spec()
        if "stack" in key:
            return bar_spec(stacked=True)
        if "combo" in key:
            return combo_spec()
        if "pie" in key:
            return pie_spec(False)
        if "donut" in key:
            return pie_spec(True)
        # default
        return bar_spec()

    return {"type": "none"}
