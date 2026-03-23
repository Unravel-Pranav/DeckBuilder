"""
Data Transformation Utilities
This module provides utilities for transforming data, including converting
decimal types to float and calculating quarter-over-quarter (QoQ) and year-over-year (YoY) changes for numeric columns in a DataFrame.
"""

import pandas as pd 
import numpy as np
import decimal 

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException

class DataTransformer:

    def __init__(self):
        pass

    def convert_decimal_to_float(self, obj):
        """Convert decimal.Decimal to float for JSON serialization.
        Args:
            obj: Object to convert
        Returns:
            Converted object or original if not decimal
        """
        try:
            if isinstance(obj, decimal.Decimal):
                return float(obj)
            else:
                return obj
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "convert_decimal_to_float", "system", "N/A")
            return obj

    # Quick one-liners to find numeric columns
    def find_numeric_columns(self, df):
        """
        Identify numeric columns in the DataFrame.
        Args:
            df: DataFrame to analyze
        Returns:
            Dictionary with lists of int, float, and numeric columns
        """
        return {
            'int': df.select_dtypes(include=['int']).columns.tolist(),
            'float': df.select_dtypes(include=['float']).columns.tolist(),
            'numeric': df.select_dtypes(include=[np.number]).columns.tolist()
        }

    def calculate_qoq_yoy_changes(self, df, decimal_places=2):
        """
        Calculate Quarter over Quarter and Year over Year changes for numeric columns.
        
        Args:
            df: DataFrame with PERIOD_LABEL and numeric columns
            decimal_places: Number of decimal places for rounding
        
        Returns:
            DataFrame with original data plus QoQ and YoY columns
        """
        try:
            # Create a copy to avoid modifying original
            result_df = df.copy()
            
            # Ensure data is sorted by PERIOD_LABEL for proper chronological order
            if 'PERIOD_LABEL' in df.columns:
                # Extract year and quarter for proper sorting
                def extract_sort_key(period_label):
                    try:
                        parts = period_label.split()
                        quarter = int(parts[0][1])  # Extract Q1, Q2, etc.
                        year = int(parts[1])
                        return (year, quarter)
                    except:
                        return (0, 0)
                
                result_df['_sort_key'] = result_df['PERIOD_LABEL'].apply(extract_sort_key)
                result_df = result_df.sort_values('_sort_key').drop('_sort_key', axis=1)
            
            # Identify numeric columns (excluding PERIOD_LABEL)
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            logger.info(f"Numeric columns identified: {numeric_cols}")
            
            for col in numeric_cols:
                # QoQ changes - absolute difference
                qoq_absolute = result_df[col].diff()
                # result_df[f'{col}_QoQ_abs'] = qoq_absolute.round(decimal_places)
                
                # QoQ changes - percentage change (as percentage, not basis points)
                qoq_pct = result_df[col].pct_change() * 100
                result_df[f'{col}_QoQ_pct'] = qoq_pct.round(decimal_places)

            for col in numeric_cols:
                # YoY changes - absolute difference
                yoy_absolute = result_df[col].diff(periods=4)
                # result_df[f'{col}_YoY_abs'] = yoy_absolute.round(decimal_places)
                
                # YoY changes - percentage change (as percentage, not basis points)
                yoy_pct = result_df[col].pct_change(periods=4) * 100
                result_df[f'{col}_YoY_pct'] = yoy_pct.round(decimal_places)
                
            return result_df
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "calculate_qoq_yoy_changes", "system", "N/A")
            return df

    def convert_all_to_strings(self, df):
        """
        Convert all DataFrame values to strings.
        
        Args:
            df: DataFrame to convert
            
        Returns:
            DataFrame with all values as strings
        """
        try:
            # Convert all columns to string, handling NaN values
            result_df = df.copy()
            
            for col in result_df.columns:
                # Convert to string, replacing NaN/None with empty string
                result_df[col] = result_df[col].astype(str).replace('nan', '').replace('None', '')
            
            return result_df
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "convert_all_to_strings", "system", "N/A")
            return df

    def process(self, results):
        """
        Process raw query results:
        - Convert decimal types to float
        - Load into DataFrame
        - Calculate QoQ and YoY changes
        - Convert all values to strings
        
        Args:
            results: List of dictionaries from Snowflake query
        Returns:
            Processed list of dictionaries with QoQ and YoY changes, all values as strings
        """
        try:
            # Convert the results
            converted_results = []
            for record in results:
                converted_record = {}
                for key, value in record.items():
                    converted_record[key] = self.convert_decimal_to_float(value)
                converted_results.append(converted_record)

            df = pd.DataFrame(converted_results)
            # Calculate QoQ and YoY changes
            result_df = self.calculate_qoq_yoy_changes(df)
            
            # Fill NaN values with empty strings
            result_df = result_df.fillna('')

            # replace infinity values with np.nan 
            result_df = result_df.replace([np.inf, -np.inf], np.nan)

            # Convert all values to strings
            result_df = self.convert_all_to_strings(result_df)

            return result_df.to_dict(orient='records')
        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "process", "system", "N/A")
            return []


if __name__ == "__main__":
    # Example usage
    import decimal
    transformer = DataTransformer()
    sample_data = [{'SUBMARKET': 'Cass', 'AVAILABLE_TOTAL_PERCENT': 3.3, 'AVAILABLE_DIRECT_PERCENT': 3.3, 'AVAILABLE_SUBLEASE_PERCENT': 0.0, 'AVAILABLE_DIRECT_SF': 146200.0, 'AVAILABLE_SUBLEASE_SF': 0.0}, {'SUBMARKET': 'Clay', 'AVAILABLE_TOTAL_PERCENT': 3.8, 'AVAILABLE_DIRECT_PERCENT': 3.5, 'AVAILABLE_SUBLEASE_PERCENT': 0.3, 'AVAILABLE_DIRECT_SF': 1800612.0, 'AVAILABLE_SUBLEASE_SF': 132695.0}, {'SUBMARKET': 'Jackson', 'AVAILABLE_TOTAL_PERCENT': 5.9, 'AVAILABLE_DIRECT_PERCENT': 5.6, 'AVAILABLE_SUBLEASE_PERCENT': 0.3, 'AVAILABLE_DIRECT_SF': 5235967.0, 'AVAILABLE_SUBLEASE_SF': 263783.0}, {'SUBMARKET': 'Johnson', 'AVAILABLE_TOTAL_PERCENT': 7.5, 'AVAILABLE_DIRECT_PERCENT': 6.6, 'AVAILABLE_SUBLEASE_PERCENT': 0.8, 'AVAILABLE_DIRECT_SF': 5434933.0, 'AVAILABLE_SUBLEASE_SF': 681418.0}, {'SUBMARKET': 'Platte', 'AVAILABLE_TOTAL_PERCENT': 9.1, 'AVAILABLE_DIRECT_PERCENT': 7.1, 'AVAILABLE_SUBLEASE_PERCENT': 2.0, 'AVAILABLE_DIRECT_SF': 1319003.0, 'AVAILABLE_SUBLEASE_SF': 377222.0}, {'SUBMARKET': 'Wyandotte', 'AVAILABLE_TOTAL_PERCENT': 3.9, 'AVAILABLE_DIRECT_PERCENT': 3.5, 'AVAILABLE_SUBLEASE_PERCENT': 0.4, 'AVAILABLE_DIRECT_SF': 1465073.0, 'AVAILABLE_SUBLEASE_SF': 184007.0}]
    df = transformer.process(sample_data)
    logger.info(df)