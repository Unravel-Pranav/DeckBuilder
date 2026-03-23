"""
Snowflake Data Loader for Agent Workflow

This module provides a high-level interface for loading Snowflake data
into the agent workflow based on section names and configuration.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from hello.ml.logger import GLOBAL_LOGGER as logger

from hello.ml.utils.snowflake_query_loader import SnowflakeQueryLoader
from hello.ml.utils.snowflake_connector import SnowflakeConnector


class SnowflakeDataLoader:
    """
    High-level data loader for agent workflow integration.

    Manages configuration loading, parameter preparation, and data retrieval
    for sections based on their session type.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Snowflake data loader.

        Args:
            config_path: Path to config.yaml. If None, uses default path.
        """
        if config_path is None:
            # Default path relative to this file
            config_dir = Path(__file__).parent.parent / "config"
            config_path = config_dir / "config.yaml"

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.query_loader = SnowflakeQueryLoader()
        self._connector = None

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            return config

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {str(e)}")
            return {}

    def is_enabled(self) -> bool:
        """
        Check if Snowflake integration is enabled.

        Returns:
            True if enabled in config, False otherwise
        """
        snowflake_config = self.config.get("snowflake", {})
        return snowflake_config.get("enabled", False)

    def get_default_parameters(self) -> Dict[str, Any]:
        """
        Get default query parameters from configuration.

        Returns:
            Dictionary of default parameters
        """
        snowflake_config = self.config.get("snowflake", {})
        return snowflake_config.get("default_parameters", {})

    def load_data_for_section(
        self,
        section_name: str,
        custom_parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Load Snowflake data for a specific section.

        Args:
            section_name: Name of the section (e.g., 'vacancy', 'market_overview')
                         Maps to session_type in agent workflow
            custom_parameters: Optional custom parameters to override defaults
                              Required: defined_market_name, current_quarter, start_period

        Returns:
            JSON string of query results, or None if:
            - Snowflake is disabled
            - Query execution fails
            - Section not found

        Example:
            loader = SnowflakeDataLoader()
            data = loader.load_data_for_section(
                'vacancy',
                {
                    'defined_market_name': 'Kansas City',
                    'current_quarter': '2025-Q2',
                    'start_period': '2024-Q1'
                }
            )
        """
        # Check if Snowflake integration is enabled
        if not self.is_enabled():
            logger.info("Snowflake integration is disabled - skipping data load")
            return None

        try:
            # Prepare parameters by merging defaults with custom
            parameters = self.get_default_parameters().copy()
            if custom_parameters:
                parameters.update(custom_parameters)

            # For testing purposes only 
            # parameters = {}

            # Validate required parameters
            required_params = ["defined_market_name", "current_quarter", "start_period"]
            missing_params = [p for p in required_params if p not in parameters]

            if missing_params:
                logger.warning(
                    f"Missing required parameters for Snowflake query: {missing_params}"
                )
                

            # Get or create connector
            if self._connector is None:
                logger.info("Creating new Snowflake connector")
                self._connector = SnowflakeConnector()

            # Execute query for section
            logger.info(f"Loading Snowflake data for section: {section_name}")
            results = self.query_loader.execute_query_for_section(
                section_name, parameters, self._connector
            )

            if results is None:
                logger.warning(f"No Snowflake data retrieved for section: {section_name}")
                return None

            # Format results as JSON
            json_data = self.query_loader.format_results_as_json(results)
            logger.info(
                f"Successfully loaded {len(results)} rows for section '{section_name}'"
            )

            return json_data

        except Exception as e:
            logger.error(f"Failed to load Snowflake data for section '{section_name}': {str(e)}")
            return None

    def close(self):
        """Close Snowflake connection if open."""
        if self._connector:
            self._connector.disconnect()
            self._connector = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def load_snowflake_data_if_enabled(
    section_name: str,
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Convenience function to load Snowflake data if enabled.

    This is the main function agents should use to optionally load Snowflake data.

    Args:
        section_name: Session/section type (e.g., 'vacancy', 'market_overview')
        custom_parameters: Optional custom parameters

    Returns:
        JSON string of query results if Snowflake is enabled and successful,
        None otherwise

    Example:
        # In agent workflow
        snowflake_data = load_snowflake_data_if_enabled(
            session_type,
            {
                'defined_market_name': 'Kansas City',
                'current_quarter': '2025-Q2',
                'start_period': '2024-Q1'
            }
        )

        # Use snowflake_data if available, otherwise use input_data
        data_to_analyze = snowflake_data if snowflake_data else input_data
    """
    try:
        logger.info(f"section_name ----> : {section_name}")
        logger.info(f"custom_parameters ----> : {custom_parameters}")
        logger.info("load_snowflake_data_if_enabled ----> : ")
        loader = SnowflakeDataLoader()

        if not loader.is_enabled():
            return None

        return loader.load_data_for_section(section_name, custom_parameters)

    except Exception as e:
        logger.error(f"Error loading Snowflake data: {str(e)}")
        return None


# Mapping of common session types to section names
# (In case they differ in naming)
SESSION_TYPE_TO_SECTION_MAP = {
    "vacancy": "vacancy",
    "market_overview": "market_overview",
    "asking_rent": "asking_rent",
    "net_absorption": "net_absorption",
    "construction_activity": "construction_activity",
    "leasing_activity": "leasing_activity",
    # Add more mappings as needed
}


def get_section_name_for_session_type(session_type: str) -> str:
    """
    Map session type to section name for query lookup.

    Args:
        session_type: Session type from agent workflow

    Returns:
        Section name for Snowflake query lookup
    """
    # Direct mapping or fallback to session_type itself
    return SESSION_TYPE_TO_SECTION_MAP.get(session_type.lower(), session_type.lower())


# Example usage
if __name__ == "__main__":
    """Test Snowflake data loader"""
    try:
        # Create loader
        loader = SnowflakeDataLoader()

        # Check if enabled
        if loader.is_enabled():
            logger.info("✅ Snowflake integration is enabled")

            # Test loading data for vacancy section
            test_params = {
                "defined_market_name": "Kansas City",
                "current_quarter": "2025-Q2",
                "start_period": "2024-Q1",
            }

            logger.info(f"\n🔍 Testing data load for 'vacancy' section")
            data = loader.load_data_for_section("vacancy", test_params)

            if data:
                logger.info(f"✅ Successfully loaded data (length: {len(data)} chars)")
                logger.info(f"First 200 chars: {data[:200]}...")
            else:
                logger.info("⚠️  No data retrieved (check Snowflake credentials)")

        else:
            logger.info("ℹ️  Snowflake integration is disabled in config")
            logger.info("   Set 'snowflake.enabled: true' in config.yaml to enable")

    except Exception as e:
        logger.info(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
