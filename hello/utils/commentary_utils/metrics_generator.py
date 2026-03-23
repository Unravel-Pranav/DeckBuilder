from hello.utils.commentary_utils.utils import format_period_code, get_prev_quarter, get_x_years_ago_quarter, parse_quarter_string, get_value, get_last_n_periods_list, get_periods_from_to, get_net_gross_formatting
from hello.utils.sql_utils import get_asking_rate_field
from typing import Any
import pandas as pd
from hello.ml.logger import GLOBAL_LOGGER as logger


def _determine_direction(
    current_value: float | int | None, 
    comparison_value: float | int | None, 
    threshold: float = 0.0
) -> str:
    """
    Determine the direction of change between current and comparison values.
    
    Always compares current period value to comparison period value, using a configurable
    threshold for "neutral" classification.
    
    Args:
        current_value: The current period value
        comparison_value: The comparison period value (previous quarter, year ago, etc.)
        threshold: Threshold for neutral classification (default: 0.0)
        
    Returns:
        str: One of "up", "down", "neutral", or "none"
    """
    # If either value is None/NA, return "none"
    if pd.isna(current_value) or pd.isna(comparison_value):
        return "none"
    
    # Convert to float for comparison
    try:
        current_val = float(current_value)
        comparison_val = float(comparison_value)
    except (TypeError, ValueError):
        return "none"
    
    # Calculate the difference
    difference = current_val - comparison_val
    
    # Apply threshold logic
    if abs(difference) <= threshold:
        return "neutral"
    elif difference > 0:
        return "up"
    else:
        return "down"



def _create_metric_entry(
    current: float | int | None,
    qoq_comparison: float | int | None = None,
    yoy_comparison: float | int | None = None,
    historical_comparison: float | int | None = None,
    neutral_threshold: float = 0.0
) -> dict[str, Any]:
    """
    Create a structured metric entry with current value and directional indicators.
    
    Args:
        current: Current period value
        qoq_comparison: Previous quarter value for QoQ direction
        yoy_comparison: Year-ago value for YoY direction
        historical_comparison: Historical period value for historical direction
        neutral_threshold: Threshold for neutral classification
        
    Returns:
        dict: Structured metric entry with current, qoq, yoy, historical, and direction keys
    """
    # Create the base entry
    entry = {
        'current': current,
        'qoq': {'direction': _determine_direction(current, qoq_comparison, neutral_threshold)},
        'yoy': {'direction': _determine_direction(current, yoy_comparison, neutral_threshold)},
        'historical': {'direction': _determine_direction(current, historical_comparison, neutral_threshold)},
        'direction': _determine_direction(current, qoq_comparison, neutral_threshold)  # Primary direction is QoQ
    }
    
    return entry




def generate_metrics_from_dataframes(
    total_market_df: pd.DataFrame,
    property_class_df: pd.DataFrame,
    report_params: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate structured metrics dictionary from DataFrames for YAML-based narrative generation.
    
    This function processes the DataFrames returned by _fetch_calculated_metrics_data and
    transforms them into a structured format that supports the new YAML template system.
    
    Args:
        total_market_df: DataFrame with total market metrics by period
        property_class_df: DataFrame with property class metrics by period and class
        report_params: Report configuration parameters
        
    Returns:
        dict: Structured metrics dictionary matching the YAML template expectations
    """
    logger.debug(f"Generating metrics from DataFrames for property_type: {report_params.get('property_type')}")
    
    # Validate that current_quarter is not None
    if report_params.get('quarter') is None:
        raise ValueError("quarter cannot be None")
    
    # Parse time periods from generation_params
    current_year, current_q_num = parse_quarter_string(report_params.get('quarter'))
    x_years = int(str(report_params.get('history_range')).split('-')[0])

    current_period = report_params.get('quarter')
    prev_q_year, prev_q_num = get_prev_quarter(current_year, current_q_num)
    prev_quarter_period = format_period_code(prev_q_year, prev_q_num)
    year_ago_q_year, year_ago_q_num = get_x_years_ago_quarter(current_year, current_q_num)
    year_ago_period = format_period_code(year_ago_q_year, year_ago_q_num)
    x_yrs_ago_q_year, x_yrs_ago_q_num = get_x_years_ago_quarter(current_year, current_q_num, x_years)
    x_yrs_ago_period = format_period_code(x_yrs_ago_q_year, x_yrs_ago_q_num)
    
    metrics = {}
    
    # Configure thresholds (can be made configurable later)
    percentage_threshold = 0.1  # 0.1% threshold for percentage metrics
    rate_threshold = 0.05       # $0.05 threshold for rate metrics
    sf_threshold = 1000         # 1,000 SF threshold for square footage metrics
    
    # =====================
    # OVERVIEW METRICS
    # =====================
    
    # --- TOTAL AVAILABILITY RATE ---
    current_total_avail = get_value(total_market_df, current_period, 'available_total_percent')
    qoq_total_avail = get_value(total_market_df, prev_quarter_period, 'available_total_percent')
    yoy_total_avail = get_value(total_market_df, year_ago_period, 'available_total_percent')
    historical_total_avail = get_value(total_market_df, x_yrs_ago_period, 'available_total_percent')
    
    metrics['total_availability_rate'] = _create_metric_entry(
        current_total_avail, qoq_total_avail, yoy_total_avail, historical_total_avail, percentage_threshold
    )
    
    # --- TOTAL VACANCY RATE ---
    current_vacancy = get_value(total_market_df, current_period, 'vacant_total_percent')
    qoq_vacancy = get_value(total_market_df, prev_quarter_period, 'vacant_total_percent')
    yoy_vacancy = get_value(total_market_df, year_ago_period, 'vacant_total_percent')
    historical_vacancy = get_value(total_market_df, x_yrs_ago_period, 'vacant_total_percent')
    
    metrics['total_vacancy_rate'] = _create_metric_entry(
        current_vacancy, qoq_vacancy, yoy_vacancy, historical_vacancy, percentage_threshold
    )
    
    # --- AVERAGE ASKING RENT ---
    current_rent = get_value(total_market_df, current_period, 'avg_asking_rate')
    qoq_rent = get_value(total_market_df, prev_quarter_period, 'avg_asking_rate')
    yoy_rent = get_value(total_market_df, year_ago_period, 'avg_asking_rate')
    historical_rent = get_value(total_market_df, x_yrs_ago_period, 'avg_asking_rate')
    
    metrics['average_asking_rent'] = _create_metric_entry(
        current_rent, qoq_rent, yoy_rent, historical_rent, rate_threshold
    )
    
    # --- NET ABSORPTION ---
    current_absorption = get_value(total_market_df, current_period, 'net_absorption')
    qoq_absorption = get_value(total_market_df, prev_quarter_period, 'net_absorption')
    yoy_absorption = get_value(total_market_df, year_ago_period, 'net_absorption')
    historical_absorption = get_value(total_market_df, x_yrs_ago_period, 'net_absorption')
    
    metrics['net_absorption'] = _create_metric_entry(
        current_absorption, qoq_absorption, yoy_absorption, historical_absorption, sf_threshold
    )
    
    # --- SUBLEASE AVAILABILITY RATE ---
    current_sublease_avail = get_value(total_market_df, current_period, 'available_sublease_percent')
    qoq_sublease_avail = get_value(total_market_df, prev_quarter_period, 'available_sublease_percent')
    yoy_sublease_avail = get_value(total_market_df, year_ago_period, 'available_sublease_percent')
    historical_sublease_avail = get_value(total_market_df, x_yrs_ago_period, 'available_sublease_percent')
    
    metrics['sublease_availability_rate'] = _create_metric_entry(
        current_sublease_avail, qoq_sublease_avail, yoy_sublease_avail, historical_sublease_avail, percentage_threshold
    )
    
    # --- DIRECT AVAILABILITY RATE ---
    current_direct_avail = get_value(total_market_df, current_period, 'available_direct_percent')
    qoq_direct_avail = get_value(total_market_df, prev_quarter_period, 'available_direct_percent')
    yoy_direct_avail = get_value(total_market_df, year_ago_period, 'available_direct_percent')
    historical_direct_avail = get_value(total_market_df, x_yrs_ago_period, 'available_direct_percent')
    
    metrics['direct_availability_rate'] = _create_metric_entry(
        current_direct_avail, qoq_direct_avail, yoy_direct_avail, historical_direct_avail, percentage_threshold
    )
    
    # =====================
    # CONSTRUCTION METRICS
    # =====================
    
    # --- UNDER CONSTRUCTION ---
    current_under_construction = get_value(total_market_df, current_period, 'under_construction_area')
    qoq_under_construction = get_value(total_market_df, prev_quarter_period, 'under_construction_area')
    yoy_under_construction = get_value(total_market_df, year_ago_period, 'under_construction_area')
    historical_under_construction = get_value(total_market_df, x_yrs_ago_period, 'under_construction_area')
    
    metrics['under_construction'] = _create_metric_entry(
        current_under_construction, qoq_under_construction, yoy_under_construction, 
        historical_under_construction, sf_threshold
    )
    
    # --- CONSTRUCTION DELIVERIES ---
    current_deliveries = get_value(total_market_df, current_period, 'delivered_construction_area')
    qoq_deliveries = get_value(total_market_df, prev_quarter_period, 'delivered_construction_area')
    yoy_deliveries = get_value(total_market_df, year_ago_period, 'delivered_construction_area')
    historical_deliveries = get_value(total_market_df, x_yrs_ago_period, 'delivered_construction_area')
    
    metrics['deliveries'] = _create_metric_entry(
        current_deliveries, qoq_deliveries, yoy_deliveries, historical_deliveries, sf_threshold
    )
    
    # =====================
    # LEASING ACTIVITY METRICS
    # =====================
    
    # --- LEASING ACTIVITY ---
    if 'total_area_leased_sf' in total_market_df.columns:
        current_leasing = get_value(total_market_df, current_period, 'total_area_leased_sf')
        qoq_leasing = get_value(total_market_df, prev_quarter_period, 'total_area_leased_sf')
        yoy_leasing = get_value(total_market_df, year_ago_period, 'total_area_leased_sf')
        historical_leasing = get_value(total_market_df, x_yrs_ago_period, 'total_area_leased_sf')
        
        metrics['leasing_activity'] = _create_metric_entry(
            current_leasing, qoq_leasing, yoy_leasing, historical_leasing, sf_threshold
        )
    else:
        logger.warning("Leasing activity column not found in total_market_df")
        metrics['leasing_activity'] = _create_metric_entry(None, None, None, None)
    
    # =====================
    # OFFICE-SPECIFIC METRICS
    # =====================

    property_type = (report_params.get("property_type") or "").strip().casefold()
    if property_type == 'office' and not property_class_df.empty:
        for class_type in ['Class A', 'Class B']:
            class_prefix = 'office_class_a' if class_type == 'Class A' else 'office_class_b'
            
            # --- CLASS VACANCY RATE ---
            current_class_vacancy = get_value(property_class_df, current_period, 'vacant_total_percent', class_type)
            qoq_class_vacancy = get_value(property_class_df, prev_quarter_period, 'vacant_total_percent', class_type)
            yoy_class_vacancy = get_value(property_class_df, year_ago_period, 'vacant_total_percent', class_type)
            historical_class_vacancy = get_value(property_class_df, x_yrs_ago_period, 'vacant_total_percent', class_type)
            
            metrics[f'{class_prefix}_vacancy_rate'] = _create_metric_entry(
                current_class_vacancy, qoq_class_vacancy, yoy_class_vacancy, historical_class_vacancy, percentage_threshold
            )
            
            # --- CLASS ASKING RENT ---
            current_class_rent = get_value(property_class_df, current_period, 'avg_asking_rate', class_type)
            qoq_class_rent = get_value(property_class_df, prev_quarter_period, 'avg_asking_rate', class_type)
            yoy_class_rent = get_value(property_class_df, year_ago_period, 'avg_asking_rate', class_type)
            historical_class_rent = get_value(property_class_df, x_yrs_ago_period, 'avg_asking_rate', class_type)
            
            metrics[f'{class_prefix}_asking_rent'] = _create_metric_entry(
                current_class_rent, qoq_class_rent, yoy_class_rent, historical_class_rent, rate_threshold
            )
            
            # --- CLASS LEASING ACTIVITY ---
            if 'total_area_leased_sf' in property_class_df.columns:
                current_class_leasing = get_value(property_class_df, current_period, 'total_area_leased_sf', class_type)
                qoq_class_leasing = get_value(property_class_df, prev_quarter_period, 'total_area_leased_sf', class_type)
                yoy_class_leasing = get_value(property_class_df, year_ago_period, 'total_area_leased_sf', class_type)
                historical_class_leasing = get_value(property_class_df, x_yrs_ago_period, 'total_area_leased_sf', class_type)
                
                metrics[f'{class_prefix}_leasing_activity'] = _create_metric_entry(
                    current_class_leasing, qoq_class_leasing, yoy_class_leasing, historical_class_leasing, sf_threshold
                )
            else:
                logger.warning(f"Leasing activity column not found for {class_type}")
                metrics[f'{class_prefix}_leasing_activity'] = _create_metric_entry(None, None, None, None)
    
    logger.debug(f"Generated {len(metrics)} metrics entries")
    return metrics


def generate_calculated_metrics_for_variables(
    total_market_df: pd.DataFrame,
    property_class_df: pd.DataFrame,
    report_params: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate the complete calculated metrics dictionary that provides all the variable values
    needed by the YAML templates. This function creates the flat dictionary structure that
    the template variable substitution system expects.
    
    Args:
        total_market_df: DataFrame with total market metrics by period
        property_class_df: DataFrame with property class metrics by period and class
        generation_params: Report configuration parameters
        
    Returns:
        dict: Flat dictionary with all calculated metric values for template variables
    """
    logger.debug("Generating calculated metrics for template variables")
    
    # Validate that current_quarter is not None
    if report_params.get('quarter') is None:
        raise ValueError("quarter cannot be None")
    
    # Parse time periods from generation_params
    current_year, current_q_num = parse_quarter_string(report_params.get('quarter'))
    x_years = int(str(report_params.get('history_range')).split('-')[0])
    
    current_period = report_params.get("quarter")
    prev_q_year, prev_q_num = get_prev_quarter(current_year, current_q_num)
    prev_quarter_period = format_period_code(prev_q_year, prev_q_num)
    year_ago_q_year, year_ago_q_num = get_x_years_ago_quarter(current_year, current_q_num)
    year_ago_period = format_period_code(year_ago_q_year, year_ago_q_num)
    x_yrs_ago_q_year, x_yrs_ago_q_num = get_x_years_ago_quarter(current_year, current_q_num, x_years)
    x_yrs_ago_period = format_period_code(x_yrs_ago_q_year, x_yrs_ago_q_num)
    
    
    # Calculate period lists for multi-period calculations
    all_periods_in_df = sorted(total_market_df['period'].unique())
    last_4_periods_list = get_last_n_periods_list(current_period, 4, all_periods_in_df)
    last_x_yrs_periods_list = get_periods_from_to(x_yrs_ago_period, current_period, all_periods_in_df)

    formatted_asking_rate_type = get_net_gross_formatting(
        get_asking_rate_field(report_params.get("asking_rate_type"), report_params.get("asking_rate_frequency")),
        str(report_params.get("asking_rate_frequency"))
    )

    calculated_metrics = {}
    
    # =====================
    # OVERVIEW METRICS
    # =====================
    
    # --- TOTAL AVAILABILITY RATE ---
    cq_total_avail_pct = get_value(total_market_df, current_period, 'available_total_percent')
    pq_total_avail_pct = get_value(total_market_df, prev_quarter_period, 'available_total_percent')
    ya_total_avail_pct = get_value(total_market_df, year_ago_period, 'available_total_percent')
    xya_total_avail_pct = get_value(total_market_df, x_yrs_ago_period, 'available_total_percent')
    
    calculated_metrics['current_quarter_total_available_percent'] = cq_total_avail_pct
    calculated_metrics['qoq_change_in_total_available_percent_bps'] = (cq_total_avail_pct - pq_total_avail_pct) * 100 if pd.notna(cq_total_avail_pct) and pd.notna(pq_total_avail_pct) else None
    calculated_metrics['yoy_change_in_total_available_percent_bps'] = (cq_total_avail_pct - ya_total_avail_pct) * 100 if pd.notna(cq_total_avail_pct) and pd.notna(ya_total_avail_pct) else None
    calculated_metrics['last_x_yrs_change_in_total_available_percent_bps'] = (cq_total_avail_pct - xya_total_avail_pct) * 100 if pd.notna(cq_total_avail_pct) and pd.notna(xya_total_avail_pct) else None
    
    # --- TOTAL VACANCY RATE ---
    cq_total_vac_pct = get_value(total_market_df, current_period, 'vacant_total_percent')
    pq_total_vac_pct = get_value(total_market_df, prev_quarter_period, 'vacant_total_percent')
    ya_total_vac_pct = get_value(total_market_df, year_ago_period, 'vacant_total_percent')
    xya_total_vac_pct = get_value(total_market_df, x_yrs_ago_period, 'vacant_total_percent')
    
    calculated_metrics['current_quarter_total_vacant_percent'] = cq_total_vac_pct
    calculated_metrics['qoq_change_in_total_vacant_percent_bps'] = (cq_total_vac_pct - pq_total_vac_pct) * 100 if pd.notna(cq_total_vac_pct) and pd.notna(pq_total_vac_pct) else None
    calculated_metrics['yoy_change_in_total_vacant_percent_bps'] = (cq_total_vac_pct - ya_total_vac_pct) * 100 if pd.notna(cq_total_vac_pct) and pd.notna(ya_total_vac_pct) else None
    calculated_metrics['last_x_yrs_change_in_total_vacant_percent_bps'] = (cq_total_vac_pct - xya_total_vac_pct) * 100 if pd.notna(cq_total_vac_pct) and pd.notna(xya_total_vac_pct) else None
    
    # --- AVERAGE ASKING RENT ---
    cq_ask_rate = get_value(total_market_df, current_period, 'avg_asking_rate')
    pq_ask_rate = get_value(total_market_df, prev_quarter_period, 'avg_asking_rate')
    ya_ask_rate = get_value(total_market_df, year_ago_period, 'avg_asking_rate')
    xya_ask_rate = get_value(total_market_df, x_yrs_ago_period, 'avg_asking_rate')
    
    calculated_metrics['current_quarter_asking_rate'] = cq_ask_rate
    calculated_metrics['current_quarter_asking_rate_type'] = formatted_asking_rate_type
    calculated_metrics['qoq_change_in_asking_rate_dollars'] = (cq_ask_rate - pq_ask_rate) if pd.notna(cq_ask_rate) and pd.notna(pq_ask_rate) else None
    calculated_metrics['qoq_change_in_asking_rate_percent'] = ((cq_ask_rate - pq_ask_rate) / pq_ask_rate) * 100 if pd.notna(cq_ask_rate) and pd.notna(pq_ask_rate) and pq_ask_rate != 0 else None
    calculated_metrics['yoy_change_in_asking_rate_dollars'] = (cq_ask_rate - ya_ask_rate) if pd.notna(cq_ask_rate) and pd.notna(ya_ask_rate) else None
    calculated_metrics['yoy_change_in_asking_rate_percent'] = ((cq_ask_rate - ya_ask_rate) / ya_ask_rate) * 100 if pd.notna(cq_ask_rate) and pd.notna(ya_ask_rate) and ya_ask_rate != 0 else None
    calculated_metrics['last_x_yrs_change_in_asking_rate_dollars'] = (cq_ask_rate - xya_ask_rate) if pd.notna(cq_ask_rate) and pd.notna(xya_ask_rate) else None
    calculated_metrics['last_x_yrs_change_in_asking_rate_percent'] = ((cq_ask_rate - xya_ask_rate) / xya_ask_rate) * 100 if pd.notna(cq_ask_rate) and pd.notna(xya_ask_rate) and xya_ask_rate != 0 else None
    
    # --- NET ABSORPTION ---
    calculated_metrics['current_quarter_net_absorption_sf'] = get_value(total_market_df, current_period, 'net_absorption')
    calculated_metrics['prior_quarter_net_absorption_sf'] = get_value(total_market_df, prev_quarter_period, 'net_absorption')
    df_last_4_periods = total_market_df[total_market_df['period'].isin(last_4_periods_list)]
    calculated_metrics['last_4_quarters_net_absorption_sf'] = df_last_4_periods['net_absorption'].sum() if not df_last_4_periods.empty else None
    df_last_x_yrs_periods_data = total_market_df[total_market_df['period'].isin(last_x_yrs_periods_list)]
    calculated_metrics['last_x_yrs_net_absorption_sf'] = df_last_x_yrs_periods_data['net_absorption'].sum() if not df_last_x_yrs_periods_data.empty else None
    
    # --- SUBLEASE AVAILABILITY RATE ---
    cq_subl_avail_pct = get_value(total_market_df, current_period, 'available_sublease_percent')
    pq_subl_avail_pct = get_value(total_market_df, prev_quarter_period, 'available_sublease_percent')
    ya_subl_avail_pct = get_value(total_market_df, year_ago_period, 'available_sublease_percent')
    xya_subl_avail_pct = get_value(total_market_df, x_yrs_ago_period, 'available_sublease_percent')
    
    calculated_metrics['current_quarter_sublease_available_percent'] = cq_subl_avail_pct
    calculated_metrics['qoq_change_in_sublease_available_percent_bps'] = (cq_subl_avail_pct - pq_subl_avail_pct) * 100 if pd.notna(cq_subl_avail_pct) and pd.notna(pq_subl_avail_pct) else None
    calculated_metrics['yoy_change_in_sublease_available_percent_bps'] = (cq_subl_avail_pct - ya_subl_avail_pct) * 100 if pd.notna(cq_subl_avail_pct) and pd.notna(ya_subl_avail_pct) else None
    calculated_metrics['last_x_yrs_change_in_sublease_available_percent_bps'] = (cq_subl_avail_pct - xya_subl_avail_pct) * 100 if pd.notna(cq_subl_avail_pct) and pd.notna(xya_subl_avail_pct) else None
    
    # --- DIRECT AVAILABILITY RATE ---
    cq_direct_avail_pct = get_value(total_market_df, current_period, 'available_direct_percent')
    pq_direct_avail_pct = get_value(total_market_df, prev_quarter_period, 'available_direct_percent')
    ya_direct_avail_pct = get_value(total_market_df, year_ago_period, 'available_direct_percent')
    xya_direct_avail_pct = get_value(total_market_df, x_yrs_ago_period, 'available_direct_percent')
    
    calculated_metrics['current_quarter_direct_available_percent'] = cq_direct_avail_pct
    calculated_metrics['qoq_change_in_direct_available_percent_bps'] = (cq_direct_avail_pct - pq_direct_avail_pct) * 100 if pd.notna(cq_direct_avail_pct) and pd.notna(pq_direct_avail_pct) else None
    calculated_metrics['yoy_change_in_direct_available_percent_bps'] = (cq_direct_avail_pct - ya_direct_avail_pct) * 100 if pd.notna(cq_direct_avail_pct) and pd.notna(ya_direct_avail_pct) else None
    calculated_metrics['last_x_yrs_change_in_direct_available_percent_bps'] = (cq_direct_avail_pct - xya_direct_avail_pct) * 100 if pd.notna(cq_direct_avail_pct) and pd.notna(xya_direct_avail_pct) else None
    
    # =====================
    # CONSTRUCTION METRICS
    # =====================
    
    # --- UNDER CONSTRUCTION ---
    calculated_metrics['current_quarter_under_construction_count'] = get_value(total_market_df, current_period, 'under_construction_property_count')
    calculated_metrics['current_quarter_under_construction_sf'] = get_value(total_market_df, current_period, 'under_construction_area')
    calculated_metrics['prior_quarter_under_construction_sf'] = get_value(total_market_df, prev_quarter_period, 'under_construction_area')
    calculated_metrics['last_year_under_construction_sf'] = get_value(total_market_df, year_ago_period, 'under_construction_area')
    calculated_metrics['last_x_yr_under_construction_sf'] = get_value(total_market_df, x_yrs_ago_period, 'under_construction_area')
    
    # --- DELIVERIES ---
    calculated_metrics['current_quarter_delivered_count'] = get_value(total_market_df, current_period, 'delivered_construction_property_count')
    calculated_metrics['current_quarter_delivered_sf'] = get_value(total_market_df, current_period, 'delivered_construction_area')
    calculated_metrics['prior_quarter_delivered_sf'] = get_value(total_market_df, prev_quarter_period, 'delivered_construction_area')
    df_last_4_periods = total_market_df[total_market_df['period'].isin(last_4_periods_list)]
    calculated_metrics['prior_four_quarter_delivered_sf'] = df_last_4_periods['delivered_construction_area'].sum() if not df_last_4_periods.empty else None
    calculated_metrics['last_x_yr_delivered_sf'] = df_last_x_yrs_periods_data['delivered_construction_area'].sum() if not df_last_x_yrs_periods_data.empty else None
    
    # =====================
    # LEASING ACTIVITY METRICS
    # =====================
    
    # --- LEASING ACTIVITY ---
    if 'total_area_leased_sf' in total_market_df.columns and 'total_leased_count' in total_market_df.columns:
        cq_leased_sf = get_value(total_market_df, current_period, 'total_area_leased_sf')
        pq_leased_sf = get_value(total_market_df, prev_quarter_period, 'total_area_leased_sf')
        ya_leased_sf = get_value(total_market_df, year_ago_period, 'total_area_leased_sf')
        
        calculated_metrics['current_quarter_total_area_leased_sf'] = cq_leased_sf
        calculated_metrics['current_quarter_total_leased_count'] = get_value(total_market_df, current_period, 'total_leased_count')
        calculated_metrics['qoq_change_in_total_area_leased_sf'] = (cq_leased_sf - pq_leased_sf) if pd.notna(cq_leased_sf) and pd.notna(pq_leased_sf) else None
        calculated_metrics['yoy_change_in_total_area_leased_sf'] = (cq_leased_sf - ya_leased_sf) if pd.notna(cq_leased_sf) and pd.notna(ya_leased_sf) else None
        
        avg_leased_sf_last_x_yrs = df_last_x_yrs_periods_data['total_area_leased_sf'].mean() if not df_last_x_yrs_periods_data.empty else None
        calculated_metrics['last_x_yr_avg_total_leased_area_sf'] = avg_leased_sf_last_x_yrs
        calculated_metrics['last_x_yr_avg_total_leased_area_difference_percent'] = ((cq_leased_sf - avg_leased_sf_last_x_yrs) / avg_leased_sf_last_x_yrs) * 100 if pd.notna(cq_leased_sf) and pd.notna(avg_leased_sf_last_x_yrs) and avg_leased_sf_last_x_yrs != 0 else None
    
    # =====================
    # OFFICE-SPECIFIC METRICS
    # =====================

    property_type = (report_params.get("property_type") or "").strip().casefold()
    if property_type == 'office' and not property_class_df.empty:
        for class_type in ['Class A', 'Class B']:
            class_prefix = 'class_a' if class_type == 'Class A' else 'class_b'
            
            # --- CLASS VACANCY RATE ---
            cq_c_vac_pct = get_value(property_class_df, current_period, 'vacant_total_percent', class_type)
            pq_c_vac_pct = get_value(property_class_df, prev_quarter_period, 'vacant_total_percent', class_type)
            ya_c_vac_pct = get_value(property_class_df, year_ago_period, 'vacant_total_percent', class_type)
            xya_c_vac_pct = get_value(property_class_df, x_yrs_ago_period, 'vacant_total_percent', class_type)
            
            calculated_metrics[f'current_quarter_{class_prefix}_total_vacant_percent'] = cq_c_vac_pct
            calculated_metrics[f'qoq_change_in_{class_prefix}_total_vacant_percent_bps'] = (cq_c_vac_pct - pq_c_vac_pct) * 100 if pd.notna(cq_c_vac_pct) and pd.notna(pq_c_vac_pct) else None
            calculated_metrics[f'yoy_change_in_{class_prefix}_total_vacant_percent_bps'] = (cq_c_vac_pct - ya_c_vac_pct) * 100 if pd.notna(cq_c_vac_pct) and pd.notna(ya_c_vac_pct) else None
            calculated_metrics[f'last_x_yrs_change_in_{class_prefix}_total_vacant_percent_bps'] = (cq_c_vac_pct - xya_c_vac_pct) * 100 if pd.notna(cq_c_vac_pct) and pd.notna(xya_c_vac_pct) else None
            
            # --- CLASS ASKING RENT ---
            cq_c_ask_rate = get_value(property_class_df, current_period, 'avg_asking_rate', class_type)
            pq_c_ask_rate = get_value(property_class_df, prev_quarter_period, 'avg_asking_rate', class_type)
            ya_c_ask_rate = get_value(property_class_df, year_ago_period, 'avg_asking_rate', class_type)
            xya_c_ask_rate = get_value(property_class_df, x_yrs_ago_period, 'avg_asking_rate', class_type)
            
            calculated_metrics[f'current_quarter_{class_prefix}_asking_rate'] = cq_c_ask_rate
            calculated_metrics[f'qoq_change_in_{class_prefix}_asking_rate_dollars'] = (cq_c_ask_rate - pq_c_ask_rate) if pd.notna(cq_c_ask_rate) and pd.notna(pq_c_ask_rate) else None
            calculated_metrics[f'qoq_change_in_{class_prefix}_asking_rate_percent'] = ((cq_c_ask_rate - pq_c_ask_rate) / pq_c_ask_rate) * 100 if pd.notna(cq_c_ask_rate) and pd.notna(pq_c_ask_rate) and pq_c_ask_rate != 0 else None
            calculated_metrics[f'yoy_change_in_{class_prefix}_asking_rate_dollars'] = (cq_c_ask_rate - ya_c_ask_rate) if pd.notna(cq_c_ask_rate) and pd.notna(ya_c_ask_rate) else None
            calculated_metrics[f'yoy_change_in_{class_prefix}_asking_rate_percent'] = ((cq_c_ask_rate - ya_c_ask_rate) / ya_c_ask_rate) * 100 if pd.notna(cq_c_ask_rate) and pd.notna(ya_c_ask_rate) and ya_c_ask_rate != 0 else None
            calculated_metrics[f'last_x_yrs_change_in_{class_prefix}_asking_rate_dollars'] = (cq_c_ask_rate - xya_c_ask_rate) if pd.notna(cq_c_ask_rate) and pd.notna(xya_c_ask_rate) else None
            calculated_metrics[f'last_x_yrs_change_in_{class_prefix}_asking_rate_percent'] = ((cq_c_ask_rate - xya_c_ask_rate) / xya_c_ask_rate) * 100 if pd.notna(cq_c_ask_rate) and pd.notna(xya_c_ask_rate) and xya_c_ask_rate != 0 else None
            
            # --- CLASS NET ABSORPTION ---
            cq_c_net_absorption = get_value(property_class_df, current_period, 'net_absorption', class_type)
            pq_c_net_absorption = get_value(property_class_df, prev_quarter_period, 'net_absorption', class_type)
            
            calculated_metrics[f'current_quarter_{class_prefix}_net_absorption_sf'] = cq_c_net_absorption
            calculated_metrics[f'prior_quarter_{class_prefix}_net_absorption_sf'] = pq_c_net_absorption
            
            # Class-specific last 4 quarters net absorption
            df_c_last_4_periods = property_class_df[
                (property_class_df['period'].isin(last_4_periods_list)) & 
                (property_class_df['property_class'] == class_type)
            ]
            calculated_metrics[f'last_4_quarters_{class_prefix}_net_absorption_sf'] = df_c_last_4_periods['net_absorption'].sum() if not df_c_last_4_periods.empty else None
            
            # Class-specific last X years net absorption
            df_c_last_x_yrs_periods = property_class_df[
                (property_class_df['period'].isin(last_x_yrs_periods_list)) & 
                (property_class_df['property_class'] == class_type)
            ]
            calculated_metrics[f'last_x_yrs_{class_prefix}_net_absorption_sf'] = df_c_last_x_yrs_periods['net_absorption'].sum() if not df_c_last_x_yrs_periods.empty else None
            
            # --- CLASS LEASING ACTIVITY ---
            if 'total_area_leased_sf' in property_class_df.columns and 'total_leased_count' in property_class_df.columns:
                cq_c_leased_sf = get_value(property_class_df, current_period, 'total_area_leased_sf', class_type)
                pq_c_leased_sf = get_value(property_class_df, prev_quarter_period, 'total_area_leased_sf', class_type)
                ya_c_leased_sf = get_value(property_class_df, year_ago_period, 'total_area_leased_sf', class_type)
                
                calculated_metrics[f'current_quarter_{class_prefix}_total_area_leased_sf'] = cq_c_leased_sf
                calculated_metrics[f'current_quarter_{class_prefix}_total_leased_count'] = get_value(property_class_df, current_period, 'total_leased_count', class_type)
                calculated_metrics[f'qoq_change_in_{class_prefix}_total_area_leased_sf'] = (cq_c_leased_sf - pq_c_leased_sf) if pd.notna(cq_c_leased_sf) and pd.notna(pq_c_leased_sf) else None
                calculated_metrics[f'yoy_change_in_{class_prefix}_total_area_leased_sf'] = (cq_c_leased_sf - ya_c_leased_sf) if pd.notna(cq_c_leased_sf) and pd.notna(ya_c_leased_sf) else None
                
                # Class-specific X-year averages
                df_c_last_x_yrs_periods = property_class_df[
                    (property_class_df['period'].isin(last_x_yrs_periods_list)) & 
                    (property_class_df['property_class'] == class_type)
                ]
                avg_c_leased_sf_last_x_yrs = df_c_last_x_yrs_periods['total_area_leased_sf'].mean() if not df_c_last_x_yrs_periods.empty else None
                calculated_metrics[f'last_x_yr_{class_prefix}_avg_total_leased_area_sf'] = avg_c_leased_sf_last_x_yrs
                calculated_metrics[f'last_x_yr_{class_prefix}_avg_total_leased_area_difference_percent'] = ((cq_c_leased_sf - avg_c_leased_sf_last_x_yrs) / avg_c_leased_sf_last_x_yrs) * 100 if pd.notna(cq_c_leased_sf) and pd.notna(avg_c_leased_sf_last_x_yrs) and avg_c_leased_sf_last_x_yrs != 0 else None
    
    # Add configuration-based variables
    calculated_metrics['current_quarter'] = report_params.get("quarter") or report_params.get("current_quarter")
    calculated_metrics['market'] = report_params.get("defined_market_name")
    calculated_metrics['property_type'] = report_params.get("property_type")
    calculated_metrics['number_of_years'] = x_years

    logger.info(f"Generated {len(calculated_metrics)} calculated metric values")
    return calculated_metrics
