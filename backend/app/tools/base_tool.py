"""Tool infrastructure — ToolResult, ToolDefinition, registry, and @register_tool decorator."""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Standardized return type for every tool function."""

    success: bool
    data: T | None = None
    error: str | None = None
    execution_time_ms: float | None = None

    @classmethod
    def ok(cls, data: Any, **kwargs: Any) -> ToolResult:
        return cls(success=True, data=data, **kwargs)

    @classmethod
    def fail(cls, error: str, **kwargs: Any) -> ToolResult:
        return cls(success=False, error=error, **kwargs)


@dataclass
class ToolDefinition:
    """Registry entry for a single tool. Uses dataclass because fn is not JSON-serializable."""

    name: str
    description: str
    fn: Callable
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    requires_session: bool = False


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(
    name: str,
    description: str,
    input_schema: type[BaseModel],
    output_schema: type[BaseModel],
    requires_session: bool = False,
) -> Callable:
    """Decorator that registers an async tool function into TOOL_REGISTRY.

    Also wraps the function to auto-measure execution_time_ms on the
    returned ToolResult.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> ToolResult:
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                return ToolResult.fail(error=str(exc), execution_time_ms=elapsed)
            elapsed = (time.perf_counter() - start) * 1000
            if isinstance(result, ToolResult):
                result.execution_time_ms = elapsed
                return result
            return ToolResult.ok(data=result, execution_time_ms=elapsed)

        TOOL_REGISTRY[name] = ToolDefinition(
            name=name,
            description=description,
            fn=wrapper,
            input_schema=input_schema,
            output_schema=output_schema,
            requires_session=requires_session,
        )
        return wrapper

    return decorator
