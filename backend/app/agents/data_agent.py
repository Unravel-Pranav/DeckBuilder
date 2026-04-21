"""data_agent — fetch or map data for each section in the structure.

Three paths:
  1. data_profile exists (CSV/Excel ingested) → map_columns_to_chart per section
  2. report_id / template_id (DB source)      → fetch_report_data / fetch_template_summary
  3. inline_json                              → convert inline_data to sections_data directly
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.schemas.tool_schema import DataProfile
from app.tools.data_tool import fetch_report_data, fetch_template_summary
from app.tools.ingest_tool import parse_file, profile_data
from app.tools.mapping_tool import map_columns_to_chart
from app.utils.logger import logger


def _transform_db_sections(db_sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform DB section dicts into the chart-mapping format downstream nodes expect.

    ppt_agent._build_normal_payload reads: x_axis, y_axis, data_slice, elements.
    DB sections have: id, key, name, elements[{element_type, config, ...}].
    """
    mappings: list[dict[str, Any]] = []
    for idx, section in enumerate(db_sections):
        chart_data: list[dict[str, Any]] = []
        chart_type = "bar"
        x_axis = "Category"
        y_axis: list[str] = []

        for elem in section.get("elements", []):
            if elem.get("element_type") == "chart":
                config = elem.get("config", {})
                chart_data = config.get("chart_data", [])
                chart_type = config.get("chart_type", "bar")
                axis_cfg = config.get("axisConfig", {})
                x_keys = axis_cfg.get("xAxis", [])
                y_keys = axis_cfg.get("yAxis", [])
                if x_keys:
                    x_axis = x_keys[0].get("key", "Category")
                if y_keys:
                    y_axis = [y.get("key", "value") for y in y_keys]
                break

        mappings.append({
            "section_index": idx,
            "section_name": section.get("name", f"Section {idx}"),
            "chart_type": chart_type,
            "x_axis": x_axis,
            "y_axis": y_axis if y_axis else ["value"],
            "data_slice": chart_data,
            "elements": section.get("elements", []),
        })
    return mappings


async def data_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    data_source = state.get("data_source")
    data_profile = state.get("data_profile")
    structure = state.get("structure")
    mode = state.get("mode", "full")

    # --- Path 1: CSV/Excel ingested → map columns to charts per section ---
    if data_profile is not None and structure:
        profile_obj = (
            data_profile
            if isinstance(data_profile, DataProfile)
            else DataProfile(**data_profile)
        )
        sections = (
            structure.get("sections", [])
            if isinstance(structure, dict)
            else structure.sections
        )

        mappings: list[dict[str, Any]] = []
        for idx, section in enumerate(sections):
            sec_dict = section if isinstance(section, dict) else section.model_dump()
            chart_type = sec_dict.get("chart_type") or "bar"

            file_id = data_source.file_id if data_source else None
            filename = data_source.filename if data_source else None

            result = await map_columns_to_chart(
                data_profile=profile_obj,
                chart_type=chart_type,
                section_index=idx,
                file_id=file_id,
                filename=filename,
            )
            if result.success:
                mappings.append(result.data)
            else:
                logger.warning("Data: mapping failed for section %d: %s", idx, result.error)
                mappings.append(
                    {"section_index": idx, "chart_type": chart_type, "warnings": [result.error]}
                )

        logger.info("Data: mapped %d sections from data profile", len(mappings))
        return {"sections_data": mappings, "data_mappings": mappings}

    # --- Path 1b: CSV/XLSX but ingest was skipped (ppt_only mode) ---
    if (
        data_source
        and data_source.source_type in ("csv_upload", "xlsx_upload")
        and data_profile is None
    ):
        logger.info("Data: CSV/XLSX source but no profile — running inline ingest")
        parse_result = await parse_file(
            file_id=data_source.file_id,
            filename=data_source.filename,
        )
        if not parse_result.success:
            raise RuntimeError(f"Inline parse failed: {parse_result.error}")

        profile_result = await profile_data(
            file_id=data_source.file_id,
            filename=data_source.filename,
        )
        if not profile_result.success:
            raise RuntimeError(f"Inline profile failed: {profile_result.error}")

        profile_obj = DataProfile(**profile_result.data)

        single_mapping = await map_columns_to_chart(
            data_profile=profile_obj,
            chart_type="bar",
            section_index=0,
            file_id=data_source.file_id,
            filename=data_source.filename,
        )
        mappings = [single_mapping.data] if single_mapping.success else []

        updates: dict[str, Any] = {
            "data_profile": profile_obj,
            "sections_data": mappings,
            "data_mappings": mappings,
        }
        if not structure:
            updates["structure"] = _auto_structure_from_sections(mappings)
            logger.info("Data: ppt_only auto-generated structure from CSV profile")
        return updates

    # --- Path 2: DB source → fetch from repository ---
    if data_source:
        session_factory = state.get("session_factory")
        if session_factory is None:
            raise RuntimeError(
                "session_factory required for DB data source but not found in state"
            )

        if data_source.source_type == "report_id" and data_source.report_id is not None:
            async with session_factory() as session:
                result = await fetch_report_data(
                    session=session, report_id=data_source.report_id
                )
            if not result.success:
                raise RuntimeError(
                    f"Failed to fetch report {data_source.report_id}: {result.error}"
                )
            raw_sections = result.data.get("sections", [])
            mappings = _transform_db_sections(raw_sections)
            logger.info(
                "Data: fetched report %d with %d sections → transformed to mappings",
                data_source.report_id,
                len(raw_sections),
            )
            updates: dict[str, Any] = {"sections_data": mappings, "data_mappings": mappings}
            if mode == "ppt_only" and not structure:
                updates["structure"] = _auto_structure_from_sections(mappings)
                logger.info("Data: ppt_only auto-generated structure with %d sections", len(mappings))
            return updates

        if data_source.source_type == "template_id" and data_source.template_id is not None:
            async with session_factory() as session:
                result = await fetch_template_summary(
                    session=session, template_id=data_source.template_id
                )
            if not result.success:
                raise RuntimeError(
                    f"Failed to fetch template {data_source.template_id}: {result.error}"
                )
            logger.info("Data: fetched template %d", data_source.template_id)
            sections_data = [result.data]
            updates = {"sections_data": sections_data}
            if mode == "ppt_only" and not structure:
                updates["structure"] = _auto_structure_from_sections(sections_data)
                logger.info("Data: ppt_only auto-generated structure for template")
            return updates

        # --- Path 3: inline_json → use inline_data directly ---
        if data_source.source_type == "inline_json" and data_source.inline_data:
            logger.info(
                "Data: using %d inline_data rows directly", len(data_source.inline_data)
            )
            sections_data = data_source.inline_data
            updates = {"sections_data": sections_data}
            if mode == "ppt_only" and not structure:
                updates["structure"] = _auto_structure_from_sections(
                    [{"section_name": f"Section {i+1}", "chart_type": "bar"}
                     for i in range(max(1, len(sections_data) // 5))]
                )
                logger.info("Data: ppt_only auto-generated structure for inline_json")
            return updates

    logger.warning("Data: no data source resolved — sections_data will be empty")
    return {"sections_data": []}


def _auto_structure_from_sections(sections_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate minimal structure when ppt_only mode has data but no structure."""
    sections = []
    for idx, sec in enumerate(sections_data):
        sections.append({
            "name": sec.get("section_name", f"Section {idx + 1}"),
            "element_type": "chart",
            "chart_type": sec.get("chart_type", "bar"),
        })
    return {"title": "Auto-generated", "sections": sections}
