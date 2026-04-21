"""Adapts internal ToolDefinition entries to MCP-compatible tool functions.

Each tool's Pydantic input_schema fields are expanded into individual
function parameters so FastMCP generates a flat JSON schema (not nested).
Session-requiring tools get a short-lived AsyncSession injected from
the captured session_factory.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.tools.base_tool import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


def register_tool_as_mcp(
    server: FastMCP,
    tool_def: ToolDefinition,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Register a single ToolDefinition on the MCP server."""
    InputModel = tool_def.input_schema

    sig_params: list[inspect.Parameter] = []
    for field_name, field_info in InputModel.model_fields.items():
        if field_info.is_required():
            default = inspect.Parameter.empty
        else:
            default = field_info.default
        sig_params.append(inspect.Parameter(
            field_name,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=default,
            annotation=field_info.annotation,
        ))

    _tool_fn = tool_def.fn
    _requires_session = tool_def.requires_session
    _name = tool_def.name

    async def wrapper(**kwargs: Any) -> str:
        validated = InputModel(**kwargs)
        call_kwargs = {k: getattr(validated, k) for k in InputModel.model_fields}

        if _requires_session:
            async with session_factory() as session:
                result: ToolResult = await _tool_fn(session=session, **call_kwargs)
        else:
            result = await _tool_fn(**call_kwargs)

        return result.model_dump_json()

    wrapper.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    wrapper.__name__ = _name
    wrapper.__doc__ = tool_def.description

    server.add_tool(wrapper, name=_name, description=tool_def.description)
    logger.debug("Registered MCP tool: %s (requires_session=%s)", _name, _requires_session)
