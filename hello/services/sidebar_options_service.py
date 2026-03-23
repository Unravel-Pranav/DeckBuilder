from __future__ import annotations

from typing import List, Optional

from hello.ml.utils.snowflake_connector import SnowflakeConnector
from hello.utils.sql_utils import escape_single_quotes
from hello.ml.logger import GLOBAL_LOGGER as logger


def _run_query(query: str) -> list[dict]:
    """Execute a Snowflake query and return raw rows."""
    connector = SnowflakeConnector()
    try:
        return connector.execute_query(query)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception(
            "Snowflake sidebar query failed",
            extra={"query_preview": query[:200]},
        )
        raise


def _extract(row: dict, key: str) -> Optional[str]:
    """Safely extract a string value from a Snowflake row."""
    value = row.get(key) or row.get(key.lower()) or row.get(key.upper())
    if value is None:
        return None
    return str(value).strip()


def fetch_divisions() -> List[str]:
    """Return distinct divisions excluding New England."""
    query = """
        select distinct division
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where division not like '%New England%'
        order by division
    """
    rows = _run_query(query)
    return [div for row in rows if (div := _extract(row, "division"))]



def fetch_publishing_groups(division: str) -> List[str]:
    """Return publishing groups for a division filtered to Office/Industrial markets."""
    division = escape_single_quotes(division) or ""
    query = f"""
        select distinct publishing_group
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where division = '{division}'
          and defined_market_sector in ('Industrial', 'Office')
          and defined_market_name not like '%REFERENCE ONLY%'
        order by publishing_group
    """
    rows = _run_query(query)
    return [pg for row in rows if (pg := _extract(row, "publishing_group"))]



def fetch_property_types(division: str, publishing_group: str) -> List[str]:
    """Return property types available for the division + publishing group."""
    division = escape_single_quotes(division) or ""
    publishing_group = escape_single_quotes(publishing_group) or ""
    query = f"""
        select distinct defined_market_sector
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where division = '{division}'
          and publishing_group = '{publishing_group}'
          and defined_market_name not like '%REFERENCE ONLY%'
        order by defined_market_sector
    """
    rows = _run_query(query)

    def _normalize(pt: str) -> Optional[str]:
        lower = pt.lower()
        if "industrial" in lower:
            return "Industrial"
        if "office" in lower:
            return "Office"
        return pt

    results = []
    for row in rows:
        raw = _extract(row, "defined_market_sector")
        if not raw:
            continue
        norm = _normalize(raw)
        if norm and norm not in results:
            results.append(norm)
    return results



def fetch_markets(
    division: str, publishing_group: str, property_type: str
) -> List[str]:
    """Return markets filtered by division/publishing group/property type."""
    division = escape_single_quotes(division) or ""
    publishing_group = escape_single_quotes(publishing_group) or ""
    property_type = escape_single_quotes(property_type) or ""

    where_clauses = [
        f"division = '{division}'",
        f"publishing_group = '{publishing_group}'",
        "defined_market_sector in ('Industrial','Office')",
        "defined_market_name not like '%REFERENCE ONLY%'",
        "defined_market_name not like '%R&D%'",
        "defined_market_name not like '%Medical%'",
        "defined_market_name not like '%San Francisco Metro Office%'",
        "defined_market_name not like '%Fairfield County Office%'",
        "defined_market_name not like '%Hartford Office%'",
        "defined_market_name not like '%Long Island Office%'",
        "defined_market_name not like '%Westchester County Office%'",
    ]

    where_clause = " AND ".join(where_clauses)
    query = f"""
        select distinct defined_market_name
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where {where_clause}
        order by defined_market_name
    """
    rows = _run_query(query)
    markets: list[str] = []
    property_type_lower = property_type.lower()

    for row in rows:
        name = _extract(row, "defined_market_name")
        if not name:
            continue
        if property_type_lower in {"industrial", "office"}:
            # Ensure the market name matches the requested property type
            if property_type_lower not in name.lower():
                continue
        markets.append(name)

    return markets



def fetch_quarters(
    defined_market_name: str, publishing_group: str, limit: int = 3
) -> List[str]:
    """Return the most recent quarters for a market + publishing group."""
    market = escape_single_quotes(defined_market_name) or ""
    publishing_group = escape_single_quotes(publishing_group) or ""
    limit = max(1, min(limit, 12))  # defensive bounds

    query = f"""
        select distinct period
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where publishing_group = '{publishing_group}'
          and defined_market_name = '{market}'
        order by period desc
        limit {limit}
    """
    rows = _run_query(query)
    return [q for row in rows if (q := _extract(row, "period"))]


def fetch_vacancy_indices(defined_market_name: str) -> List[str]:
    """Return vacancy index values for a market, ensuring 'All' is present first."""
    market = escape_single_quotes(defined_market_name) or ""
    query = f"""
        select distinct
            case when vacancy_index = '*TOTAL*' then 'All' else vacancy_index end as vacancy_index
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where defined_market_name = '{market}'
        order by vacancy_index
    """
    rows = _run_query(query)
    options = [v for row in rows if (v := _extract(row, "vacancy_index"))]
    if "All" in options:
        options.remove("All")
    options.insert(0, "All")
    return options



def fetch_submarkets(
    defined_market_name: str, vacancy_index: Optional[List[str]] = None
) -> List[str]:
    """Return submarkets for a market; optionally filter by one or more vacancy indices."""
    market = escape_single_quotes(defined_market_name) or ""
    where_clause = f"where defined_market_name = '{market}'"

    # Support filtering by multiple vacancy_index values; treat "All" as no filter.
    if vacancy_index:
        cleaned_values = [
            escape_single_quotes(v)
            for v in vacancy_index
            if v and v != "All"
        ]
        if cleaned_values:
            in_list = ", ".join(f"'{v}'" for v in cleaned_values)
            where_clause += f" and vacancy_index in ({in_list})"

    query = f"""
        select distinct
            case when submarket = '*TOTAL*' then 'All' else submarket end as submarket
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        {where_clause}
        order by submarket
    """
    rows = _run_query(query)
    options = [s for row in rows if (s := _extract(row, "submarket"))]
    if "All" in options:
        options.remove("All")
    options.insert(0, "All")
    return options


def fetch_submarkets_new(defined_market_name: str) -> List[str]:
    """Return distinct submarkets for a market, placing 'All' first."""
    market = escape_single_quotes(defined_market_name) or ""
    query = f"""
        select distinct
            case when submarket = '*TOTAL*' then 'All' else submarket end as submarket
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where defined_market_name = '{market}'
        order by submarket
    """
    rows = _run_query(query)
    options = [s for row in rows if (s := _extract(row, "submarket"))]
    if "All" in options:
        options.remove("All")
    options.insert(0, "All")
    return options


def fetch_districts(
    defined_market_name: str,
    vacancy_index: Optional[List[str]] = None,
    submarket: Optional[List[str]] = None,
) -> List[str]:
    """Return districts for a market; optionally filter by vacancy index/submarket."""
    market = escape_single_quotes(defined_market_name) or ""
    where_clause = f"where defined_market_name = '{market}'"

    # Optional filter by one or more vacancy indices; "All" means no filter.
    if vacancy_index:
        cleaned_values = [
            escape_single_quotes(v)
            for v in vacancy_index
            if v and v != "All"
        ]
        if cleaned_values:
            in_list = ", ".join(f"'{v}'" for v in cleaned_values)
            where_clause += f" and vacancy_index in ({in_list})"

    # Optional filter by one or more submarkets; "All" means no filter.
    if submarket:
        cleaned_submarkets = [
            escape_single_quotes(s)
            for s in submarket
            if s and s != "All"
        ]
        if cleaned_submarkets:
            in_list = ", ".join(f"'{s}'" for s in cleaned_submarkets)
            where_clause += f" and submarket in ({in_list})"

    query = f"""
        select distinct
            case when district = '*TOTAL*' then 'All' else district end as district
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        {where_clause}
        order by district
    """
    rows = _run_query(query)
    options = [d for row in rows if (d := _extract(row, "district"))]
    if "All" in options:
        options.remove("All")
    options.insert(0, "All")
    return options


def fetch_districts_new(defined_market_name: str) -> List[str]:
    """Return distinct districts for a market, placing 'All' first."""
    market = escape_single_quotes(defined_market_name) or ""
    query = f"""
        select distinct
            case when district = '*TOTAL*' then 'All' else district end as district
        from PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
        where defined_market_name = '{market}'
        order by district
    """
    rows = _run_query(query)
    options = [d for row in rows if (d := _extract(row, "district"))]
    if "All" in options:
        options.remove("All")
    options.insert(0, "All")
    return options


__all__ = [
    "fetch_divisions",
    "fetch_publishing_groups",
    "fetch_property_types",
    "fetch_markets",
    "fetch_quarters",
    "fetch_vacancy_indices",
    "fetch_submarkets",
    "fetch_submarkets_new",
    "fetch_districts",
    "fetch_districts_new",
]
