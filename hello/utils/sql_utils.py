import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union, overload
from hello.services.snowflake_service import fetch_snowflake_data
from functools import lru_cache
from hello.services.config import settings


env = settings.TESTING_ENV

__all__ = [
    "calculate_start_period",
    "get_asking_rate_field",
    "resolve_standard_dynamic_filters",
    "resolve_submarket_snapshot_dynamic_filters",
    "get_absorption_field",
    "get_quarter_end_date",
    "escape_single_quotes",
    "build_where_clause",
    "build_submarket_where_clause",
    "build_multi_quarter_where_clause",
    "build_property_class_where_clause",
    "build_lease_where_clause",
    "build_sublease_where_clause",
    "FilterRule",
    "SQLFilterBuilder",
    "SQLArgumentResolver",
    "SQLFieldResolver",
    "SQLTemplateRenderer",
    "DEFAULT_SQL_FIELD_MAPPING",
    "DEFAULT_SQL_UTILITY_FUNCTION_REGISTRY",
    "DEFAULT_FILTER_RULES",
    "DEFAULT_FILTER_BUILDER",
    "SUBMARKET_SNAPSHOT_FILTER_RULES",
    "SUBMARKET_SNAPSHOT_FILTER_BUILDER",
    "render_sql_template",
]

_HISTORY_RANGE_PATTERN = re.compile(r"^(?P<years>\d+)\s*-\s*year(s)?$", re.IGNORECASE)
_QUARTER_PATTERN = re.compile(r"^(?P<year>\d{4})\s*(?:Q|q)(?P<quarter>[1-4])$")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_SQL_IDENTIFIER_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
_SQL_NUMERIC_LITERAL_RE = re.compile(r"^\d+(?:\.\d+)?$")
_SQL_SIMPLE_ARITHMETIC_OPERATORS = {"+", "-", "*", "/"}


class SQLPlaceholderRenderMode(str, Enum):
    """Controls how resolved placeholder values are rendered into SQL."""

    LITERAL = "literal"
    IDENTIFIER = "identifier"
    RAW = "raw"


def _parse_history_range(history_range: str) -> int:
    """Extract the number of years from a history range string."""
    match = _HISTORY_RANGE_PATTERN.match(history_range.strip())
    if not match:
        raise ValueError(f"Invalid history_range format: '{history_range}'")
    return int(match.group("years"))


def _parse_quarter(current_quarter: str) -> tuple[int, str]:
    """Parse the year and quarter from a quarter string."""
    match = _QUARTER_PATTERN.match(current_quarter.strip())
    if not match:
        raise ValueError(f"Invalid current_quarter format: '{current_quarter}'")
    return int(match.group("year")), f"Q{match.group('quarter')}"


def calculate_start_period(current_quarter: str, history_range: str) -> str:
    """Calculate the start period based on the current quarter and history range.

    Computes the start period (in 'YYYY Qn' format) by subtracting a number of years from
    the current year, preserving the quarter. The number of years is extracted from the
    ``history_range`` string (e.g., '3-Year', '5-Year', '10-Year').
    """
    year, quarter = _parse_quarter(current_quarter)
    years_back = _parse_history_range(history_range)
    return f"{year - years_back} {quarter}"


def get_quarter_end_date(current_quarter: str) -> str:
    """Convert period format to the end date of the specified quarter.

    Transforms a quarter string into the calendar end date for that quarter.

    Args:
        period (str): Period in 'YYYY Qn' format (e.g., '2023 Q4')

    Returns:
        str: End date of quarter in 'YYYYMMDD' format (e.g., '20231231')

    Notes:
        Q1 ends 03/31, Q2 ends 06/30, Q3 ends 09/30, Q4 ends 12/31
    """
    year = int(current_quarter.split()[0])
    quarter = int(current_quarter.split()[1][1])

    # Map quarter to month end
    quarter_end_months = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}

    return f"{year}{quarter_end_months[quarter]}"


_ASKING_RATE_FIELD_MAP: dict[str, str] = {
    "gross-up": "avg_asking_lease_rate_direct_gross",
    "average": "avg_asking_lease_rate_direct",
    "net-down": "avg_asking_lease_rate_direct_net",
}


def get_asking_rate_field(asking_rate_type: str, monthly_yearly_select: str) -> str:
    """Determine the correct asking rate field for SQL queries."""
    base_field = _ASKING_RATE_FIELD_MAP.get(
        asking_rate_type.lower(), _ASKING_RATE_FIELD_MAP["average"]
    )
    if monthly_yearly_select.lower() == "monthly":
        return f"{base_field} / 12"
    return base_field


def _escape_sql_string(value: str) -> str:
    """Escape single quotes in a string for SQL."""
    return value.replace("'", "''")


def _extract_payload_value(
    payload: Union[Mapping[str, Any], Any], key: str, default: Any = None
) -> Any:
    """Safely retrieve a value from a mapping-like payload"""
    if payload is None:
        return default
    return payload.get(key, default)


def _is_empty_value(value: Any) -> bool:
    """Determine whether a value should be considered empty for filtering purposes."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_is_empty_value(item) for item in value)
    return False


def _normalize_to_sequence(value: Any) -> list[Any]:
    """Normalize various container types into a list of concrete values."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized: list[Any] = []
        for item in value:
            if _is_empty_value(item):
                continue
            normalized.append(item)
        return normalized
    return [value]


def _quote_sql_string(value: Any) -> str:
    """Quote and escape a Python value for inclusion in SQL."""
    return f"'{_escape_sql_string(str(value))}'"


def _tokenize_identifier_expression(expression: str) -> list[str]:
    """Split an arithmetic expression into SQL identifier-safe tokens."""
    tokens: list[str] = []
    buffer: list[str] = []
    for char in expression:
        if char.isspace():
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            continue
        if char in _SQL_SIMPLE_ARITHMETIC_OPERATORS or char in "()":
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            tokens.append(char)
        else:
            buffer.append(char)
    if buffer:
        tokens.append("".join(buffer))
    return tokens


def _is_valid_identifier_expression(candidate: str) -> bool:
    """Allow simple arithmetic expressions composed of identifiers and numbers."""
    tokens = _tokenize_identifier_expression(candidate)
    if not tokens:
        return False

    expect_operand = True
    paren_depth = 0
    for token in tokens:
        if token == "(":
            if not expect_operand:
                return False
            paren_depth += 1
            continue
        if token == ")":
            if expect_operand or paren_depth == 0:
                return False
            paren_depth -= 1
            continue
        if token in _SQL_SIMPLE_ARITHMETIC_OPERATORS:
            if expect_operand:
                return False
            expect_operand = True
            continue
        if _SQL_IDENTIFIER_RE.fullmatch(token) or _SQL_NUMERIC_LITERAL_RE.fullmatch(
            token
        ):
            if not expect_operand:
                return False
            expect_operand = False
            continue
        return False

    return not expect_operand and paren_depth == 0


def _coerce_sql_identifier(value: Any) -> str:
    """Validate and return a SQL identifier."""
    if not isinstance(value, str):
        raise TypeError(f"SQL identifier must be a string, got {type(value).__name__}")
    candidate = value.strip()
    if not candidate:
        raise ValueError("SQL identifier cannot be empty or whitespace")
    if _SQL_IDENTIFIER_RE.fullmatch(candidate) or _is_valid_identifier_expression(
        candidate
    ):
        return candidate
    raise ValueError(f"Invalid SQL identifier: '{value}'")


def _in_clause_factory(
    column: str, operator: str = "IN"
) -> Callable[[Any, Union[Mapping[str, Any], Any]], Union[str, None]]:
    """Create a clause factory for IN/NOT IN lookups."""

    def _builder(value: Any, _: Union[Mapping[str, Any], Any]) -> Union[str, None]:
        values = _normalize_to_sequence(value)
        if not values:
            return None
        formatted = ", ".join(_quote_sql_string(v) for v in values)
        return f"{column} {operator} ({formatted})"

    return _builder


def _required_tag_clause_factory(
    property_tags_expression: str,
) -> Callable[[Any, Union[Mapping[str, Any], Any]], Union[str, None]]:
    """Create a clause factory for ARRAY_CONTAINS tag lookups."""

    def _builder(value: Any, _: Union[Mapping[str, Any], Any]) -> Union[str, None]:
        tags = _normalize_to_sequence(value)
        if not tags:
            return None
        conditions = [
            f"ARRAY_CONTAINS('{_escape_sql_string(tag)}'::VARIANT, SPLIT({property_tags_expression}, ', '))"
            for tag in tags
        ]
        return f"({' OR '.join(conditions)})"

    return _builder


def _min_property_size_clause_factory(
    column: str,
) -> Callable[[Any, Union[Mapping[str, Any], Any]], Union[str, None]]:
    """Create a clause factory for minimum property size comparisons."""

    def _builder(value: Any, _: Union[Mapping[str, Any], Any]) -> Union[str, None]:
        sizes = _normalize_to_sequence(value)
        if not sizes:
            return None
        min_size = sizes[0]
        if isinstance(min_size, str):
            min_size = min_size.strip()
        return f"{column} >= {min_size}"

    return _builder


_DEFAULT_REQUIRED_TAG_CLAUSE = _required_tag_clause_factory("property_tags")
_DEFAULT_MIN_PROPERTY_SIZE_CLAUSE = _min_property_size_clause_factory(
    "net_rentable_area_all_status"
)


def _required_tag_clause(
    value: Any, payload: Union[Mapping[str, Any], Any]
) -> Union[str, None]:
    """Build an ARRAY_CONTAINS clause for required tags."""
    return _DEFAULT_REQUIRED_TAG_CLAUSE(value, payload)


def _min_property_size_clause(
    value: Any, payload: Union[Mapping[str, Any], Any]
) -> Union[str, None]:
    """Build a numeric lower bound filter for property size."""
    return _DEFAULT_MIN_PROPERTY_SIZE_CLAUSE(value, payload)


@dataclass(frozen=True)
class FilterRule:
    """Declarative description of how to turn payload data into a SQL clause."""

    key: str
    clause_builder: Callable[[Any, Union[Mapping[str, Any], Any]], Union[str, None]]

    def build_clause(self, payload: Union[Mapping[str, Any], Any]) -> Union[str, None]:
        """Evaluate the rule against the payload and return the resulting clause."""
        value = _extract_payload_value(payload, self.key)
        if _is_empty_value(value):
            return None
        return self.clause_builder(value, payload)


class SQLFilterBuilder:
    """Compose WHERE clauses from a collection of reusable filter rules."""

    def __init__(self, rules: Sequence[FilterRule] | None = None):
        self._rules = list(rules or [])

    def build(self, payload: Union[Mapping[str, Any], Any]) -> str:
        """Generate a SQL WHERE clause for the provided payload."""
        if payload is None:
            return "1=1"

        filters: list[str] = []
        for rule in self._rules:
            clause = rule.build_clause(payload)
            if clause:
                filters.append(clause)
        return " AND ".join(filters) if filters else "1=1"


DEFAULT_FILTER_RULES: tuple[FilterRule, ...] = (
    FilterRule("Market", _in_clause_factory("market")),
    FilterRule("Property Type", _in_clause_factory("property_type")),
    FilterRule("Submarket", _in_clause_factory("submarket")),
    FilterRule(
        "Excluded Submarket", _in_clause_factory("submarket", operator="NOT IN")
    ),
    FilterRule("Property Subtype", _in_clause_factory("property_subtype")),
    FilterRule(
        "Excluded Property Subtype",
        _in_clause_factory("property_subtype", operator="NOT IN"),
    ),
    FilterRule("Required Tag", _required_tag_clause),
    FilterRule("Vacancy Index", _in_clause_factory("vacancy_index")),
    FilterRule("Min. Property Size", _min_property_size_clause),
)

DEFAULT_FILTER_BUILDER = SQLFilterBuilder(DEFAULT_FILTER_RULES)

SUBMARKET_SNAPSHOT_FILTER_RULES: tuple[FilterRule, ...] = (
    FilterRule("Market", _in_clause_factory("phs.market")),
    FilterRule("Property Type", _in_clause_factory("phs.property_type")),
    FilterRule("Submarket", _in_clause_factory("phs.submarket")),
    FilterRule(
        "Excluded Submarket", _in_clause_factory("phs.submarket", operator="NOT IN")
    ),
    FilterRule("Property Subtype", _in_clause_factory("phs.property_subtype")),
    FilterRule(
        "Excluded Property Subtype",
        _in_clause_factory("phs.property_subtype", operator="NOT IN"),
    ),
    FilterRule("Required Tag", _required_tag_clause_factory("phs.property_tags")),
    FilterRule("Vacancy Index", _in_clause_factory("phs.vacancy_index")),
    FilterRule(
        "Min. Property Size",
        _min_property_size_clause_factory("phs.net_rentable_area_all_status"),
    ),
)

SUBMARKET_SNAPSHOT_FILTER_BUILDER = SQLFilterBuilder(SUBMARKET_SNAPSHOT_FILTER_RULES)


def build_submarket_snapshot_dynamic_filters(
    methodology: Union[Mapping[str, Any], Any],
) -> str:
    """Generate SQL WHERE filters for submarket snapshot queries.

    Mirrors ``build_dynamic_filters`` but prefixes the field references with the ``phs`` alias
    used by snapshot SQL templates.
    """
    return SUBMARKET_SNAPSHOT_FILTER_BUILDER.build(methodology)


@lru_cache()
def get_market_methodology(defined_market_name: str) -> dict[str, Any]:
    try:
        query = f"""
        SELECT defining_methodology_long_description 
        FROM PROD_USDM_DB.RECORDS.PROPERTY_HIST_SNAPSHOT_FOR_AGGREGATION 
        WHERE defined_market_name = '{defined_market_name}' 
        LIMIT 1;
        """
        if env == "CBRE":
            results = fetch_snowflake_data(query)
        else:
            results = [
                {
                    "Statistical": "Y",
                    "Market": ["Silicon Valley", "San Francisco Peninsula"],
                    "Property Type": ["Industrial", "Office"],
                    "Property Subtype": "R&D/Flex",
                    "Excluded Submarket": [
                        "Belmont",
                        "Brisbane",
                        "Burlingame",
                        "Daly City",
                    ],
                    "Excluded Property Subtype": ["Warehouse", "Distribution"],
                    "Submarket": ["Downtown", "Midtown"],
                }
            ]

        first_row = results[0]
        methodology_str = first_row.get(
            "DEFINING_METHODOLOGY_LONG_DESCRIPTION"
        ) or first_row.get("defining_methodology_long_description")

        if not methodology_str:
            return {}

        methodology_dict: dict[str, Any] = {}
        methodology_parts = methodology_str.split(" | ")

        for part in methodology_parts:
            if ": " not in part:
                continue
            key, value = part.split(": ", 1)
            normalized_key = key.strip()
            if normalized_key in [
                "Market",
                "Property Type",
                "Excluded Submarket",
                "Excluded Property Subtype",
                "Submarket",
                "Required Tag",
            ]:
                methodology_dict[normalized_key] = [
                    v.strip() for v in value.split(",") if v.strip()
                ]
            else:
                methodology_dict[normalized_key] = value.strip()

        return methodology_dict
    except Exception as e:
        raise Exception(f"Error getting market methodology: {str(e)}") from e


def build_dynamic_filters(methodology: Union[Mapping[str, Any], Any]) -> str:
    """Generate SQL WHERE filters using the default filter builder configuration."""
    return DEFAULT_FILTER_BUILDER.build(methodology)


def resolve_standard_dynamic_filters(defined_market_name: str) -> str:
    """Resolve standard dynamic filters for the given market.
    
    Args:
        defined_market_name: The name of the defined market
        
    Returns:
        SQL WHERE clause fragment with standard dynamic filters
    """
    methodology = get_market_methodology(defined_market_name)
    return build_dynamic_filters(methodology)


def resolve_submarket_snapshot_dynamic_filters(defined_market_name: str) -> str:
    """Resolve submarket snapshot dynamic filters for the given market.
    
    Args:
        defined_market_name: The name of the defined market
        
    Returns:
        SQL WHERE clause fragment with submarket snapshot dynamic filters
    """
    methodology = get_market_methodology(defined_market_name)
    return build_submarket_snapshot_dynamic_filters(methodology)


def get_absorption_field(
    period: str,
    absorption_choice: str | None,
    direct_vs_total_choice: str | None,
) -> str:
    """Return the SQL column name for the selected absorption metric."""
    normalized_period = (period or "").strip().lower()
    if normalized_period not in {"qtd", "ytd"}:
        raise ValueError(f"Unsupported absorption period: {period}")

    suffix = (
        "_direct"
        if (direct_vs_total_choice or "").strip().lower() == "direct"
        else "_total"
    )

    normalized_choice = (absorption_choice or "").strip().lower()
    if normalized_choice == "vacant available":
        prefix = (
            "ytd_net_absorption" if normalized_period == "ytd" else "net_absorption"
        )
        return f"{prefix}{suffix}_vacant_avail"

    base_fields = {
        "qtd": {
            "availability": "qtd_change_in_availability",
            "off market occupied": "qtd_change_in_off_market_occupied",
            "occupancy": "qtd_change_in_occupancy",
        },
        "ytd": {
            "availability": "ytd_qtd_change_in_availability",
            "off market occupied": "ytd_qtd_change_in_off_market_occupied",
            "occupancy": "ytd_qtd_change_in_occupancy",
        },
    }
    period_fields = base_fields[normalized_period]
    base_field = period_fields.get(normalized_choice, period_fields["occupancy"])
    return f"{base_field}{suffix}"


@overload
def escape_single_quotes(value: None) -> None: ...


@overload
def escape_single_quotes(value: str) -> str: ...


@overload
def escape_single_quotes(value: list[str]) -> list[str]: ...


def escape_single_quotes(
    value: Union[str, list[str], None],
) -> Union[str, list[str], None]:
    """Escape single quotes in strings for SQL safety.

    Handles edge cases where field values (like submarket names) contain single quotes
    that need to be escaped for SQL queries.

    Args:
        value: String, list of strings, or None to escape

    Returns:
        Escaped string, list of escaped strings, or None

    Examples:
        >>> escape_single_quotes("O'Hare")
        "O''Hare"
        >>> escape_single_quotes(["O'Hare", "Downtown"])
        ["O''Hare", "Downtown"]
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [v.replace("'", "''") if isinstance(v, str) else v for v in value]
    return value.replace("'", "''")


def _is_geography_value_empty(value: Union[str, list[str], None]) -> bool:
    """Check if a geography filter value should be treated as empty.

    Handles multiple representations of "no filter":
    - None
    - Empty list []
    - List with single 'All' element ['All']
    - String 'All'

    Args:
        value: The geography filter value to check

    Returns:
        True if the value represents "no filter", False otherwise
    """
    if value is None:
        return True
    if isinstance(value, list):
        if len(value) == 0:
            return True
        if len(value) == 1 and value[0] == "All":
            return True
    if isinstance(value, str) and value == "All":
        return True
    return False


def build_where_clause(
    defined_market_name: str,
    publishing_group: str,
    current_quarter: str,
    history_range: str,
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build a SQL WHERE clause for market data queries based on geography parameters.

    Constructs a SQL WHERE clause with appropriate filters for different geography levels
    (market, vacancy index, submarket, district) based on the provided selections.

    Args:
        defined_market_name: The market name to filter by
        publishing_group: The publishing group identifier
        current_quarter: The current quarter in 'YYYY QQ' format
        history_range: The history range (e.g., '3-Year', '5-Year')
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        Complete SQL WHERE clause with appropriate filters for the geography level

    Notes:
        Properly escapes single quotes in strings to prevent SQL injection.
        Handles all possible combinations of geography level filters.
        Empty lists and None values are treated the same way (no filter for that level).
        Calculates start_period internally using calculate_start_period.

    Examples:
        >>> build_where_clause('Boston Office', 'CBRE', '2023 Q1', '3-Year', 'Core', None, None)
        "where defined_market_name = 'Boston Office' and publishing_group = 'CBRE' ..."
    """
    # Calculate start period from quarter and history range
    start_period = calculate_start_period(current_quarter, history_range)
    
    # Start with base WHERE conditions that apply to all queries
    where_clause = f"""where defined_market_name = '{defined_market_name}' 
    and publishing_group = '{publishing_group}' 
    and period between '{start_period}' and '{current_quarter}'"""

    # Check if values are None, empty lists, or 'All'
    is_vacancy_empty = _is_geography_value_empty(vacancy_index)
    is_submarket_empty = _is_geography_value_empty(submarket)
    is_district_empty = _is_geography_value_empty(district)

    # Handle all possible filter combinations
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        # No specific geography - use market total
        where_clause += " and breakdown_full_desc = '*TOTAL*'"

    elif not is_vacancy_empty and is_submarket_empty and is_district_empty:
        # Only vacancy index specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index' and vacancy_index = '{v_index}'"

    elif not is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Vacancy index and submarket specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape after extracting from list
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket' and vacancy_index = '{v_index}' and submarket = '{s_market}'"

    elif not is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # All three levels specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape after extracting from list
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and vacancy_index = '{v_index}' and submarket = '{s_market}' and district = '{d_district}'"

    elif is_vacancy_empty and is_submarket_empty and not is_district_empty:
        # Only district specified
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and district = '{d_district}'"

    elif is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Only submarket specified
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape after extracting from list
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket' and submarket = '{s_market}'"

    elif is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # Submarket and district specified
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape after extracting from list
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and submarket = '{s_market}' and district = '{d_district}'"

    return where_clause


def build_submarket_where_clause(
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build a SQL WHERE clause for submarket queries with geography filters.

    Creates an additional WHERE clause specifically for submarket queries where table
    aliases (phs.*) are needed, based on the selection of geography levels.

    Args:
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        SQL WHERE clause fragment with "and" prefix for adding to an existing query

    Notes:
        Returns "and 1=1" (always true) if no geography filters are specified.
        All fields are prefixed with "phs." table alias.
        Properly escapes single quotes in values to prevent SQL injection.

    Examples:
        >>> build_submarket_where_clause('Core', 'Downtown', None)
        "and phs.vacancy_index = 'Core' and phs.submarket = 'Downtown'"
    """
    # Default where clause that's always true
    where_clause = "and 1=1"

    # Check if values are None or empty lists
    is_vacancy_empty = vacancy_index is None or (
        isinstance(vacancy_index, list) and len(vacancy_index) == 0
    )
    is_submarket_empty = submarket is None or (
        isinstance(submarket, list) and len(submarket) == 0
    )
    is_district_empty = district is None or (
        isinstance(district, list) and len(district) == 0
    )

    # If none are specified, return the default (no filtering)
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        return where_clause

    # Extract values and escape as needed
    if not is_vacancy_empty:
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        where_clause = f"and phs.vacancy_index = '{v_index}'"

    if not is_submarket_empty:
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        # Escape single quotes
        s_market = escape_single_quotes(s_market)
        where_clause += f" and phs.submarket = '{s_market}'"

    if not is_district_empty:
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and phs.district = '{d_district}'"

    return where_clause


def build_multi_quarter_where_clause(
    defined_market_name: str,
    publishing_group: str,
    current_quarter: str,
    history_range: str,
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build SQL WHERE clause for multi-quarter data with geography parameters.

    Creates a SQL WHERE clause for queries spanning multiple quarters, with appropriate
    filters based on the selected geography level hierarchy.

    Args:
        defined_market_name: The market name to filter by
        publishing_group: The publishing group identifier
        current_quarter: The current quarter in 'YYYY QQ' format
        history_range: The history range (e.g., '3-Year', '5-Year')
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        Complete SQL WHERE clause with appropriate filters for the geography level

    Notes:
        Similar to build_where_clause but specifically optimized for
        multi-quarter historical queries.
        Properly escapes single quotes in strings to prevent SQL injection.
        Calculates start_period internally using calculate_start_period.

    Examples:
        >>> build_multi_quarter_where_clause('Chicago Office', 'CBRE', '2023 Q1', '3-Year', 'CBD', None, None)
        "where defined_market_name = 'Chicago Office' and publishing_group = 'CBRE' ..."
    """
    # Calculate start period from quarter and history range
    start_period = calculate_start_period(current_quarter, history_range)
    
    # Base WHERE clause that's common to all queries
    where_clause = f"""where defined_market_name = '{defined_market_name}' 
    and publishing_group = '{publishing_group}'
    and period between '{start_period}' and '{current_quarter}'"""

    # Check if values are None or empty lists
    is_vacancy_empty = vacancy_index is None or (
        isinstance(vacancy_index, list) and len(vacancy_index) == 0
    )
    is_submarket_empty = submarket is None or (
        isinstance(submarket, list) and len(submarket) == 0
    )
    is_district_empty = district is None or (
        isinstance(district, list) and len(district) == 0
    )

    # Handle all possible filter combinations
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        # No specific geography - use market total
        where_clause += " and breakdown_full_desc = '*TOTAL*'"

    elif not is_vacancy_empty and is_submarket_empty and is_district_empty:
        # Only vacancy index specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index' and vacancy_index = '{v_index}'"

    elif not is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Vacancy index and submarket specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape for SQL safety
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket' and vacancy_index = '{v_index}' and submarket = '{s_market}'"

    elif not is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # All three levels specified
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and vacancy_index = '{v_index}' and submarket = '{s_market}' and district = '{d_district}'"

    elif is_vacancy_empty and is_submarket_empty and not is_district_empty:
        # Only district specified
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and district = '{d_district}'"

    elif is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Only submarket specified
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket' and submarket = '{s_market}'"

    elif is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # Submarket and district specified
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District' and submarket = '{s_market}' and district = '{d_district}'"

    return where_clause


def build_property_class_where_clause(
    defined_market_name: str,
    publishing_group: str,
    current_quarter: str,
    history_range: str,
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build SQL WHERE clause for property class data queries.

    Creates a SQL WHERE clause specifically for property class data, filtering by
    geography levels and restricting to Class A and Class B properties.

    Args:
        defined_market_name: The market name to filter by
        publishing_group: The publishing group identifier
        current_quarter: The current quarter in 'YYYY QQ' format
        history_range: The history range (e.g., '3-Year', '5-Year')
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        Complete SQL WHERE clause with appropriate filters for property class data

    Notes:
        Always includes 'Class A' and 'Class B' property classes in the filter.
        Properly escapes single quotes in strings to prevent SQL injection.
        Calculates start_period internally using calculate_start_period.

    Examples:
        >>> build_property_class_where_clause('Boston Office', 'CBRE', '2023 Q1', '3-Year', None, 'Downtown', None)
        "where defined_market_name = 'Boston Office' and publishing_group = 'CBRE' ..."
    """
    # Calculate start period from quarter and history range
    start_period = calculate_start_period(current_quarter, history_range)
    
    # Base WHERE clause
    where_clause = f"""where defined_market_name = '{defined_market_name}' 
    and publishing_group = '{publishing_group}' 
    and period BETWEEN '{start_period}' AND '{current_quarter}'"""

    # Check if values are None or empty lists
    is_vacancy_empty = vacancy_index is None or (
        isinstance(vacancy_index, list) and len(vacancy_index) == 0
    )
    is_submarket_empty = submarket is None or (
        isinstance(submarket, list) and len(submarket) == 0
    )
    is_district_empty = district is None or (
        isinstance(district, list) and len(district) == 0
    )

    # Get sanitized values when they exist
    v_index = None
    s_market = None
    d_district = None

    if not is_vacancy_empty:
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index

    if not is_submarket_empty:
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        s_market = escape_single_quotes(s_market)  # Escape for SQL safety

    if not is_district_empty:
        d_district = district[0] if isinstance(district, list) else district

    # Handle different geography combinations
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        # Market-level property class
        where_clause += " and breakdown_full_desc = 'Market | Property Class'"

    elif not is_vacancy_empty and is_submarket_empty and is_district_empty:
        # Vacancy Index level
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Property Class' and vacancy_index = '{v_index}' AND property_class in ('Class A', 'Class B')"

    elif not is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Vacancy Index + Submarket level
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | Property Class' and vacancy_index = '{v_index}' and submarket = '{s_market}' AND property_class in ('Class A', 'Class B')"

    elif not is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # All three levels
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District | Property Class' and vacancy_index = '{v_index}' and submarket = '{s_market}' and district = '{d_district}' AND property_class in ('Class A', 'Class B')"

    elif is_vacancy_empty and is_submarket_empty and not is_district_empty:
        # District only
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District | Property Class' and district = '{d_district}' AND property_class in ('Class A', 'Class B')"

    elif is_vacancy_empty and not is_submarket_empty and is_district_empty:
        # Submarket only
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | Property Class' and submarket = '{s_market}' AND property_class in ('Class A', 'Class B')"

    elif is_vacancy_empty and not is_submarket_empty and not is_district_empty:
        # Submarket + District
        where_clause += f" and breakdown_full_desc = 'Market | Vacancy Index | Submarket | District | Property Class' and submarket = '{s_market}' and district = '{d_district}' AND property_class in ('Class A', 'Class B')"

    return where_clause


def build_lease_where_clause(
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build a SQL WHERE clause for lease data with geography filters.

    Creates a SQL WHERE clause fragment with appropriate filters for lease data queries
    based on the geography level selections.

    Args:
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        SQL WHERE clause fragment with "and" prefix for adding to an existing query

    Notes:
        Returns "and 1=1" (always true) if no geography filters are specified.
        Properly escapes single quotes in values to prevent SQL injection.
        Unlike submarket queries, does not use table aliases in the field names.

    Examples:
        >>> build_lease_where_clause('CBD', 'Downtown', None)
        "and vacancy_index = 'CBD' and submarket = 'Downtown'"
    """
    # Default where clause that's always true
    where_clause = "and 1=1"

    # Check if values are None or empty lists
    is_vacancy_empty = vacancy_index is None or (
        isinstance(vacancy_index, list) and len(vacancy_index) == 0
    )
    is_submarket_empty = submarket is None or (
        isinstance(submarket, list) and len(submarket) == 0
    )
    is_district_empty = district is None or (
        isinstance(district, list) and len(district) == 0
    )

    # If none are specified, return the default (no filtering)
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        return where_clause

    # Process values if they exist
    if not is_vacancy_empty:
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        where_clause = f"and vacancy_index = '{v_index}'"

    if not is_submarket_empty:
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        # Escape single quotes in submarket for SQL query safety
        s_market = escape_single_quotes(s_market)
        where_clause += f" and submarket = '{s_market}'"

    if not is_district_empty:
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and district = '{d_district}'"

    return where_clause


def build_sublease_where_clause(
    vacancy_index: Union[str, list[str], None],
    submarket: Union[str, list[str], None],
    district: Union[str, list[str], None],
) -> str:
    """Build a SQL WHERE clause for sublease data with geography filters.

    Creates a SQL WHERE clause fragment specifically for sublease queries where
    table alias 'arv.' is used with all field names.

    Args:
        vacancy_index: Vacancy index selection(s)
        submarket: Submarket selection(s)
        district: District selection(s)

    Returns:
        SQL WHERE clause fragment with "and" prefix for adding to an existing query

    Notes:
        Returns "and 1=1" (always true) if no geography filters are specified.
        All fields are prefixed with "arv." table alias for sublease queries.
        Properly escapes single quotes in values to prevent SQL injection.

    Examples:
        >>> build_sublease_where_clause('CBD', 'Downtown', None)
        "and arv.vacancy_index = 'CBD' and arv.submarket = 'Downtown'"
    """
    # Default where clause that's always true
    where_clause = "and 1=1"

    # Check if values are None or empty lists
    is_vacancy_empty = vacancy_index is None or (
        isinstance(vacancy_index, list) and len(vacancy_index) == 0
    )
    is_submarket_empty = submarket is None or (
        isinstance(submarket, list) and len(submarket) == 0
    )
    is_district_empty = district is None or (
        isinstance(district, list) and len(district) == 0
    )

    # If none are specified, return the default (no filtering)
    if is_vacancy_empty and is_submarket_empty and is_district_empty:
        return where_clause

    # Process values if they exist
    if not is_vacancy_empty:
        v_index = vacancy_index[0] if isinstance(vacancy_index, list) else vacancy_index
        where_clause = f"and arv.vacancy_index = '{v_index}'"

    if not is_submarket_empty:
        s_market = submarket[0] if isinstance(submarket, list) else submarket
        # Escape single quotes for SQL safety
        s_market = escape_single_quotes(s_market)
        where_clause += f" and arv.submarket = '{s_market}'"

    if not is_district_empty:
        d_district = district[0] if isinstance(district, list) else district
        where_clause += f" and arv.district = '{d_district}'"

    return where_clause


DEFAULT_SQL_UTILITY_FUNCTION_REGISTRY: dict[str, Callable[..., Any]] = {
    "calculate_start_period": calculate_start_period,
    "get_asking_rate_field": get_asking_rate_field,
    "resolve_standard_dynamic_filters": resolve_standard_dynamic_filters,
    "resolve_submarket_snapshot_dynamic_filters": resolve_submarket_snapshot_dynamic_filters,
    "get_absorption_field": get_absorption_field,
    "get_quarter_end_date": get_quarter_end_date,
    "build_where_clause": build_where_clause,
    "build_submarket_where_clause": build_submarket_where_clause,
    "build_multi_quarter_where_clause": build_multi_quarter_where_clause,
    "build_property_class_where_clause": build_property_class_where_clause,
    "build_lease_where_clause": build_lease_where_clause,
    "build_sublease_where_clause": build_sublease_where_clause,
}


DEFAULT_SQL_FIELD_MAPPING: dict[str, dict[str, Any]] = {
    "defined_market_name": {
        "type": "path",
        "path": "report_parameters.defined_markets.0",
    },
    "publishing_group": {
        "type": "path",
        "path": "report_parameters.publishing_group",
    },
    "start_period": {
        "type": "function",
        "name": "calculate_start_period",
        "args": [
            {"type": "path", "path": "report_parameters.quarter"},
            {"type": "path", "path": "report_parameters.history_range"},
        ],
    },
    "current_quarter": {
        "type": "path",
        "path": "report_parameters.quarter",
    },
    "asking_rate_field": {
        "type": "function",
        "name": "get_asking_rate_field",
        "args": [
            {"type": "path", "path": "report_parameters.asking_rate_type"},
            {"type": "path", "path": "report_parameters.asking_rate_frequency"},
        ],
        "render_mode": SQLPlaceholderRenderMode.IDENTIFIER.value,
    },
    "dynamic_filters": {
        "type": "function",
        "name": "resolve_standard_dynamic_filters",
        "args": [
            {"type": "path", "path": "report_parameters.defined_markets.0"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "submarket_snapshot_dynamic_filters": {
        "type": "function",
        "name": "resolve_submarket_snapshot_dynamic_filters",
        "args": [
            {"type": "path", "path": "report_parameters.defined_markets.0"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "min_transaction_size": {
        "type": "path",
        "path": "report_parameters.minimum_transaction_size",
    },
    "qtd_absorption": {
        "type": "function",
        "name": "get_absorption_field",
        "args": [
            {"type": "literal", "value": "qtd"},
            {"type": "path", "path": "report_parameters.absorption_calculation"},
            {"type": "path", "path": "report_parameters.total_vs_direct_absorption"},
        ],
        "render_mode": SQLPlaceholderRenderMode.IDENTIFIER.value,
    },
    "ytd_absorption": {
        "type": "function",
        "name": "get_absorption_field",
        "args": [
            {"type": "literal", "value": "ytd"},
            {"type": "path", "path": "report_parameters.absorption_calculation"},
            {"type": "path", "path": "report_parameters.total_vs_direct_absorption"},
        ],
        "render_mode": SQLPlaceholderRenderMode.IDENTIFIER.value,
    },
    "current_quarter_end_date": {
        "type": "function",
        "name": "get_quarter_end_date",
        "args": [{"type": "path", "path": "report_parameters.quarter"}],
    },
    "where_clause": {
        "type": "function",
        "name": "build_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.defined_markets.0"},
            {"type": "path", "path": "report_parameters.publishing_group"},
            {"type": "path", "path": "report_parameters.quarter"},
            {"type": "path", "path": "report_parameters.history_range"},
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "submarket_where_clause": {
        "type": "function",
        "name": "build_submarket_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "multi_quarter_where_clause": {
        "type": "function",
        "name": "build_multi_quarter_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.defined_markets.0"},
            {"type": "path", "path": "report_parameters.publishing_group"},
            {"type": "path", "path": "report_parameters.quarter"},
            {"type": "path", "path": "report_parameters.history_range"},
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "property_class_where_clause": {
        "type": "function",
        "name": "build_property_class_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.defined_markets.0"},
            {"type": "path", "path": "report_parameters.publishing_group"},
            {"type": "path", "path": "report_parameters.quarter"},
            {"type": "path", "path": "report_parameters.history_range"},
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "lease_where_clause": {
        "type": "function",
        "name": "build_lease_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "sublease_where_clause": {
        "type": "function",
        "name": "build_sublease_where_clause",
        "args": [
            {"type": "path", "path": "report_parameters.vacancy_index"},
            {"type": "path", "path": "report_parameters.submarket"},
            {"type": "path", "path": "report_parameters.district"},
        ],
        "render_mode": SQLPlaceholderRenderMode.RAW.value,
    },
    "monthly_yearly_select": {
        "type": "path",
        "path": "report_parameters.asking_rate_frequency",
    },
}


def default_sql_literal(value: Any) -> str:
    """Coerce a Python value into a SQL literal string."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        inner = ", ".join(default_sql_literal(v) for v in value)
        return f"({inner})"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


class SQLArgumentResolver:
    """Resolve argument specifications into payload values."""

    def __init__(
        self,
        payload: Union[Mapping[str, Any], Any],
        context: Union[Mapping[str, Any], Any, None] = None,
    ):
        self._payload = payload
        self._context = context

    def get_by_path(self, path: str) -> Any:
        parts = path.split(".")
        current = self._payload
        traversed: list[str] = []
        for part in parts:
            traversed.append(part)
            current = self._follow(current, part, ".".join(traversed))
        return current

    def resolve(self, spec: Any) -> Any:
        if isinstance(spec, dict):
            spec_type = spec.get("type")
            if spec_type == "literal":
                return spec.get("value")
            if spec_type == "payload":
                return self._payload
            if spec_type == "path":
                try:
                    return self.get_by_path(spec["path"])
                except KeyError as exc:
                    raise KeyError(f"Path not found: {spec['path']}") from exc
            if spec_type == "context":
                path = spec.get("path")
                if path is None:
                    raise ValueError("Context spec requires 'path'")
                try:
                    return self.get_from_context(path)
                except KeyError as exc:
                    raise KeyError(f"Context path not found: {path}") from exc
            raise ValueError(f"Unknown argument type: {spec_type}")
        return spec

    def get_from_context(self, path: str) -> Any:
        if self._context is None:
            raise KeyError("No context available for resolver")
        parts = path.split(".")
        current = self._context
        traversed: list[str] = []
        for part in parts:
            traversed.append(part)
            current = self._follow(current, part, ".".join(traversed))
        return current

    def _follow(self, current: Any, key: str, path: str) -> Any:
        if isinstance(current, Mapping):
            if key in current:
                return current[key]
            raise KeyError(f"Path not found: {path}")
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            try:
                index = int(key)
            except ValueError as exc:
                raise KeyError(
                    f"Invalid sequence index '{key}' in path '{path}'"
                ) from exc
            try:
                return current[index]
            except IndexError as exc:
                raise KeyError(f"Path index out of range: {path}") from exc
        raise KeyError(
            f"Unsupported path traversal at '{path}' for type {type(current).__name__}"
        )


class SQLFieldResolver:
    """Resolve field mapping specifications against a payload."""

    def __init__(
        self,
        field_mapping: Mapping[str, Mapping[str, Any]],
        utility_registry: Mapping[str, Callable[..., Any]],
        argument_resolver_cls: type[SQLArgumentResolver] = SQLArgumentResolver,
    ):
        self.field_mapping = dict(field_mapping)
        self.utility_registry = dict(utility_registry)
        self.argument_resolver_cls = argument_resolver_cls

    def resolve(
        self,
        name: str,
        payload: Union[Mapping[str, Any], Any],
        argument_resolver: Union[SQLArgumentResolver, None] = None,
    ) -> Any:
        if name not in self.field_mapping:
            # Try to get the value directly from the payload (fallback for raw values)
            if isinstance(payload, Mapping):
                if name in payload:
                    return payload[name]
            raise KeyError(f"No mapping provided for placeholder '{name}'")
        resolver = argument_resolver or self.argument_resolver_cls(payload)
        spec = self.field_mapping[name]
        spec_type = spec.get("type")
        if spec_type == "path":
            return resolver.get_by_path(spec["path"])
        if spec_type == "literal":
            return spec.get("value")
        if spec_type == "function":
            fn_name = spec["name"]
            fn = self.utility_registry.get(fn_name)
            if fn is None:
                raise KeyError(f"Utility function not found: {fn_name}")
            args = [resolver.resolve(arg) for arg in spec.get("args", [])]
            kwargs = {k: resolver.resolve(v) for k, v in spec.get("kwargs", {}).items()}
            return fn(*args, **kwargs)
        raise ValueError(f"Unknown mapping type: {spec_type}")


class SQLTemplateRenderer:
    """Render SQL templates by resolving placeholders against a payload."""

    def __init__(
        self,
        field_mapping: Mapping[str, Mapping[str, Any]],
        utility_registry: Mapping[str, Callable[..., Any]],
        *,
        literal_formatter: Callable[[Any], str] = default_sql_literal,
        argument_resolver_cls: type[SQLArgumentResolver] = SQLArgumentResolver,
    ):
        self.field_resolver = SQLFieldResolver(
            field_mapping, utility_registry, argument_resolver_cls
        )
        self.literal_formatter = literal_formatter

    def render(self, sql_template: str, payload: Union[Mapping[str, Any], Any]) -> str:
        placeholders = list(
            dict.fromkeys(
                match.group(1) for match in PLACEHOLDER_RE.finditer(sql_template)
            )
        )
        context = {"sql_template": sql_template}
        argument_resolver = self.field_resolver.argument_resolver_cls(
            payload, context=context
        )
        resolved_values = {
            name: self.field_resolver.resolve(name, payload, argument_resolver)
            for name in placeholders
        }
        coerced: dict[str, str] = {}
        for placeholder, value in resolved_values.items():
            mapping = self.field_resolver.field_mapping.get(placeholder, {})
            render_mode = mapping.get("render_mode")
            if render_mode is not None:
                try:
                    mode = SQLPlaceholderRenderMode(render_mode)
                except ValueError as exc:
                    raise ValueError(
                        f"Unknown render_mode '{render_mode}' for placeholder '{placeholder}'"
                    ) from exc
            elif placeholder not in self.field_resolver.field_mapping:
                # If not in field mapping but exists in payload, treat as RAW
                mode = SQLPlaceholderRenderMode.RAW
            else:
                mode = SQLPlaceholderRenderMode.LITERAL

            if mode is SQLPlaceholderRenderMode.IDENTIFIER:
                coerced[placeholder] = _coerce_sql_identifier(value)
            elif mode is SQLPlaceholderRenderMode.RAW:
                coerced[placeholder] = str(value)
            else:
                coerced[placeholder] = self.literal_formatter(value)

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in coerced:
                raise KeyError(f"Unresolved placeholder during replacement: {key}")
            return coerced[key]

        rendered = PLACEHOLDER_RE.sub(replace, sql_template)
        leftover = re.findall(r"\{[^}]*\}", rendered)
        if leftover:
            raise RuntimeError(f"Unreplaced placeholders remain: {leftover}")
        return rendered


def render_sql_template(
    sql_template: str,
    payload: Union[Mapping[str, Any], Any],
    *,
    field_mapping: Union[Mapping[str, Mapping[str, Any]], None] = None,
    utility_registry: Union[Mapping[str, Callable[..., Any]], None] = None,
    literal_formatter: Callable[[Any], str] = default_sql_literal,
    argument_resolver_cls: type[SQLArgumentResolver] = SQLArgumentResolver,
) -> str:
    """Convenience wrapper for rendering SQL templates with optional overrides."""
    renderer = SQLTemplateRenderer(
        field_mapping or DEFAULT_SQL_FIELD_MAPPING,
        utility_registry or DEFAULT_SQL_UTILITY_FUNCTION_REGISTRY,
        literal_formatter=literal_formatter,
        argument_resolver_cls=argument_resolver_cls,
    )
    return renderer.render(sql_template, payload)
