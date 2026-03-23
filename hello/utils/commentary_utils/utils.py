import pandas as pd
import numpy as np
from hello.ml.logger import GLOBAL_LOGGER as logger

def parse_quarter_string(quarter_str: str) -> tuple:
    """Parse a quarter string in the format 'YYYY QQ' into year and quarter number."""
    parts = quarter_str.split(' ')
    year = int(parts[0])
    q_num = int(parts[1][1:])
    return year, q_num

def get_prev_quarter(year: int, q_num: int) -> tuple:
    """Calculate the previous quarter based on the given year and quarter."""
    if q_num == 1:
        return year - 1, 4
    else:
        return year, q_num - 1
    
def format_period_code(year: int, q_num: int) -> str:
    """Format year and quarter number into a period code string."""
    return f"{year} Q{q_num}"

def get_x_years_ago_quarter(year: int, q_num: int, x_years: int = 1) -> tuple:
    """Calculate the quarter from X years ago based on the given year and quarter."""
    return year - x_years, q_num

def get_value(df: pd.DataFrame, period_code: str | None, column: str, property_class_filter: str | None = None, default_value=None):
    """Safely extract a specific value from a DataFrame based on period and optional property class."""
    if period_code is None:
        return default_value
        
    filtered_df = df[df['period'] == period_code]
    if property_class_filter:
        filtered_df = filtered_df[filtered_df['property_class'] == property_class_filter]
    
    if not filtered_df.empty:
        value = filtered_df[column].iloc[0]
        # Convert pd.NA to None for type consistency
        if pd.isna(value):
            return None
        # Ensure we return a scalar value, not a Series
        if hasattr(value, 'item'):
            return value.item()
        return float(value) if isinstance(value, (int, float)) else value
    return default_value

def get_last_n_periods_list(current_period_code: str, num_periods: int, all_available_periods: list) -> list:
    """Get a list of the last N periods including the current period."""
    try:
        current_index = all_available_periods.index(current_period_code)
        start_index = max(0, current_index - num_periods + 1)
        return all_available_periods[start_index:current_index + 1]
    except ValueError:
        logger.warning(f"Current period {current_period_code} not found in available periods")
        return []

def get_periods_from_to(start_period: str, end_period: str, all_available_periods: list) -> list:
    """
    Get all periods from start_period to end_period (inclusive) that exist in the available periods list.
    
    Args:
        start_period: Starting period (e.g., "2022 Q2")
        end_period: Ending period (e.g., "2025 Q2") 
        all_available_periods: Sorted list of all available periods
        
    Returns:
        list: List of periods from start to end that exist in the data
    """
    try:
        start_index = all_available_periods.index(start_period)
        end_index = all_available_periods.index(end_period)
        
        if start_index <= end_index:
            return all_available_periods[start_index:end_index + 1]
        else:
            logger.warning(f"Start period {start_period} comes after end period {end_period}")
            return []
            
    except ValueError as e:
        logger.warning(f"Period not found in available periods: {e}")
        return []
    
def ensure_all_periods(df: pd.DataFrame, period_col: str, all_periods: pd.Series, fill_value: float = 0) -> pd.DataFrame:
    logger.debug(f"_ensure_all_periods called with period_col={period_col}, fill_value={fill_value}")
    logger.debug(f"all_periods: {all_periods.tolist()}")
    df = df.set_index(period_col)
    df = df.reindex(all_periods, fill_value=np.nan).reset_index()
    df = df.rename(columns={'index': period_col})
    # Fill all columns except period with 0 where missing
    for col in df.columns:
        if col != period_col:
            df[col] = df[col].fillna(fill_value)
    return df

def ensure_all_classes(df: pd.DataFrame, period_col: str, class_col: str, classes: list, fill_value: float = 0) -> pd.DataFrame:
    logger.debug(f"_ensure_all_classes called with period_col={period_col}, class_col={class_col}, classes={classes}, fill_value={fill_value}")
    periods = df[period_col].unique()
    idx = pd.MultiIndex.from_product([list(periods), classes], names=[period_col, class_col])
    df = df.set_index([period_col, class_col])
    df = df.reindex(idx, fill_value=np.nan).reset_index()
    # Fill all columns except period and class with 0 where missing
    for col in df.columns:
        if col not in [period_col, class_col]:
            df[col] = df[col].fillna(fill_value)
    return df

def get_net_gross_formatting(asking_rate_field: str, monthly_yearly_select: str) -> str:
    logger.debug(f"_get_net_gross_formatting called with asking_rate_field={asking_rate_field}, monthly_yearly_select={monthly_yearly_select}")
    """Determine the net/gross parameter string based on asking rate field and time period.
    
    Formats the rent descriptor based on whether the rate is net, gross, or unspecified,
    and whether it's reported monthly or yearly.
    
    Args:
        asking_rate_field (str): Asking rate field name (e.g., "avg_asking_rate_gross")
        monthly_yearly_select (str): 'Monthly' or 'Yearly' time period specification
        
    Returns:
        str: Formatted parameter string (e.g., "gross per sq ft/yr")
        
    Examples:
        >>> _get_net_gross_formatting("avg_asking_rate_gross", "Yearly")
        "per sq. ft. year gross"
        >>> _get_net_gross_formatting("avg_asking_rate_net", "Monthly")
        "net per sq. ft. month"
        >>> _get_net_gross_formatting("avg_asking_rate", "Yearly")
        "per sq. ft. year"
    """
    rate_type = ""
    period = "per sq. ft. month" if monthly_yearly_select == "Monthly" else "per sq. ft. year"

    if 'gross' in asking_rate_field.lower():
        rate_type = "gross"
    elif 'net' in asking_rate_field.lower():
        rate_type = "net"

    result = f"{period} {rate_type}" if rate_type else period
    logger.debug(f"Resulting net/gross formatting: {result}")
    return result

def format_metric_value(var_name: str, var_value) -> str:
    """
    Format metric values based on their suffix conventions.
    
    Args:
        var_name: The variable name (e.g., "current_quarter_total_available_percent")
        var_value: The numeric value to format
        
    Returns:
        str: Formatted value as string
    """
    if var_value is None or pd.isna(var_value):
        return "N/A"
    
    try:
        # Convert to float for processing
        numeric_value = float(var_value)
        
        # Format based on suffix
        if var_name.endswith('_percent'):
            # Round to 1 decimal place for percentages
            return f"{numeric_value:.1f}%"
        elif var_name.endswith('_bps'):
            # Round to whole number, always positive for basis points
            return f"{abs(numeric_value):.0f}"
        elif var_name.endswith('_dollars') or var_name.endswith('_rate'):
            # Format as currency with 2 decimal places
            return f"${numeric_value:.2f}"
        elif var_name.endswith('_sf'):
            # Check if this is an absorption metric for special positive/negative handling
            if '_absorption' in var_name:
                if abs(numeric_value) >= 1_000_000:
                    # Format as millions with 1 decimal place
                    millions = abs(numeric_value) / 1_000_000
                    if numeric_value >= 0:
                        return f"positive {millions:.1f} million sq. ft"
                    else:
                        return f"negative {millions:.1f} million sq. ft"
                else:
                    # Format with commas, no decimal places for thousands
                    if numeric_value >= 0:
                        return f"positive {numeric_value:,.0f} sq. ft"
                    else:
                        return f"negative {abs(numeric_value):,.0f} sq. ft"
            elif '_leased' in var_name:
                # Format as abs millions with 1 decimal place
                if abs(numeric_value) >= 1_000_000:
                    millions = abs(numeric_value) / 1_000_000
                    if numeric_value >= 0:
                        return f"{millions:.1f} million sq. ft leased"
                    else:
                        return f"{millions:.1f} million sq. ft unleased"
                else:
                    # Format with commas, no decimal places for thousands
                    if numeric_value >= 0:
                        return f"{numeric_value:,.0f} sq. ft leased"
                    else:
                        return f"{abs(numeric_value):,.0f} sq. ft unleased"
            else:
                # Regular square footage formatting (non-absorption)
                if abs(numeric_value) >= 1_000_000:
                    # Format as millions with 1 decimal place
                    millions = numeric_value / 1_000_000
                    return f"{millions:.1f} million sq. ft"
                else:
                    # Format with commas, no decimal places for thousands
                    return f"{numeric_value:,.0f} sq. ft"
        else:
            # Default formatting for other metrics
            if isinstance(var_value, float):
                # If it's a float, format with appropriate precision
                if numeric_value == int(numeric_value):
                    return f"{int(numeric_value):,}"
                else:
                    return f"{numeric_value:,.2f}"
            else:
                return str(var_value)
                
    except (ValueError, TypeError):
        # If conversion fails, return as string
        return str(var_value)
