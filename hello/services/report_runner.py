from __future__ import annotations

import re
import time
from typing import Any
import json
import asyncio
import pandas as pd
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hello import models
from hello.services.ppt_builder import build_report_ppt_from_context
from hello.services.pptx_builder import generate_presentation
from hello.services.storage import (
    generate_presigned_url_for_key,
    save_report_to_s3,
)
from hello.services.agent_service import generate_section_llm
from hello.services.snowflake_service import fetch_snowflake_data
from hello.utils.sql_utils import render_sql_template
from hello.schemas import SectionRequest
from hello.utils.utils import build_ppt_download_url, get_latest_complete_quarter
from hello.utils.commentary_utils.text_generator import generate_market_narrative
from hello.utils.report_utils import fetch_multi_market_hero_fields
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as log

env = settings.TESTING_ENV


def _is_multi_geography_property_sub_type(property_sub_type: str | None) -> bool:
    """Check if the property_sub_type supports multi-geography report generation."""
    if not property_sub_type:
        return False
    return property_sub_type.lower() in [
        pst.lower() for pst in settings.MULTI_GEOGRAPHY_PROPERTY_SUB_TYPES
    ]


def _build_items_to_process(
    report_params: dict,
) -> list[tuple[str | None, str | None, str | None]]:
    """Build list of (market, geo_item, geo_level) tuples for report generation.

    For multi-geography property sub types, this creates one tuple per geography
    selection. For regular reports, returns a single tuple with market only.

    Args:
        report_params: Dictionary containing report parameters including
            defined_markets, vacancy_index, submarket, district, and property_sub_type

    Returns:
        List of (market, geo_item, geo_level) tuples where:
        - market: The market name (first one if multiple, with warning)
        - geo_item: The specific geography item (e.g., "Downtown") or None
        - geo_level: The geography level ("Vacancy Index", "Submarket", "District") or None
    """
    # Extract market - enforce single market
    defined_markets = report_params.get("defined_markets") or []
    if isinstance(defined_markets, str):
        defined_markets = [defined_markets]

    if len(defined_markets) > 1:
        log.warning(
            "Multiple markets provided for multi-geography report. "
            "Using first market only: %s (ignoring: %s)",
            defined_markets[0],
            defined_markets[1:],
        )

    market = defined_markets[0] if defined_markets else None

    # Check if this is a multi-geography property sub type
    property_sub_type = report_params.get("property_sub_type")
    if not _is_multi_geography_property_sub_type(property_sub_type):
        # Regular report - return single item with market only
        return [(market, None, None)]

    # Build list of geography selections
    specific_geographies: list[tuple[str, str]] = []

    # Add vacancy index selections
    vacancy_index = report_params.get("vacancy_index") or []
    if isinstance(vacancy_index, str):
        vacancy_index = [vacancy_index]
    for item in vacancy_index:
        if item and item != "All":
            specific_geographies.append((item, "Vacancy Index"))

    # Add submarket selections
    submarket = report_params.get("submarket") or []
    if isinstance(submarket, str):
        submarket = [submarket]
    for item in submarket:
        if item and item != "All":
            specific_geographies.append((item, "Submarket"))

    # Add district selections
    district = report_params.get("district") or []
    if isinstance(district, str):
        district = [district]
    for item in district:
        if item and item != "All":
            specific_geographies.append((item, "District"))

    if not specific_geographies:
        # No specific geographies selected - generate market-level report
        log.info("No specific geographies selected - generating market-level report")
        return [(market, None, None)]

    log.info(
        "Multi-geography report: %d items to process for market %s",
        len(specific_geographies),
        market,
    )
    return [(market, item, level) for item, level in specific_geographies]


def _build_report_params_for_geography(
    base_params: dict,
    market: str | None,
    geo_item: str | None,
    geo_level: str | None,
) -> dict:
    """Create a copy of report params with single geography values set.

    This modifies the params so that SQL templates render with the specific
    geography item instead of lists.

    Args:
        base_params: Original report parameters dictionary
        market: Single market name
        geo_item: Specific geography item (e.g., "Downtown") or None
        geo_level: Geography level ("Vacancy Index", "Submarket", "District") or None

    Returns:
        New dict with modified geography parameters for single item processing
    """
    import copy

    params = copy.deepcopy(base_params)

    # Set single market
    params["defined_markets"] = [market] if market else []

    # Reset all geography choices
    params["vacancy_index"] = []
    params["submarket"] = []
    params["district"] = []

    # Set only the relevant geography choice
    if geo_item and geo_level:
        if geo_level == "Vacancy Index":
            params["vacancy_index"] = [geo_item]
        elif geo_level == "Submarket":
            params["submarket"] = [geo_item]
        elif geo_level == "District":
            params["district"] = [geo_item]

    # Store current geography info for filename generation
    params["current_geography_item"] = geo_item
    params["current_geography_level"] = geo_level

    return params


def _build_geography_display_name(
    market: str | None,
    geo_item: str | None,
    geo_level: str | None,
) -> str:
    """Build a display name for the geography combination.

    Used for PPT filenames and email notifications.

    Args:
        market: Market name
        geo_item: Geography item name or None
        geo_level: Geography level or None

    Returns:
        Display name like "Denver-Downtown" or just "Denver"
    """
    parts = []
    if market:
        parts.append(market)
    if geo_item:
        parts.append(geo_item)
    return "-".join(parts) if parts else "Unknown"


def _extract_s3_key(s3_path: str) -> str:
    """Extract S3 key from s3:// path or return as-is if already a key."""
    if s3_path.startswith("s3://"):
        _, rest = s3_path.split("s3://", 1)
        _, s3_key = rest.split("/", 1)
        return s3_key
    return s3_path


async def _load_report(session: AsyncSession, report_id: int) -> models.Report | None:
    log.info("_load_report report_id=%s", report_id)
    from sqlalchemy.orm import joinedload

    res = await session.execute(
        select(models.Report)
        .options(
            joinedload(models.Report.sections).joinedload(models.ReportSection.elements)
        )
        .where(models.Report.id == report_id)
    )
    return res.scalars().unique().one_or_none()


async def _ensure_terminal_run_states(
    session: AsyncSession,
    run_state_updates: dict[int, str],
    run_ids: list[int],
    *,
    default_state: str | None = None,
    context: str = "",
) -> None:
    """Make sure ReportRun rows don't stay stuck in the transient "running" state."""

    if not run_ids:
        return

    desired_updates: dict[str, list[int]] = {"completed": [], "failed": []}
    for run_id in run_ids:
        target_state = run_state_updates.get(run_id)
        if not target_state and default_state:
            target_state = default_state
        normalized_state = (target_state or "").lower()
        if normalized_state in desired_updates:
            desired_updates[normalized_state].append(run_id)

    updated_any = False
    for state, ids in desired_updates.items():
        if not ids:
            continue
        await session.execute(
            update(models.ReportRun)
            .where(models.ReportRun.id.in_(ids))
            .where(models.ReportRun.run_state == "running")
            .values(run_state=state)
        )
        updated_any = True

    if updated_any:
        await session.commit()
        summary_bits = [
            f"{state}:{len(ids)}" for state, ids in desired_updates.items() if ids
        ]
        summary = ", ".join(summary_bits)
        log.info(
            "Synced ReportRun.run_state for %s (%s)",
            summary,
            context or "report_runner",
        )


def _safe(obj):
    """JSON-serializable helper for datetimes and SQLAlchemy models."""
    import datetime as _dt

    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (_dt.datetime, _dt.date)):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe(v) for v in obj]
    # Fallback string
    return str(obj)


def _merge_ppt_data(hero_fields, scoped_fields):
    """Preserve ppt_data when scoping hero_fields to a market or geography."""
    if not isinstance(scoped_fields, dict):
        return scoped_fields
    if isinstance(hero_fields, dict):
        ppt_data = hero_fields.get("ppt_data")
        if isinstance(ppt_data, list):
            merged = dict(scoped_fields)
            merged["ppt_data"] = ppt_data
            return merged
    return scoped_fields


def _extract_commentary_text(el: models.ReportSectionElement) -> str:
    """Strictly return saved final commentary from section_commentary.

    No fallback to prompt_text or config fields, per requirement.
    """
    sc = getattr(el, "section_commentary", None)
    return (sc or "").strip()


def _build_report_context(report: models.Report) -> dict:
    """Assemble a full dictionary of the saved report, sections, elements and SQL.

    The shape is stable and JSON-serializable so it can be logged or passed
    into future PPT/LLM pipelines.
    """
    # If run_quarter is "Dynamic", calculate the latest complete quarter
    actual_quarter = report.quarter
    if report.run_quarter and report.run_quarter.lower() == "dynamic":
        actual_quarter = get_latest_complete_quarter()
        log.info(
            "Report %s has Dynamic run_quarter. Using latest complete quarter: %s",
            report.id,
            actual_quarter,
        )

    # Top-level meta
    meta = {
        "id": report.id,
        "name": report.name,
        "template_id": report.template_id,
        "template_name": report.template_name,
        "report_type": report.report_type,
        "division": report.division,
        "publishing_group": report.publishing_group,
        "property_type": report.property_type,
        "property_sub_type": report.property_sub_type,
        "defined_markets": list(report.defined_markets or []),
        # Geography fields for multi-geography report generation
        "vacancy_index": list(report.vacancy_index or []),
        "submarket": list(report.submarket or []),
        "district": list(report.district or []),
        "quarter": actual_quarter,  # Use calculated quarter if dynamic
        "run_quarter": report.run_quarter,
        "history_range": report.history_range,
        "absorption_calculation": report.absorption_calculation,
        "total_vs_direct_absorption": report.total_vs_direct_absorption,
        "asking_rate_frequency": report.asking_rate_frequency,
        "asking_rate_type": report.asking_rate_type,
        "minimum_transaction_size": report.minimum_transaction_size,
        "use_auto_generated_text": report.use_auto_generated_text,
        "automation_mode": report.automation_mode,
        "status": report.status,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "hero_fields": report.hero_fields,
    }

    sections_payload: list[dict] = []
    for sec in sorted(report.sections or [], key=lambda s: s.display_order or 0):
        if sec.selected is False:
            continue
        elements_payload: list[dict] = []
        charts_sql: list[str] = []
        tables_sql: list[str] = []
        commentary_text: str | None = None
        for el in sorted(sec.elements or [], key=lambda e: e.display_order or 0):
            cfg = el.config if isinstance(el.config, dict) else {}
            et = (el.element_type or "").lower()
            if et == "commentary" and commentary_text is None:
                commentary_text = _extract_commentary_text(el)
            if et in {"chart", "table"}:
                sql = _extract_sql(el)
                if et == "chart" and sql:
                    charts_sql.append(sql)
                if et == "table" and sql:
                    tables_sql.append(sql)
            elements_payload.append(
                {
                    "id": el.id,
                    "element_type": el.element_type,
                    "label": el.label,
                    "selected": el.selected,
                    "display_order": el.display_order,
                    "config": cfg or {},
                    "section_commentary": getattr(el, "section_commentary", None),
                    "prompt_text": el.prompt_text,
                    "feedback_prompt": getattr(el, "feedback_prompt", None),
                }
            )

        sections_payload.append(
            {
                "id": sec.id,
                "key": sec.key,
                "name": sec.name,
                "sectionname_alias": sec.sectionname_alias,
                "display_order": sec.display_order,
                "selected": sec.selected,
                "layout_preference": getattr(sec, "layout_preference", None),
                "prompt_template": {
                    "id": sec.prompt_template_id,
                    "label": sec.prompt_template_label,
                    "body": sec.prompt_template_body,
                },
                "commentary": commentary_text or "",
                "elements": elements_payload,
                "charts_sql": charts_sql,
                "tables_sql": tables_sql,
            }
        )

    context = {"report": _safe(meta), "sections": _safe(sections_payload)}
    return context


def _build_report_context_for_market(report: models.Report, market: str | None) -> dict:
    """Build report context for a specific market.

    This is a specialized version of _build_report_context that overrides
    the defined_markets to include only the specified market, ensuring
    the PPT generation focuses on a single market.

    Additionally extracts market-specific hero_fields if the report has
    the new multi-market structure.

    Args:
        report: The Report model instance
        market: Single market identifier to include in the context

    Returns:
        dict: Report context with single market and market-specific hero_fields
    """
    # Build the full context first
    context = _build_report_context(report)

    # Override the defined_markets to include only the specified market
    if isinstance(context.get("report"), dict):
        context["report"]["defined_markets"] = [market]

        # Extract market-specific hero_fields if multi-market structure is present
        hero_fields = context["report"].get("hero_fields")
        if hero_fields and isinstance(hero_fields, dict):
            # Detect if this is the new multi-market structure
            # New structure: {"Denver": {"stats": {...}}, "NYC": {"stats": {...}}}
            # Old structure: {"stats": {...}}
            is_multi_market_structure = False
            for key, value in hero_fields.items():
                if isinstance(value, dict) and "stats" in value:
                    is_multi_market_structure = True
                    break

            if is_multi_market_structure:
                # Extract only this market's data
                market_hero_fields = hero_fields.get(market, {})
                context["report"]["hero_fields"] = _merge_ppt_data(
                    hero_fields, market_hero_fields
                )
                log.info(
                    "_build_report_context_for_market: Extracted hero_fields for market %s",
                    market,
                )
            # else: keep the old structure as-is for backward compatibility

    return context


def _build_report_context_for_geography(
    report: models.Report,
    market: str | None,
    geo_item: str | None,
    geo_level: str | None,
) -> dict:
    """Build report context for a specific market and geography combination.

    This extends _build_report_context_for_market to also set specific geography
    parameters (vacancy_index, submarket, district) for multi-geography reports.
    Also extracts geography-specific hero_fields using the display name as key.

    Args:
        report: The Report model instance
        market: Single market identifier
        geo_item: Specific geography item (e.g., "Downtown") or None
        geo_level: Geography level ("Vacancy Index", "Submarket", "District") or None

    Returns:
        dict: Report context with single market, geography item, and geography-specific hero_fields
    """
    # Start with base context (not market-specific to avoid double extraction)
    context = _build_report_context(report)

    if isinstance(context.get("report"), dict):
        # Override defined_markets with single market
        context["report"]["defined_markets"] = [market] if market else []

        # Reset all geography parameters
        context["report"]["vacancy_index"] = []
        context["report"]["submarket"] = []
        context["report"]["district"] = []

        # Set only the specific geography if provided
        if geo_item and geo_level:
            if geo_level == "Vacancy Index":
                context["report"]["vacancy_index"] = [geo_item]
            elif geo_level == "Submarket":
                context["report"]["submarket"] = [geo_item]
            elif geo_level == "District":
                context["report"]["district"] = [geo_item]

            log.info(
                "_build_report_context_for_geography: Set %s=%s for market %s",
                geo_level,
                geo_item,
                market,
            )

        # Store current geography info for filename generation
        context["report"]["current_geography_item"] = geo_item
        context["report"]["current_geography_level"] = geo_level

        # Extract geography-specific hero_fields
        # For multi-geography reports, hero_fields is keyed by display name (e.g., "Denver-Downtown")
        hero_fields = context["report"].get("hero_fields")
        if hero_fields and isinstance(hero_fields, dict):
            display_name = _build_geography_display_name(market, geo_item, geo_level)

            # Check if this is a multi-geography structure (keys are display names)
            if display_name in hero_fields:
                geo_hero_fields = hero_fields.get(display_name, {})
                context["report"]["hero_fields"] = _merge_ppt_data(
                    hero_fields, geo_hero_fields
                )
                log.info(
                    "_build_report_context_for_geography: Extracted hero_fields for %s",
                    display_name,
                )
            elif market and market in hero_fields:
                # Fallback to market-only key (for backwards compatibility)
                market_hero_fields = hero_fields.get(market, {})
                context["report"]["hero_fields"] = _merge_ppt_data(
                    hero_fields, market_hero_fields
                )
                log.info(
                    "_build_report_context_for_geography: Fallback to market hero_fields for %s",
                    market,
                )
            # else: keep the original structure

    return context


def _dummy_chart_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "X": ["Q1", "Q2", "Q3", "Q4"],
            "Series A": [10, 12, 9, 14],
            "Series B": [7, 9, 11, 8],
        }
    )


def _dummy_table_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Metric": ["Vacancy", "Absorption", "Leasing"],
            "Current": ["21.2%", "50,328", "542,721"],
            "Prior": ["22.1%", "-148,717", "560,498"],
        }
    )


def _extract_commentary(elements: list[models.ReportSectionElement]) -> str:
    """Return commentary strictly from section_commentary column.

    We intentionally do not fall back to prompt_text or template prompt bodies,
    per the requirement that the PPT should display the saved final commentary.
    """
    for el in elements:
        if (el.element_type or "").lower() == "commentary":
            sc = getattr(el, "section_commentary", None)
            text = (sc or "").strip()
            if text:
                return text
    return ""


def _extract_sql(el: models.ReportSectionElement) -> str:
    cfg = el.config or {}
    if isinstance(cfg, dict):
        sql = cfg.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    return "-- SQL not provided"


def _map_sections_to_ppt_items(report: models.Report) -> list[dict[str, Any]]:
    sections_payload: list[dict[str, Any]] = []
    for sec in sorted(report.sections or [], key=lambda s: s.display_order or 0):
        if sec.selected is False:
            continue
        items: list[dict[str, Any]] = []
        # Stable order of elements
        for el in sorted(sec.elements or [], key=lambda e: e.display_order or 0):
            et = (el.element_type or "").lower()
            if et == "chart":
                df = _dummy_chart_df()
                # Try to honor axis columns from config if present
                x_col = "X"
                y_cols = [c for c in df.columns if c != x_col]
                items.append(
                    {
                        "kind": "chart",
                        "title": el.label or "Chart",
                        "df": df,
                        "x": x_col,
                        "ys": y_cols,
                        "type": (
                            (el.config or {}).get("chart_type")
                            if isinstance(el.config, dict)
                            else None
                        )
                        or "line_markers",
                    }
                )
                items.append(
                    {
                        "kind": "code",
                        "title": "Chart SQL",
                        "text": _extract_sql(el),
                    }
                )
            elif et == "table":
                df = _dummy_table_df()
                items.append(
                    {
                        "kind": "table",
                        "title": el.label or "Table",
                        "df": df,
                    }
                )
                items.append(
                    {
                        "kind": "code",
                        "title": "Table SQL",
                        "text": _extract_sql(el),
                    }
                )
            elif et == "commentary":
                # commentary is rendered on the title slide for the section
                pass

        commentary = _extract_commentary(list(sec.elements or []))
        sections_payload.append(
            {
                "name": sec.name or sec.key or "Section",
                "commentary": commentary or "",
                "items": items,
            }
        )
    return sections_payload


async def generate_ppt_bytes_for_report(session: AsyncSession, report_id: int) -> bytes:
    log.info("generate_ppt_bytes_for_report report_id=%s", report_id)
    report = await _load_report(session, report_id)
    if not report:
        raise ValueError("Report not found")
    context = _build_report_context(report)
    # Print happens inside the PPT builder adapter; it will log the full dict.
    return build_report_ppt_from_context(context, report)


def _extract_commentary_elements(report_sections: list[dict]) -> dict[str, dict]:
    """Extract commentary elements and their configuration from report sections."""
    section_commentary_data = {}

    for section in report_sections:
        elements = section.get("elements", [])
        for el in elements:
            if el.get("element_type") == "commentary":
                section_name = section["name"]
                config = el.get("config", {})

                section_commentary_data[section_name] = {
                    "commentary_sql_list": config.get("sql_list", [])
                    if isinstance(config.get("sql_list"), list)
                    else [],
                    "adjust_prompt": config.get("adjust_prompt")
                    if isinstance(config.get("adjust_prompt"), str)
                    else None,
                    "commentary_prompt_list": config.get("prompt_list", [])
                    if isinstance(config.get("prompt_list"), list)
                    else [],
                    "feedback_list": el.get("feedback_prompt", None),
                    "commentary_data": [],
                }
                break  # Only process first commentary element per section

    return section_commentary_data


def _render_sql_templates(section_commentary_data: dict, report_params: dict) -> None:
    """Render SQL templates with report parameters."""
    payload = {
        "report_parameters": report_params,
        "section": {
            "property_sub_type": report_params.get("property_sub_type", "Figures")
        },
    }

    for section_name, section_data in section_commentary_data.items():
        section_data["commentary_sql_list"] = [
            render_sql_template(sql_template, payload)
            for sql_template in section_data["commentary_sql_list"]
        ]


async def _fetch_commentary_data(section_commentary_data: dict) -> None:
    """Fetch data from Snowflake for all commentary sections."""
    for section_name, section_data in section_commentary_data.items():
        commentary_results = []
        for sql in section_data["commentary_sql_list"]:
            try:
                data = await asyncio.to_thread(fetch_snowflake_data, sql)
                commentary_results.append(json.dumps(data, indent=2))
            except Exception as e:
                log.error(f"Failed to fetch data for section {section_name}, query: {sql}, error: {e}")
                commentary_results = []
                break
        section_data["commentary_data"] = commentary_results


def _build_section_requests(section_commentary_data: dict) -> list[SectionRequest]:
    """Build SectionRequest objects for LLM processing."""
    sections = []

    for section_name, section_data in section_commentary_data.items():
        if not section_data["commentary_data"]:
            continue
        user_feedback = section_data.get("feedback_list")
        consolidation_prompt = section_data.get("adjust_prompt", "")
        sql_prompts = section_data.get("commentary_prompt_list", [])
        data_list = section_data["commentary_data"]

        prompt_obj = {
            "consolidation_prompt": consolidation_prompt,
            "sql_prompts": sql_prompts,
        }

        section_request = SectionRequest(
            section_id=section_name,
            section_name=section_name,
            session_type=section_name,
            input_data=data_list,
            prompt=prompt_obj,
            feedback=json.dumps(user_feedback, indent=2) if user_feedback else None,
        )
        sections.append(section_request)

    return sections


def _update_sections_with_commentary(
    report_sections: list[dict], llm_results: dict
) -> None:
    """Update report sections with generated commentary."""
    for section in report_sections:
        section_name = section["name"]
        elements = section.get("elements", [])
        for element in elements:
            if element.get("element_type") == "commentary":
                config = element.get("config", {})
                if section_name in llm_results:
                    result = llm_results[section_name]
                    final_text = getattr(result, "summary_result", "")
                    if hasattr(result, "error") and result.error:
                        # section["commentary"] = "Agent couldn't generate the commentary, Please try again..."
                        # config["commentary_json"] = "Agent couldn't generate the commentary, Please try again..."
                        section["commentary"] = "Need Human Review:\n\n" + final_text
                        config["commentary_json"] = (
                            "Need Human Review:\n\n" + final_text
                        )
                    else:
                        section["commentary"] = final_text
                        config["commentary_json"] = final_text
                element["config"] = config


def _extract_chart_table_elements(report_sections: list[dict]) -> dict[str, dict]:
    """Extract chart and table elements with their SQL queries from report sections.

    Returns:
        Dictionary mapping element_id to element data with SQL and metadata
    """
    chart_table_data = {}

    for section in report_sections:
        section_name = section.get("name", "")
        elements = section.get("elements", [])

        for el in elements:
            element_type = el.get("element_type", "").lower()
            if element_type in {"chart", "table"}:
                element_id = str(el.get("id", ""))
                config = el.get("config", {})
                sql = config.get("sql", "").strip() if isinstance(config, dict) else ""

                if sql:
                    chart_table_data[element_id] = {
                        "element_type": element_type,
                        "section_name": section_name,
                        "element": el,
                        "sql_template": sql,
                        "sql": None,  # Will be populated after rendering
                        "data": None,  # Will be populated after fetching
                    }
                else:
                    log.warning(
                        "Element %s (type=%s) in section '%s' has no SQL query",
                        element_id,
                        element_type,
                        section_name,
                    )

    return chart_table_data


def _render_chart_table_sql_templates(
    chart_table_data: dict, report_params: dict
) -> None:
    """Render SQL templates for charts and tables with report parameters."""
    payload = {
        "report_parameters": report_params,
        "section": {
            "property_sub_type": report_params.get("property_sub_type", "Figures")
        },
    }

    for element_id, element_data in chart_table_data.items():
        try:
            sql_template = element_data["sql_template"]
            rendered_sql = render_sql_template(sql_template, payload)
            element_data["sql"] = rendered_sql
            log.debug(
                "Rendered SQL for element %s (%s): %s...",
                element_id,
                element_data["element_type"],
                rendered_sql[:100],
            )
        except Exception as e:
            log.error("Failed to render SQL template for element %s: %s", element_id, e)
            element_data["sql"] = None


async def _fetch_chart_table_data(chart_table_data: dict) -> None:
    """Fetch data from Snowflake for all chart and table elements."""
    for element_id, element_data in chart_table_data.items():
        sql = element_data.get("sql")
        if not sql:
            log.warning("No SQL query for element %s, skipping data fetch", element_id)
            continue

        try:
            log.info(
                "Fetching %s data for element %s in section '%s'",
                element_data["element_type"],
                element_id,
                element_data["section_name"],
            )
            data = await asyncio.to_thread(fetch_snowflake_data, sql)
            element_data["data"] = data
            log.info(
                "Successfully fetched %d rows for element %s",
                len(data) if data else 0,
                element_id,
            )
        except Exception as e:
            log.error(
                "Failed to fetch data from Snowflake for element %s: %s", element_id, e
            )
            element_data["data"] = []


def _generate_source_text(
    quarter: str | None, existing_source: str | None = None
) -> str:
    """Generate source text with quarter information.

    Args:
        quarter: Quarter string like "2025 Q1" or "Q1 2025"
        existing_source: User-provided source text (if any)

    Returns:
        Source text like "Source: CBRE Research, Q1 2025" or "Source: <user source>, Q1 2025"
    """
    # Use user-provided source if it exists and is not empty
    if existing_source and isinstance(existing_source, str) and existing_source.strip():
        user_source = existing_source.strip()
        # Ensure "Source: " prefix is always present
        if user_source.lower().startswith("source:"):
            base_source = user_source
        else:
            base_source = f"Source: {user_source}"
    else:
        # Default source
        base_source = "Source: CBRE Research"

    # Add quarter if available
    if quarter and isinstance(quarter, str) and quarter.strip():
        # Flip quarter to "Q1 2025" format if needed
        parts = quarter.strip().split()
        if len(parts) == 2:
            # If format is "2025 Q1", flip to "Q1 2025"
            if parts[0].isdigit() and parts[1].upper().startswith("Q"):
                flipped_quarter = f"{parts[1]} {parts[0]}"
                return f"{base_source}, {flipped_quarter}"
            # If format is already "Q1 2025", use as is
            elif parts[0].upper().startswith("Q") and parts[1].isdigit():
                return f"{base_source}, {quarter.strip()}"
            else:
                return f"{base_source}, {quarter.strip()}"
        else:
            return f"{base_source}, {quarter.strip()}"

    return base_source


def _strip_quarter_from_source(source: str) -> str:
    """Strip any existing quarter from the source text.

    Removes patterns like ", Q1 2025" or ", 2025 Q1" from the end of source text.

    Args:
        source: Source text that may contain a quarter

    Returns:
        Source text without the quarter suffix
    """
    if not source:
        return source
    # Pattern to match quarter suffixes like ", Q1 2025" or ", 2025 Q1"
    quarter_pattern = r",\s*(Q[1-4]\s+\d{4}|\d{4}\s+Q[1-4])\s*$"
    return re.sub(quarter_pattern, "", source, flags=re.IGNORECASE).strip()


def _update_source_text_for_quarter(
    report_sections: list[dict], quarter: str | None = None
) -> None:
    """Update chart/table source text with the correct quarter (without fetching data).

    This is a lightweight function to just update the source text for attended reports
    where we don't need to refresh data from Snowflake, but need to update the quarter
    in the source attribution (especially for dynamic quarter).

    Args:
        report_sections: List of report sections
        quarter: Quarter string for source attribution
    """
    for section in report_sections:
        elements = section.get("elements", [])

        for element in elements:
            element_type = element.get("element_type", "").lower()
            config = element.get("config", {})

            if not isinstance(config, dict):
                continue

            if element_type == "chart":
                # Get existing source (user-provided or empty)
                existing_source = (
                    config.get("chart_source")
                    or config.get("figure_source")
                    or config.get("source")
                    or ""
                )
                # Strip any existing quarter from the source before adding the new one
                existing_source = _strip_quarter_from_source(existing_source)
                # Generate source text with the new quarter
                source_text = _generate_source_text(quarter, existing_source)
                config["chart_source"] = source_text
                config["figure_source"] = source_text
                element["config"] = config
            elif element_type == "table":
                # Get existing source (user-provided or empty)
                existing_source = config.get("table_source") or config.get("source", "")
                # Strip any existing quarter from the source before adding the new one
                existing_source = _strip_quarter_from_source(existing_source)
                # Generate source text with the new quarter
                source_text = _generate_source_text(quarter, existing_source)
                config["table_source"] = source_text
                element["config"] = config


def _update_sections_with_chart_table_data(
    report_sections: list[dict], chart_table_data: dict, quarter: str | None = None
) -> None:
    """Update report sections with fetched chart and table data.

    Args:
        report_sections: List of report sections
        chart_table_data: Dictionary of fetched data
        quarter: Quarter string for source attribution
    """
    for section in report_sections:
        elements = section.get("elements", [])

        for element in elements:
            element_id = str(element.get("id", ""))
            element_type = element.get("element_type", "").lower()

            if element_id in chart_table_data:
                data = chart_table_data[element_id]["data"]
                config = element.get("config", {})

                if not isinstance(config, dict):
                    config = {}

                # Update the config with fresh data
                if element_type == "chart":
                    # Get existing source (user-provided or empty)
                    existing_source = (
                        config.get("chart_source")
                        or config.get("figure_source")
                        or config.get("source")
                        or ""
                    )
                    # Generate source text (respects user's source if provided)
                    source_text = _generate_source_text(quarter, existing_source)

                    config["chart_data"] = data
                    config["chart_source"] = source_text
                    config["figure_source"] = source_text
                    log.info(
                        "Updated chart_data for element %s with %d rows (source: %s)",
                        element_id,
                        len(data) if data else 0,
                        source_text,
                    )
                elif element_type == "table":
                    # Get existing source (user-provided or empty)
                    existing_source = config.get("table_source") or config.get(
                        "source", ""
                    )
                    # Generate source text (respects user's source if provided)
                    source_text = _generate_source_text(quarter, existing_source)

                    config["table_data"] = data
                    config["table_source"] = source_text
                    log.info(
                        "Updated table_data for element %s with %d rows (source: %s)",
                        element_id,
                        len(data) if data else 0,
                        source_text,
                    )

                element["config"] = config


async def _generate_tier1_commentary(
    report_params: dict, report_sections: list[dict]
) -> dict:
    """Generate commentary for tier1 automation mode and refresh chart/table data."""

    # Extract commentary elements
    section_commentary_data = _extract_commentary_elements(report_sections)

    # Extract chart and table elements
    chart_table_data = _extract_chart_table_elements(report_sections)
    log.info(
        "Report ID %s: Found %d chart/table elements to refresh",
        report_params.get("id"),
        len(chart_table_data),
    )

    # Process commentary if available
    if section_commentary_data:
        try:
            log.info(
                "Forming commentary SQLs for report ID %s", report_params.get("id")
            )
            _render_sql_templates(section_commentary_data, report_params)
        except Exception as e:
            log.error("Error while forming commentary SQLs: %s", e)
            raise ValueError(f"Failed to render SQL templates: {e}") from e

        try:
            log.info(
                "Fetching commentary data from snowflake for report ID %s",
                report_params.get("id"),
            )
            await _fetch_commentary_data(section_commentary_data)
        except Exception as e:
            log.error("Error while fetching commentary data from snowflake: %s", e)
            raise ValueError(
                f"Failed to fetch commentary data from Snowflake: {e}"
            ) from e

        try:
            log.info(
                "Generating commentary text for report ID %s", report_params.get("id")
            )
            sections = _build_section_requests(section_commentary_data)
            results = await generate_section_llm(sections)
        except Exception as e:
            log.error("Error while generating commentary text: %s", e)
            raise ValueError(f"Failed to generate commentary text: {e}") from e

        _update_sections_with_commentary(report_sections, results)

    # Process chart and table data refresh
    if chart_table_data:
        try:
            log.info(
                "Rendering chart/table SQLs for report ID %s", report_params.get("id")
            )
            _render_chart_table_sql_templates(chart_table_data, report_params)
        except Exception as e:
            log.error("Error while rendering chart/table SQLs: %s", e)
            raise ValueError(f"Failed to render chart/table SQL templates: {e}") from e

        try:
            log.info(
                "Fetching chart/table data from snowflake for report ID %s",
                report_params.get("id"),
            )
            await _fetch_chart_table_data(chart_table_data)
        except Exception as e:
            log.error("Error while fetching chart/table data from snowflake: %s", e)
            raise ValueError(
                f"Failed to fetch chart/table data from Snowflake: {e}"
            ) from e

        log.info(
            "Updating sections with fresh chart/table data for report ID %s",
            report_params.get("id"),
        )
        quarter = report_params.get("quarter")
        _update_sections_with_chart_table_data(
            report_sections, chart_table_data, quarter
        )

    return {"report": report_params, "sections": report_sections}


async def _refresh_chart_table_data(
    report_params: dict, report_sections: list[dict]
) -> None:
    """Refresh chart and table data from Snowflake for all sections.

    This is a standalone function that can be called independently of commentary generation.
    """
    chart_table_data = _extract_chart_table_elements(report_sections)

    if not chart_table_data:
        log.info(
            "No chart/table elements found to refresh for report ID %s",
            report_params.get("id"),
        )
        return

    log.info(
        "Report ID %s: Found %d chart/table elements to refresh",
        report_params.get("id"),
        len(chart_table_data),
    )

    try:
        log.info("Rendering chart/table SQLs for report ID %s", report_params.get("id"))
        _render_chart_table_sql_templates(chart_table_data, report_params)
    except Exception as e:
        log.error("Error while rendering chart/table SQLs: %s", e)
        raise ValueError(f"Failed to render chart/table SQL templates: {e}") from e

    try:
        log.info(
            "Fetching chart/table data from snowflake for report ID %s",
            report_params.get("id"),
        )
        await _fetch_chart_table_data(chart_table_data)
    except Exception as e:
        log.error("Error while fetching chart/table data from snowflake: %s", e)
        raise ValueError(f"Failed to fetch chart/table data from Snowflake: {e}") from e

    log.info(
        "Updating sections with fresh chart/table data for report ID %s",
        report_params.get("id"),
    )
    quarter = report_params.get("quarter")
    _update_sections_with_chart_table_data(report_sections, chart_table_data, quarter)


async def _generate_tier3_commentary(
    report_params: dict, report_sections: list[dict]
) -> dict:
    """Generate commentary for tier3 automation mode and refresh chart/table data."""

    # Generate tier3 commentary
    for section in report_sections:
        normalized_section_name = section["sectionname_alias"].replace(" ", "_").lower()
        elements = section.get("elements", [])

        # Find commentary element
        for element in elements:
            if element.get("element_type") == "commentary":
                commentary = ""
                config = element.get("config")
                try:
                    if env == "CBRE":
                        response = generate_market_narrative(
                            report_params, paragraph_keys=[normalized_section_name]
                        )
                        commentary = response.get(normalized_section_name, "")
                    else:
                        commentary = f"Tier 3 commentary for {section['name']}"
                except Exception as e:
                    log.error(
                        "Error generating tier3 commentary for section %s: %s",
                        section["name"],
                        e,
                    )
                    commentary = "Failed to generate commentary. Please try again."
                finally:
                    section["commentary"] = commentary
                    element["section_commentary"] = commentary
                    if config:
                        config["commentary_json"] = commentary
                        if "commentary_text" in config:
                            config.pop("commentary_text", None)
                    element["config"] = config
                break

    # Refresh chart and table data (same as tier1)
    await _refresh_chart_table_data(report_params, report_sections)

    return {"report": report_params, "sections": report_sections}


async def generate_commentary_for_report(report: dict) -> dict:
    """Generate commentary for all sections in the report.

    Args:
        report: Dictionary containing report parameters and sections

    Returns:
        Updated report dictionary with commentary added to sections

    Raises:
        ValueError: If automation mode is invalid or if commentary generation fails
    """
    report_params = report["report"]
    report_sections = report["sections"]
    automation_mode = report_params.get("automation_mode", "").lower()

    if automation_mode == "tier1":
        log.info(
            "Generating tier1 commentary for report ID %s", report_params.get("id")
        )
        return await _generate_tier1_commentary(report_params, report_sections)
    elif automation_mode == "tier3":
        log.info(
            "Generating tier3 commentary for report ID %s", report_params.get("id")
        )
        return await _generate_tier3_commentary(report_params, report_sections)
    else:
        log.error("Invalid automation mode: %s", automation_mode)
        raise ValueError(f"Invalid automation mode: {automation_mode}")


async def generate_report_ppt_only(
    session: AsyncSession,
    report_id: int,
    trigger_source: str = "manual",
    *,
    created_by: int | None = None,
) -> dict[str, Any]:
    """Generate PPT for a report and upload to S3, creating ReportRun entries for tracking.

    This is used by PATCH endpoints when a report is edited. Creates individual ReportRun
    entries for each market, just like run_report_now().

    Returns:
        dict with keys: ppt_url (list), s3_path (list), all_ppt_urls (list),
        all_s3_paths (list), market_ppt_mapping (dict), all_run_ids (list), elapsed_seconds
    """
    start = time.time()

    log.info(
        "generate_report_ppt_only: Starting PPT generation - report_id=%s, "
        "trigger_source=%s, created_by=%s",
        report_id,
        trigger_source,
        created_by,
    )

    report = await _load_report(session, report_id)
    if not report:
        log.error(
            "generate_report_ppt_only: Report not found - report_id=%s", report_id
        )
        raise ValueError("Report not found")

    selected_sections = [
        (s.name or s.key)
        for s in sorted(report.sections or [], key=lambda x: x.display_order or 0)
        if getattr(s, "selected", True)
    ]

    # Get list of markets to generate PPTs for
    markets_to_generate = report.defined_markets or []
    if not markets_to_generate:
        log.warning("Report %s has no defined markets, cannot generate PPTs", report_id)
        raise ValueError("No markets defined for report")

    # Check if this is a multi-geography property sub type
    is_multi_geography = _is_multi_geography_property_sub_type(report.property_sub_type)

    # Build items to process based on property sub type
    if is_multi_geography:
        # Build report params dict for geography processing
        report_params_for_geo = {
            "defined_markets": list(markets_to_generate),
            "property_sub_type": report.property_sub_type,
            "vacancy_index": list(report.vacancy_index or []),
            "submarket": list(report.submarket or []),
            "district": list(report.district or []),
        }
        items_to_process = _build_items_to_process(report_params_for_geo)
        log.info(
            "Multi-geography report %s: processing %d geography combinations",
            report_id,
            len(items_to_process),
        )
    else:
        # Regular report - one item per market
        items_to_process = [(market, None, None) for market in markets_to_generate]

    # Store PPT info for each item
    all_s3_paths = []
    all_ppt_urls = []
    market_ppt_mapping = {}
    all_run_ids = []
    market_ppt_info = []
    run_state_updates: dict[int, str] = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Generate a PPT for each item (market or market+geography combination)
        for idx, (current_market, geo_item, geo_level) in enumerate(
            items_to_process, 1
        ):
            item_start = time.time()
            display_name = _build_geography_display_name(
                current_market, geo_item, geo_level
            )
            log.info(
                "Generating PPT for report %s, item %d/%d: %s",
                report_id,
                idx,
                len(items_to_process),
                display_name,
            )

            # Create a ReportRun entry for this item (for PATCH/edit tracking)
            item_run = models.ReportRun(
                report_id=report.id,
                schedule_id=None,
                trigger_source=trigger_source,
                run_time_seconds=None,
                report_name=report.name,
                report_type=report.report_type or report.template_name,
                market=display_name,  # Use display name for multi-geography
                sections={"selected": selected_sections},
                status="Pending",
                run_state="running",
                output_format="ppt",
                email_status=None,
                created_by=created_by,
            )

            session.add(item_run)
            await session.flush()
            item_run_id = item_run.id
            all_run_ids.append(item_run_id)
            await session.commit()

            try:
                # Build context based on whether this is multi-geography or not
                if is_multi_geography:
                    item_context = _build_report_context_for_geography(
                        report, current_market, geo_item, geo_level
                    )
                else:
                    item_context = _build_report_context_for_market(
                        report, current_market
                    )

                # Generate commentary only for unattended (tier-3) reports
                # Note: submarket property_sub_type doesn't have commentary element
                unattended_types = {"tier3", "unattended"}
                if (
                    report.automation_mode
                    and report.automation_mode.lower() in unattended_types
                ):
                    item_context = await generate_commentary_for_report(item_context)
                else:
                    # For attended (tier1) reports, just update the source text with the correct quarter
                    # (especially for dynamic quarter) without re-fetching data from Snowflake
                    report_params = item_context.get("report", {})
                    report_sections = item_context.get("sections", [])
                    quarter = report_params.get("quarter")
                    _update_source_text_for_quarter(report_sections, quarter)

                item_context_json = json.dumps(
                    item_context, indent=2, ensure_ascii=False, default=str
                )
                log.debug("Report context for %s: %s", display_name, item_context_json)

                # Generate PPT with item-specific filename
                file_info = await generate_presentation(item_context)
                file_path = file_info.get("file_path")
                if not file_path:
                    raise ValueError(f"PPT not found for {display_name}")

                # Create item-specific filename
                safe_report_name = report.name.replace(" ", "_").replace("/", "-")
                safe_display_name = display_name.replace(" ", "_").replace("/", "-")
                item_filename = (
                    f"{safe_report_name}_{safe_display_name}_{timestamp}.pptx"
                )

                # Upload to S3 with item-specific filename
                with open(file_path, "rb") as ppt:
                    ppt_bytes = ppt.read()
                    s3_path = await save_report_to_s3(
                        content=ppt_bytes,
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        filename=item_filename,
                    )

                # Generate presigned URL using run_id (for frontend API)
                ppt_url = build_ppt_download_url(run_id=str(item_run_id))

                # Generate direct presigned S3 URL for email (7 days expiration)
                s3_key = _extract_s3_key(s3_path)
                ppt_url_email = await generate_presigned_url_for_key(
                    key=s3_key, expires_in=7 * 24 * 60 * 60
                )

                # Build display name for this PPT
                ppt_display_name = f"{report.name}-{display_name}"

                # Store the paths and URLs in new format
                all_s3_paths.append(s3_path)
                all_ppt_urls.append({"name": ppt_display_name, "ppt_url": ppt_url})
                market_ppt_mapping[display_name] = ppt_url

                # Store item info with both URLs
                market_ppt_info.append(
                    {
                        "market": display_name,
                        "geography_item": geo_item,
                        "geography_level": geo_level,
                        "s3_path": s3_path,
                        "ppt_url": ppt_url_email if ppt_url_email else ppt_url,
                        "run_id": item_run_id,
                        "status": "Success",
                    }
                )

                item_elapsed = int(time.time() - item_start)

                # Update this item's ReportRun as successful
                run_state_updates[item_run_id] = "completed"
                await session.execute(
                    update(models.ReportRun)
                    .where(models.ReportRun.id == item_run_id)
                    .where(models.ReportRun.run_state != "aborted")
                    .values(
                        status="Success",
                        run_state="completed",
                        run_time_seconds=item_elapsed,
                        s3_path=s3_path,
                        ppt_url=ppt_url,
                        email_status="Success",
                    )
                )
                await session.commit()
                run_state_updates.pop(item_run_id, None)

                log.info(
                    "Generated PPT for %s: %s (run_id=%s)",
                    display_name,
                    s3_path,
                    item_run_id,
                )

            except Exception as item_err:
                # Mark this specific item run as failed
                item_elapsed = int(time.time() - item_start)
                run_state_updates[item_run_id] = "failed"
                await session.execute(
                    update(models.ReportRun)
                    .where(models.ReportRun.id == item_run_id)
                    .where(models.ReportRun.run_state != "aborted")
                    .values(
                        status="Failed",
                        run_state="failed",
                        run_time_seconds=item_elapsed,
                        s3_path=None,
                        ppt_url=None,
                        email_status="Failed",
                    )
                )
                await session.commit()
                run_state_updates.pop(item_run_id, None)
                log.error(
                    "Failed to generate PPT for %s: %s", display_name, str(item_err)
                )

                # Track failed item
                market_ppt_info.append(
                    {
                        "market": display_name,
                        "geography_item": geo_item,
                        "geography_level": geo_level,
                        "s3_path": None,
                        "ppt_url": None,
                        "run_id": item_run_id,
                        "status": "Failed",
                    }
                )

                continue

        elapsed = int(time.time() - start)

        # Calculate success/failure statistics
        failed_items = [
            info["market"] for info in market_ppt_info if info.get("status") == "Failed"
        ]
        successful_items = [
            info["market"]
            for info in market_ppt_info
            if info.get("status") == "Success"
        ]
        has_failures = len(failed_items) > 0

        log.info(
            "Generated PPTs for report %s (PATCH): %d successful, %d failed. Items: %s",
            report_id,
            len(successful_items),
            len(failed_items),
            ", ".join(successful_items)
            + (f" | FAILED: {', '.join(failed_items)}" if failed_items else ""),
        )

        await _ensure_terminal_run_states(
            session,
            run_state_updates,
            all_run_ids,
            context=f"report_id={report_id} generate_report_ppt_only",
        )
        return {
            "ppt_url": all_ppt_urls,
            "s3_path": all_s3_paths,
            "all_ppt_urls": all_ppt_urls,
            "all_s3_paths": all_s3_paths,
            "market_ppt_mapping": market_ppt_mapping,
            "market_ppt_info": market_ppt_info,
            "all_run_ids": all_run_ids,
            "elapsed_seconds": elapsed,
            "has_failures": has_failures,
            "failed_markets": failed_items,
        }
    except Exception as err:
        elapsed = int(time.time() - start)
        log.error(
            "Complete failure in generate_report_ppt_only for report %s: %s",
            report_id,
            str(err),
        )
        try:
            if session.in_transaction():
                await session.rollback()
        except Exception as rollback_err:
            log.warning(
                "generate_report_ppt_only rollback failed before run_state sync: %s",
                rollback_err,
            )

        await _ensure_terminal_run_states(
            session,
            run_state_updates,
            all_run_ids,
            default_state="failed",
            context=f"report_id={report_id} generate_report_ppt_only",
        )
        # Return structured error info
        failed_display_names = [
            _build_geography_display_name(m, g, lvl) for m, g, lvl in items_to_process
        ]
        return {
            "ppt_url": [],
            "s3_path": [],
            "all_ppt_urls": [],
            "all_s3_paths": [],
            "market_ppt_mapping": {},
            "market_ppt_info": [],
            "all_run_ids": [],
            "elapsed_seconds": elapsed,
            "has_failures": True,
            "failed_markets": failed_display_names,
            "error": "Report generation failed",
        }


async def run_report_now(
    session: AsyncSession,
    report_id: int,
    *,
    trigger_source: str = "manual",
    schedule_id: int | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    """Generate PPT for a report, upload to S3, and keep run_state in sync for the UI."""
    start = time.time()

    log.info(
        "run_report_now: Starting report generation - report_id=%s, trigger_source=%s, "
        "schedule_id=%s, created_by=%s",
        report_id,
        trigger_source,
        schedule_id,
        created_by,
    )

    report = await _load_report(session, report_id)
    if not report:
        log.error("run_report_now: Report not found - report_id=%s", report_id)
        raise ValueError("Report not found")

    selected_sections = [
        (s.name or s.key)
        for s in sorted(report.sections or [], key=lambda x: x.display_order or 0)
        if getattr(s, "selected", True)
    ]

    # Get list of markets to generate PPTs for
    markets_to_generate = report.defined_markets or []
    if not markets_to_generate:
        log.warning("Report %s has no defined markets, cannot generate PPTs", report_id)
        raise ValueError("No markets defined for report")

    # Check if this is a multi-geography property sub type
    is_multi_geography = _is_multi_geography_property_sub_type(report.property_sub_type)

    # Build items to process based on property sub type
    if is_multi_geography:
        # Build report params dict for geography processing
        report_params_for_geo = {
            "defined_markets": list(markets_to_generate),
            "property_sub_type": report.property_sub_type,
            "vacancy_index": list(report.vacancy_index or []),
            "submarket": list(report.submarket or []),
            "district": list(report.district or []),
        }
        items_to_process = _build_items_to_process(report_params_for_geo)
        log.info(
            "Multi-geography report %s: processing %d geography combinations",
            report_id,
            len(items_to_process),
        )
    else:
        # Regular report - one item per market
        items_to_process = [(market, None, None) for market in markets_to_generate]

    # Store PPT info for each item
    all_s3_paths = []
    all_ppt_urls = []
    market_ppt_mapping = {}
    all_run_ids = []
    market_ppt_info = []  # List of dicts with market, s3_path, ppt_url, run_id
    run_state_updates: dict[int, str] = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Pre-create mapping of item index to (display_name, run_id) for later use
    item_run_mapping: dict[int, tuple[str, int]] = {}

    try:
        # Create all ReportRun entries first (so UI can show them immediately)
        for idx, (current_market, geo_item, geo_level) in enumerate(
            items_to_process, 1
        ):
            display_name = _build_geography_display_name(
                current_market, geo_item, geo_level
            )

            item_run = models.ReportRun(
                report_id=report.id,
                schedule_id=schedule_id,
                trigger_source=trigger_source,
                run_time_seconds=None,
                report_name=report.name,
                report_type=report.report_type or report.template_name,
                market=display_name,
                sections={"selected": selected_sections},
                status="Pending",
                run_state="running",
                output_format="ppt",
                email_status=None,
                created_by=created_by,
            )

            session.add(item_run)
            await session.flush()
            item_run_id = item_run.id
            all_run_ids.append(item_run_id)
            item_run_mapping[idx] = (display_name, item_run_id)

        await session.commit()
        log.info(
            "run_report_now: Created %d ReportRun entries for report %s",
            len(all_run_ids),
            report_id,
        )

        # Fetch fresh hero_fields for all markets before PPT generation
        if report.defined_markets:
            try:
                report_context = _build_report_context(report)
                hero_fields = await asyncio.to_thread(
                    fetch_multi_market_hero_fields,
                    report_meta=report_context.get("report"),
                    property_sub_type=report.property_sub_type,
                    asking_rate_type=report.asking_rate_type,
                    asking_rate_frequency=report.asking_rate_frequency,
                )
                ppt_data = report.hero_fields.get('ppt_data')
                if ppt_data:
                    hero_fields['ppt_data'] = ppt_data
                report.hero_fields = hero_fields
                await session.commit()
                log.info(
                    "run_report_now: Fetched fresh hero_fields for %d markets",
                    len(report.defined_markets),
                )
            except Exception as hero_err:
                log.warning(
                    "run_report_now: Failed to fetch hero_fields: %s", str(hero_err)
                )

        # Generate a PPT for each item (market or market+geography combination)
        for idx, (current_market, geo_item, geo_level) in enumerate(
            items_to_process, 1
        ):
            item_start = time.time()
            display_name, item_run_id = item_run_mapping[idx]
            log.info(
                "Generating PPT for report %s, item %d/%d: %s",
                report_id,
                idx,
                len(items_to_process),
                display_name,
            )

            try:
                # Build context based on whether this is multi-geography or not
                if is_multi_geography:
                    item_context = _build_report_context_for_geography(
                        report, current_market, geo_item, geo_level
                    )
                else:
                    item_context = _build_report_context_for_market(
                        report, current_market
                    )

                # Generate commentary for this item
                # Note: submarket property_sub_type doesn't have commentary element
                item_context = await generate_commentary_for_report(item_context)
                item_context_json = json.dumps(
                    item_context, indent=2, ensure_ascii=False, default=str
                )
                log.info(
                    "Context for %s after commentary generation (json): %s",
                    display_name,
                    item_context_json,
                )

                # Generate PPT with item-specific filename
                file_info = await generate_presentation(item_context)
                file_path = file_info.get("file_path")
                if not file_path:
                    raise ValueError(f"PPT not found for {display_name}")

                # Create item-specific filename
                safe_report_name = report.name.replace(" ", "_").replace("/", "-")
                safe_display_name = display_name.replace(" ", "_").replace("/", "-")
                item_filename = (
                    f"{safe_report_name}_{safe_display_name}_{timestamp}.pptx"
                )

                # Upload to S3 with item-specific filename
                with open(file_path, "rb") as ppt:
                    ppt_bytes = ppt.read()
                    s3_path = await save_report_to_s3(
                        content=ppt_bytes,
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        filename=item_filename,
                    )

                # Generate presigned URL for this item's run (for frontend API)
                ppt_url = build_ppt_download_url(run_id=str(item_run_id))

                # Generate direct presigned S3 URL for email (7 days expiration)
                s3_key = _extract_s3_key(s3_path)
                ppt_url_email = await generate_presigned_url_for_key(
                    key=s3_key, expires_in=7 * 24 * 60 * 60
                )

                # Build display name for this PPT
                ppt_display_name = f"{report.name}-{display_name}"

                # Store the paths and URLs in new format
                all_s3_paths.append(s3_path)
                all_ppt_urls.append({"name": ppt_display_name, "ppt_url": ppt_url})
                market_ppt_mapping[display_name] = ppt_url

                # Store item info for email (use direct S3 URL for email)
                market_ppt_info.append(
                    {
                        "market": display_name,
                        "geography_item": geo_item,
                        "geography_level": geo_level,
                        "s3_path": s3_path,
                        "ppt_url": ppt_url_email if ppt_url_email else ppt_url,
                        "run_id": item_run_id,
                        "status": "Success",
                    }
                )

                item_elapsed = int(time.time() - item_start)

                # Update this item's ReportRun as successful
                run_state_updates[item_run_id] = "completed"
                await session.execute(
                    update(models.ReportRun)
                    .where(models.ReportRun.id == item_run_id)
                    .where(models.ReportRun.run_state != "aborted")
                    .values(
                        status="Success",
                        run_state="completed",
                        run_time_seconds=item_elapsed,
                        s3_path=s3_path,
                        ppt_url=ppt_url,
                        email_status="Success",
                    )
                )
                await session.commit()
                run_state_updates.pop(item_run_id, None)

                log.info(
                    "Generated PPT for %s: %s (run_id=%s)",
                    display_name,
                    s3_path,
                    item_run_id,
                )

            except Exception as item_err:
                # Mark this specific item run as failed
                item_elapsed = int(time.time() - item_start)
                run_state_updates[item_run_id] = "failed"
                await session.execute(
                    update(models.ReportRun)
                    .where(models.ReportRun.id == item_run_id)
                    .where(models.ReportRun.run_state != "aborted")
                    .values(
                        status="Failed",
                        run_state="failed",
                        run_time_seconds=item_elapsed,
                        s3_path=None,
                        ppt_url=None,
                        email_status="Failed",
                    )
                )
                await session.commit()
                run_state_updates.pop(item_run_id, None)
                log.error(
                    "Failed to generate PPT for %s: %s", display_name, str(item_err)
                )

                # Track failed item for email notification
                market_ppt_info.append(
                    {
                        "market": display_name,
                        "geography_item": geo_item,
                        "geography_level": geo_level,
                        "s3_path": None,
                        "ppt_url": None,
                        "run_id": item_run_id,
                        "status": "Failed",
                    }
                )

                # Continue with other items instead of failing completely
                continue

        elapsed = int(time.time() - start)

        # Update the Report model with all PPT URLs and paths
        await session.execute(
            update(models.Report)
            .where(models.Report.id == report_id)
            .values(
                ppt_url=all_ppt_urls,
                s3_path=all_s3_paths,
                market_ppt_mapping=market_ppt_mapping,
            )
        )
        await session.commit()

        # Calculate success/failure statistics
        failed_items = [
            info["market"] for info in market_ppt_info if info.get("status") == "Failed"
        ]
        successful_items = [
            info["market"]
            for info in market_ppt_info
            if info.get("status") == "Success"
        ]
        has_failures = len(failed_items) > 0

        # Determine overall status
        if not successful_items and failed_items:
            overall_status = "Failed"
        elif successful_items and failed_items:
            overall_status = "Partial"
        else:
            overall_status = "Success"

        log.info(
            "Generated PPTs for report %s: %d successful, %d failed. Items: %s",
            report_id,
            len(successful_items),
            len(failed_items),
            ", ".join(successful_items)
            + (f" | FAILED: {', '.join(failed_items)}" if failed_items else ""),
        )

        await _ensure_terminal_run_states(
            session,
            run_state_updates,
            all_run_ids,
            context=f"report_id={report_id} run_report_now",
        )
        return {
            "s3_path": all_s3_paths[0]
            if all_s3_paths
            else None,  # First one for backwards compatibility
            "all_s3_paths": all_s3_paths,
            "elapsed_seconds": elapsed,
            "ppt_url": all_ppt_urls[0]
            if all_ppt_urls
            else None,  # First one for backwards compatibility
            "all_ppt_urls": all_ppt_urls,
            "market_ppt_mapping": market_ppt_mapping,
            "market_ppt_info": market_ppt_info,  # List of item info for email (includes status)
            "run_id": all_run_ids[0]
            if all_run_ids
            else None,  # Return first run_id for backwards compatibility
            "all_run_ids": all_run_ids,
            "email_status": "Success",
            "run_state": "completed" if successful_items else "failed",
            "status": overall_status,
            "has_failures": has_failures,
            "failed_markets": failed_items,
            "schedule_id": schedule_id,
        }
    except Exception as err:
        # If complete failure before any items processed
        elapsed = int(time.time() - start)
        log.error(
            "Complete failure in run_report_now for report %s: %s", report_id, str(err)
        )
        try:
            if session.in_transaction():
                await session.rollback()
        except Exception as rollback_err:
            log.warning(
                "run_report_now rollback failed before run_state sync: %s",
                rollback_err,
            )
        await _ensure_terminal_run_states(
            session,
            run_state_updates,
            all_run_ids,
            default_state="failed",
            context=f"report_id={report_id} run_report_now",
        )

        # Return structured error info so caller can send notifications
        # Use items_to_process if available, otherwise fall back to markets_to_generate
        try:
            failed_display_names = [
                _build_geography_display_name(m, g, lvl)
                for m, g, lvl in items_to_process
            ]
        except NameError:
            failed_display_names = list(markets_to_generate)

        return {
            "s3_path": None,
            "all_s3_paths": [],
            "elapsed_seconds": elapsed,
            "ppt_url": None,
            "all_ppt_urls": [],
            "market_ppt_mapping": {},
            "market_ppt_info": [],
            "run_id": None,
            "all_run_ids": [],
            "email_status": "Failed",
            "run_state": "failed",
            "status": "Failed",
            "has_failures": True,
            "failed_markets": failed_display_names,
            "schedule_id": schedule_id,
            "error": "Report generation failed",
        }
