from hello.utils.commentary_utils.text_narrative_engine import create_narrative_engine
from hello.utils.commentary_utils.text_generation_utils import fetch_calculated_metrics_data
from hello.utils.commentary_utils.metrics_generator import generate_metrics_from_dataframes, generate_calculated_metrics_for_variables
from hello.utils.commentary_utils.text_narrative_engine import TemplateContext
from typing import Any
import pandas as pd
from hello.ml.logger import GLOBAL_LOGGER as logger

class TextGenerator:
    """
    Main text generation class that orchestrates the metrics generation and narrative creation.
    """
    
    def __init__(self, template_path: str | None = None):
        """
        Initialize the text generator.
        
        Args:
            template_path: Optional path to custom YAML template file
        """
        self.narrative_engine = create_narrative_engine(template_path)
    
    def generate_narrative_from_session(
        self,
        report_parameters: dict[str, Any],
        paragraph_keys: list[str] | None = None,
        metric_keys: dict[str, list[str]] | None = None
    ) -> dict[str, str]:
        """
        Generate complete narrative text from report parameters.
        
        Args:
            report_parameters: Report configuration parameters
            paragraph_keys: Optional list of specific paragraphs to generate
            metric_keys: Optional dict mapping paragraph keys to metric keys to include
            
        Returns:
            dict: Dictionary mapping paragraph keys to generated narrative text
        """
        logger.info(f"Generating narrative for {report_parameters.get('property_type', '')} market in {report_parameters.get('defined_markets', [])}")
        
        # Step 1: Fetch raw data using existing data pipeline
        try:
            total_market_df, property_class_df = fetch_calculated_metrics_data(report_parameters)
            logger.debug(f"Fetched data: {len(total_market_df)} total market rows, {len(property_class_df)} property class rows")
        except Exception as e:
            logger.error(f"Failed to fetch data: {e}")
            raise
        
        # Step 2: Generate structured metrics from DataFrames
        try:
            metrics_data = generate_metrics_from_dataframes(
                total_market_df,
                property_class_df,
                report_parameters
            )
            
            # Also generate calculated metrics for variable substitution
            try:
                calculated_metrics = generate_calculated_metrics_for_variables(
                    total_market_df,
                    property_class_df,
                    report_parameters
                )
                
                # Add calculated metrics to the main metrics data
                metrics_data['calculated_metrics'] = calculated_metrics
                logger.info(f"Generated metrics for {len(metrics_data)} metrics with {len(calculated_metrics)} calculated variables")
            except Exception as calc_error:
                logger.warning(f"Could not generate calculated metrics, proceeding with basic metrics only: {calc_error}")
                logger.debug(f"Generated metrics for {len(metrics_data)} metrics")
                
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            raise
        
        # Step 3: Create template context (keep original quarter format)
        context = TemplateContext(
            property_type=report_parameters.get('property_type') or "all",
            office_class=report_parameters.get('office_class'),
            current_quarter=report_parameters.get('quarter') or report_parameters.get('current_quarter') or "",
            market_name=report_parameters.get('defined_markets', ['Unknown Market'])[0],
            number_of_years=int(str(report_parameters.get('history_range')).split('-')[0]) if report_parameters.get('history_range') else 5
        )
        
        # Step 4: Generate narrative using the engine
        try:
            if metric_keys:
                # Generate paragraphs with specific metrics
                narrative = {}
                for para_key in (paragraph_keys or metric_keys.keys()):
                    if para_key in metric_keys:
                        narrative[para_key] = self.narrative_engine.generate_paragraph_text(
                            para_key,
                            metrics_data,
                            context,
                            metric_keys[para_key]
                        )
                    else:
                        narrative[para_key] = self.narrative_engine.generate_paragraph_text(
                            para_key,
                            metrics_data,
                            context
                        )
            else:
                # Generate all paragraphs
                narrative = self.narrative_engine.generate_full_narrative(
                    metrics_data,
                    context,
                    paragraph_keys
                )
                
            logger.info(f"Generated narrative with {len(narrative)} paragraphs")
            return narrative
            
        except Exception as e:
            logger.error(f"Failed to generate narrative: {e}")
            raise
    
    def generate_narrative_from_dataframes(
        self,
        total_market_df: pd.DataFrame,
        property_class_df: pd.DataFrame,
        report_params: dict[str, Any],
        paragraph_keys: list[str] | None = None,
        metric_keys: dict[str, list[str]] | None = None
    ) -> dict[str, str]:
        """
        Generate complete narrative text from pre-fetched DataFrames.
        
        This method is kept for backward compatibility but the session-based method
        is preferred for new integrations.
        
        Args:
            total_market_df: DataFrame with total market metrics by period
            property_class_df: DataFrame with property class metrics by period and class
            report_config: Report configuration parameters
            paragraph_keys: Optional list of specific paragraphs to generate
            metric_keys: Optional dict mapping paragraph keys to metric keys to include
            
        Returns:
            dict: Dictionary mapping paragraph keys to generated narrative text
        """
        logger.info(f"Generating narrative from DataFrames for {report_params.get('property_type')} market")
        
        # Step 1: Generate structured metrics from DataFrames
        try:
            metrics_data = generate_metrics_from_dataframes(
                total_market_df,
                property_class_df,
                report_params
            )
            
            # Also generate calculated metrics for variable substitution
            try:
                calculated_metrics = generate_calculated_metrics_for_variables(
                    total_market_df,
                    property_class_df,
                    report_params
                )
                
                # Add calculated metrics to the main metrics data
                metrics_data['calculated_metrics'] = calculated_metrics
                logger.debug(f"Generated metrics for {len(metrics_data)} metrics with {len(calculated_metrics)} calculated variables")
            except Exception as calc_error:
                logger.warning(f"Could not generate calculated metrics, proceeding with basic metrics only: {calc_error}")
                logger.debug(f"Generated metrics for {len(metrics_data)} metrics")
                
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            raise
        
        # Step 2: Create template context (keep original quarter format)
        context = TemplateContext(
            property_type=report_params.get('property_type') or "all",
            office_class=report_params.get('office_class'),
            current_quarter=report_params.get('quarter') or report_params.get('current_quarter') or "",
            market_name=report_params.get('defined_markets', ['Unknown Market'])[0],
            number_of_years=int(str(report_params.get('history_range')).split('-')[0]) if report_params.get('history_range') else 5
        )
        
        # Step 3: Generate narrative using the engine
        try:
            if metric_keys:
                # Generate paragraphs with specific metrics
                narrative = {}
                for para_key in (paragraph_keys or metric_keys.keys()):
                    if para_key in metric_keys:
                        narrative[para_key] = self.narrative_engine.generate_paragraph_text(
                            para_key,
                            metrics_data,
                            context,
                            metric_keys[para_key]
                        )
                    else:
                        narrative[para_key] = self.narrative_engine.generate_paragraph_text(
                            para_key,
                            metrics_data,
                            context
                        )
            else:
                # Generate all paragraphs
                narrative = self.narrative_engine.generate_full_narrative(
                    metrics_data,
                    context,
                    paragraph_keys
                )
                
            logger.info(f"Generated narrative with {len(narrative)} paragraphs")
            return narrative
            
        except Exception as e:
            logger.error(f"Failed to generate narrative: {e}")
            raise

def generate_market_narrative(
    report_params: dict[str, Any],
    template_path: str | None = None,
    paragraph_keys: list[str] | None = None
) -> dict[str, str]:
    """
    Generate market narrative text using only session and generation parameters.
    
    This is the main API function that should be used for narrative generation.
    It fetches all required data internally and produces complete narrative text.
    
    Args:
        report_params: Report parameters
        template_path: Optional path to custom YAML template file
        paragraph_keys: Optional list of specific paragraphs to generate
        
    Returns:
        dict: Dictionary mapping paragraph keys to generated narrative text
        
    Example:
        ```python
        narrative = generate_market_narrative(session, report_config)
        overview_text = narrative.get("overview", "")
        ```
    """
    generator = TextGenerator(template_path)
    return generator.generate_narrative_from_session(
        report_params,
        paragraph_keys
    )
