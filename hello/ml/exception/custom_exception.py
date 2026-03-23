import sys
import traceback
from typing import Optional, cast, Union

from hello.ml.logger import GLOBAL_LOGGER as logger


class MultiAgentWorkflowException(Exception):
    """
    Custom exception class for Multi-Agent Workflow errors.

    Provides enhanced error information including file location, line number,
    and full traceback for better debugging and logging.
    """

    def __init__(
        self,
        error_message: Union[str, BaseException],
        error_details: Optional[object] = None,
    ):
        # Normalize message - always convert to string
        norm_msg = str(error_message)

        # Extract exception information
        exc_type = exc_value = exc_tb = None
        if error_details is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        elif hasattr(error_details, "exc_info"):  # e.g., sys module
            exc_info_obj = cast(sys, error_details)
            exc_type, exc_value, exc_tb = exc_info_obj.exc_info()
        elif isinstance(error_details, BaseException):
            exc_type, exc_value, exc_tb = (
                type(error_details),
                error_details,
                error_details.__traceback__,
            )
        else:
            # Fallback to current exception info
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Walk to the last frame to report the most relevant location
        last_tb = exc_tb
        while last_tb and last_tb.tb_next:
            last_tb = last_tb.tb_next

        # Safely extract file information
        try:
            self.file_name = (
                last_tb.tb_frame.f_code.co_filename if last_tb else "<unknown>"
            )
            self.lineno = last_tb.tb_lineno if last_tb else -1
        except (AttributeError, TypeError):
            self.file_name = "<unknown>"
            self.lineno = -1

        self.error_message = norm_msg

        # Generate full traceback (if available)
        try:
            if exc_type and exc_tb:
                self.traceback_str = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )
            else:
                self.traceback_str = ""
        except Exception:
            self.traceback_str = ""

        super().__init__(self.__str__())

    def __str__(self) -> str:
        """Return a compact, logger-friendly error message."""
        base = f"Error in [{self.file_name}] at line [{self.lineno}] | Message: {self.error_message}"
        if self.traceback_str:
            return f"{base}\nTraceback:\n{self.traceback_str}"
        return base

    def __repr__(self) -> str:
        return f"MultiAgentWorkflowException(file={self.file_name!r}, line={self.lineno}, message={self.error_message!r})"

    @property
    def has_traceback(self) -> bool:
        """Check if traceback information is available."""
        return bool(self.traceback_str)

    def to_dict(self) -> dict:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "file_name": self.file_name,
            "line_number": self.lineno,
            "message": self.error_message,
            "has_traceback": self.has_traceback,
            "traceback": self.traceback_str if self.has_traceback else None,
        }

    @staticmethod
    def log_exception(
        exception: Exception,
        operation: str = "unknown_operation",
        user_context: str = "unknown_user",
        session_id: str = "unknown_session",
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Static method to log exceptions with rich context.

        Args:
            exception: The exception to log
            operation: Name of the operation that failed
            user_context: User context (e.g., user_id, username)
            session_id: Session identifier
            additional_context: Additional context data to include

        Usage:
            from hello.ml.exception.custom_exception import MultiAgentWorkflowException

            try:
                # Some risky operation
                result = risky_function()
            except Exception as e:
                MultiAgentWorkflowException.log_exception(e, "data_processing", "user123", "session456")
        """
        from hello.ml.logger import GLOBAL_LOGGER as logger

        # Create custom exception with context
        custom_exception = MultiAgentWorkflowException(
            f"Operation '{operation}' failed: {str(exception)}", exception
        )

        # Prepare extra context
        extra_context = {
            "exception_details": custom_exception.to_dict(),
            "operation": operation,
            "user_context": user_context,
            "session_id": session_id,
            "error_type": type(exception).__name__,
            "error_message": str(exception),
        }

        # Add additional context if provided
        if additional_context:
            extra_context.update(additional_context)

        # Log the exception
        logger.error(
            f"Exception occurred in operation '{operation}'", extra=extra_context
        )


if __name__ == "__main__":
    # # Demo: Show how to use the custom exception
    # from hello.ml.logger import GLOBAL_LOGGER as logger
    # """Simulate a data processing function that might fail."""
    # try:
    #     # Simulate some risky operation
    #     x = 1 / 0

    # except Exception as e:

    #     # Create custom exception with context
    #     custom_exception = MultiAgentWorkflowException(
    #         f"Data processing failed: {str(e)}",
    #         e
    #     )

    #     # Log the custom exception with rich context
    #     logger.error(
    #         "MultiAgentWorkflowException occurred",
    #         extra={
    #             "exception_details": custom_exception.to_dict(),
    #             "operation": "process_data",
    #             "user_context": "test_user",
    #             "session_id": "test_session_123"
    #         }
    #     )

    """
        Test file to demonstrate how to use the log_exception utility function.
        """

    def test_basic_usage():
        """Test basic usage of log_exception function."""
        try:
            # Simulate some risky operation
            x = 1 / 0
        except Exception as e:
            MultiAgentWorkflowException.log_exception(
                e, "division_operation", "test_user", "session_123"
            )

    def test_with_additional_context():
        """Test log_exception with additional context."""
        try:
            # Simulate a file operation
            with open("nonexistent_file.txt", "r") as f:
                content = f.read()
        except Exception as e:
            additional_context = {
                "file_path": "nonexistent_file.txt",
                "operation_type": "file_read",
                "severity": "medium",
            }
            MultiAgentWorkflowException.log_exception(
                e, "file_operation", "test_user", "session_456", additional_context
            )

    def test_custom_exception():
        """Test with a custom exception."""
        try:
            # Simulate a custom error
            raise ValueError("Custom error message")
        except Exception as e:
            MultiAgentWorkflowException.log_exception(
                e, "custom_operation", "admin_user", "session_789"
            )

    if __name__ == "__main__":
        logger.info("Testing log_exception utility function...")

        logger.info("\n1. Testing basic usage:")
        test_basic_usage()

        logger.info("\n2. Testing with additional context:")
        test_with_additional_context()

        logger.info("\n3. Testing custom exception:")
        test_custom_exception()

        logger.info("\nAll tests completed! Check the log file for results.")
