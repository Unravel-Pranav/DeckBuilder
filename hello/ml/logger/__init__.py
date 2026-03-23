# logger/__init__.py
from hello.ml.logger.custom_logger import CustomLogger

# Create a single shared logger instance
GLOBAL_LOGGER = CustomLogger().get_logger("multi_agent_workflow")
