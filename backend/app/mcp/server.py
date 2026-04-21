"""MCP server — exposes TOOL_REGISTRY as MCP tools.

Usage:
    from app.mcp.server import mcp_server, register_all_tools
    register_all_tools()           # populate tools from TOOL_REGISTRY
    await mcp_server.run_stdio_async()   # or mount via SSE/streamable-http
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from app.core.config import settings

logger = logging.getLogger(__name__)

mcp_server = FastMCP(
    name="AutoDeck",
    instructions="AutoDeck presentation generation tools. Use these to build, "
    "analyze, and generate PowerPoint presentations from data.",
    streamable_http_path="/",
)


def register_all_tools() -> None:
    """Import tool registry and register each tool on the MCP server."""
    from app.core.database import async_session_factory
    from app.mcp.tool_adapters import register_tool_as_mcp
    from app.tools import TOOL_REGISTRY

    for tool_def in TOOL_REGISTRY.values():
        register_tool_as_mcp(mcp_server, tool_def, async_session_factory)

    logger.info(
        "MCP server: registered %d tools (%d require session)",
        len(TOOL_REGISTRY),
        sum(1 for t in TOOL_REGISTRY.values() if t.requires_session),
    )
