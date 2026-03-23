import re
from typing import Any

from hello.services.config import settings
from datetime import datetime

_MULTISPACE_RE = re.compile(r"\s{2,}")
_PLAIN_NUMERIC_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_COMMA_GROUPED_NUMERIC_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")

_WRAPPING_MARKDOWN_EMPHASIS = (
    ("**", "**"),
    ("__", "__"),
    ("*", "*"),
    ("_", "_"),
)


def _strip_wrapping_markdown_emphasis(value: str) -> str:
    """Strip wrapping markdown emphasis markers if they wrap the whole string.

    Examples:
    - "**TOTAL**" -> "TOTAL"
    - "_TOTAL_" -> "TOTAL"
    - "__total__" -> "total"

    This is intentionally conservative: it only strips when the marker wraps the
    entire string (after trimming), and it repeats so nested wrappers are handled
    (e.g., "***TOTAL***").
    """
    s = value.strip()
    if not s:
        return s

    while True:
        changed = False
        for left, right in _WRAPPING_MARKDOWN_EMPHASIS:
            if s.startswith(left) and s.endswith(right) and len(s) > (len(left) + len(right)):
                s = s[len(left) : -len(right)].strip()
                changed = True
        if not changed:
            break
    return s


def normalize_table_label(value: Any, *, strip_markdown: bool) -> str:
    """Normalize a table label for exact comparisons (e.g., TOTAL detection)."""
    s = "" if value is None else str(value)
    s = s.strip()
    if strip_markdown:
        s = _strip_wrapping_markdown_emphasis(s)
    s = _MULTISPACE_RE.sub(" ", s).strip()
    return s


def is_total_label(value: Any) -> bool:
    """Return True if `value` matches the configured TOTAL row label exactly."""
    strip_md = bool(getattr(settings, "table_total_row_strip_markdown", True))
    case_insensitive = bool(
        getattr(settings, "table_total_row_match_case_insensitive", True)
    )
    label = getattr(settings, "table_total_row_label", "TOTAL")

    left = normalize_table_label(value, strip_markdown=strip_md)
    right = normalize_table_label(label, strip_markdown=strip_md)
    if case_insensitive:
        return left.casefold() == right.casefold()
    return left == right


def total_display_text(value: Any) -> str:
    """Text to display for the first cell of a detected TOTAL row.

    By default we preserve the input casing (after stripping markdown wrappers and
    normalizing whitespace). This avoids forcing TOTAL to all-caps when the input is
    e.g. "Total".
    """
    strip_md = bool(getattr(settings, "table_total_row_strip_markdown", True))
    preserve = bool(getattr(settings, "table_total_row_preserve_input_casing", True))
    if preserve:
        return normalize_table_label(value, strip_markdown=strip_md)

    display = getattr(settings, "table_total_row_display", "TOTAL")
    return normalize_table_label(display, strip_markdown=strip_md)


def _is_numeric_string(value: str, *, allow_commas: bool) -> bool:
    s = value.strip()
    if not s:
        return False
    if s.startswith("(") and s.endswith(")"):
        # Already accounting-style or otherwise parenthesized; don't reinterpret.
        return False
    if _PLAIN_NUMERIC_RE.match(s):
        return True
    if allow_commas and _COMMA_GROUPED_NUMERIC_RE.match(s):
        return True
    return False


def format_table_cell_value(value: Any) -> str:
    """Format values intended for PPT table cells.

    Behavior:
    - Adds US-style thousand separators for numeric values (delegates to format_number_with_commas).
    - If configured, renders negative numbers in accounting style parentheses:
        -1234 -> "(1,234)"
        "-1,234" -> "(1,234)"
    - Leaves non-numeric strings (e.g., "$-1,234", "12%") unchanged.
    """
    if value is None:
        return ""

    negative_style = (getattr(settings, "table_negative_number_style", "parentheses") or "").lower()
    allow_commas = bool(getattr(settings, "table_numeric_string_allow_commas", True))

    # Numeric strings (including "-1,234") should be handled here so we can wrap negatives.
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return value

        if _is_numeric_string(s, allow_commas=allow_commas):
            is_negative = s.startswith("-")
            if is_negative:
                s_abs = s[1:].strip()
            else:
                s_abs = s.lstrip("+").strip()

            # Preserve decimal places exactly as provided in the string.
            s_abs_no_commas = s_abs.replace(",", "")
            if "." in s_abs_no_commas:
                integer_part, decimal_part = s_abs_no_commas.split(".", 1)
                try:
                    int_val = int(integer_part) if integer_part else 0
                except ValueError:
                    return value
                formatted_abs = f"{int_val:,}.{decimal_part}"
            else:
                try:
                    int_val = int(s_abs_no_commas)
                except ValueError:
                    return value
                formatted_abs = f"{int_val:,}"

            if is_negative and negative_style == "parentheses":
                return f"({formatted_abs})"
            return formatted_abs if not is_negative else f"-{formatted_abs}"

        # Not a numeric string we recognize (e.g. "$-1,234", "12%") -> leave as-is
        return value

    # Numeric types
    if isinstance(value, (int, float)):
        is_negative = value < 0
        formatted_abs = format_number_with_commas(abs(value)) if is_negative else format_number_with_commas(value)
        if is_negative and negative_style == "parentheses":
            return f"({formatted_abs})"
        return formatted_abs if not is_negative else f"-{formatted_abs}"

    return str(value)


def format_number_with_commas(value: Any) -> str:
    """Format numeric values with US-style thousand separators.

    Converts numeric values to strings with commas for readability:
    - Integers: 1234567 -> "1,234,567"
    - Floats: 1234567.89 -> "1,234,567.89"
    - Non-numeric values: returned as-is (converted to string)
    - None: returns empty string

    Args:
        value: The value to format. Can be int, float, str, or None.

    Returns:
        Formatted string with thousand separators for numeric values,
        or the original value as a string for non-numeric inputs.
    """
    if value is None:
        return ""

    # If already a string, try to parse as number
    if isinstance(value, str):
        # Return empty strings as-is
        if not value.strip():
            return value
        # Try to parse as float/int
        try:
            # Check if it's a float (has decimal point)
            if "." in value:
                numeric_value = float(value)
                # Format with commas, preserving decimal places
                integer_part = int(numeric_value)
                decimal_part = value.split(".")[1]
                return f"{integer_part:,}.{decimal_part}"
            else:
                numeric_value = int(value)
                return f"{numeric_value:,}"
        except (ValueError, TypeError):
            # Not a number, return as-is
            return value

    # Handle numeric types directly
    if isinstance(value, float):
        # Check if it's effectively an integer
        if value == int(value):
            return f"{int(value):,}"
        # Round to 2 decimal places to avoid floating-point precision issues
        # (e.g., 1234567.89 stored as 1234567.8899999999)
        rounded = round(value, 2)
        # Format with commas
        formatted = f"{rounded:,.2f}"
        # Strip trailing zeros after decimal point for cleaner display
        # e.g., "1,234.50" -> "1,234.5", "1,234.00" -> "1,234"
        formatted = formatted.rstrip("0").rstrip(".")
        return formatted

    if isinstance(value, int):
        return f"{value:,}"

    # For any other type, convert to string
    return str(value)


def format_label(label: str, fallback: str = "") -> str:
    """Format a label for display in charts and tables.

    Rules:
    - Replace underscores with single spaces
    - Collapse multiple whitespace runs
    - Trim leading/trailing whitespace
    - Convert to title case for readability
    - If label becomes empty after cleaning, return fallback
    """
    if label is None:
        return fallback
    cleaned = label.replace("_", " ")
    cleaned = _MULTISPACE_RE.sub(" ", cleaned).strip()
    return cleaned.title() if cleaned else fallback


def name():
    return "hello"


def build_ppt_download_url(
    report_id: str | None = None, run_id: str | None = None
) -> str:
    if report_id is None and run_id is None:
        raise ValueError("Either report_id or run_id is required")

    base_url = settings.api_base_url.rstrip("/")
    endpoint = "/reports/download"
    if run_id:
        url = f"{base_url}{endpoint}?run_id={run_id}"
    else:
        url = f"{base_url}{endpoint}?report_id={report_id}"
    return url


def get_latest_complete_quarter() -> str:
    """
    Calculate the latest complete quarter based on the current date.

    Returns:
        str: Quarter in 'YYYY QN' format (e.g., '2024 Q4')

    Example:
        If today is January 15, 2025, the latest complete quarter is Q4 2024.
        If today is April 1, 2025, the latest complete quarter is Q1 2025.
    """
    now = datetime.utcnow()
    current_month = now.month
    current_year = now.year

    # Determine which quarter we're in
    # Q1: Jan-Mar (1-3), Q2: Apr-Jun (4-6), Q3: Jul-Sep (7-9), Q4: Oct-Dec (10-12)
    current_quarter = (current_month - 1) // 3 + 1

    # The latest complete quarter is the previous quarter
    if current_quarter == 1:
        # If we're in Q1, the last complete quarter is Q4 of previous year
        latest_complete_quarter = 4
        latest_complete_year = current_year - 1
    else:
        # Otherwise, it's the previous quarter of the current year
        latest_complete_quarter = current_quarter - 1
        latest_complete_year = current_year

    return f"{latest_complete_year} Q{latest_complete_quarter}"
