import sys

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.utils.snowflake_connector import SnowflakeConnector
from hello.ml.utils.snowflake_exception import NoDataReturnedFromSnowflakeException



def fetch_snowflake_data(query: str) -> list[dict]:
    """
    Fetch data from Snowflake for a given section using provided parameters.

    Args:
        query (str): Query string to execute against the Snowflake database.
    Returns:
        List of dictionaries representing rows of data
    """
    try:
        connector = SnowflakeConnector()
        logger.info(f"Executing Snowflake query: {query}")
        results = connector.execute_query(query)
        if not results:
            raise NoDataReturnedFromSnowflakeException(error_message="No data returned from snowflake",
                                                       error_details=sys.exc_info())
        logger.info(f"📊 Query results: {results}")
        logger.info(f"✅ Snowflake query executed successfully! Returned {len(results)} rows")
        return results
    except NoDataReturnedFromSnowflakeException as e:
        raise e
    except Exception as e:
        logger.error("Exception occurred while fetching data from Snowflake", error=str(e))
        raise e