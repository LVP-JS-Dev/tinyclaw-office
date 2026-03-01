"""
Logging module with structured JSON output for TinyClaw Office.

This module provides a centralized logging configuration that outputs
structured JSON logs for easy parsing and analysis in production environments.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any

from src.shared.config import settings


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        # Create base log entry with standard fields
        log_entry: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add stack trace if present
        if record.stack_info:
            log_entry["stack_trace"] = self.formatStack(record.stack_info)

        # Add extra fields from the record (custom context)
        # Keys that start with underscore are reserved
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "asctime", "continent", "old_continent", "continent_state",
            } and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger with structured JSON output.

    Args:
        name: The name of the logger (typically __name__ from the calling module)

    Returns:
        A configured logger instance

    Example:
        >>> from src.shared.logging import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started", extra={"user_id": "123"})
        {"timestamp": "2025-01-01T12:00:00Z", "level": "INFO", "logger": "myapp",
         "message": "Application started", "user_id": "123", ...}
    """
    # Get or create logger
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())

        # Set log level from settings
        logger.setLevel(getattr(logging, settings.LOG_LEVEL))
        handler.setLevel(getattr(logging, settings.LOG_LEVEL))

        # Add handler to logger
        logger.addHandler(handler)

        # Prevent propagation to avoid duplicate logs
        logger.propagate = False

    return logger


def configure_logging(level: str | None = None) -> None:
    """
    Configure the root logger with structured JSON output.

    This function sets up the root logger and all child loggers to use
    structured JSON formatting. Call this once at application startup.

    Args:
        level: Optional log level (defaults to settings.LOG_LEVEL)

    Example:
        >>> from src.shared.logging import configure_logging
        >>> configure_logging()
    """
    log_level = level or settings.LOG_LEVEL

    # Get root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(getattr(logging, log_level))

    # Configure root logger
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.addHandler(handler)


class LoggerContext:
    """
    Context manager for adding temporary context to log records.

    This allows you to add contextual information to all log messages
    within a specific code block.

    Example:
        >>> logger = get_logger(__name__)
        >>> with LoggerContext(logger, request_id="abc-123"):
        ...     logger.info("Processing request")  # Includes request_id
        ...     logger.warning("Slow response")     # Includes request_id
    """

    def __init__(self, logger: logging.Logger, **context: Any):
        """
        Initialize the logger context.

        Args:
            logger: The logger instance to add context to
            **context: Key-value pairs to add to log records
        """
        self.logger = logger
        self.context = context
        self.old_factory: logging.LogRecord | None = None

    def _record_factory(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        """Custom record factory that injects context."""
        record = self.old_factory(*args, **kwargs)  # type: ignore
        for key, value in self.context.items():
            setattr(record, key, value)
        return record

    def __enter__(self) -> "LoggerContext":
        """Enter the context and inject context into log records."""
        self.old_factory = logging.getLogRecordFactory()
        logging.setLogRecordFactory(self._record_factory)
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit the context and restore the original record factory."""
        logging.setLogRecordFactory(self.old_factory)
