

from hello.services.snowflake_service import fetch_snowflake_data
from hello.utils.sql_utils import render_sql_template, get_asking_rate_field
from hello.utils.commentary_utils.utils import get_net_gross_formatting, ensure_all_periods, ensure_all_classes
from typing import Any, Tuple
import pandas as pd
import numpy as np
from hello.ml.logger import GLOBAL_LOGGER as logger


# --- Config-driven SQL templates and query definitions ---
METRICS_CONFIG = {
    "total_market": {
        "sql_template": """
            SELECT
                period,
                CONCAT(SUBSTR(period, 6, 2), ' ', SUBSTR(period, 1, 4)) AS period_label,
                property_class,
                CAST({qtd_absorption} AS INT) AS net_absorption,
                ROUND(vacant_total_percent * 100, 1) AS vacant_total_percent,
                ROUND(available_total_percent * 100, 1) AS available_total_percent,
                ROUND(available_direct_percent * 100, 1) AS available_direct_percent,
                ROUND(available_sublease_percent * 100, 1) AS available_sublease_percent,
                under_construction_area,
                under_construction_property_count,
                delivered_construction_area,
                delivered_construction_property_count,
                ROUND({asking_rate_field}, 2) AS avg_asking_rate
            FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
            WHERE defined_market_name = {defined_market_name}
                AND breakdown_full_desc = '*TOTAL*'
                AND publishing_group = {publishing_group}
                AND period BETWEEN {start_period} AND {current_quarter}
            ORDER BY period ASC
        """,
        "postprocess": None,
    },
    "property_class": {
        "sql_template": """
            SELECT
                period,
                CONCAT(SUBSTR(period, 6, 2), ' ', SUBSTR(period, 1, 4)) AS period_label,
                property_class,
                CAST({qtd_absorption} AS INT) AS net_absorption,
                ROUND(vacant_total_percent * 100, 1) AS vacant_total_percent,
                ROUND(available_total_percent * 100, 1) AS available_total_percent,
                ROUND(available_direct_percent * 100, 1) AS available_direct_percent,
                ROUND(available_sublease_percent * 100, 1) AS available_sublease_percent,
                under_construction_area,
                under_construction_property_count,
                delivered_construction_area,
                delivered_construction_property_count,
                ROUND({asking_rate_field}, 2) AS avg_asking_rate
            FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
            WHERE defined_market_name = {defined_market_name}
                AND breakdown_full_desc = 'Property Class'
                AND publishing_group = {publishing_group}
                AND period BETWEEN {start_period} AND {current_quarter}
            ORDER BY period ASC
        """,
        "postprocess": None,
    },
    "total_lease_activity": {
        "sql_template": """
            SELECT
                period,
                COUNT(period) as total_leased_count,
                CAST(SUM(leased_area) AS INT) AS total_area_leased_sf
            FROM PROD_USDM_DB.REPORTING_ALL.AGGREGATE_TRANSACTION_DETAIL
            WHERE period BETWEEN {start_period} AND {current_quarter}
                AND {dynamic_filters}
                AND lease_transaction_type IN ('New Lease', 'Renewal')
                AND lease_record_type IN ('Lease Comp', 'Transaction', 'Partial Lease Comp')
                AND leased_area >= {min_transaction_size}
            GROUP BY period
            ORDER BY period ASC
        """,
        "postprocess": None,
    },
    "class_lease_activity": {
        "sql_template": """
            SELECT
                period,
                property_class,
                COUNT(period) as total_leased_count,
                CAST(SUM(leased_area) AS INT) AS total_area_leased_sf
            FROM PROD_USDM_DB.REPORTING_ALL.AGGREGATE_TRANSACTION_DETAIL
            WHERE period BETWEEN {start_period} AND {current_quarter}
                AND {dynamic_filters}
                AND lease_transaction_type IN ('New Lease', 'Renewal')
                AND lease_record_type IN ('Lease Comp', 'Transaction', 'Partial Lease Comp')
                AND leased_area >= {min_transaction_size}
            GROUP BY period, property_class
            ORDER BY period ASC
        """,
        "postprocess": None,
    },
}

def _fetch_metric_df(metric_key: str, params: dict) -> pd.DataFrame:
    """Fetch a metric DataFrame using config-driven SQL."""
    logger.info(f"Fetching metric DataFrame for key={metric_key}")
    config = METRICS_CONFIG[metric_key]
    sql = render_sql_template(config["sql_template"], {"report_parameters": params, "section": {"property_sub_type": params.get("property_sub_type", "Figures")}})
    df = pd.DataFrame(fetch_snowflake_data(sql))
    if not df.empty:
        df.columns = df.columns.str.lower()
    if config["postprocess"]:
        df = config["postprocess"](df)
    return df

def fetch_calculated_metrics_data(generation_params: dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    logger.debug(f"fetch_calculated_metrics_data called with generation_params={generation_params}")

    # Fetch all metric DataFrames using config
    total_market_df = _fetch_metric_df("total_market", generation_params)
    property_class_df = _fetch_metric_df("property_class", generation_params)
    total_lease_activity_df = _fetch_metric_df("total_lease_activity", generation_params)
    class_lease_activity_df = _fetch_metric_df("class_lease_activity", generation_params)

    # --- DataFrame post-processing (modularized) ---
    all_periods = pd.Series(sorted(set(total_market_df['period']).union(total_lease_activity_df['period'])))
    total_market_df = ensure_all_periods(total_market_df, 'period', all_periods, fill_value=0)
    total_lease_activity_df = ensure_all_periods(total_lease_activity_df, 'period', all_periods, fill_value=0)

    formatted_asking_rate = get_net_gross_formatting(
        get_asking_rate_field(generation_params['asking_rate_type'], generation_params['asking_rate_frequency']),
        str(generation_params["asking_rate_frequency"])
    )
    total_market_df["avg_asking_rate_type"] = formatted_asking_rate
    property_class_df["avg_asking_rate_type"] = formatted_asking_rate

    # filter out blank property class
    property_class_df = property_class_df[property_class_df['property_class'] != '[blank]']
    class_lease_activity_df = class_lease_activity_df[class_lease_activity_df['property_class'] != '[blank]']

    # filter to just class A and B
    property_class_df = property_class_df[property_class_df['property_class'].isin(['Class A', 'Class B'])]
    class_lease_activity_df = class_lease_activity_df[class_lease_activity_df['property_class'].isin(['Class A', 'Class B'])]

    # Ensure every period has both Class A and Class B rows in property_class_df and class_lease_activity_df
    property_class_df = ensure_all_classes(property_class_df, 'period', 'property_class', ['Class A', 'Class B'], fill_value=0)
    class_lease_activity_df = ensure_all_classes(class_lease_activity_df, 'period', 'property_class', ['Class A', 'Class B'], fill_value=0)

    # Join total_market_df with total_lease_activity_df on 'period'
    total_market_df = pd.merge(
        total_market_df,
        total_lease_activity_df[['period', 'total_leased_count', 'total_area_leased_sf']],
        on='period',
        how='left'
    )

    # Join property_class_df with class_lease_activity_df on 'period' and 'property_class'
    property_class_df = pd.merge(
        property_class_df,
        class_lease_activity_df[['period', 'property_class', 'total_leased_count', 'total_area_leased_sf']],
        on=['period', 'property_class'],
        how='left'
    )

    logger.debug("DataFrames fetched and processed.")
    return total_market_df, property_class_df
