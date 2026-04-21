"""skeleton_contracts_agent — generate data contracts for skeleton mode.

Only runs when mode == 'skeleton'.  Produces DataContract specs that
describe what data each slide needs, then ppt_agent uses them to
build a skeleton PPT with sample data.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.schemas.tool_schema import DataProfile
from app.tools.mapping_tool import generate_data_contract
from app.utils.logger import logger


async def skeleton_contracts_node(
    state: AgentState, config: RunnableConfig,
) -> dict[str, Any]:
    structure = state.get("structure")
    if not structure:
        raise RuntimeError("Skeleton mode requires a structure but none found in state")

    sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else structure.sections
    )
    sections_dicts = [
        s if isinstance(s, dict) else s.model_dump()
        for s in sections
    ]

    data_profile_raw = state.get("data_profile")
    data_profile = None
    if data_profile_raw is not None:
        data_profile = (
            data_profile_raw
            if isinstance(data_profile_raw, DataProfile)
            else DataProfile(**data_profile_raw)
        )

    for s in sections_dicts:
        if not s.get("chart_type"):
            s["chart_type"] = "bar"

    result = await generate_data_contract(
        sections=sections_dicts,
        data_profile=data_profile,
    )
    if not result.success:
        raise RuntimeError(f"Data contract generation failed: {result.error}")

    contracts = result.data
    for contract in contracts:
        if isinstance(contract, dict) and not contract.get("chart_type"):
            contract["chart_type"] = "bar"

    logger.info("Skeleton: generated %d data contracts", len(contracts))
    return {"data_contracts": contracts}
