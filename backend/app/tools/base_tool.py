"""Base tool abstractions and lightweight tool registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
    execution_time_ms: float | None = None

    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, error=error)


class ToolDefinition(BaseModel):
    name: str
    description: str
    fn: Callable[..., Any]
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None

    model_config = {"arbitrary_types_allowed": True}


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(
    *,
    name: str,
    description: str,
    input_schema: type[BaseModel] | None = None,
    output_schema: type[BaseModel] | None = None,
):
    """Decorator to register a tool in the global registry."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOL_REGISTRY[name] = ToolDefinition(
            name=name,
            description=description,
            fn=fn,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        return fn

    return decorator
