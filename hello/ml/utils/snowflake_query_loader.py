"""
Snowflake Query Loader Utility

This module provides utilities for loading and executing Snowflake queries
from the YAML configuration file based on section names.
"""

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.utils.snowflake_connector import SnowflakeConnector


class SnowflakeQueryLoader:
    """
    Loader for Snowflake queries from YAML configuration.

    Reads queries from snowflake_queries.yaml and executes them with
    the provided parameters for each section type.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize query loader.

        Args:
            config_path: Path to snowflake_queries.yaml. If None, uses default path.
        """
        if config_path is None:
            # Default path relative to this file
            config_dir = Path(__file__).parent.parent / "config"
            config_path = config_dir / "snowflake_queries.yaml"

        self.config_path = Path(config_path)
        self.queries = self._load_queries()

    def _load_queries(self) -> Dict[str, Dict[str, str]]:
        """
        Load queries from YAML configuration file.

        Returns:
            Dictionary mapping section names to query configurations

        Raises:
            FileNotFoundError: If config file not found
            yaml.YAMLError: If config file is invalid
        """
        try:
            if not self.config_path.exists():
                raise FileNotFoundError(
                    f"Snowflake queries configuration not found at: {self.config_path}"
                )

            with open(self.config_path, 'r') as f:
                queries = yaml.safe_load(f)

            logger.info(f"Loaded {len(queries)} Snowflake query configurations")
            return queries

        except Exception as e:
            logger.error(f"Failed to load Snowflake queries: {str(e)}")
            raise

    def get_query(self, section_name: str) -> Optional[str]:
        """
        Get SQL query template for a specific section.

        Args:
            section_name: Name of the section (e.g., 'vacancy', 'market_overview')

        Returns:
            SQL query template string, or None if section not found
        """
        section_config = self.queries.get(section_name)

        if section_config is None:
            logger.warning(f"No Snowflake query found for section: {section_name}")
            return None

        return section_config.get("query")

    def get_query_description(self, section_name: str) -> Optional[str]:
        """
        Get description for a specific section's query.

        Args:
            section_name: Name of the section

        Returns:
            Query description, or None if section not found
        """
        section_config = self.queries.get(section_name)

        if section_config is None:
            return None

        return section_config.get("description")

    def execute_query_for_section(
        self,
        section_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        connector: Optional[SnowflakeConnector] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute Snowflake query for a specific section with parameters.

        Args:
            section_name: Name of the section (e.g., 'vacancy', 'market_overview')
            parameters: Dictionary of parameters to substitute in query
            connector: Optional SnowflakeConnector instance. If None, creates new one.

        Returns:
            List of result rows as dictionaries, or None if query fails

        Example parameters:
            {
                'defined_market_name': 'Kansas City',
                'publishing_group': 'Office',
                'current_quarter': '2025-Q2',
                'start_period': '2020-Q1',
                'qtd_absorption': 'qtd_net_absorption',
                'ytd_absorption': 'ytd_net_absorption',
                'asking_rate_field': 'avg_asking_rate',
                'dynamic_filters': "defined_market_name = 'Kansas City'",
                'min_transaction_size': 5000
            }
        """
        try:
            # Get query template for section
            query_template = self.get_query(section_name)

            if query_template is None:
                logger.error(f"Cannot execute query - section not found: {section_name}")
                return None

            # Create connector if not provided
            should_close_connector = False
            if connector is None:
                connector = SnowflakeConnector()
                should_close_connector = True

            try:
                # Execute query with parameters
                logger.info(f"Executing Snowflake query for section: {section_name}")
                results = connector.execute_query(query_template, parameters)

                logger.info(
                    f"Successfully executed query for '{section_name}' - returned {len(results)} rows"
                )

                return results

            finally:
                # Close connector if we created it
                if should_close_connector:
                    connector.disconnect()

        except Exception as e:
            logger.error(
                f"Failed to execute Snowflake query for section '{section_name}': {str(e)}"
            )
            return None

    def get_available_sections(self) -> List[str]:
        """
        Get list of available section names.

        Returns:
            List of section names configured in YAML
        """
        return list(self.queries.keys())

    def format_results_as_json(
        self, results: List[Dict[str, Any]]
    ) -> str:
        """
        Format query results as JSON string.

        Args:
            results: List of result dictionaries

        Returns:
            JSON-formatted string of results
        """
        try:
            return json.dumps(results, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to format results as JSON: {str(e)}")
            return "[]"


def load_snowflake_data_for_section(
    section_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    config_path: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience function to load Snowflake data for a section and return as JSON string.

    Args:
        section_name: Name of the section (e.g., 'vacancy', 'market_overview')
        parameters: Dictionary of query parameters
        config_path: Optional path to queries config file

    Returns:
        JSON string of query results, or None if query fails
    """
    try:
        loader = SnowflakeQueryLoader(config_path)
        results = loader.execute_query_for_section(section_name, parameters)

        logger.info(f"Results from load_snowflake_data_for_section: {results}")
        if results is None:
            return None

        return loader.format_results_as_json(results)

    except Exception as e:
        logger.error(f"Failed to load Snowflake data for section '{section_name}': {str(e)}")
        return None


# Example usage
if __name__ == "__main__":
    """Test Snowflake query loader"""
    try:
        # Create loader
        loader = SnowflakeQueryLoader()

        # Show available sections
        logger.info("📋 Available sections:")
        for section in loader.get_available_sections():
            description = loader.get_query_description(section)
            logger.info(f"  - {section}: {description}")

        # Example: Load vacancy data
        test_section = "vacancy"
        test_parameters = {
            "defined_market_name": "Kansas City",
            "publishing_group": "Office",
            "current_quarter": "2025-Q2",
            "start_period": "2024-Q1",
        }

        logger.info(f"\n🔍 Testing query for section: {test_section}")

        # Get query template (without executing)
        query = loader.get_query(test_section)
        logger.info(f"Query template (first 200 chars): {query[:200] if query else 'None'}...")

        # Note: To actually execute, you need valid Snowflake credentials
        # results = loader.execute_query_for_section(test_section, test_parameters)
        # if results:
        #     logger.info(f"✅ Retrieved {len(results)} rows")

    except Exception as e:
        logger.info(f"❌ Error: {str(e)}")
