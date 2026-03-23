from __future__ import annotations

"""
Template-driven PPT builder.

This scaffolds a shape-driven presentation generator that:
 - Loads a .pptx template file
 - Updates named shapes using our shared update utilities
 - Uses the saved report context (sections, elements, commentary, SQL) to bind data

Conventions for default shape names (overrideable via shape_map):
 - section.{i}.title        -> 'section_{i}_title_text'
 - section.{i}.commentary   -> 'section_{i}_commentary_text'
 - section.{i}.chart.{k}    -> 'section_{i}_chart_{k}'
 - section.{i}.chart_sql.{k}-> 'section_{i}_chart_{k}_sql_text'
 - section.{i}.table.{k}    -> 'section_{i}_table_{k}'
 - section.{i}.table_sql.{k}-> 'section_{i}_table_{k}_sql_text'

Designers can name shapes in the PPTX template accordingly, or provide a
custom mapping via `shape_map`.
"""

from io import BytesIO
from typing import Any, Callable, Optional

import pandas as pd
from pptx import Presentation

from hello import models
from hello.services.pptx_update import update_shape


# -----------------------
# Small helpers / dummies
# -----------------------

def _dummy_chart_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Quarter": ["2023 Q1", "2023 Q2", "2023 Q3", "2023 Q4", "2024 Q1", "2024 Q2"],
            "Series A": [10, 12, 9, 14, 16, 18],
            "Series B": [7, 9, 11, 8, 13, 10],
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


def _extract_commentary_text(sec: models.ReportSection) -> str:
    for el in sorted(sec.elements or [], key=lambda e: e.display_order or 0):
        if (el.element_type or "").lower() == "commentary":
            sc = getattr(el, "section_commentary", None)
            return (sc or "").strip()
    return ""


def _shape_for(key: str, shape_map: dict[str, str] | None, default: str) -> str:
    if isinstance(shape_map, dict) and key in shape_map:
        return shape_map[key]
    return default


# -----------------------
# Core builders
# -----------------------

def build_ppt_from_template_with_context(
    template_path: str,
    context: dict,
    *,
    shape_map: dict[str, str] | None = None,
    data_provider: Optional[Callable[[dict], pd.DataFrame]] = None,
) -> bytes:
    """
    Render a PPTX from a template, based on a stable report context dict.

    - template_path: path to a .pptx template file
    - context: dict produced by our report runner (see _build_report_context)
    - shape_map: optional mapping from logical keys to PPT shape names
    - data_provider: optional callback that accepts an element payload dict and
      returns a DataFrame for charts/tables. If not provided, dummy data is used.
    """
    prs = Presentation(template_path)

    sections = context.get("sections") or []

    for i, sec in enumerate(sections, start=1):
        # Title
        title_shape = _shape_for(f"section.{i}.title", shape_map, f"section_{i}_title_text")
        update_shape(prs, title_shape, sec.get("name") or f"Section {i}")

        # Commentary
        commentary = (sec.get("commentary") or "").strip()
        commentary_shape = _shape_for(
            f"section.{i}.commentary", shape_map, f"section_{i}_commentary_text"
        )
        if commentary:
            update_shape(prs, commentary_shape, commentary)

        # Elements (charts / tables) in consistent order
        chart_idx = 0
        table_idx = 0
        elements = sec.get("elements") or []
        for el in sorted(elements, key=lambda e: (e.get("display_order") or 0)):
            et = (el.get("element_type") or "").lower()

            # Resolve data from provider or use dummies
            df: pd.DataFrame | None = None
            if data_provider is not None and et in {"chart", "table"}:
                try:
                    df = data_provider(el)
                except Exception:
                    df = None

            if et == "chart":
                chart_idx += 1
                df = df if isinstance(df, pd.DataFrame) else _dummy_chart_df()
                x_col = df.columns[0]
                chart_shape = _shape_for(
                    f"section.{i}.chart.{chart_idx}", shape_map, f"section_{i}_chart_{chart_idx}"
                )
                update_shape(prs, chart_shape, df, dynamic_y_axis=True)

                # Optional SQL note into a text box
                sql_shape = _shape_for(
                    f"section.{i}.chart_sql.{chart_idx}", shape_map, f"section_{i}_chart_{chart_idx}_sql_text"
                )
                sql_text = el.get("config", {}).get("sql") if isinstance(el.get("config"), dict) else None
                if sql_text:
                    update_shape(prs, sql_shape, str(sql_text))

            elif et == "table":
                table_idx += 1
                df = df if isinstance(df, pd.DataFrame) else _dummy_table_df()
                table_shape = _shape_for(
                    f"section.{i}.table.{table_idx}", shape_map, f"section_{i}_table_{table_idx}"
                )
                update_shape(prs, table_shape, df)

                sql_shape = _shape_for(
                    f"section.{i}.table_sql.{table_idx}", shape_map, f"section_{i}_table_{table_idx}_sql_text"
                )
                sql_text = el.get("config", {}).get("sql") if isinstance(el.get("config"), dict) else None
                if sql_text:
                    update_shape(prs, sql_shape, str(sql_text))

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_report_ppt_from_template(
    report: models.Report,
    template_path: str,
    *,
    shape_map: dict[str, str] | None = None,
    data_provider: Optional[Callable[[models.ReportSectionElement], pd.DataFrame]] = None,
) -> bytes:
    """
    Convenience wrapper building context from a SQLAlchemy `Report` instance.

    - Uses saved commentary from section_commentary fields
    - Binds section titles and optional charts/tables into named shapes
    - Data provider can return DataFrames for each chart/table element
    """
    prs = Presentation(template_path)

    for i, sec in enumerate(sorted(report.sections or [], key=lambda s: s.display_order or 0), start=1):
        if getattr(sec, "selected", True) is False:
            continue

        # Title
        title_shape = _shape_for(f"section.{i}.title", shape_map, f"section_{i}_title_text")
        update_shape(prs, title_shape, sec.name or sec.key or f"Section {i}")

        # Commentary
        commentary = _extract_commentary_text(sec)
        commentary_shape = _shape_for(
            f"section.{i}.commentary", shape_map, f"section_{i}_commentary_text"
        )
        if commentary:
            update_shape(prs, commentary_shape, commentary)

        chart_idx = 0
        table_idx = 0
        for el in sorted(sec.elements or [], key=lambda e: e.display_order or 0):
            et = (el.element_type or "").lower()
            if et == "chart":
                chart_idx += 1
                df = None
                if data_provider is not None:
                    try:
                        df = data_provider(el)
                    except Exception:
                        df = None
                if not isinstance(df, pd.DataFrame):
                    df = _dummy_chart_df()
                chart_shape = _shape_for(
                    f"section.{i}.chart.{chart_idx}", shape_map, f"section_{i}_chart_{chart_idx}"
                )
                update_shape(prs, chart_shape, df, dynamic_y_axis=True)

                # Optional SQL into text shape
                sql_shape = _shape_for(
                    f"section.{i}.chart_sql.{chart_idx}", shape_map, f"section_{i}_chart_{chart_idx}_sql_text"
                )
                sql_text = None
                cfg = el.config if isinstance(el.config, dict) else {}
                if isinstance(cfg, dict):
                    sql_text = cfg.get("sql")
                if sql_text:
                    update_shape(prs, sql_shape, str(sql_text))

            elif et == "table":
                table_idx += 1
                df = None
                if data_provider is not None:
                    try:
                        df = data_provider(el)
                    except Exception:
                        df = None
                if not isinstance(df, pd.DataFrame):
                    df = _dummy_table_df()
                table_shape = _shape_for(
                    f"section.{i}.table.{table_idx}", shape_map, f"section_{i}_table_{table_idx}"
                )
                update_shape(prs, table_shape, df)

                sql_shape = _shape_for(
                    f"section.{i}.table_sql.{table_idx}", shape_map, f"section_{i}_table_{table_idx}_sql_text"
                )
                sql_text = None
                cfg = el.config if isinstance(el.config, dict) else {}
                if isinstance(cfg, dict):
                    sql_text = cfg.get("sql")
                if sql_text:
                    update_shape(prs, sql_shape, str(sql_text))

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()

