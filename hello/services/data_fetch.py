from __future__ import annotations

from typing import Any, Iterable
import asyncio
import concurrent.futures

from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger


_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    return _EXECUTOR


def _snowflake_available() -> bool:
    return all(
        [
            settings.snowflake_account,
            settings.snowflake_user,
            getattr(settings, "snowflake_password", None),
            settings.snowflake_warehouse,
            settings.snowflake_database,
            settings.snowflake_schema,
        ]
    )


def _sf_connect():
    import snowflake.connector  # lazy import

    return snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=getattr(settings, "snowflake_password", None),
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=settings.snowflake_schema,
        client_session_keep_alive=True,
    )


def _rows_to_dicts(cur) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


SECTION_SQL: dict[str, tuple[str, Iterable[str]]] = {
    # section key (lower) → (sql, ordered param names)
    "chart 1": (
        """
        SELECT quarter, net_absorption, vacancy_rate
        FROM market_data
        WHERE property_type = %s AND market = %s
        ORDER BY quarter
        """,
        ("property_type", "market"),
    ),
    "table 2": (
        """
        SELECT metric_name AS metric, current_value AS current, previous_value AS previous,
               change_pct AS change
        FROM supporting_metrics
        WHERE property_type = %s AND market = %s
        ORDER BY metric_name
        """,
        ("property_type", "market"),
    ),
    "commentary 3": (
        """
        SELECT summary AS text
        FROM market_commentary
        WHERE property_type = %s AND market = %s
        ORDER BY period DESC
        LIMIT 1
        """,
        ("property_type", "market"),
    ),
}


async def fetch_section_data(
    section: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fetch section data from Snowflake if credentials are configured; otherwise
    return deterministic dummy data for development.

    Section queries are looked up by name in SECTION_SQL; falls back to dummy when
    the section is unknown.
    """
    key = section.lower()
    if _snowflake_available() and key in SECTION_SQL:
        sql, order = SECTION_SQL[key]
        args = [
            params.get("property_type", "Office"),
            params.get("market", "Oakland Office"),
        ]

        def _run_query() -> list[dict[str, Any]]:
            conn = _sf_connect()
            try:
                cur = conn.cursor()
                try:
                    cur.execute(sql, args)
                    return _rows_to_dicts(cur)
                finally:
                    cur.close()
            except Exception as e:
                logger.exception("Snowflake query failed", exc_info=e)
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        loop_executor = _get_executor()
        try:
            return await asyncio.get_event_loop().run_in_executor(loop_executor, _run_query)
        except Exception:
            # Fall back to dummy data on failure
            logger.warning("Falling back to dummy data for section '%s'", section)
            # continue to dummy fallbacks below
            pass

    # Fallback dummy data
    if key.startswith("chart"):
        return [
            {
                "quarter": f"Q{i} 202{3 + (i > 4)}",
                "net_absorption": 600 + i * 40,
                "vacancy_rate": 12.5 - i * 0.2,
            }
            for i in range(1, 9)
        ]
    if key.startswith("table"):
        return [
            {
                "metric": "Vacancy Rate",
                "current": "12.8%",
                "previous": "13.2%",
                "change": "-0.4%",
            },
            {
                "metric": "Avg Rent PSF",
                "current": "$68.50",
                "previous": "$67.80",
                "change": "+$0.70",
            },
            {
                "metric": "Net Absorption",
                "current": "2.4M SF",
                "previous": "2.2M SF",
                "change": "+0.2M SF",
            },
        ]
    return [
        {"text": "The Northeast office market displayed robust momentum in Q4 2024."}
    ]
