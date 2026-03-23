from collections.abc import Callable, Mapping, Sequence
from typing import Any
from datetime import datetime

from hello.services.snowflake_service import fetch_snowflake_data
from hello.utils.sql_utils import render_sql_template, get_asking_rate_field
from hello.models import Report
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger


def _is_cbre_env() -> bool:
    return (settings.TESTING_ENV or "").upper() == "CBRE"

_BASE_TICKER_QUERY_TEMPLATE = """
WITH LastTwoQuarters AS (
    SELECT period
    FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
    WHERE defined_market_name = {defined_market_name}
      AND breakdown_full_desc = '*TOTAL*'
      AND publishing_group = {publishing_group}
      AND period <= {current_quarter}
    ORDER BY period DESC
    LIMIT 2
)
SELECT {METRIC_SELECT} AS VALUE, period AS PERIOD
FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
WHERE defined_market_name = {defined_market_name}
  AND breakdown_full_desc = '*TOTAL*'
  AND publishing_group = {publishing_group}
  AND period IN (SELECT period FROM LastTwoQuarters)
ORDER BY period DESC
"""

_SUBMARKET_TICKER_QUERY_TEMPLATE = """
WITH LastTwoQuarters AS (
    SELECT period
    FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
    {WHERE_CLAUSE}
    ORDER BY period DESC
    LIMIT 2
)
SELECT {METRIC_SELECT} AS VALUE, period AS PERIOD
FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
{WHERE_CLAUSE}
  AND period IN (SELECT period FROM LastTwoQuarters)
ORDER BY period DESC
"""

_DEFAULT_TICKER_METRICS: dict[str, str] = {
    "vacancy": "ROUND(vacant_total_percent * 100, 1)",
    "absorption": "CAST({qtd_absorption} AS INT)",
    "deliveries": "CAST(delivered_construction_area AS INT)",
    "construction": "CAST(under_construction_area AS INT)",
    "asking_rate": "ROUND({asking_rate_field}, 2)",
}

_SUBMARKET_TICKER_METRICS: dict[str, str] = {
    **_DEFAULT_TICKER_METRICS,
    "vacancy": "ROUND(vacant_total_percent * 100, 2)",
}


def _format_number(value: Any) -> str:
    """Format numeric values with common ticker suffix rules."""
    if value is None:
        value = 0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    abs_value = abs(numeric)
    if abs_value >= 1_000_000:
        formatted = f"{numeric / 1_000_000:.1f}M"
    else:
        formatted = f"{numeric:,.0f}"

    if numeric < 0:
        return f"({formatted.replace('-', '')})"
    return formatted


def _extract_value(rows: Sequence[Any], index: int) -> Any:
    """Safely extract a value from the Snowflake response rows."""
    if not rows or index >= len(rows):
        return 0
    row = rows[index]
    if isinstance(row, Mapping):
        value = row.get("VALUE")
    else:
        value = None
    return 0 if value is None else value


def _render_query(template: str, metric_select: str, report_params: Mapping[str, Any]) -> str:
    query_template = template.replace("{METRIC_SELECT}", metric_select)
    return render_sql_template(query_template, {"report_parameters": report_params})


def _collect_metric_rows(
    metrics: Mapping[str, str],
    query_builder: Callable[[str], str],
) -> dict[str, list[dict[str, Any]]]:
    return {
        metric: (fetch_snowflake_data(query_builder(metric_sql)) or []) if _is_cbre_env() else [
            {"period": "2023Q4", "VALUE": 8.7},
            {"period": "2023Q3", "VALUE": 9.1},
        ]
        for metric, metric_sql in metrics.items()
    }


def _build_ticker_payload(
    ticker_rows: Mapping[str, Sequence[Any]],
    *,
    vacancy_precision: int = 1,
) -> dict[str, dict[str, Any]]:
    values: dict[str, Any] = {}
    for metric, rows in ticker_rows.items():
        values[f"current_{metric}"] = _extract_value(rows, 0)
        values[f"previous_{metric}"] = _extract_value(rows, 1)

    formatted_values = {
        "vacancy": (
            f"{values['current_vacancy']:.{vacancy_precision}f}%"
            if values.get("current_vacancy") is not None
            else "0"
        ),
        "absorption": _format_number(values.get("current_absorption")),
        "deliveries": _format_number(values.get("current_deliveries")),
        "construction": _format_number(values.get("current_construction")),
        "asking_rate": (
            f"${values['current_asking_rate']:.2f}"
            if values.get("current_asking_rate") is not None
            else "0"
        ),
    }

    return {"formatted": formatted_values, "raw": values}


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _coerce_literal_or_placeholder(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        return f"'{_escape_sql_literal(candidate)}'"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{_escape_sql_literal(str(value))}'"


def _normalize_selection(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
    else:
        items = [value]

    normalized: list[str] = []
    for item in items:
        if item is None:
            continue
        candidate = str(item).strip()
        if not candidate or candidate.lower() == "all":
            continue
        normalized.append(candidate)
    return normalized


def build_where_clause(
    defined_market_name: Any = "{defined_market_name}",
    publishing_group: Any = "{publishing_group}",
    start_period: Any = "{start_period}",
    current_quarter: Any = "{current_quarter}",
    vacancy_index: str | Sequence[str] | None = None,
    submarket: str | Sequence[str] | None = None,
    district: str | Sequence[str] | None = None,
) -> str:
    """Construct a reusable WHERE clause for geography-aware queries."""
    vacancy_values = _normalize_selection(vacancy_index)
    submarket_values = [_escape_sql_literal(value) for value in _normalize_selection(submarket)]
    district_values = [_escape_sql_literal(value) for value in _normalize_selection(district)]

    parts = [
        f"where defined_market_name = {_coerce_literal_or_placeholder(defined_market_name)}",
        f"  and publishing_group = {_coerce_literal_or_placeholder(publishing_group)}",
        f"  and period between {_coerce_literal_or_placeholder(start_period)} and {_coerce_literal_or_placeholder(current_quarter)}",
    ]

    if district_values:
        breakdown = "Market | Vacancy Index | Submarket | District"
    elif submarket_values:
        breakdown = "Market | Vacancy Index | Submarket"
    elif vacancy_values:
        breakdown = "Market | Vacancy Index"
    else:
        breakdown = "*TOTAL*"

    parts.append(f"  and breakdown_full_desc = '{breakdown}'")

    if vacancy_values:
        parts.append(f"  and vacancy_index = '{_escape_sql_literal(vacancy_values[0])}'")

    if submarket_values:
        parts.append(f"  and submarket = '{submarket_values[0]}'")

    if district_values:
        parts.append(f"  and district = '{district_values[0]}'")

    return "\n".join(parts)


def _build_submarket_query_builder(report_params: Mapping[str, Any]) -> Callable[[str], str]:
    where_clause = build_where_clause(
        defined_market_name="{defined_market_name}",
        publishing_group="{publishing_group}",
        start_period="{start_period}",
        current_quarter="{current_quarter}",
        vacancy_index=report_params.get("vacancy_index"),
        submarket=report_params.get("submarket"),
        district=report_params.get("district"),
    )

    base_template = _SUBMARKET_TICKER_QUERY_TEMPLATE.replace("{WHERE_CLAUSE}", where_clause)

    def build_query(metric_select: str) -> str:
        return _render_query(base_template, metric_select, report_params)

    return build_query


def fetch_ticker_data(report_params: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Fetch market-level ticker data (vacancy, absorption, deliveries, etc.)."""
    def build_query(metric_select: str) -> str:
        return _render_query(_BASE_TICKER_QUERY_TEMPLATE, metric_select, report_params)

    ticker_rows = _collect_metric_rows(_DEFAULT_TICKER_METRICS, build_query)
    return _build_ticker_payload(ticker_rows)


def fetch_submarket_ticker_data(report_params: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Fetch ticker data for custom geographies (vacancy index, submarket, district)."""
    query_builder = _build_submarket_query_builder(report_params)
    ticker_rows = _collect_metric_rows(_SUBMARKET_TICKER_METRICS, query_builder)
    return _build_ticker_payload(ticker_rows)


def ticker_data_resolver(report_params: Mapping[str, Any], property_sub_type: str | None = None):
    """Resolve the correct ticker data fetcher based on property sub type."""
    if (property_sub_type or "").lower() == "submarket":
        return fetch_submarket_ticker_data(report_params)
    return fetch_ticker_data(report_params)

def arrange_ticker_data(
    ticker_payload: dict,
    *,
    asking_rate_type: str | None = None,
    monthly_yearly_select: str | None = None,
) -> dict:
    raw = ticker_payload.get("raw") or {}
    formatted = ticker_payload.get("formatted") or {}

    def resolve_trend(current_key: str, previous_key: str) -> str:
        current = raw.get(current_key)
        previous = raw.get(previous_key)
        if current is None or previous is None:
            return "neutral"
        if current > previous:
            return "up"
        if current < previous:
            return "down"
        return "neutral"

    def resolve_lease_rate_label() -> str:
        resolved_field = get_asking_rate_field(
            asking_rate_type or "average",
            monthly_yearly_select or "Yearly",
        )
        field_hint = (resolved_field or "").lower()
        if "gross" in field_hint:
            rate_type = "FSG"
        elif "net" in field_hint:
            rate_type = "NNN"
        else:
            rate_type = "AVG"

        frequency = (monthly_yearly_select or "").strip().lower()
        if frequency == "monthly":
            rate_type = f"{rate_type}/MTH"
        else:
            rate_type = f"{rate_type}/YR"

        return f"{rate_type} Direct Lease Rate"

    lease_rate_label = resolve_lease_rate_label()

    mappings = [
        {
            "output_key": "vacancy_rate",
            "label": "Vacancy Rate",
            "formatted_key": "vacancy",
            "current_key": "current_vacancy",
            "previous_key": "previous_vacancy",
        },
        {
            "output_key": "sf_net_absorption",
            "label": "SF Net Absorption",
            "formatted_key": "absorption",
            "current_key": "current_absorption",
            "previous_key": "previous_absorption",
        },
        {
            "output_key": "sf_construction_delivered",
            "label": "SF Construction Delivered",
            "formatted_key": "deliveries",
            "current_key": "current_deliveries",
            "previous_key": "previous_deliveries",
        },
        {
            "output_key": "sf_under_construction",
            "label": "SF Under Construction",
            "formatted_key": "construction",
            "current_key": "current_construction",
            "previous_key": "previous_construction",
        },
        {
            "output_key": "lease_rate",
            "label": lease_rate_label,
            "formatted_key": "asking_rate",
            "current_key": "current_asking_rate",
            "previous_key": "previous_asking_rate",
        },
    ]

    arranged = {}
    for mapping in mappings:
        arranged[mapping["output_key"]] = {
            "label": mapping["label"],
            "value": formatted.get(mapping["formatted_key"]),
            "trend": resolve_trend(mapping["current_key"], mapping["previous_key"]),
        }
    return arranged


def _build_geography_items(report_meta: dict) -> list[tuple[str | None, str | None, str | None]]:
    """Build list of (market, geo_item, geo_level) tuples from report metadata.
    
    Used for multi-geography property sub types to iterate over each geography selection.
    """
    # Extract market - enforce single market for multi-geography
    defined_markets = report_meta.get("defined_markets") or []
    if isinstance(defined_markets, str):
        defined_markets = [defined_markets]
    market = defined_markets[0] if defined_markets else None
    
    # Build list of geography selections
    specific_geographies: list[tuple[str, str]] = []
    
    vacancy_index = report_meta.get("vacancy_index") or []
    if isinstance(vacancy_index, str):
        vacancy_index = [vacancy_index]
    for item in vacancy_index:
        if item and item != "All":
            specific_geographies.append((item, "Vacancy Index"))
    
    submarket = report_meta.get("submarket") or []
    if isinstance(submarket, str):
        submarket = [submarket]
    for item in submarket:
        if item and item != "All":
            specific_geographies.append((item, "Submarket"))
    
    district = report_meta.get("district") or []
    if isinstance(district, str):
        district = [district]
    for item in district:
        if item and item != "All":
            specific_geographies.append((item, "District"))
    
    if not specific_geographies:
        return [(market, None, None)]
    
    return [(market, item, level) for item, level in specific_geographies]


def _build_geography_display_name(
    market: str | None,
    geo_item: str | None,
    geo_level: str | None,
) -> str:
    """Build a display name for the geography combination."""
    parts = []
    if market:
        parts.append(market)
    if geo_item:
        parts.append(geo_item)
    return "-".join(parts) if parts else "Unknown"


def fetch_multi_market_hero_fields(
    report_meta: dict,
    property_sub_type: str | None = None,
    asking_rate_type: str | None = None,
    asking_rate_frequency: str | None = None,
) -> dict[str, Any]:
    """Fetch hero_fields for all markets/geographies in report.
    
    For regular reports: iterates over markets.
    For multi-geography reports (submarket): iterates over each geography combination.
    
    Args:
        report_meta: Report metadata dictionary containing defined_markets and geography selections
        property_sub_type: Property sub-type (e.g., "submarket")
        asking_rate_type: Type of asking rate (e.g., "average")
        asking_rate_frequency: Frequency for asking rate (e.g., "Yearly")
    
    Returns:
        dict with display names as keys: 
        - For regular: {"Denver": {"stats": {...}}, "NYC": {"stats": {...}}}
        - For multi-geography: {"Denver-Downtown": {"stats": {...}}, "Denver-Midtown": {"stats": {...}}}
    """
    from hello.services.config import settings
    
    defined_markets = report_meta.get("defined_markets") or []
    if not defined_markets:
        logger.warning("fetch_multi_market_hero_fields: No defined_markets found")
        return {}
    
    # Check if this is a multi-geography property sub type
    is_multi_geography = (property_sub_type or "").lower() in [
        pst.lower() for pst in settings.MULTI_GEOGRAPHY_PROPERTY_SUB_TYPES
    ]
    
    result: dict[str, Any] = {}
    
    if is_multi_geography:
        # Build items to process (geography combinations)
        items_to_process = _build_geography_items(report_meta)
        
        if len(defined_markets) > 1:
            logger.warning(
                "fetch_multi_market_hero_fields: Multiple markets for multi-geography. "
                "Using first market only: %s",
                defined_markets[0]
            )
        
        logger.info(
            "fetch_multi_market_hero_fields: Multi-geography mode with %d combinations",
            len(items_to_process)
        )
        
        for market, geo_item, geo_level in items_to_process:
            display_name = _build_geography_display_name(market, geo_item, geo_level)
            try:
                # Create temporary meta with single market and single geography
                temp_meta = dict(report_meta)
                temp_meta["defined_markets"] = [market] if market else []
                
                # Reset all geography selections and set only the current one
                temp_meta["vacancy_index"] = []
                temp_meta["submarket"] = []
                temp_meta["district"] = []
                
                if geo_item and geo_level:
                    if geo_level == "Vacancy Index":
                        temp_meta["vacancy_index"] = [geo_item]
                    elif geo_level == "Submarket":
                        temp_meta["submarket"] = [geo_item]
                    elif geo_level == "District":
                        temp_meta["district"] = [geo_item]
                
                # Fetch ticker data for this geography combination
                ticker_data = ticker_data_resolver(temp_meta, property_sub_type)
                
                if not ticker_data:
                    logger.warning(
                        "fetch_multi_market_hero_fields: No ticker data for %s",
                        display_name
                    )
                    continue
                
                # Arrange the ticker data
                arranged_data = arrange_ticker_data(
                    ticker_data,
                    asking_rate_type=asking_rate_type,
                    monthly_yearly_select=asking_rate_frequency,
                )
                
                # Store in result with display name as key
                result[display_name] = {"stats": arranged_data}
                logger.info(
                    "fetch_multi_market_hero_fields: Successfully fetched data for %s",
                    display_name
                )
                
            except Exception as err:
                logger.warning(
                    "fetch_multi_market_hero_fields: Failed to fetch data for %s: %s",
                    display_name,
                    str(err),
                )
                continue
    else:
        # Regular market iteration
        for market in defined_markets:
            try:
                # Create temporary meta with single market for this iteration
                temp_meta = dict(report_meta)
                temp_meta["defined_markets"] = [market]
                
                # Fetch ticker data for this market
                ticker_data = ticker_data_resolver(temp_meta, property_sub_type)
                
                if not ticker_data:
                    logger.warning("fetch_multi_market_hero_fields: No ticker data for market %s", market)
                    continue
                
                # Arrange the ticker data
                arranged_data = arrange_ticker_data(
                    ticker_data,
                    asking_rate_type=asking_rate_type,
                    monthly_yearly_select=asking_rate_frequency,
                )
                
                # Store in result with market as key
                result[market] = {"stats": arranged_data}
                logger.info("fetch_multi_market_hero_fields: Successfully fetched data for market %s", market)
                
            except Exception as err:
                logger.warning(
                    "fetch_multi_market_hero_fields: Failed to fetch data for market %s: %s",
                    market,
                    str(err),
                )
                # Continue processing other markets even if one fails
                continue
    
    return result


def normalize_feedback_prompt_entries(value: list | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in value or []:
        if item is None:
            continue
        if isinstance(item, dict):
            feedback = str(item.get("feedback") or "").strip()
            commentary = str(item.get("commentary") or "").strip()
            timestamp_raw = item.get("timestamp")
        elif hasattr(item, "model_dump"):
            data = item.model_dump()
            feedback = str(data.get("feedback") or "").strip()
            commentary = str(data.get("commentary") or "").strip()
            timestamp_raw = data.get("timestamp")
        else:
            feedback = str(item).strip()
            commentary = ""
            timestamp_raw = None

        timestamp = (
            str(timestamp_raw).strip()
            if isinstance(timestamp_raw, str) and str(timestamp_raw).strip()
            else datetime.utcnow().isoformat() + "Z"
        )

        normalized.append(
            {
                "feedback": feedback,
                "commentary": commentary,
                "timestamp": timestamp,
            }
        )
    return normalized
