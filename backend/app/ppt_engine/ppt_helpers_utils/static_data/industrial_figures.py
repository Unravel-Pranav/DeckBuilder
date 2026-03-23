import pandas as pd
from app.core.config import settings


def fetch_snowflake_data(*args, **kwargs):
    """Stub — Snowflake not available in local dev."""
    return pd.DataFrame()


def render_sql_template(*args, **kwargs):
    """Stub — SQL templates not available in local dev."""
    return ""


def get_quarter_end_date(*args, **kwargs):
    """Stub — returns empty string."""
    return ""


def _config_to_payload(config) -> dict:
    """Convert config object to render_sql_template payload format."""
    return {
        "report_parameters": {
            "defined_markets": config.defined_markets,
            "publishing_group": config.publishing_group,
            "quarter": config.quarter,
            "asking_rate_type": config.asking_rate_type,
            "asking_rate_frequency": config.asking_rate_frequency,
            "absorption_calculation": config.absorption_calculation,
            "total_vs_direct_absorption": config.total_vs_direct_absorption,
        }
    }


def asking_rate_calc(
    df: pd.DataFrame, asking_rate_type: str, monthly_yearly_select: str
) -> list[float]:
    """One-line summary: Calculate asking rate from a DataFrame with numerator and denominator columns.

    Computes weighted average asking rates by summing the numerators and denominators
    separately, then dividing, to create proper weighted averages.

    Args:
        df (pd.DataFrame): DataFrame containing asking rate numerator and denominator columns
        asking_rate_type (str): Type of asking rate to calculate ('gross-up', 'net-down', or 'average')
        monthly_yearly_select (str): Time period for rate calculation ('monthly' or 'yearly')

    Returns:
        List[float]: Single-element list containing the calculated asking rate value

    Notes:
        Uses weighted average calculation by summing numerators and denominators first
        Converts to monthly rate by dividing by 12 if monthly_yearly_select is 'monthly'

    Examples:
        >>> df = pd.DataFrame({
        ...     'DIRECT_GROSS_ASKING_RATE_NUMERATOR': [1000, 2000],
        ...     'DIRECT_GROSS_ASKING_RATE_DENOMINATOR': [10, 10]
        ... })
        >>> asking_rate_calc(df, 'gross-up', 'yearly')
        [150.0]  # (1000+2000)/(10+10)
    """
    if not asking_rate_type:
        asking_rate_type = "average"
    if not monthly_yearly_select:
        monthly_yearly_select = "yearly"

    asking_rate_type_lower = asking_rate_type.lower()

    # Determine which numerator/denominator to use based on asking rate type
    if "gross" in asking_rate_type_lower:
        asking_rate = [
            df["DIRECT_GROSS_ASKING_RATE_NUMERATOR"].astype(float).sum()
            / df["DIRECT_GROSS_ASKING_RATE_DENOMINATOR"].astype(float).sum()
        ]
    elif "net" in asking_rate_type_lower:
        asking_rate = [
            df["DIRECT_NET_ASKING_RATE_NUMERATOR"].astype(float).sum()
            / df["DIRECT_NET_ASKING_RATE_DENOMINATOR"].astype(float).sum()
        ]
    else:
        # Default to gross for 'average' or any other type
        asking_rate = [
            df["DIRECT_GROSS_ASKING_RATE_NUMERATOR"].astype(float).sum()
            / df["DIRECT_GROSS_ASKING_RATE_DENOMINATOR"].astype(float).sum()
        ]

    # Convert to monthly rate if specified
    if monthly_yearly_select.lower() == "monthly":
        asking_rate = [rate / 12 for rate in asking_rate]

    return asking_rate


def asking_rate_label(asking_rate_type: str, monthly_yearly_select: str) -> str:
    """One-line summary: Generate human-readable labels for asking rate fields.

    Creates a descriptive label for asking rates based on the rate type and period.

    Args:
        asking_rate_type (str): Type of asking rate ('gross-up', 'net-down', or 'average')
        monthly_yearly_select (str): Time period for rate ('monthly' or 'yearly')

    Returns:
        str: Human-readable label for the asking rate type and period

    Notes:
        FSG = Full Service Gross rate
        NNN = Triple Net rate
        AVG = Average rate (default)
        MTH = Monthly rate
        YR = Yearly rate

    Examples:
        >>> asking_rate_label('gross-up', 'monthly')
        'Avg. Direct Asking Rate (FSG/MTH)'
        >>> asking_rate_label('net-down', 'yearly')
        'Avg. Direct Asking Rate (NNN/YR)'
        >>> asking_rate_label('average', 'yearly')
        'Avg. Direct Asking Rate (AVG/YR)'
    """
    if not asking_rate_type:
        asking_rate_type = "average"
    if not monthly_yearly_select:
        monthly_yearly_select = "yearly"

    asking_rate_type_lower = asking_rate_type.lower()

    # Determine label based on asking rate type
    if "gross" in asking_rate_type_lower:
        if monthly_yearly_select.lower() == "monthly":
            asking_rate_label = "Avg. Direct Asking Rate (FSG/MTH)"
        else:
            asking_rate_label = "Avg. Direct Asking Rate (FSG/YR)"
    elif "net" in asking_rate_type_lower:
        if monthly_yearly_select.lower() == "monthly":
            asking_rate_label = "Avg. Direct Asking Rate (NNN/MTH)"
        else:
            asking_rate_label = "Avg. Direct Asking Rate (NNN/YR)"
    else:
        # Default to average label
        if monthly_yearly_select.lower() == "monthly":
            asking_rate_label = "Avg. Direct Asking Rate (AVG/MTH)"
        else:
            asking_rate_label = "Avg. Direct Asking Rate (AVG/YR)"

    return asking_rate_label


# SQL Templates for industrial figures queries
SIZE_BUCKET_SP_TEMPLATE = """
call PROD_USDM_DB.SUPPORTING_INFO.SP_AGGREGATE_PROPERTY_STATS
(
    'PROD_USDM_DB.REPORTING_ALL.SIZE_BUCKET_DATA',
    'defined_market_name',
    {defined_market_name},
    null,
    null,
    'publishing_group = ''' || {publishing_group} || '''',
    {current_quarter_end_date},
    {current_quarter_end_date},
    null,
    'SIZE_BUCKET',
    {size_bucket_definition}
)
"""

SIZE_BUCKET_SELECT_TEMPLATE = """
SELECT
    defined_market_name,
    PERIOD,
    SIZE_BUCKET,
    NET_RENTABLE_AREA,
    VACANT_TOTAL_AREA,
    AVAILABLE_TOTAL_AREA,
    AVAILABLE_DIRECT_AREA,
    AVAILABLE_SUBLEASE_AREA,
    {qtd_absorption} as NET_ABSORPTION_TOTAL,
    {ytd_absorption} as YTD_NET_ABSORPTION_TOTAL,
    DELIVERED_CONSTRUCTION_AREA,
    UNDER_CONSTRUCTION_AREA,
    DIRECT_GROSS_ASKING_RATE_NUMERATOR,
    DIRECT_GROSS_ASKING_RATE_DENOMINATOR,
    DIRECT_NET_ASKING_RATE_NUMERATOR,
    DIRECT_NET_ASKING_RATE_DENOMINATOR,
    VACANT_TOTAL_PERCENT,
    AVAILABLE_TOTAL_PERCENT,
    AVAILABLE_DIRECT_PERCENT,
    AVAILABLE_SUBLEASE_PERCENT,
    BREAKDOWN_FULL_DESC,
    ROUND({asking_rate_field}, 2) AS avg_asking_lease_rate
    FROM prod_usdm_db.reporting_all.size_bucket_data
"""

PRODUCT_TYPE_SP_TEMPLATE = """
call PROD_USDM_DB.SUPPORTING_INFO.SP_AGGREGATE_PROPERTY_STATS
(
    'PROD_USDM_DB.REPORTING_ALL.SIZE_BUCKET_DATA',
    'defined_market_name',
    {defined_market_name},
    null,
    null,
    'publishing_group = ''' || {publishing_group} || '''',
    {current_quarter_end_date},
    {current_quarter_end_date},
    null,
    'PRODUCT_TYPE',
    {product_type_definition}
)
"""

PRODUCT_TYPE_SELECT_TEMPLATE = """
SELECT 
    defined_market_name,
    PERIOD,
    PRODUCT_TYPE,
    NET_RENTABLE_AREA,
    VACANT_TOTAL_AREA,
    AVAILABLE_TOTAL_AREA,
    AVAILABLE_DIRECT_AREA,
    AVAILABLE_SUBLEASE_AREA,
    {qtd_absorption} as NET_ABSORPTION_TOTAL,
    {ytd_absorption} as YTD_NET_ABSORPTION_TOTAL,
    DELIVERED_CONSTRUCTION_AREA,
    UNDER_CONSTRUCTION_AREA,
    DIRECT_GROSS_ASKING_RATE_NUMERATOR,
    DIRECT_GROSS_ASKING_RATE_DENOMINATOR,
    DIRECT_NET_ASKING_RATE_NUMERATOR,
    DIRECT_NET_ASKING_RATE_DENOMINATOR,
    VACANT_TOTAL_PERCENT,
    AVAILABLE_TOTAL_PERCENT,
    AVAILABLE_DIRECT_PERCENT,
    AVAILABLE_SUBLEASE_PERCENT,
    BREAKDOWN_FULL_DESC,
    ROUND({asking_rate_field}, 2) AS avg_asking_lease_rate
    FROM prod_usdm_db.reporting_all.size_bucket_data
"""

INDUSTRIAL_CLASS_SP_TEMPLATE = """
call PROD_USDM_DB.SUPPORTING_INFO.SP_AGGREGATE_PROPERTY_STATS
(
    'PROD_USDM_DB.REPORTING_ALL.SIZE_BUCKET_DATA',
    'defined_market_name',
    {defined_market_name},
    null,
    null,
    'publishing_group = ''' || {publishing_group} || '''',
    {current_quarter_end_date},
    {current_quarter_end_date},
    null,
    'INDUSTRIAL_CLASS',
    {industrial_class_definition}
)
"""

INDUSTRIAL_CLASS_SELECT_TEMPLATE = """
SELECT
    defined_market_name,
    PERIOD,
    INDUSTRIAL_CLASS,
    NET_RENTABLE_AREA,
    VACANT_TOTAL_AREA,
    AVAILABLE_TOTAL_AREA,
    AVAILABLE_DIRECT_AREA,
    AVAILABLE_SUBLEASE_AREA,
    {qtd_absorption} as NET_ABSORPTION_TOTAL,
    {ytd_absorption} as YTD_NET_ABSORPTION_TOTAL,
    DELIVERED_CONSTRUCTION_AREA,
    UNDER_CONSTRUCTION_AREA,
    DIRECT_GROSS_ASKING_RATE_NUMERATOR,
    DIRECT_GROSS_ASKING_RATE_DENOMINATOR,
    DIRECT_NET_ASKING_RATE_NUMERATOR,
    DIRECT_NET_ASKING_RATE_DENOMINATOR,
    VACANT_TOTAL_PERCENT,
    AVAILABLE_TOTAL_PERCENT,
    AVAILABLE_DIRECT_PERCENT,
    AVAILABLE_SUBLEASE_PERCENT,
    BREAKDOWN_FULL_DESC,
    ROUND({asking_rate_field}, 2) AS avg_asking_lease_rate
    FROM prod_usdm_db.reporting_all.size_bucket_data
"""

SUBMARKET_QUERY_TEMPLATE = """
SELECT
    SUBMARKET,
    TRIM(TO_CHAR(CAST(net_rentable_area AS INT), '999,999,999')) AS net_rentable_area,
    ROUND(vacant_total_percent * 100, 1) AS vacant_total_percent,
    ROUND(available_total_percent * 100, 1) AS available_total_percent,
    ROUND(available_direct_percent * 100, 1) AS available_direct_percent,
    ROUND(available_sublease_percent * 100, 1) AS available_sublease_percent,
    ROUND({asking_rate_field}, 2) AS avg_asking_lease_rate,
    CASE 
        WHEN {qtd_absorption} < 0 THEN '(' || TRIM(TO_CHAR(ABS(CAST({qtd_absorption} AS INT)), '999,999,999')) || ')'
        ELSE TRIM(TO_CHAR(CAST({qtd_absorption} AS INT), '999,999,999'))
    END AS net_absorption_total,
    CASE
        WHEN {ytd_absorption} < 0 THEN '(' || TRIM(TO_CHAR(ABS(CAST({ytd_absorption} AS INT)), '999,999,999')) || ')'
        ELSE TRIM(TO_CHAR(CAST({ytd_absorption} AS INT), '999,999,999')) 
    END AS ytd_net_absorption_total,
    TO_CHAR(CAST(delivered_construction_area AS INT), '999,999,999') AS delivered_construction_area,
    TO_CHAR(CAST(under_construction_area AS INT), '999,999,999') AS under_construction_area
FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
WHERE defined_market_name = {defined_market_name}
  AND breakdown_full_desc = 'Market | Vacancy Index | Submarket'
  AND period = {current_quarter}
ORDER BY SUBMARKET ASC
"""

MARKET_TOTAL_QUERY_TEMPLATE = """
SELECT
    SUBMARKET,
    TRIM(TO_CHAR(CAST(net_rentable_area AS INT), '999,999,999,999,999')) AS net_rentable_area,
    ROUND(vacant_total_percent * 100, 1) AS vacant_total_percent,
    ROUND(available_total_percent * 100, 1) AS available_total_percent,
    ROUND(available_direct_percent * 100, 1) AS available_direct_percent,
    ROUND(available_sublease_percent * 100, 1) AS available_sublease_percent,
    ROUND({asking_rate_field}, 2) AS avg_asking_lease_rate,
    CASE 
        WHEN {qtd_absorption} < 0 THEN '(' || TO_CHAR(ABS(CAST({qtd_absorption} AS INT)), '999,999,999') || ')'
        ELSE TO_CHAR(CAST({qtd_absorption} AS INT), '999,999,999')
    END AS net_absorption_total,
    CASE
        WHEN {ytd_absorption} < 0 THEN '(' || TO_CHAR(ABS(CAST({ytd_absorption} AS INT)), '999,999,999') || ')'
        ELSE TO_CHAR(CAST({ytd_absorption} AS INT), '999,999,999') 
    END AS ytd_net_absorption_total,
    TO_CHAR(CAST(delivered_construction_area AS INT), '999,999,999') AS delivered_construction_area,
    TO_CHAR(CAST(under_construction_area AS INT), '999,999,999') AS under_construction_area
FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
WHERE defined_market_name = {defined_market_name}
  AND publishing_group = {publishing_group}
  AND breakdown_full_desc = '*TOTAL*'
  AND period = {current_quarter}
ORDER BY SUBMARKET ASC
"""


def _generate_mock_size_bucket_data(config) -> pd.DataFrame:
    """Generate mock size bucket data for non-CBRE environments."""
    import random

    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    # Create size buckets
    size_buckets = [
        "Under 100,000 sq. ft.",
        "100,000-199,999 sq. ft.",
        "200,000-299,999 sq. ft.",
        "300,000-499,999 sq. ft.",
        "500,000-749,999 sq. ft.",
        "750,000 sq. ft.",
    ]

    mock_data = []
    for bucket in size_buckets:
        # Generate realistic industrial metrics
        net_rentable_area = random.randint(5000000, 15000000)
        vacancy_percent = round(random.uniform(5.0, 8.5), 1)
        available_total_percent = round(random.uniform(7.0, 11.0), 1)
        available_direct_percent = round(random.uniform(5.0, 9.0), 1)
        available_sublease_percent = round(random.uniform(1.5, 3.5), 1)
        avg_asking_rate = round(random.uniform(8.50, 12.75), 2)
        net_absorption = random.randint(-10000, 50000)
        ytd_absorption = random.randint(-50000, 200000)
        deliveries = random.randint(0, 300000)
        under_construction = random.randint(0, 500000)

        mock_data.append(
            {
                "SIZE_BUCKET": bucket,
                "NET_RENTABLE_AREA": net_rentable_area,
                "VACANT_TOTAL_PERCENT": vacancy_percent,
                "AVAILABLE_TOTAL_PERCENT": available_total_percent,
                "AVAILABLE_DIRECT_PERCENT": available_direct_percent,
                "AVAILABLE_SUBLEASE_PERCENT": available_sublease_percent,
                "AVG_ASKING_LEASE_RATE": avg_asking_rate,
                "NET_ABSORPTION_TOTAL": net_absorption,
                "YTD_NET_ABSORPTION_TOTAL": ytd_absorption,
                "DELIVERED_CONSTRUCTION_AREA": deliveries,
                "UNDER_CONSTRUCTION_AREA": under_construction,
            }
        )

    # Create totals row
    total_row = pd.DataFrame(mock_data).sum()
    total_row["SIZE_BUCKET"] = "Total"
    total_row["VACANT_TOTAL_PERCENT"] = round(total_row["VACANT_TOTAL_PERCENT"] / 6, 1)
    total_row["AVAILABLE_TOTAL_PERCENT"] = round(
        total_row["AVAILABLE_TOTAL_PERCENT"] / 6, 1
    )
    total_row["AVAILABLE_DIRECT_PERCENT"] = round(
        total_row["AVAILABLE_DIRECT_PERCENT"] / 6, 1
    )
    total_row["AVAILABLE_SUBLEASE_PERCENT"] = round(
        total_row["AVAILABLE_SUBLEASE_PERCENT"] / 6, 1
    )
    total_row["AVG_ASKING_LEASE_RATE"] = round(
        total_row["AVG_ASKING_LEASE_RATE"] / 6, 2
    )

    mock_data.append(total_row.to_dict())
    return pd.DataFrame(mock_data)


def fetch_industrial_size_bucket_data(config):
    """
    Fetches and processes industrial property data aggregated by size buckets from Snowflake database.
    This function calls a stored procedure to aggregate property statistics, processes the results,
    and returns a formatted DataFrame with metrics broken down by building size ranges.
    Parameters:
        config: Configuration object containing parameters
    Returns:
        pandas.DataFrame: Processed data with the following columns:
            - '' (Size bucket ranges)
            - 'Net Rentable Area' (Total rentable area formatted with commas)
            - 'Total Vacancy' (Percentage with 1 decimal place)
            - 'Total Availability' (Percentage with 1 decimal place)
            - 'Direct Availability' (Percentage with 1 decimal place)
            - 'Sublease Availability' (Percentage with 1 decimal place)
            - 'Avg. Net Direct Asking Rate' (Rate with 2 decimal places)
            - 'Current Quarter Net Absorption' (Integer with commas and parentheses for negative)
            - 'YTD Net Absorption' (Integer with commas and parentheses for negative)
            - 'Deliveries' (Integer with commas)
            - 'Under Construction' (Integer with commas)
    Notes:
        - Size buckets are predefined ranges from "Under 100,000 sq. ft." to "750,000 sq. ft."
        - Includes a "Total" row with aggregated metrics across all size buckets
        - Negative values are formatted with parentheses
        - Temporary table 'size_bucket_data' is dropped after execution
    """
    # Check environment
    env = settings.TESTING_ENV
    if env != "CBRE":
        result = _generate_mock_size_bucket_data(config)
        # Format the mock data to match production output
        asking_rate_type = getattr(config, "asking_rate_type", "average")
        monthly_yearly_select = config.monthly_yearly_select
        asking_rate_label_text = asking_rate_label(
            asking_rate_type, monthly_yearly_select
        )

        # Define the desired order
        size_bucket_order = [
            "Under 100,000 sq. ft.",
            "100,000-199,999 sq. ft.",
            "200,000-299,999 sq. ft.",
            "300,000-499,999 sq. ft.",
            "500,000-749,999 sq. ft.",
            "750,000 sq. ft.",
            "Total",
        ]

        # Sort using the custom order
        result["sort_order"] = result["SIZE_BUCKET"].map(
            {v: i for i, v in enumerate(size_bucket_order)}
        )
        result = result.sort_values("sort_order").drop("sort_order", axis=1)
        result.reset_index(drop=True, inplace=True)

        # Rename columns
        column_mapping = {
            "SIZE_BUCKET": "",
            "NET_RENTABLE_AREA": "Net Rentable Area",
            "VACANT_TOTAL_PERCENT": "Total Vacancy",
            "AVAILABLE_TOTAL_PERCENT": "Total Availability",
            "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
            "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
            "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
            "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
            "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
            "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
            "UNDER_CONSTRUCTION_AREA": "Under Construction",
        }
        result = result.rename(columns=column_mapping)

        # Format columns
        percent_columns = [
            "Total Vacancy",
            "Total Availability",
            "Direct Availability",
            "Sublease Availability",
        ]
        for col in percent_columns:
            result[col] = result[col].apply(lambda x: f"{x:.1f}")

        # Format integer columns with commas
        integer_columns = [
            "Net Rentable Area",
            "Current Quarter Net Absorption",
            "YTD Net Absorption",
            "Deliveries",
            "Under Construction",
        ]
        for col in integer_columns:
            result[col] = result[col].apply(
                lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}"
            )

        # Format asking rate
        result[asking_rate_label_text] = result[asking_rate_label_text].apply(
            lambda x: f"{x:.2f}"
        )

        return result

    # Build payload for render_sql_template
    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    # Create payload for render_sql_template
    payload = _config_to_payload(config)

    # Define size bucket case statement
    # IMPORTANT: Wrap the CASE expression in a Snowflake dollar-quoted string so it is
    # passed as a literal argument to the stored procedure. The previous version
    # sent the raw CASE ... AS SIZE_BUCKET without quoting, causing the parser to
    # see 'AS' as an unexpected token inside the CALL argument list.
    size_bucket_definition = """$$case
            when NET_RENTABLE_AREA_ALL_STATUS < 100000 then 'Under 100,000 sq. ft.'
            when NET_RENTABLE_AREA_ALL_STATUS >= 100000 and NET_RENTABLE_AREA_ALL_STATUS <= 199999 then '100,000-199,999 sq. ft.'
            when NET_RENTABLE_AREA_ALL_STATUS >= 200000 and NET_RENTABLE_AREA_ALL_STATUS <= 299999 then '200,000-299,999 sq. ft.'
            when NET_RENTABLE_AREA_ALL_STATUS >= 300000 and NET_RENTABLE_AREA_ALL_STATUS <= 499999 then '300,000-499,999 sq. ft.'
            when NET_RENTABLE_AREA_ALL_STATUS >= 500000 and NET_RENTABLE_AREA_ALL_STATUS <= 749999 then '500,000-749,999 sq. ft.'
            when NET_RENTABLE_AREA_ALL_STATUS >= 750000 then '750,000 sq. ft.'
        else 'Not In Range' END as SIZE_BUCKET$$"""

    # We need to get the quarter end date for the stored procedure parameters
    current_quarter_end_date = get_quarter_end_date(config.current_quarter)

    # Add custom fields to payload for raw rendering
    payload["current_quarter_end_date"] = current_quarter_end_date
    payload["size_bucket_definition"] = size_bucket_definition

    # Render the stored procedure query using render_sql_template
    query = render_sql_template(SIZE_BUCKET_SP_TEMPLATE, payload)

    # Execute stored procedure as a regular query
    fetch_snowflake_data(query)

    # Render and execute the select query
    select_aggregate_query = render_sql_template(SIZE_BUCKET_SELECT_TEMPLATE, payload)
    result_rows = fetch_snowflake_data(select_aggregate_query)
    result = pd.DataFrame(result_rows)

    # Convert all datetime columns to be timezone unaware
    datetime_columns = [
        col
        for col in result.columns
        if isinstance(result[col].dtype, pd.DatetimeTZDtype)
    ]
    for col in datetime_columns:
        result[col] = result[col].dt.tz_localize(None)

    needed_columns = [
        "SIZE_BUCKET",
        "NET_RENTABLE_AREA",
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
        "AVG_ASKING_LEASE_RATE",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]

    # Filter and create a new DataFrame instead of modifying a view
    size_bucket_rows = result[result["BREAKDOWN_FULL_DESC"] == "Size Bucket"].copy()
    filtered_rows = size_bucket_rows[
        size_bucket_rows["SIZE_BUCKET"].isin(
            [
                "Under 100,000 sq. ft.",
                "100,000-199,999 sq. ft.",
                "200,000-299,999 sq. ft.",
                "300,000-499,999 sq. ft.",
                "500,000-749,999 sq. ft.",
                "750,000 sq. ft.",
            ]
        )
    ].copy()

    # Calculate totals row
    total_row = pd.DataFrame(
        {
            "SIZE_BUCKET": ["Total"],
            "NET_RENTABLE_AREA": [
                filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "VACANT_TOTAL_PERCENT": [
                filtered_rows["VACANT_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_TOTAL_PERCENT": [
                filtered_rows["AVAILABLE_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_DIRECT_PERCENT": [
                filtered_rows["AVAILABLE_DIRECT_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_SUBLEASE_PERCENT": [
                filtered_rows["AVAILABLE_SUBLEASE_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVG_ASKING_LEASE_RATE": asking_rate_calc(
                filtered_rows, asking_rate_type, monthly_yearly_select
            ),
            "NET_ABSORPTION_TOTAL": [
                filtered_rows["NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "YTD_NET_ABSORPTION_TOTAL": [
                filtered_rows["YTD_NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "DELIVERED_CONSTRUCTION_AREA": [
                filtered_rows["DELIVERED_CONSTRUCTION_AREA"].astype(float).sum()
            ],
            "UNDER_CONSTRUCTION_AREA": [
                filtered_rows["UNDER_CONSTRUCTION_AREA"].astype(float).sum()
            ],
        }
    )

    # Combine and create a new DataFrame
    result = pd.concat([filtered_rows[needed_columns], total_row], ignore_index=True)

    # Format columns using loc to avoid warnings
    # Format percentages
    percent_columns = [
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
    ]

    # Convert to float and format percentages with exactly 2 decimal places
    for col in percent_columns:
        # Convert to float first with NaN handling
        result.loc[:, col] = pd.to_numeric(
            result[col], errors="coerce"
        )  # Convert to float
        # Only format non-null values
        result.loc[:, col] = result[col].apply(
            lambda x: "{:.1f}".format(x * 100) if pd.notnull(x) else x
        )
        # Convert back to numeric with NaN handling
        result.loc[:, col] = pd.to_numeric(result[col], errors="coerce")

    # Format average asking rate
    result.loc[:, "AVG_ASKING_LEASE_RATE"] = (
        result["AVG_ASKING_LEASE_RATE"]
        .astype(float)
        .apply(lambda x: "{:.2f}".format(x) if pd.notnull(x) else "-")
    )

    # Format integer columns
    integer_columns = [
        "NET_RENTABLE_AREA",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]
    for col in integer_columns:
        result.loc[:, col] = (
            result[col]
            .astype(float)
            .round(0)
            .astype(int)
            .apply(lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}")
        )
        # Format negative values with parentheses

    asking_rate_label_text = asking_rate_label(asking_rate_type, monthly_yearly_select)

    # Define the desired order
    size_bucket_order = [
        "Under 100,000 sq. ft.",
        "100,000-199,999 sq. ft.",
        "200,000-299,999 sq. ft.",
        "300,000-499,999 sq. ft.",
        "500,000-749,999 sq. ft.",
        "750,000 sq. ft.",
        "Total",
    ]

    # Sort using the custom order
    result["sort_order"] = result["SIZE_BUCKET"].map(
        {v: i for i, v in enumerate(size_bucket_order)}
    )
    result = result.sort_values("sort_order").drop("sort_order", axis=1)
    result.reset_index(drop=True, inplace=True)

    # Rename columns
    column_mapping = {
        "SIZE_BUCKET": "",
        "NET_RENTABLE_AREA": "Net Rentable Area",
        "VACANT_TOTAL_PERCENT": "Total Vacancy",
        "AVAILABLE_TOTAL_PERCENT": "Total Availability",
        "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
        "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
        "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
        "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
        "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
        "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
        "UNDER_CONSTRUCTION_AREA": "Under Construction",
    }
    result = result.rename(columns=column_mapping)

    # Drop custom table
    try:
        fetch_snowflake_data(
            "drop table if exists prod_usdm_db.reporting_all.size_bucket_data"
        )
    except Exception:
        pass

    return result


def _generate_mock_product_type_data(config) -> pd.DataFrame:
    """Generate mock product type data for non-CBRE environments."""
    import random

    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    product_types = [
        "Distribution / Logistics",
        "Manufacturing",
        "R&D / Flex",
        "Other Industrial",
    ]

    mock_data = []
    for product_type in product_types:
        # Generate realistic industrial metrics
        net_rentable_area = random.randint(8000000, 20000000)
        vacancy_percent = round(random.uniform(4.0, 7.5), 1)
        available_total_percent = round(random.uniform(6.0, 10.0), 1)
        available_direct_percent = round(random.uniform(4.5, 8.5), 1)
        available_sublease_percent = round(random.uniform(1.0, 3.0), 1)
        avg_asking_rate = round(random.uniform(7.00, 11.50), 2)
        net_absorption = random.randint(-20000, 80000)
        ytd_absorption = random.randint(-80000, 300000)
        deliveries = random.randint(0, 500000)
        under_construction = random.randint(0, 800000)

        mock_data.append(
            {
                "PRODUCT_TYPE": product_type,
                "NET_RENTABLE_AREA": net_rentable_area,
                "VACANT_TOTAL_PERCENT": vacancy_percent,
                "AVAILABLE_TOTAL_PERCENT": available_total_percent,
                "AVAILABLE_DIRECT_PERCENT": available_direct_percent,
                "AVAILABLE_SUBLEASE_PERCENT": available_sublease_percent,
                "AVG_ASKING_LEASE_RATE": avg_asking_rate,
                "NET_ABSORPTION_TOTAL": net_absorption,
                "YTD_NET_ABSORPTION_TOTAL": ytd_absorption,
                "DELIVERED_CONSTRUCTION_AREA": deliveries,
                "UNDER_CONSTRUCTION_AREA": under_construction,
            }
        )

    # Create totals row
    total_row = pd.DataFrame(mock_data).sum()
    total_row["PRODUCT_TYPE"] = "Total"
    total_row["VACANT_TOTAL_PERCENT"] = round(total_row["VACANT_TOTAL_PERCENT"] / 4, 1)
    total_row["AVAILABLE_TOTAL_PERCENT"] = round(
        total_row["AVAILABLE_TOTAL_PERCENT"] / 4, 1
    )
    total_row["AVAILABLE_DIRECT_PERCENT"] = round(
        total_row["AVAILABLE_DIRECT_PERCENT"] / 4, 1
    )
    total_row["AVAILABLE_SUBLEASE_PERCENT"] = round(
        total_row["AVAILABLE_SUBLEASE_PERCENT"] / 4, 1
    )
    total_row["AVG_ASKING_LEASE_RATE"] = round(
        total_row["AVG_ASKING_LEASE_RATE"] / 4, 2
    )

    mock_data.append(total_row.to_dict())
    return pd.DataFrame(mock_data)


def fetch_industrial_product_type_data(config):
    """Fetch market data aggregated by product type from Snowflake, process it, and return a formatted DataFrame.
    Parameters
    ----------
    config : Config object
        Configuration object containing parameters
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the processed and formatted market data with the following columns:
        - '': Product type category
        - 'Net Rentable Area': Total rentable area (formatted as comma-separated integers)
        - 'Total Vacancy': Vacancy percentage with 1 decimal place
        - 'Total Availability': Availability percentage with 1 decimal place
        - 'Direct Availability': Direct availability percentage with 1 decimal place
        - 'Sublease Availability': Sublease availability percentage with 1 decimal place
        - 'Avg. Net Direct Asking Rate': Average asking rate with 2 decimal places
        - 'Current Quarter Net Absorption': Net absorption for current quarter (formatted integers)
        - 'YTD Net Absorption': Year-to-date net absorption (formatted integers)
        - 'Deliveries': Delivered construction area (formatted integers)
        - 'Under Construction': Area under construction (formatted integers)
    Notes
    -----
    1. Converts the given quarter to its end date
    2. Defines product type classifications
    3. Executes a stored procedure to aggregate property stats
    4. Fetches and processes the aggregated data
    5. Calculates totals row
    6. Formats numbers (percentages, integers, decimals)
    7. Sorts by predefined product type order
    8. Renames columns for readability
    9. Drops temporary table
    Product types are categorized as:
    - Distribution / Logistics
    - Manufacturing
    - R&D / Flex
    - Other Industrial
    - Total (calculated)
    """
    # Check environment
    env = settings.TESTING_ENV
    if env != "CBRE":
        result = _generate_mock_product_type_data(config)

        asking_rate_type = getattr(config, "asking_rate_type", "average")
        monthly_yearly_select = config.monthly_yearly_select
        asking_rate_label_text = asking_rate_label(
            asking_rate_type, monthly_yearly_select
        )

        # Format percentages
        percent_columns = [
            "VACANT_TOTAL_PERCENT",
            "AVAILABLE_TOTAL_PERCENT",
            "AVAILABLE_DIRECT_PERCENT",
            "AVAILABLE_SUBLEASE_PERCENT",
        ]
        for col in percent_columns:
            result.loc[:, col] = result[col].apply(
                lambda x: "{:.1f}".format(x) if pd.notnull(x) else "0.0"
            )

        # Format integer columns
        integer_columns = [
            "NET_RENTABLE_AREA",
            "NET_ABSORPTION_TOTAL",
            "YTD_NET_ABSORPTION_TOTAL",
            "DELIVERED_CONSTRUCTION_AREA",
            "UNDER_CONSTRUCTION_AREA",
        ]
        for col in integer_columns:
            result.loc[:, col] = result[col].apply(
                lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}"
            )

        # Format Avg. Net Direct Asking Rate to 2 decimal places
        result.loc[:, "AVG_ASKING_LEASE_RATE"] = result["AVG_ASKING_LEASE_RATE"].apply(
            lambda x: f"{x:.2f}" if pd.notnull(x) else "-"
        )

        # Define custom sort order
        product_type_order = [
            "Distribution / Logistics",
            "Manufacturing",
            "R&D / Flex",
            "Other Industrial",
            "Total",
        ]

        # Create a categorical type with custom ordering
        result["PRODUCT_TYPE"] = pd.Categorical(
            result["PRODUCT_TYPE"], categories=product_type_order, ordered=True
        )

        # Sort the DataFrame
        result = result.sort_values("PRODUCT_TYPE")
        result.reset_index(drop=True, inplace=True)

        # Rename columns
        column_mapping = {
            "PRODUCT_TYPE": "",
            "NET_RENTABLE_AREA": "Net Rentable Area",
            "VACANT_TOTAL_PERCENT": "Total Vacancy",
            "AVAILABLE_TOTAL_PERCENT": "Total Availability",
            "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
            "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
            "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
            "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
            "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
            "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
            "UNDER_CONSTRUCTION_AREA": "Under Construction",
        }
        result = result.rename(columns=column_mapping)
        # Remove rows where all values are 0 or like 0.00
        result = result[(result.iloc[:, 1:] != 0).any(axis=1)]

        return result

    # Build payload for render_sql_template
    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    payload = _config_to_payload(config)
    current_quarter_end_date = get_quarter_end_date(config.current_quarter)

    # Define product type case statement
    # Wrap in dollar-quoted string for same reason as size_bucket_definition
    product_type_definition = """$$case
    when property_subtype = 'R&D/Flex' then 'R&D / Flex'
    when property_subtype = 'Manufacturing' then 'Manufacturing'
    when property_subtype = 'Light Manufacturing' then 'Manufacturing'
    when property_subtype = 'Heavy Manufacturing' then 'Manufacturing'
    when property_subtype = 'Food Processing' then 'Manufacturing'
    when property_subtype = 'Distribution/Logistics' then 'Distribution / Logistics'
    when property_subtype = 'Cold Storage' then 'Distribution / Logistics'
    when property_subtype = 'Cross-Dock' then 'Distribution / Logistics'
    when property_subtype = 'Warehouse/Distribution' then 'Distribution / Logistics'
    when property_subtype = 'Warehouse/Storage' then 'Distribution / Logistics'
    else 'Other Industrial' END as PRODUCT_TYPE$$"""

    # Add custom fields to payload
    payload["current_quarter_end_date"] = current_quarter_end_date
    payload["product_type_definition"] = product_type_definition

    # Render and execute the stored procedure
    query = render_sql_template(PRODUCT_TYPE_SP_TEMPLATE, payload)
    fetch_snowflake_data(query)

    # Render and execute the select query
    select_aggregate_query = render_sql_template(PRODUCT_TYPE_SELECT_TEMPLATE, payload)
    result_rows = fetch_snowflake_data(select_aggregate_query)
    result = pd.DataFrame(result_rows)

    # Convert all datetime columns to be timezone unaware
    datetime_columns = [
        col
        for col in result.columns
        if isinstance(result[col].dtype, pd.DatetimeTZDtype)
    ]
    for col in datetime_columns:
        result[col] = result[col].dt.tz_localize(None)

    # Define the numerator and denominator based on asking rate type

    needed_columns = [
        "PRODUCT_TYPE",
        "NET_RENTABLE_AREA",
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
        "AVG_ASKING_LEASE_RATE",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]

    # Filter and create a new DataFrame instead of modifying a view
    product_type_rows = result[result["BREAKDOWN_FULL_DESC"] == "Product Type"].copy()
    filtered_rows = product_type_rows[
        product_type_rows["PRODUCT_TYPE"].isin(
            [
                "Distribution / Logistics",
                "Manufacturing",
                "R&D / Flex",
                "Other Industrial",
            ]
        )
    ].copy()

    # Calculate totals row
    total_row = pd.DataFrame(
        {
            "PRODUCT_TYPE": ["Total"],
            "NET_RENTABLE_AREA": [
                filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "VACANT_TOTAL_PERCENT": [
                filtered_rows["VACANT_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_TOTAL_PERCENT": [
                filtered_rows["AVAILABLE_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_DIRECT_PERCENT": [
                filtered_rows["AVAILABLE_DIRECT_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_SUBLEASE_PERCENT": [
                filtered_rows["AVAILABLE_SUBLEASE_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVG_ASKING_LEASE_RATE": asking_rate_calc(
                filtered_rows, asking_rate_type, monthly_yearly_select
            ),
            "NET_ABSORPTION_TOTAL": [
                filtered_rows["NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "YTD_NET_ABSORPTION_TOTAL": [
                filtered_rows["YTD_NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "DELIVERED_CONSTRUCTION_AREA": [
                filtered_rows["DELIVERED_CONSTRUCTION_AREA"].astype(float).sum()
            ],
            "UNDER_CONSTRUCTION_AREA": [
                filtered_rows["UNDER_CONSTRUCTION_AREA"].astype(float).sum()
            ],
        }
    )

    # Combine and create a new DataFrame
    result = pd.concat(
        [filtered_rows[needed_columns], total_row], ignore_index=True
    ).fillna(0)

    # Format columns using loc to avoid warnings
    # Format percentages
    percent_columns = [
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
    ]

    # Convert to float and format percentages with exactly 2 decimal places
    for col in percent_columns:
        result.loc[:, col] = pd.to_numeric(
            result[col], errors="coerce"
        )  # Convert to float
        result.loc[:, col] = result[col].apply(
            lambda x: "{:.1f}".format(x * 100)
        )  # Format as string with 2 decimals
        result.loc[:, col] = pd.to_numeric(result[col])  # Convert back to numeric

    # Format integer columns
    integer_columns = [
        "NET_RENTABLE_AREA",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]
    for col in integer_columns:
        result.loc[:, col] = (
            result[col]
            .astype(float)
            .round(0)
            .astype(int)
            .apply(lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}")
        )

    # Format Avg. Net Direct Asking Rate to 2 decimal places
    result.loc[:, "AVG_ASKING_LEASE_RATE"] = result["AVG_ASKING_LEASE_RATE"].apply(
        lambda x: f"{x:.2f}" if pd.notnull(x) else "-"
    )

    # Define custom sort order
    product_type_order = [
        "Distribution / Logistics",
        "Manufacturing",
        "R&D / Flex",
        "Other Industrial",
        "Total",
    ]

    # Create a categorical type with custom ordering
    result["PRODUCT_TYPE"] = pd.Categorical(
        result["PRODUCT_TYPE"], categories=product_type_order, ordered=True
    )

    # Sort the DataFrame
    result = result.sort_values("PRODUCT_TYPE")
    result.reset_index(drop=True, inplace=True)

    asking_rate_label_text = asking_rate_label(asking_rate_type, monthly_yearly_select)

    # Rename columns
    column_mapping = {
        "PRODUCT_TYPE": "",
        "NET_RENTABLE_AREA": "Net Rentable Area",
        "VACANT_TOTAL_PERCENT": "Total Vacancy",
        "AVAILABLE_TOTAL_PERCENT": "Total Availability",
        "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
        "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
        "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
        "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
        "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
        "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
        "UNDER_CONSTRUCTION_AREA": "Under Construction",
    }
    result = result.rename(columns=column_mapping)
    # Remove rows where all values are 0 or like 0.00
    result = result[(result.iloc[:, 1:] != 0).any(axis=1)]

    # Drop custom table
    try:
        fetch_snowflake_data(
            "drop table if exists prod_usdm_db.reporting_all.size_bucket_data"
        )
    except Exception:
        pass

    return result


def _generate_mock_industrial_class_data(config) -> pd.DataFrame:
    """Generate mock industrial class data for non-CBRE environments."""
    import random

    classes = ["Class A", "All Other Buildings"]

    mock_data = []
    for class_type in classes:
        net_rentable_area = (
            random.randint(10000000, 25000000)
            if class_type == "Class A"
            else random.randint(15000000, 35000000)
        )
        vacancy_percent = (
            round(random.uniform(3.5, 6.5), 1)
            if class_type == "Class A"
            else round(random.uniform(6.0, 9.0), 1)
        )
        available_total_percent = (
            round(random.uniform(5.5, 9.5), 1)
            if class_type == "Class A"
            else round(random.uniform(8.0, 12.0), 1)
        )
        available_direct_percent = (
            round(random.uniform(4.0, 8.0), 1)
            if class_type == "Class A"
            else round(random.uniform(6.5, 10.0), 1)
        )
        available_sublease_percent = (
            round(random.uniform(0.8, 2.5), 1)
            if class_type == "Class A"
            else round(random.uniform(1.5, 3.5), 1)
        )
        avg_asking_rate = (
            round(random.uniform(10.00, 14.50), 2)
            if class_type == "Class A"
            else round(random.uniform(7.00, 11.00), 2)
        )
        net_absorption = random.randint(-15000, 60000)
        ytd_absorption = random.randint(-60000, 250000)
        deliveries = random.randint(0, 400000)
        under_construction = random.randint(0, 700000)

        mock_data.append(
            {
                "INDUSTRIAL_CLASS": class_type,
                "NET_RENTABLE_AREA": net_rentable_area,
                "VACANT_TOTAL_PERCENT": vacancy_percent,
                "AVAILABLE_TOTAL_PERCENT": available_total_percent,
                "AVAILABLE_DIRECT_PERCENT": available_direct_percent,
                "AVAILABLE_SUBLEASE_PERCENT": available_sublease_percent,
                "AVG_ASKING_LEASE_RATE": avg_asking_rate,
                "NET_ABSORPTION_TOTAL": net_absorption,
                "YTD_NET_ABSORPTION_TOTAL": ytd_absorption,
                "DELIVERED_CONSTRUCTION_AREA": deliveries,
                "UNDER_CONSTRUCTION_AREA": under_construction,
            }
        )

    # Create totals row
    total_row = pd.DataFrame(mock_data).sum()
    total_row["INDUSTRIAL_CLASS"] = "Total"
    total_row["VACANT_TOTAL_PERCENT"] = round(total_row["VACANT_TOTAL_PERCENT"] / 2, 1)
    total_row["AVAILABLE_TOTAL_PERCENT"] = round(
        total_row["AVAILABLE_TOTAL_PERCENT"] / 2, 1
    )
    total_row["AVAILABLE_DIRECT_PERCENT"] = round(
        total_row["AVAILABLE_DIRECT_PERCENT"] / 2, 1
    )
    total_row["AVAILABLE_SUBLEASE_PERCENT"] = round(
        total_row["AVAILABLE_SUBLEASE_PERCENT"] / 2, 1
    )
    total_row["AVG_ASKING_LEASE_RATE"] = round(
        total_row["AVG_ASKING_LEASE_RATE"] / 2, 2
    )

    mock_data.append(total_row.to_dict())
    return pd.DataFrame(mock_data)


def fetch_industrial_class_data(config):
    """Fetches and processes industrial class market data from Snowflake database.
    This function queries Snowflake for industrial property statistics, aggregates the data by industrial class
    (Class A and All Other Buildings), calculates totals, and formats the results into a presentable DataFrame.
    Parameters:
        config: Configuration object containing parameters
    Returns:
        pandas.DataFrame: Processed DataFrame containing industrial class statistics with the following columns:
            - '' (Industrial Class): Class A, All Other Buildings, or Total
            - Net Rentable Area: Formatted as integers with commas
            - Total Vacancy: Percentage with 1 decimal place
            - Total Availability: Percentage with 1 decimal place
            - Direct Availability: Percentage with 1 decimal place
            - Sublease Availability: Percentage with 1 decimal place
            - Avg. Net Direct Asking Rate: Formatted to 2 decimal places
            - Current Quarter Net Absorption: Formatted integers with commas and parentheses for negative values
            - YTD Net Absorption: Formatted integers with commas and parentheses for negative values
            - Deliveries: Formatted integers with commas
            - Under Construction: Formatted integers with commas
    Notes:
        - Class A buildings are defined as Industrial properties with:
            * Minimum clear height of 32 feet
            * Built in or after 2000
            * ESFR sprinkler system
        - The function handles temporary table cleanup after data retrieval
        - All datetime values are converted to timezone-unaware format
    """
    # Check environment
    env = settings.TESTING_ENV
    if env != "CBRE":
        result = _generate_mock_industrial_class_data(config)

        asking_rate_type = getattr(config, "asking_rate_type", "average")
        monthly_yearly_select = config.monthly_yearly_select
        asking_rate_label_text = asking_rate_label(
            asking_rate_type, monthly_yearly_select
        )

        # Format percentages
        percent_columns = [
            "VACANT_TOTAL_PERCENT",
            "AVAILABLE_TOTAL_PERCENT",
            "AVAILABLE_DIRECT_PERCENT",
            "AVAILABLE_SUBLEASE_PERCENT",
        ]
        for col in percent_columns:
            result.loc[:, col] = pd.to_numeric(result[col], errors="coerce")
            result.loc[:, col] = result[col].apply(
                lambda x: "{:.1f}".format(x * 100) if pd.notnull(x) else x
            )
            result.loc[:, col] = pd.to_numeric(result[col], errors="coerce")

        # Format integer columns
        integer_columns = [
            "NET_RENTABLE_AREA",
            "NET_ABSORPTION_TOTAL",
            "YTD_NET_ABSORPTION_TOTAL",
            "DELIVERED_CONSTRUCTION_AREA",
            "UNDER_CONSTRUCTION_AREA",
        ]
        for col in integer_columns:
            result.loc[:, col] = (
                result[col]
                .astype(float)
                .round(0)
                .astype(int)
                .apply(lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}")
            )

        # Format Avg. Net Direct Asking Rate to 2 decimal places
        result.loc[:, "AVG_ASKING_LEASE_RATE"] = result["AVG_ASKING_LEASE_RATE"].apply(
            lambda x: f"{x:.2f}" if pd.notnull(x) else "-"
        )

        # Define custom sort order
        industrial_class_order = ["Class A", "All Other Buildings", "Total"]
        result["INDUSTRIAL_CLASS"] = pd.Categorical(
            result["INDUSTRIAL_CLASS"], categories=industrial_class_order, ordered=True
        )
        result = result.sort_values("INDUSTRIAL_CLASS")
        result.reset_index(drop=True, inplace=True)

        # Rename columns
        column_mapping = {
            "INDUSTRIAL_CLASS": "",
            "NET_RENTABLE_AREA": "Net Rentable Area",
            "VACANT_TOTAL_PERCENT": "Total Vacancy",
            "AVAILABLE_TOTAL_PERCENT": "Total Availability",
            "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
            "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
            "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
            "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
            "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
            "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
            "UNDER_CONSTRUCTION_AREA": "Under Construction",
        }
        result = result.rename(columns=column_mapping)

        return result

    # Build payload for sql_utils functions
    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    payload = _config_to_payload(config)
    current_quarter_end_date = get_quarter_end_date(config.current_quarter)

    # Define industrial class case statement
    industrial_class_definition = """$$case
            when property_type = 'Industrial' and IFNULL(clear_height_min, clear_height_max) >= 32 and year_built >= 2000 and sprinkler_type = 'ESFR' then 'Class A'
        else 'All Other Buildings' END as INDUSTRIAL_CLASS$$"""

    # Add custom fields to payload
    payload["current_quarter_end_date"] = current_quarter_end_date
    payload["industrial_class_definition"] = industrial_class_definition

    # Render and execute the stored procedure
    query = render_sql_template(INDUSTRIAL_CLASS_SP_TEMPLATE, payload)
    fetch_snowflake_data(query)

    # Render and execute the select query
    select_aggregate_query = render_sql_template(
        INDUSTRIAL_CLASS_SELECT_TEMPLATE, payload
    )
    result_rows = fetch_snowflake_data(select_aggregate_query)
    result = pd.DataFrame(result_rows)

    # Convert all datetime columns to be timezone unaware
    datetime_columns = [
        col
        for col in result.columns
        if isinstance(result[col].dtype, pd.DatetimeTZDtype)
    ]
    for col in datetime_columns:
        result[col] = result[col].dt.tz_localize(None)

    needed_columns = [
        "INDUSTRIAL_CLASS",
        "NET_RENTABLE_AREA",
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
        "AVG_ASKING_LEASE_RATE",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]

    # Filter and create a new DataFrame instead of modifying a view
    industrial_class_rows = result[
        result["BREAKDOWN_FULL_DESC"] == "Industrial Class"
    ].copy()
    filtered_rows = industrial_class_rows[
        industrial_class_rows["INDUSTRIAL_CLASS"].isin(
            ["Class A", "All Other Buildings"]
        )
    ].copy()

    # Calculate totals row
    total_row = pd.DataFrame(
        {
            "INDUSTRIAL_CLASS": ["Total"],
            "NET_RENTABLE_AREA": [
                filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "VACANT_TOTAL_PERCENT": [
                filtered_rows["VACANT_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_TOTAL_PERCENT": [
                filtered_rows["AVAILABLE_TOTAL_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_DIRECT_PERCENT": [
                filtered_rows["AVAILABLE_DIRECT_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVAILABLE_SUBLEASE_PERCENT": [
                filtered_rows["AVAILABLE_SUBLEASE_AREA"].astype(float).sum()
                / filtered_rows["NET_RENTABLE_AREA"].astype(float).sum()
            ],
            "AVG_ASKING_LEASE_RATE": asking_rate_calc(
                filtered_rows, asking_rate_type, monthly_yearly_select
            ),
            "NET_ABSORPTION_TOTAL": [
                filtered_rows["NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "YTD_NET_ABSORPTION_TOTAL": [
                filtered_rows["YTD_NET_ABSORPTION_TOTAL"].astype(float).sum()
            ],
            "DELIVERED_CONSTRUCTION_AREA": [
                filtered_rows["DELIVERED_CONSTRUCTION_AREA"].astype(float).sum()
            ],
            "UNDER_CONSTRUCTION_AREA": [
                filtered_rows["UNDER_CONSTRUCTION_AREA"].astype(float).sum()
            ],
        }
    )

    # Combine and create a new DataFrame
    result = pd.concat([filtered_rows[needed_columns], total_row], ignore_index=True)

    # Format columns using loc to avoid warnings
    # Format percentages
    percent_columns = [
        "VACANT_TOTAL_PERCENT",
        "AVAILABLE_TOTAL_PERCENT",
        "AVAILABLE_DIRECT_PERCENT",
        "AVAILABLE_SUBLEASE_PERCENT",
    ]

    # Convert to float and format percentages with exactly 2 decimal places
    for col in percent_columns:
        # Convert to float first with NaN handling
        result.loc[:, col] = pd.to_numeric(
            result[col], errors="coerce"
        )  # Convert to float
        # Only format non-null values
        result.loc[:, col] = result[col].apply(
            lambda x: "{:.1f}".format(x * 100) if pd.notnull(x) else x
        )
        # Convert back to numeric with NaN handling
        result.loc[:, col] = pd.to_numeric(result[col], errors="coerce")

    # Format integer columns
    integer_columns = [
        "NET_RENTABLE_AREA",
        "NET_ABSORPTION_TOTAL",
        "YTD_NET_ABSORPTION_TOTAL",
        "DELIVERED_CONSTRUCTION_AREA",
        "UNDER_CONSTRUCTION_AREA",
    ]
    for col in integer_columns:
        result.loc[:, col] = (
            result[col]
            .astype(float)
            .round(0)
            .astype(int)
            .apply(lambda x: f"({abs(x):,})" if x < 0 else f"{x:,}")
        )

    # Format Avg. Net Direct Asking Rate to 2 decimal places
    result.loc[:, "AVG_ASKING_LEASE_RATE"] = result["AVG_ASKING_LEASE_RATE"].apply(
        lambda x: f"{x:.2f}" if pd.notnull(x) else "-"
    )

    asking_rate_label_text = asking_rate_label(asking_rate_type, monthly_yearly_select)

    # Define custom sort order
    industrial_class_order = ["Class A", "All Other Buildings", "Total"]
    # Convert to categorical with custom ordering and sort
    result["INDUSTRIAL_CLASS"] = pd.Categorical(
        result["INDUSTRIAL_CLASS"], categories=industrial_class_order, ordered=True
    )
    result = result.sort_values("INDUSTRIAL_CLASS")
    result.reset_index(drop=True, inplace=True)

    # Rename columns
    column_mapping = {
        "INDUSTRIAL_CLASS": "",
        "NET_RENTABLE_AREA": "Net Rentable Area",
        "VACANT_TOTAL_PERCENT": "Total Vacancy",
        "AVAILABLE_TOTAL_PERCENT": "Total Availability",
        "AVAILABLE_DIRECT_PERCENT": "Direct Availability",
        "AVAILABLE_SUBLEASE_PERCENT": "Sublease Availability",
        "AVG_ASKING_LEASE_RATE": asking_rate_label_text,
        "NET_ABSORPTION_TOTAL": "Current Quarter Net Absorption",
        "YTD_NET_ABSORPTION_TOTAL": "YTD Net Absorption",
        "DELIVERED_CONSTRUCTION_AREA": "Deliveries",
        "UNDER_CONSTRUCTION_AREA": "Under Construction",
    }
    result = result.rename(columns=column_mapping)

    # Drop custom table
    try:
        fetch_snowflake_data(
            "drop table if exists prod_usdm_db.reporting_all.size_bucket_data"
        )
    except Exception:
        pass

    return result


def _generate_mock_submarket_data(config) -> pd.DataFrame:
    """Generate mock submarket data for non-CBRE environments."""
    import random

    submarkets = ["North", "South", "East", "West"]

    mock_data = []
    for submarket in submarkets:
        net_rentable_area = random.randint(3000000, 12000000)
        vacant_total_percent = round(random.uniform(5.0, 8.5), 1)
        available_total_percent = round(random.uniform(7.0, 11.0), 1)
        available_direct_percent = round(random.uniform(5.5, 9.0), 1)
        available_sublease_percent = round(random.uniform(1.0, 3.0), 1)
        avg_asking_lease_rate = round(random.uniform(8.00, 13.00), 2)
        net_absorption_total = random.randint(-8000, 35000)
        ytd_net_absorption_total = random.randint(-30000, 150000)
        delivered_construction_area = random.randint(0, 250000)
        under_construction_area = random.randint(0, 400000)

        mock_data.append(
            {
                "SUBMARKET": submarket,
                "NET_RENTABLE_AREA": f"{net_rentable_area:,}",
                "VACANT_TOTAL_PERCENT": vacant_total_percent,
                "AVAILABLE_TOTAL_PERCENT": available_total_percent,
                "AVAILABLE_DIRECT_PERCENT": available_direct_percent,
                "AVAILABLE_SUBLEASE_PERCENT": available_sublease_percent,
                "AVG_ASKING_LEASE_RATE": f"{avg_asking_lease_rate:.2f}",
                "NET_ABSORPTION_TOTAL": f"({abs(net_absorption_total):,})"
                if net_absorption_total < 0
                else f"{net_absorption_total:,}",
                "YTD_NET_ABSORPTION_TOTAL": f"({abs(ytd_net_absorption_total):,})"
                if ytd_net_absorption_total < 0
                else f"{ytd_net_absorption_total:,}",
                "DELIVERED_CONSTRUCTION_AREA": f"{delivered_construction_area:,}",
                "UNDER_CONSTRUCTION_AREA": f"{under_construction_area:,}",
            }
        )

    # Add Total row
    total_net_area = random.randint(25000000, 50000000)
    mock_data.append(
        {
            "SUBMARKET": "*TOTAL*",
            "NET_RENTABLE_AREA": f"{total_net_area:,}",
            "VACANT_TOTAL_PERCENT": round(random.uniform(5.5, 7.5), 1),
            "AVAILABLE_TOTAL_PERCENT": round(random.uniform(7.5, 10.5), 1),
            "AVAILABLE_DIRECT_PERCENT": round(random.uniform(6.0, 9.5), 1),
            "AVAILABLE_SUBLEASE_PERCENT": round(random.uniform(1.5, 2.8), 1),
            "AVG_ASKING_LEASE_RATE": f"{round(random.uniform(8.50, 12.50), 2):.2f}",
            "NET_ABSORPTION_TOTAL": f"{random.randint(-20000, 80000):,}",
            "YTD_NET_ABSORPTION_TOTAL": f"{random.randint(-80000, 300000):,}",
            "DELIVERED_CONSTRUCTION_AREA": f"{random.randint(500000, 1500000):,}",
            "UNDER_CONSTRUCTION_AREA": f"{random.randint(1000000, 2500000):,}",
        }
    )

    return pd.DataFrame(mock_data)


def fetch_industrial_submarket_data(config):
    """
    Fetches and processes industrial submarket data from Snowflake database.
    This function retrieves detailed statistics for industrial submarkets and the total market,
    combining them into a single DataFrame. The data includes metrics such as rentable area,
    vacancy rates, availability rates, asking rates, absorption, and construction statistics.
    Parameters
    ----------
    config : Config object
        Configuration object containing parameters
    Returns
    -------
    pandas.DataFrame
        Combined DataFrame containing both submarket and total market statistics with columns:
        - '' (Market/Submarket names)
        - Net Rentable Area (formatted with commas)
        - Total Vacancy (percentage)
        - Total Availability (percentage)
        - Direct Availability (percentage)
        - Sublease Availability (percentage)
        - Avg. Net Direct Asking Rate (dollars)
        - Current Quarter Net Absorption (formatted with commas, negatives in parentheses)
        - YTD Net Absorption (formatted with commas, negatives in parentheses)
        - Deliveries (formatted with commas)
        - Under Construction (formatted with commas)
    Notes
    -----
    - Negative absorption values are wrapped in parentheses
    - All numeric values are properly formatted with commas for thousands
    - The total market row is labeled as 'Total' in the final DataFrame
    """
    # Check environment
    env = settings.TESTING_ENV
    if env != "CBRE":
        submarket_df = _generate_mock_submarket_data(config)
        asking_rate_type = getattr(config, "asking_rate_type", "average")
        monthly_yearly_select = config.monthly_yearly_select
        asking_rate_label_text = asking_rate_label(
            asking_rate_type, monthly_yearly_select
        )

        submarket_data = pd.DataFrame(
            {
                "": submarket_df["SUBMARKET"].tolist(),
                "Net Rentable Area": submarket_df["NET_RENTABLE_AREA"].tolist(),
                "Total Vacancy": submarket_df["VACANT_TOTAL_PERCENT"].tolist(),
                "Total Availability": submarket_df["AVAILABLE_TOTAL_PERCENT"].tolist(),
                "Direct Availability": submarket_df[
                    "AVAILABLE_DIRECT_PERCENT"
                ].tolist(),
                "Sublease Availability": submarket_df[
                    "AVAILABLE_SUBLEASE_PERCENT"
                ].tolist(),
                f"{asking_rate_label_text}": submarket_df[
                    "AVG_ASKING_LEASE_RATE"
                ].tolist(),
                "Current Quarter Net Absorption": submarket_df[
                    "NET_ABSORPTION_TOTAL"
                ].tolist(),
                "YTD Net Absorption": submarket_df["YTD_NET_ABSORPTION_TOTAL"].tolist(),
                "Deliveries": submarket_df["DELIVERED_CONSTRUCTION_AREA"].tolist(),
                "Under Construction": submarket_df["UNDER_CONSTRUCTION_AREA"].tolist(),
            }
        )

        result = submarket_data.copy()
        result.loc[result[""] == "*TOTAL*", ""] = "Total"
        return result

    # Build payload for sql_utils functions
    monthly_yearly_select = config.monthly_yearly_select
    asking_rate_type = getattr(config, "asking_rate_type", "average")

    payload = _config_to_payload(config)
    payload["current_quarter"] = config.current_quarter

    # Render and execute submarket query
    submarket_query = render_sql_template(SUBMARKET_QUERY_TEMPLATE, payload)
    submarket_rows = fetch_snowflake_data(submarket_query)
    submarket_df = pd.DataFrame(submarket_rows)

    asking_rate_label_text = asking_rate_label(asking_rate_type, monthly_yearly_select)

    # Convert to pandas and create final format in one step
    submarket_data = pd.DataFrame(
        {
            "": submarket_df["SUBMARKET"].tolist(),
            "Net Rentable Area": submarket_df["NET_RENTABLE_AREA"].tolist(),
            "Total Vacancy": submarket_df["VACANT_TOTAL_PERCENT"].tolist(),
            "Total Availability": submarket_df["AVAILABLE_TOTAL_PERCENT"].tolist(),
            "Direct Availability": submarket_df["AVAILABLE_DIRECT_PERCENT"].tolist(),
            "Sublease Availability": submarket_df[
                "AVAILABLE_SUBLEASE_PERCENT"
            ].tolist(),
            f"{asking_rate_label_text}": submarket_df["AVG_ASKING_LEASE_RATE"].tolist(),
            "Current Quarter Net Absorption": submarket_df[
                "NET_ABSORPTION_TOTAL"
            ].tolist(),
            "YTD Net Absorption": submarket_df["YTD_NET_ABSORPTION_TOTAL"].tolist(),
            "Deliveries": submarket_df["DELIVERED_CONSTRUCTION_AREA"].tolist(),
            "Under Construction": submarket_df["UNDER_CONSTRUCTION_AREA"].tolist(),
        }
    )

    # Render and execute market total query
    market_query = render_sql_template(MARKET_TOTAL_QUERY_TEMPLATE, payload)
    market_rows = fetch_snowflake_data(market_query)
    market_df = pd.DataFrame(market_rows)

    # Convert to pandas and create final format in one step
    market_data = pd.DataFrame(
        {
            "": market_df["SUBMARKET"].tolist(),
            "Net Rentable Area": market_df["NET_RENTABLE_AREA"].tolist(),
            "Total Vacancy": market_df["VACANT_TOTAL_PERCENT"].tolist(),
            "Total Availability": market_df["AVAILABLE_TOTAL_PERCENT"].tolist(),
            "Direct Availability": market_df["AVAILABLE_DIRECT_PERCENT"].tolist(),
            "Sublease Availability": market_df["AVAILABLE_SUBLEASE_PERCENT"].tolist(),
            f"{asking_rate_label_text}": market_df["AVG_ASKING_LEASE_RATE"].tolist(),
            "Current Quarter Net Absorption": market_df[
                "NET_ABSORPTION_TOTAL"
            ].tolist(),
            "YTD Net Absorption": market_df["YTD_NET_ABSORPTION_TOTAL"].tolist(),
            "Deliveries": market_df["DELIVERED_CONSTRUCTION_AREA"].tolist(),
            "Under Construction": market_df["UNDER_CONSTRUCTION_AREA"].tolist(),
        }
    )

    result = pd.concat([submarket_data, market_data], ignore_index=True)
    result.loc[result[""] == "*TOTAL*", ""] = "Total"

    return result
