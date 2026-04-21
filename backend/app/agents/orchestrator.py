"""Orchestrator — LangGraph StateGraph wiring + pipeline entry point.

Builds the full agent pipeline graph, handles retry routing, metrics
wrapping, and assembles the final AgentGenerateResponse from state.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.data_agent import data_node
from app.agents.ingest_agent import ingest_node
from app.agents.insight_agent import insight_node
from app.agents.planner_agent import planner_node
from app.agents.ppt_agent import ppt_node
from app.agents.skeleton_contracts_agent import skeleton_contracts_node
from app.agents.state import AgentState
from app.agents.visualization_agent import visualization_node
from app.core.config import settings
from app.schemas.agent_schema import (
    AgentGenerateRequest,
    AgentGenerateResponse,
    StepMetric,
)
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Metrics wrapper
# ---------------------------------------------------------------------------


def _with_metrics(node_name: str, node_fn: Callable) -> Callable:
    """Wrap a node function to record StepMetric and handle exceptions.

    On success: records status="success", appends to steps_completed.
    On exception: records status="failed", increments retry_counts,
    appends structured error, returns empty dict (does NOT re-raise).
    """

    async def wrapper(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        started_at = time.time()
        metrics = dict(state.get("metrics", {}))
        metrics[node_name] = StepMetric(
            step=node_name,
            started_at=started_at,
            status="running",
        )

        try:
            result = await node_fn(state, config)
        except Exception as exc:
            ended_at = time.time()
            duration_ms = (ended_at - started_at) * 1000

            metrics[node_name] = StepMetric(
                step=node_name,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                status="failed",
                error=str(exc),
            )

            errors = list(state.get("errors", []))
            errors.append({
                "step": node_name,
                "message": str(exc),
                "timestamp": ended_at,
            })

            retry_counts = dict(state.get("retry_counts", {}))
            retry_counts[node_name] = retry_counts.get(node_name, 0) + 1

            logger.error(
                "Node '%s' failed (attempt %d): %s",
                node_name, retry_counts[node_name], exc,
            )

            return {
                "metrics": metrics,
                "errors": errors,
                "retry_counts": retry_counts,
            }

        ended_at = time.time()
        duration_ms = (ended_at - started_at) * 1000

        metrics[node_name] = StepMetric(
            step=node_name,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            status="success",
        )

        steps_completed = list(state.get("steps_completed", []))
        steps_completed.append(node_name)

        updates = result if isinstance(result, dict) else {}
        updates["metrics"] = metrics
        updates["steps_completed"] = steps_completed
        return updates

    wrapper.__name__ = f"{node_name}_wrapped"
    return wrapper


# ---------------------------------------------------------------------------
# Fallbacks (used by parallel_decisions_node)
# ---------------------------------------------------------------------------


def _fallback_table_layout(state: AgentState) -> list[dict[str, Any]]:
    """Produce a viz_mapping fallback: every section gets chart_type='table'."""
    structure = state.get("structure", {})
    sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else getattr(structure, "sections", [])
    )
    return [
        {
            "section_index": idx,
            "chart_type": "table",
            "confidence": 0.5,
            "reasoning": "Fallback — visualization failed",
            "source": "fallback",
        }
        for idx in range(len(sections))
    ]


def _fallback_static_commentary(state: AgentState) -> dict[str, str]:
    """Produce generic commentary for every section."""
    structure = state.get("structure", {})
    sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else getattr(structure, "sections", [])
    )
    result: dict[str, str] = {}
    for section in sections:
        name = section.get("name", "Section") if isinstance(section, dict) else section.name
        result[name] = f"Key findings for {name} are detailed in the data above."
    return result


# ---------------------------------------------------------------------------
# Composite node: parallel viz + insight
# ---------------------------------------------------------------------------


async def parallel_decisions_node(
    state: AgentState, config: RunnableConfig,
) -> dict[str, Any]:
    """Run viz and insight concurrently with independent failure isolation."""
    viz_coro = visualization_node(state, config)
    insight_coro = insight_node(state, config)

    results = await asyncio.gather(viz_coro, insight_coro, return_exceptions=True)

    now = time.time()
    updates: dict[str, Any] = {}
    errors = list(state.get("errors", []))

    if isinstance(results[0], Exception):
        updates["viz_mappings"] = _fallback_table_layout(state)
        errors.append({
            "step": "parallel_decisions",
            "message": f"Visualization failed: {results[0]}",
            "timestamp": now,
        })
        logger.warning("parallel_decisions: viz failed, using table fallback — %s", results[0])
    else:
        updates.update(results[0])

    if isinstance(results[1], Exception):
        updates["commentaries"] = _fallback_static_commentary(state)
        errors.append({
            "step": "parallel_decisions",
            "message": f"Insight failed: {results[1]}",
            "timestamp": now,
        })
        logger.warning("parallel_decisions: insight failed, using static fallback — %s", results[1])
    else:
        updates.update(results[1])

    updates["errors"] = errors
    return updates


# ---------------------------------------------------------------------------
# Sink node
# ---------------------------------------------------------------------------


async def finalize_node(
    state: AgentState, config: RunnableConfig,
) -> dict[str, Any]:
    """No-op terminal node. Response is built after the graph returns."""
    return {}


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def route_from_start(state: AgentState) -> str:
    mode = state.get("mode", "full")
    if mode == "ppt_only":
        return "data"

    data_source = state.get("data_source")
    if data_source and data_source.source_type in (
        "csv_upload", "xlsx_upload", "inline_json",
    ):
        return "ingest"

    return "planner"


def after_planner(state: AgentState) -> str:
    mode = state.get("mode", "full")
    if mode == "structure_only":
        return "finalize"
    if mode == "skeleton":
        return "skeleton_contracts"
    return "data"


def after_data(state: AgentState) -> str:
    overrides = state.get("overrides")
    if overrides and overrides.skip_viz and overrides.skip_insights:
        return "ppt"
    return "parallel_decisions"


def should_retry(state: AgentState) -> str:
    counts = state.get("retry_counts", {})
    if not counts:
        return "finalize"

    # Only retry steps where _with_metrics caught an unhandled exception
    # (those are the only steps that get entries in retry_counts).
    # Errors recorded internally by nodes with fallbacks already applied
    # (e.g., parallel_decisions) don't appear in retry_counts and don't
    # need retrying — the fallback IS the recovery.
    errors = state.get("errors", [])
    for error in reversed(errors):
        step = error["step"]
        if step in counts and counts[step] < settings.agent_max_retries:
            logger.info(
                "Retry: routing back to '%s' (attempt %d/%d)",
                step, counts[step] + 1, settings.agent_max_retries,
            )
            return step

    last_step = next(iter(counts), "unknown")
    logger.warning(
        "Retry: max retries exhausted for '%s' (%d/%d) — finalizing",
        last_step, counts.get(last_step, 0), settings.agent_max_retries,
    )
    return "finalize"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


_RETRYABLE_NODES = (
    "ingest", "planner", "data", "parallel_decisions",
    "skeleton_contracts", "ppt",
)


def _build_graph() -> Any:
    graph = StateGraph(AgentState)

    graph.add_node("ingest", _with_metrics("ingest", ingest_node))
    graph.add_node("planner", _with_metrics("planner", planner_node))
    graph.add_node("data", _with_metrics("data", data_node))
    graph.add_node(
        "parallel_decisions",
        _with_metrics("parallel_decisions", parallel_decisions_node),
    )
    graph.add_node(
        "skeleton_contracts",
        _with_metrics("skeleton_contracts", skeleton_contracts_node),
    )
    graph.add_node("ppt", _with_metrics("ppt", ppt_node))
    graph.add_node("finalize", finalize_node)

    graph.add_conditional_edges(START, route_from_start, {
        "ingest": "ingest",
        "planner": "planner",
        "data": "data",
    })

    graph.add_edge("ingest", "planner")

    graph.add_conditional_edges("planner", after_planner, {
        "finalize": "finalize",
        "skeleton_contracts": "skeleton_contracts",
        "data": "data",
    })

    graph.add_conditional_edges("data", after_data, {
        "ppt": "ppt",
        "parallel_decisions": "parallel_decisions",
    })

    graph.add_edge("parallel_decisions", "ppt")
    graph.add_edge("skeleton_contracts", "ppt")

    retry_targets = {name: name for name in _RETRYABLE_NODES}
    retry_targets["finalize"] = "finalize"
    graph.add_conditional_edges("ppt", should_retry, retry_targets)

    graph.add_edge("finalize", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _build_response(state: AgentState) -> AgentGenerateResponse:
    """Single place where AgentState becomes AgentGenerateResponse."""
    errors = state.get("errors", [])
    has_errors = len(errors) > 0
    steps = state.get("steps_completed", [])

    ppt_result = state.get("ppt_result")
    ppt_url = None
    if ppt_result and isinstance(ppt_result, dict):
        ppt_url = ppt_result.get("file_path") or ppt_result.get("filename")

    status: str
    if ppt_result and not ppt_result.get("dry_run"):
        status = "completed"
    elif state.get("dry_run"):
        status = "completed"
    elif state.get("mode") == "structure_only" and state.get("structure"):
        status = "completed"
    elif has_errors:
        status = "failed"
    else:
        status = "completed"

    structure_raw = state.get("structure")
    structure = None
    if structure_raw is not None:
        from app.schemas.tool_schema import PresentationStructure
        structure = (
            structure_raw
            if isinstance(structure_raw, PresentationStructure)
            else PresentationStructure(**structure_raw)
        )

    data_contracts_raw = state.get("data_contracts")
    data_contracts = None
    if data_contracts_raw is not None:
        from app.schemas.tool_schema import DataContract
        data_contracts = [
            dc if isinstance(dc, DataContract) else DataContract(**dc)
            for dc in data_contracts_raw
        ]

    metrics_raw = state.get("metrics", {})
    metrics = {}
    for key, val in metrics_raw.items():
        if isinstance(val, StepMetric):
            metrics[key] = val
        elif isinstance(val, dict):
            metrics[key] = StepMetric(**val)

    return AgentGenerateResponse(
        job_id=state.get("job_id", ""),
        status=status,
        mode=state.get("mode", "full"),
        dry_run=state.get("dry_run", False),
        structure=structure,
        ppt_download_url=ppt_url,
        steps_completed=steps,
        errors=errors,
        metrics=metrics,
        data_contracts=data_contracts,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_agent_pipeline(
    request: AgentGenerateRequest,
    session_factory: async_sessionmaker[AsyncSession],
) -> AgentGenerateResponse:
    """Execute the full agent pipeline and return the response.

    Accepts session_factory (not a raw session). Each agent node that
    needs DB creates a short-lived session via the factory.
    """
    job_id = str(uuid.uuid4())

    initial_state: AgentState = {
        "job_id": job_id,
        "intent": request.intent,
        "presentation_type": request.presentation_type,
        "audience": request.audience,
        "tone": request.tone,
        "mode": request.mode,
        "dry_run": request.dry_run,
        "data_source": request.data_source,
        "overrides": request.overrides,
        "session_factory": session_factory,
        "errors": [],
        "retry_counts": {},
        "metrics": {},
        "steps_completed": [],
    }

    logger.info(
        "Pipeline started: job_id=%s, mode=%s, dry_run=%s",
        job_id, request.mode, request.dry_run,
    )

    compiled = _build_graph()
    final_state = await compiled.ainvoke(initial_state)

    response = _build_response(final_state)

    logger.info(
        "Pipeline finished: job_id=%s, status=%s, steps=%s",
        job_id, response.status, response.steps_completed,
    )

    return response
