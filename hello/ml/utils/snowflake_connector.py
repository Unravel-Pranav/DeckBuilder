"""
Snowflake Connector Utility

This module provides utilities for connecting to Snowflake and executing SQL queries.
It supports parameterized queries from the configuration and connection pooling.
Supports both password and private key (.p8) authentication.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pathlib import Path
import snowflake.connector
from snowflake.connector import DictCursor
from threading import Lock
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.services.config import settings
# from hello.ml.utils.data_transformation import DataTransformer



class SnowflakeConnector:
    """
    Snowflake connector for executing SQL queries.

    Provides connection management, query execution, and result formatting
    for Snowflake data warehouse integration.
    """

    _instance: Optional["SnowflakeConnector"] = None
    _instance_lock = Lock()

    def __new__(cls, *args, **kwargs):
        # Double-checked locking to ensure singleton in multi-threaded contexts
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        account: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        warehouse: Optional[str] = None,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        role: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_passphrase: Optional[str] = None,
    ):
        """
        Initialize Snowflake connector with connection parameters.

        Parameters can be provided directly or via environment variables:
        - SNOWFLAKE_ACCOUNT
        - SNOWFLAKE_USER
        - SNOWFLAKE_PASSWORD (optional if using private key)
        - SNOWFLAKE_WAREHOUSE
        - SNOWFLAKE_DATABASE
        - SNOWFLAKE_SCHEMA
        - SNOWFLAKE_ROLE
        - SNOWFLAKE_PRIVATE_KEY_PATH (path to .p8 file)
        - SNOWFLAKE_PRIVATE_KEY_PASSPHRASE (passphrase for .p8 file)

        Authentication priority:
        1. Private key authentication (if private_key_path provided)
        2. Password authentication (if password provided)
        """
        # Prevent re-initialization if instance already initialized
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.account = account or settings.snowflake_account
        self.user = user or settings.snowflake_user
        self.password = password or settings.snowflake_private_key_passphrase
        self.warehouse = warehouse or settings.snowflake_warehouse
        self.database = database or settings.snowflake_database
        self.schema = schema or settings.snowflake_schema
        self.role = role or settings.snowflake_role
        self.private_key_path = private_key_path or settings.snowflake_private_key_path
        self.private_key_passphrase = private_key_passphrase or settings.snowflake_private_key_passphrase

        self._connection = None
        self._private_key_bytes = None
        self._connect_lock = Lock()
        self._load_private_key()
        self._validate_config()
        self._initialized = True

    def _load_private_key(self):
        """Load and process the private key file if provided."""
        logger.info("Loading private key...")
        if not self.private_key_path:
            logger.info("No private key path provided, will use password authentication")
            logger.info("No private key path provided, will use password authentication")
            return

        try:
            # Resolve the path (support both absolute and relative paths)
            key_path = Path(self.private_key_path)

            if not key_path.is_absolute():
                # If relative path, resolve from project root
                project_root = Path(__file__).parent.parent.parent.parent
                key_path = project_root / self.private_key_path
            logger.info(f"Resolved private key path: {key_path}")

            if not key_path.exists():
                raise FileNotFoundError(f"Private key file not found: {key_path}")

            logger.info(f"Loading private key from: {key_path}")

            # Read the private key file
            with open(key_path, "rb") as key_file:
                # Load the PEM private key
                passphrase_bytes = None
                if self.private_key_passphrase:
                    passphrase_bytes = self.private_key_passphrase.encode()

                p_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=passphrase_bytes,
                    backend=default_backend()
                )

                # Convert to DER format (PKCS8) for Snowflake
                self._private_key_bytes = p_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )

            logger.info("✅ Private key loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load private key: {str(e)}")
            raise ValueError(f"Failed to load private key from {self.private_key_path}: {str(e)}")

    def _validate_config(self):
        """Validate that required connection parameters are provided."""
        # Basic required parameters
        required_params = {
            "account": self.account,
            "user": self.user,
        }

        missing_params = [k for k, v in required_params.items() if not v]

        if missing_params:
            raise ValueError(
                f"Missing required Snowflake configuration parameters: {', '.join(missing_params)}. "
                f"Please set them via constructor arguments or environment variables."
            )

        # Validate authentication method
        has_password = bool(self.password)
        has_private_key = bool(self._private_key_bytes)

        if not has_password and not has_private_key:
            raise ValueError(
                "Authentication required: provide either SNOWFLAKE_PASSWORD or "
                "SNOWFLAKE_PRIVATE_KEY_PATH with SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"
            )

        if has_private_key:
            logger.info("Using private key authentication")
        else:
            logger.info("Using password authentication")

    def connect(self) -> snowflake.connector.SnowflakeConnection:
        """
        Establish connection to Snowflake using either private key or password authentication.

        Returns:
            Snowflake connection object

        Raises:
            Exception: If connection fails
        """
        try:
            if self._connection and not self._connection.is_closed():
                return self._connection

            # Ensure only one thread establishes the connection
            with self._connect_lock:
                if self._connection and not self._connection.is_closed():
                    return self._connection

                logger.info(f"Connecting to Snowflake account: {self.account}")

                # Base connection parameters
                connection_params = {
                    "account": self.account,
                    "user": self.user
                }

                # Add optional connection parameters only if they exist
                if self.warehouse:
                    connection_params["warehouse"] = self.warehouse
                if self.database:
                    connection_params["database"] = self.database

                # Add authentication (private key takes priority)
                if self._private_key_bytes:
                    connection_params["private_key"] = self._private_key_bytes
                    logger.info("Using private key authentication")
                else:
                    connection_params["password"] = self.password
                    logger.info("Using password authentication")

                # Add optional parameters
                if self.schema:
                    connection_params["schema"] = self.schema
                if self.role:
                    connection_params["role"] = self.role

                

                self._connection = snowflake.connector.connect(**connection_params)

                # Explicitly set warehouse, database, and schema after connection
                cursor = self._connection.cursor()
            
                try:
                    if self.warehouse:
                        cursor.execute(f"USE WAREHOUSE {self.warehouse}")
                        logger.info(f"Set active warehouse: {self.warehouse}")
                    
                    if self.database:
                        cursor.execute(f"USE DATABASE {self.database}")
                        logger.info(f"Set active database: {self.database}")
                        
                    if self.schema:
                        cursor.execute(f"USE SCHEMA {self.schema}")
                        logger.info(f"Set active schema: {self.schema}")
                        
                    if self.role:
                        cursor.execute(f"USE ROLE {self.role}")
                        logger.info(f"Set active role: {self.role}")
                        
                except Exception as setup_error:
                    logger.warning(f"Failed to set some session parameters: {setup_error}")
                    # Continue anyway - let queries specify full object names if needed
                finally:
                    cursor.close()

                logger.info("✅ Successfully connected to Snowflake")
                return self._connection

        except Exception as e:
            logger.error(f"❌ Failed to connect to Snowflake: {str(e)}")
            raise e

    def disconnect(self):
        """Close the Snowflake connection."""
        if self._connection and not self._connection.is_closed():
            self._connection.close()
            logger.info("Snowflake connection closed")
            self._connection = None

    def _is_token_expired_error(self, error: Exception) -> bool:
        """
        Check if the error is due to an expired authentication token.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if the error indicates token expiration
        """
        error_str = str(error).lower()
        token_expired_indicators = [
            "authentication token has expired",
            "390114",
            "08001",
            "token expired",
            "session expired"
        ]
        return any(indicator in error_str for indicator in token_expired_indicators)

    def _force_reconnect(self):
        """
        Force a reconnection by closing the current connection and creating a new one.
        """
        logger.info("Forcing Snowflake reconnection due to token expiration")
        if self._connection and not self._connection.is_closed():
            try:
                self._connection.close()
            except Exception as close_error:
                logger.warning(f"Error closing expired connection: {close_error}")
        
        self._connection = None
        # The next connect() call will create a fresh connection

    def _test_connection_health(self) -> bool:
        """
        Test if the current connection is healthy by executing a simple query.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            if not self._connection or self._connection.is_closed():
                return False
            
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            
            return result is not None and result[0] == 1
            
        except Exception as e:
            logger.warning(f"Connection health check failed: {e}")
            return False

    def get_available_warehouses(self) -> List[str]:
        """
        Get list of available warehouses for the current user.
        
        Returns:
            List of warehouse names that the user has access to
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()
            cursor.execute("SHOW WAREHOUSES")
            warehouses = cursor.fetchall()
            cursor.close()
            
            warehouse_names = [row[0] for row in warehouses]
            logger.info(f"Available warehouses: {warehouse_names}")
            return warehouse_names
            
        except Exception as e:
            logger.error(f"Failed to get available warehouses: {str(e)}")
            return []

    def get_available_databases(self) -> List[str]:
        """
        Get list of available databases for the current user.
        
        Returns:
            List of database names that the user has access to
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()
            cursor.execute("SHOW DATABASES")
            databases = cursor.fetchall()
            cursor.close()
            
            database_names = [row[1] for row in databases]  # Database name is in column 1
            logger.info(f"Available databases: {database_names}")
            return database_names
            
        except Exception as e:
            logger.error(f"Failed to get available databases: {str(e)}")
            return []

    def set_warehouse(self, warehouse: str):
        """
        Set the active warehouse for the current session.
        
        Args:
            warehouse: Name of the warehouse to activate
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()
            cursor.execute(f"USE WAREHOUSE {warehouse}")
            cursor.close()
            logger.info(f"Successfully set warehouse to: {warehouse}")
            self.warehouse = warehouse
        except Exception as e:
            logger.error(f"Failed to set warehouse {warehouse}: {str(e)}")
            raise e

    def convert_specific_fields(self, data: List[Dict]) -> List[Dict]:
        """
        Convert only specific fields from Decimal to float in a list of dictionaries.
        
        Args:
            data: List of dictionaries containing the data
            fields_to_convert: List of field names to convert. If None, converts all Decimal fields.
            
        Returns:
            List of dictionaries with specified fields converted to float
        """
        try:
            # Handle edge cases
            if not data:
                return data
            
            if not isinstance(data, list):
                logger.warning(f"Expected list, got {type(data).__name__}, returning original data")
                return data
            
            result = []
            
            for i, item in enumerate(data):
                try:
                    # Skip non-dict items
                    if not isinstance(item, dict):
                        logger.warning(f"Item at index {i} is not a dict, skipping")
                        continue
                    
                    converted_item = {}
                    for key, value in item.items():
                        try:
                            # Convert Decimal to float, preserve other types
                            if isinstance(value, Decimal):
                                converted_item[key] = float(value)
                            else:
                                converted_item[key] = value
                        except (ValueError, TypeError, OverflowError) as conv_error:
                            logger.warning(f"Failed to convert field '{key}' at index {i}: {conv_error}")
                            converted_item[key] = value  # Keep original value
                    
                    result.append(converted_item)
                    
                except Exception as item_error:
                    logger.error(f"Error processing item at index {i}: {item_error}")
                    continue  # Skip problematic items
            
            logger.info(f"Converted {len(result)} items successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to convert specific fields: {str(e)}")
            return data

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        fetch_size: int = 1000,
        max_retries: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results as a list of dictionaries.
        Automatically handles token expiration by reconnecting and retrying.

        Args:
            query: SQL query string with optional {parameter} placeholders
            parameters: Dictionary of parameter values to substitute in query
            fetch_size: Number of rows to fetch at a time
            max_retries: Maximum number of retry attempts for token expiration

        Returns:
            List of dictionaries, where each dict represents a row

        Raises:
            Exception: If query execution fails after all retries
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                # Substitute parameters in query if provided
                if parameters:
                    query = self._substitute_parameters(query, parameters)

                logger.info(f"Executing Snowflake query (attempt {attempt + 1}/{max_retries + 1}): {query[:200]}...")

                # Ensure connection is established and healthy
                connection = self.connect()
                
                # Test connection health before proceeding
                if not self._test_connection_health():
                    logger.warning("Connection health check failed, forcing reconnection")
                    self._force_reconnect()
                    connection = self.connect()
                
                # Ensure warehouse is active before executing query
                if self.warehouse:
                    try:
                        test_cursor = connection.cursor()
                        test_cursor.execute("SELECT CURRENT_WAREHOUSE()")
                        current_warehouse = test_cursor.fetchone()
                        test_cursor.close()
                        
                        if not current_warehouse or current_warehouse[0] != self.warehouse:
                            logger.info(f"Setting warehouse to {self.warehouse} before query execution")
                            warehouse_cursor = connection.cursor()
                            warehouse_cursor.execute(f"USE WAREHOUSE {self.warehouse}")
                            warehouse_cursor.close()
                    except Exception as warehouse_error:
                        logger.warning(f"Could not set warehouse {self.warehouse}: {warehouse_error}")
                        # Continue anyway - the query might still work
                
                logger.info(f"Query ---> : {query}")
                # Execute query with DictCursor for dictionary results
                cursor = connection.cursor(DictCursor)
                cursor.execute(query)

                # Fetch all results
                results = cursor.fetchall()
                results = self.convert_specific_fields(results)
                logger.info(f"Results from snowflake: {results}")

                cursor.close()

                # data_transformer = DataTransformer()
                # results = data_transformer.process(results)

                logger.info(f"Query returned {len(results)} rows")
                return results

            except Exception as e:
                last_exception = e
                error_str = str(e)
                
                # Check if this is a token expiration error
                if self._is_token_expired_error(e):
                    logger.warning(f"Token expired on attempt {attempt + 1}: {error_str}")
                    
                    if attempt < max_retries:
                        logger.info(f"Attempting to reconnect and retry (attempt {attempt + 2}/{max_retries + 1})")
                        self._force_reconnect()
                        continue
                    else:
                        logger.error(f"Token expired and max retries ({max_retries}) exceeded")
                        break
                else:
                    # For non-token-expiration errors, don't retry
                    raise e
        
        # If we get here, all retries failed
        logger.error(f"Failed to execute Snowflake query after {max_retries + 1} attempts: {str(last_exception)}")
        raise last_exception

    def _substitute_parameters(self, query: str, parameters: Dict[str, Any]) -> str:
        """
        Substitute parameters in SQL query string.

        Args:
            query: SQL query with {parameter} placeholders
            parameters: Dictionary of parameter values

        Returns:
            Query string with parameters substituted
        """
        try:
            # Use format_map for safe parameter substitution
            return query.format_map(parameters)
        except KeyError as e:
            logger.error(f"Missing required parameter in query: {str(e)}")
            raise ValueError(f"Missing required parameter: {str(e)}")

    def test_connection(self) -> bool:
        """
        Test the Snowflake connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()
            cursor.execute("SELECT CURRENT_VERSION()")
            version = cursor.fetchone()
            cursor.close()

            logger.info(f"Snowflake connection test successful. Version: {version[0]}")
            return True

        except Exception as e:
            logger.error(f"Snowflake connection test failed: {str(e)}")
            return False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


def create_snowflake_connector(**kwargs) -> SnowflakeConnector:
    """
    Factory function to create a Snowflake connector instance.

    Args:
        **kwargs: Connection parameters (account, user, password, etc.)

    Returns:
        SnowflakeConnector instance
    """
    return SnowflakeConnector(**kwargs)


# Example usage
if __name__ == "__main__":
    """Test Snowflake connector and discover available resources"""
    try:
        # Create connector (will use environment variables)
        connector = SnowflakeConnector()

        # Test connection
        if connector.test_connection():
            logger.info("✅ Snowflake connection successful")
            
            # Discover available resources
            logger.info("\n🔍 Discovering available resources...")
            
            warehouses = connector.get_available_warehouses()
            logger.info(f"📦 Available warehouses: {warehouses}")
            
            databases = connector.get_available_databases()
            logger.info(f"🗄️ Available databases: {databases}")
            
            # Try to set a warehouse if available
            if warehouses:
                first_warehouse = warehouses[0]
                logger.info(f"\n🎯 Trying to use warehouse: {first_warehouse}")
                try:
                    connector.set_warehouse(first_warehouse)
                    logger.info(f"✅ Successfully set warehouse to: {first_warehouse}")
                    
                    # Now try the original query that was failing
                    test_query = """

                    SELECT
                        SUBMARKET,
                        ROUND(available_total_percent * 100, 1) AS available_total_percent,
                        ROUND(available_direct_percent * 100, 1) AS available_direct_percent,
                        ROUND(available_sublease_percent * 100, 1) AS available_sublease_percent,
                        TRIM(TO_CHAR(CAST(AVAILABLE_DIRECT_AREA AS INT), '999,999,999')) AS available_direct_sf,
                        TRIM(TO_CHAR(CAST(AVAILABLE_SUBLEASE_AREA AS INT), '999,999,999')) AS available_sublease_sf
                    FROM PROD_USDM_DB.MARKET_AGGREGATED_STATS.PROPERTY_HISTORY_AGGREGATED_STATS
                    WHERE defined_market_name = 'Kansas City Industrial'
                    AND breakdown_full_desc = 'Market | Vacancy Index | Submarket'
                    AND period = '2025 Q2'
                    ORDER BY SUBMARKET ASC;



                    """
                    results = connector.execute_query(test_query)
                    logger.info(f"📊 Query results: {results}")
                    logger.info(f"✅ Query executed successfully! Returned {len(results)} rows")
                    
                except Exception as warehouse_error:
                    logger.info(f"❌ Failed to set warehouse: {warehouse_error}")
            else:
                logger.info("⚠️ No warehouses available")

        else:
            logger.info("❌ Snowflake connection failed")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        connector.disconnect()
