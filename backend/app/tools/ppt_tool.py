"""Tool wrapper around pptx builder generation."""

from __future__ import annotations

from pydantic import BaseModel

from app.ppt_engine.pptx_builder import generate_presentation
from app.tools.base_tool import ToolResult, register_tool


class GeneratePptInput(BaseModel):
    report: dict
    sections: list[dict]


@register_tool(
    name="generate_ppt",
    description="Generate PPT from report+sections payload",
    input_schema=GeneratePptInput,
    output_schema=None,
)
async def generate_ppt(session, report: dict, sections: list[dict]) -> ToolResult:
    try:
        result = await generate_presentation({"report": report, "sections": sections})
        return ToolResult.ok(data=result)
    except Exception as exc:  # noqa: BLE001
        return ToolResult.fail(f"PPT generation failed: {exc}")
