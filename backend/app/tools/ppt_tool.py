"""ppt_tool — thin wrapper around PptService.generate_custom_ppt.

Accepts the same JSON shape that pptx_builder expects:
  {"report": {...}, "sections": [...]}
Returns file metadata on success, ToolResult.fail() on any error.
"""

from __future__ import annotations

from app.schemas.tool_schema import PptOutput, PptPayload
from app.services.ppt_service import PptService
from app.tools.base_tool import ToolResult, register_tool
from app.utils.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession


@register_tool(
    name="generate_ppt",
    description="Generate a PowerPoint file from a report+sections JSON payload",
    input_schema=PptPayload,
    output_schema=PptOutput,
    requires_session=True,
)
async def generate_ppt(
    session: AsyncSession,
    report: dict,
    sections: list[dict],
) -> ToolResult:
    svc = PptService(session)
    payload = {"report": report, "sections": sections}

    try:
        file_info = await svc.generate_custom_ppt(payload)
    except Exception as exc:
        logger.error("PPT generation failed: %s", exc)
        return ToolResult.fail(f"PPT generation failed: {exc}")

    return ToolResult.ok(
        data=PptOutput(
            file_id=file_info.get("file_id", ""),
            filename=file_info.get("filename", ""),
            file_path=file_info.get("file_path", ""),
            file_size=file_info.get("file_size", 0),
        ).model_dump()
    )
