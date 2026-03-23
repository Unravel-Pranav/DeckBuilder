import sys
import traceback
from typing import Optional, Union, cast


class NoDataReturnedFromSnowflakeException(Exception):
    """
    Exception raised when no data is returned from Snowflake.

    Mirrors the rich diagnostic behavior of MultiAgentWorkflowException:
    captures file name, line number, and full traceback for easier debugging.
    """

    def __init__(
        self,
        error_message: Union[str, BaseException] = "No data returned from Snowflake",
        error_details: Optional[object] = None,
    ):
        # Normalize message
        normalized_message = str(error_message)

        # Extract exception information
        exc_type = exc_value = exc_tb = None
        if error_details is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
        elif hasattr(error_details, "exc_info"):
            # e.g., sys module
            exc_info_obj = cast(sys, error_details)
            exc_type, exc_value, exc_tb = exc_info_obj.exc_info()
        elif isinstance(error_details, BaseException):
            exc_type, exc_value, exc_tb = (
                type(error_details),
                error_details,
                error_details.__traceback__,
            )
        else:
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Walk to the last frame to report the most relevant location
        last_tb = exc_tb
        while last_tb and last_tb.tb_next:
            last_tb = last_tb.tb_next

        # Safely extract file information; if no traceback, fall back to call-site stack
        try:
            if last_tb:
                self.file_name = last_tb.tb_frame.f_code.co_filename
                self.lineno = last_tb.tb_lineno
            else:
                # Use the caller frame (one level up from this __init__)
                stack = traceback.extract_stack()
                caller = stack[-2] if len(stack) >= 2 else None
                if caller:
                    self.file_name = caller.filename
                    self.lineno = caller.lineno
                else:
                    self.file_name = "<unknown>"
                    self.lineno = -1
        except (AttributeError, TypeError, IndexError):
            self.file_name = "<unknown>"
            self.lineno = -1

        self.error_message = normalized_message

        # Generate full traceback (if available); otherwise include the current stack
        try:
            if exc_type and exc_tb:
                self.traceback_str = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )
            else:
                self.traceback_str = "".join(traceback.format_stack())
        except Exception:
            self.traceback_str = ""

        super().__init__(self.__str__())

    def __str__(self) -> str:
        base = (
            f"Error in [{self.file_name}] at line [{self.lineno}] | "
            f"Message: {self.error_message}"
        )
        if self.traceback_str:
            return f"{base}\nTraceback:\n{self.traceback_str}"
        return base

    def __repr__(self) -> str:
        return (
            f"NoDataReturnedFromSnowflakeException(file={self.file_name!r}, "
            f"line={self.lineno}, message={self.error_message!r})"
        )

    @property
    def has_traceback(self) -> bool:
        return bool(self.traceback_str)

    def to_dict(self) -> dict:
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
        operation: str = "snowflake_no_data",
        query: str = "unknown_query",
        additional_context: Optional[dict] = None,
    ) -> None:
        """
        Log the exception with context, mirroring the style of
        MultiAgentWorkflowException.log_exception.
        """
        from hello.ml.logger import GLOBAL_LOGGER as logger

        custom_exception = NoDataReturnedFromSnowflakeException(
            f"Operation '{operation}' failed for query '{query}': {str(exception)}",
            exception,
        )

        context = {
            "exception_details": custom_exception.to_dict(),
            "operation": operation,
            "query": query,
            "error_type": type(exception).__name__,
            "error_message": str(exception),
        }

        if additional_context:
            context.update(additional_context)

        logger.error(
            f"NoDataReturnedFromSnowflakeException occurred in operation '{operation}'",
            extra=context,
        )

