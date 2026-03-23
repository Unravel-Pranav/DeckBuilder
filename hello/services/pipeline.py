from __future__ import annotations

from typing import Any

from hello.services.data_fetch import fetch_section_data
from hello.services.plot_generation import build_plots
from hello.services.agent_service import generate_text


async def generate_first_draft(config: dict[str, Any]) -> dict[str, Any]:
    """Orchestrate the draft generation for the selected sections.

    Returns a payload the frontend can render directly.
    """
    sections = config.get("sections") or {
        "Chart 1": {"prompt": "Generate chart of net absorption by quarter"},
        "Table 2": {"prompt": "Key metrics table"},
        "Commentary 3": {"prompt": "Executive commentary"},
    }
    results: list[dict[str, Any]] = []
    for section_name, sconf in sections.items():
        data = await fetch_section_data(section_name, config)
        plot = await build_plots(section_name, data)
        text = await generate_text(section_name, data, sconf.get("prompt", ""))
        results.append(
            {"section": section_name, "plot": plot, "text": text, "data": data}
        )

    return {
        "config": config,
        "sections": results,
    }
