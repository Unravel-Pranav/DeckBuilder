"""Formatting utilities used by the PPT generation pipeline."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.config import settings


def format_label(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return s if s else ""


def format_table_cell_value(value: Any, col_name: str = "") -> str:
    if value is None:
        return ""
    s = str(value).strip()
    try:
        num = float(s.replace(",", "").replace("$", "").replace("%", ""))
        if num < 0 and settings.table_negative_number_style == "parentheses":
            abs_val = abs(num)
            if "%" in s:
                return f"({abs_val:.1f}%)"
            elif "$" in s:
                return f"(${abs_val:,.0f})"
            else:
                return f"({abs_val:,.0f})"
    except (ValueError, TypeError):
        pass
    return s


def is_total_label(label: str | None) -> bool:
    if not label:
        return False
    normalized = label.strip()
    if settings.table_total_row_strip_markdown:
        normalized = re.sub(r"\*+", "", normalized).strip()
    if settings.table_total_row_match_case_insensitive:
        return normalized.lower() == settings.table_total_row_label.lower()
    return normalized == settings.table_total_row_label


def total_display_text() -> str:
    return settings.table_total_row_display


def get_latest_complete_quarter() -> str:
    now = datetime.now()
    year, month = now.year, now.month
    if month <= 3:
        return f"{year - 1} Q4"
    elif month <= 6:
        return f"{year} Q1"
    elif month <= 9:
        return f"{year} Q2"
    else:
        return f"{year} Q3"
