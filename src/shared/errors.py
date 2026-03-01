"""
Error handling module with custom exceptions for TinyClaw Office.

This module provides a standardized exception hierarchy for all services,
with HTTP status code mapping for API error responses.
"""

from typing import Any


# ------------------------------------------------------------------------------
# Base Exception Classes
# ------------------------------------------------------------------------------

class BaseError(Exception):
    """
    Base exception class for all TinyClaw Office errors.

    All custom exceptions inherit from this class, providing consistent
    error handling and the ability to catch all application errors.

    Attributes:
        message: Human-readable error description
        details: Additional error context (optional)

    Example:
        >>> try:
        ...     raise IntegrationError("Service unavailable", details={"service": "tinyclaw"})
        ... except BaseError as e:
        ...     print(f"Error: {e}")
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """
        Initialize the base error.

        Args:
            message: Human-readable error description
            details: Optional additional context about the error
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert error to dictionary for API responses.

        Returns:
            Dictionary containing error type, message, and details
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            **self.details
        }

    @property
    def status_code(self) -> int:
        """
        Get the HTTP status code for this error.

        Returns:
            HTTP status code (default: 500)
        """
        return 500


class ValidationError(BaseError):
    """
    Exception raised for input validation failures.

    Use this when user input or request data is invalid, malformed,
    or missing required fields. Maps to HTTP 400 Bad Request.

    Example:
        >>> if not agent_id:
        ...     raise ValidationError("agent_id is required", details={"field": "agent_id"})
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 400 Bad Request."""
        return 400


class IntegrationError(BaseError):
    """
    Exception raised for external service integration failures.

    Use this when an external service (TinyClaw, MemU, Gondolin) is
    unavailable, returns an error, or cannot be reached. Maps to HTTP 503 Service Unavailable.

    Example:
        >>> if not await service.health_check():
        ...     raise IntegrationError("TinyClaw service unavailable", details={"service": "tinyclaw"})
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 503 Service Unavailable."""
        return 503


class AuthenticationError(BaseError):
    """
    Exception raised for authentication/authorization failures.

    Use this when API keys are invalid, missing, or expired.
    Maps to HTTP 401 Unauthorized.

    Example:
        >>> if credentials.credentials != settings.SECRET_KEY:
        ...     raise AuthenticationError("Invalid API key")
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 401 Unauthorized."""
        return 401


class NotFoundError(BaseError):
    """
    Exception raised when a requested resource is not found.

    Use this when an agent, memory, or other resource doesn't exist.
    Maps to HTTP 404 Not Found.

    Example:
        >>> if agent is None:
        ...     raise NotFoundError(f"Agent {agent_id} not found", details={"agent_id": agent_id})
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 404 Not Found."""
        return 404


class ConfigurationError(BaseError):
    """
    Exception raised for configuration or environment issues.

    Use this when required environment variables are missing or
    configuration is invalid. Maps to HTTP 500 Internal Server Error.

    Example:
        >>> if not settings.OPENAI_API_KEY:
        ...     raise ConfigurationError("OPENAI_API_KEY is required")
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 500 Internal Server Error."""
        return 500


class RateLimitError(BaseError):
    """
    Exception raised when rate limit is exceeded.

    Use this when API rate limits are hit. Maps to HTTP 429 Too Many Requests.

    Example:
        >>> if request_count > rate_limit:
        ...     raise RateLimitError("Rate limit exceeded", details={"retry_after": 60})
    """

    @property
    def status_code(self) -> int:
        """Return HTTP 429 Too Many Requests."""
        return 429


# ------------------------------------------------------------------------------
# Service-Specific Exceptions
# ------------------------------------------------------------------------------

class TinyClawError(IntegrationError):
    """
    Exception raised for TinyClaw-specific integration failures.

    Example:
        >>> raise TinyClawError("Failed to route message", details={"channel": "discord"})
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize TinyClaw error with default service context."""
        details = details or {}
        details.setdefault("service", "tinyclaw")
        super().__init__(message, details)


class MemUError(IntegrationError):
    """
    Exception raised for MemU-specific integration failures.

    Example:
        >>> raise MemUError("Failed to store memory", details={"agent_id": "agent-123"})
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize MemU error with default service context."""
        details = details or {}
        details.setdefault("service", "memu")
        super().__init__(message, details)


class GondolinError(IntegrationError):
    """
    Exception raised for Gondolin-specific integration failures.

    Example:
        >>> raise GondolinError("VM creation failed", details={"vm_id": "vm-456"})
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize Gondolin error with default service context."""
        details = details or {}
        details.setdefault("service", "gondolin")
        super().__init__(message, details)


# ------------------------------------------------------------------------------
# HTTP Status Code Mapping
# ------------------------------------------------------------------------------

def http_status_from_error(error: Exception) -> int:
    """
    Get the appropriate HTTP status code for an exception.

    This function maps exceptions to their HTTP status codes for
    use in FastAPI error handlers.

    Args:
        error: The exception to map

    Returns:
        HTTP status code

    Example:
        >>> try:
        ...     raise ValidationError("Invalid input")
        ... except Exception as e:
        ...     status = http_status_from_error(e)
        ...     print(status)  # 400
    """
    if isinstance(error, BaseError):
        return error.status_code

    # Default to 500 for unknown exceptions
    return 500


# Export all public exceptions
__all__ = [
    "BaseError",
    "ValidationError",
    "IntegrationError",
    "AuthenticationError",
    "NotFoundError",
    "ConfigurationError",
    "RateLimitError",
    "TinyClawError",
    "MemUError",
    "GondolinError",
    "http_status_from_error",
]
