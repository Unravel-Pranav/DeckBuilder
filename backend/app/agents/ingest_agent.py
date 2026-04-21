"""ingest_agent — parse uploaded file and profile its data.

Only runs when route_from_start determines the data source is a
file upload (csv/xlsx).  inline_json is deferred to data_agent.

NOTE: parse_file and profile_data both read from disk independently.
For large files this is a double-read; acceptable for now but a future
optimisation can pass the parsed DataFrame through to avoid it.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.tools.ingest_tool import parse_file, profile_data
from app.utils.logger import logger


async def ingest_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    data_source = state.get("data_source")
    if data_source is None:
        return {}

    if data_source.source_type == "inline_json":
        logger.info("Ingest: inline_json — skipping file parse (data_agent handles)")
        return {}

    file_id = data_source.file_id
    filename = data_source.filename

    parse_result = await parse_file(file_id=file_id, filename=filename)
    if not parse_result.success:
        raise RuntimeError(f"File parse failed: {parse_result.error}")

    logger.info(
        "Ingest: parsed %s — %d rows, %d columns",
        filename,
        parse_result.data["row_count"],
        parse_result.data["column_count"],
    )

    profile_result = await profile_data(file_id=file_id, filename=filename)
    if not profile_result.success:
        raise RuntimeError(f"Data profiling failed: {profile_result.error}")

    logger.info(
        "Ingest: profiled — dominant_pattern=%s, groupings=%d",
        profile_result.data["data_patterns"]["dominant_pattern"],
        len(profile_result.data["suggested_groupings"]),
    )

    return {"data_profile": profile_result.data}
