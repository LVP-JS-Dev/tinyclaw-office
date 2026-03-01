"""
Authentication and authorization module for TinyClaw Office.

This module provides API key authentication for protecting endpoints
using FastAPI's dependency injection system.
"""

from fastapi import Header, HTTPException, status
from src.shared.config import settings


async def verify_api_key(x_api_key: str = Header(...)) -> bool:
    """
    Verify API key for protected endpoints.

    This dependency function checks that the provided API key matches
    the configured SECRET_KEY. It also validates that SECRET_KEY is
    not set to a weak default value.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        True if authentication successful

    Raises:
        HTTPException: 500 if server not configured properly
        HTTPException: 401 if API key is invalid
    """
    # Check for weak/placeholder SECRET_KEY
    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-in-production":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Server not configured properly",
                "error_type": "ConfigurationError"
            }
        )

    # Verify API key
    if x_api_key != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid API key",
                "error_type": "AuthenticationError"
            }
        )

    return True


async def verify_api_key_optional(x_api_key: str | None = Header(None)) -> bool:
    """
    Optional API key verification for endpoints that work without auth but can use it.

    This allows endpoints to work without authentication but still validate
    the key if provided.

    Args:
        x_api_key: API key from X-API-Key header (optional)

    Returns:
        True if no key provided or if key is valid

    Raises:
        HTTPException: 401 if API key is provided but invalid
    """
    # No key provided - allow anonymous access
    if x_api_key is None:
        return True

    # Key provided - verify it
    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-in-production":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Server not configured properly",
                "error_type": "ConfigurationError"
            }
        )

    if x_api_key != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid API key",
                "error_type": "AuthenticationError"
            }
        )

    return True
