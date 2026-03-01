"""
Service coordinator for inter-service communication.

This module provides centralized coordination for all integration services
(TinyClaw, MemU, Gondolin), handling communication, health checks, and
graceful failure handling.
"""

import asyncio
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

import httpx

from src.shared.config import settings
from src.shared.errors import IntegrationError, ValidationError
from src.shared.logging import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------

@dataclass
class ServiceHealth:
    """Health status of a service."""
    service: str
    healthy: bool
    response_time_ms: float | None = None
    error: str | None = None


@dataclass
class ServiceClient:
    """HTTP client configuration for a service."""
    name: str
    base_url: str
    timeout: float = 30.0


# ------------------------------------------------------------------------------
# Service Coordinator
# ------------------------------------------------------------------------------

class ServiceCoordinator:
    """
    Central coordinator for inter-service communication.

    This class manages HTTP clients for all integration services,
    handles health checks, and provides unified request methods
    with retry logic and error handling.

    Example:
        >>> coordinator = ServiceCoordinator()
        >>> await coordinator.initialize()
        >>> health = await coordinator.check_all_health()
        >>> response = await coordinator.request_tinyclaw("GET", "/agents")
        >>> await coordinator.shutdown()
    """

    # Service endpoints
    TINYCLAW = "tinyclaw"
    MEMU = "memu"
    GONDOLIN = "gondolin"

    # Health check intervals
    HEALTH_CHECK_TIMEOUT = 5.0
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self) -> None:
        """Initialize the service coordinator."""
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._initialized = False

        # Service configurations
        self._services: dict[str, ServiceClient] = {
            self.TINYCLAW: ServiceClient(
                name=self.TINYCLAW,
                base_url=settings.TINYCLAW_API_URL,
                timeout=30.0
            ),
            self.MEMU: ServiceClient(
                name=self.MEMU,
                base_url=settings.MEMU_API_URL if hasattr(settings, 'MEMU_API_URL') else "http://localhost:8000",
                timeout=30.0
            ),
            self.GONDOLIN: ServiceClient(
                name=self.GONDOLIN,
                base_url=settings.GONDOLIN_API_URL,
                timeout=60.0  # Longer timeout for VM operations
            ),
        }

    async def initialize(self) -> None:
        """
        Initialize HTTP clients for all services.

        This should be called once at application startup.
        """
        if self._initialized:
            logger.warning("ServiceCoordinator already initialized")
            return

        logger.info("Initializing ServiceCoordinator", extra={
            "services": list(self._services.keys())
        })

        for service_name, service_config in self._services.items():
            try:
                client = httpx.AsyncClient(
                    base_url=service_config.base_url,
                    timeout=service_config.timeout,
                )
                self._clients[service_name] = client
                logger.info("Created HTTP client", extra={
                    "service": service_name,
                    "base_url": service_config.base_url
                })
            except Exception as e:
                logger.error("Failed to create HTTP client", extra={
                    "service": service_name,
                    "error": str(e)
                })
                raise IntegrationError(
                    f"Failed to initialize {service_name} client",
                    details={"service": service_name, "error": str(e)}
                )

        self._initialized = True
        logger.info("ServiceCoordinator initialized successfully")

    async def shutdown(self) -> None:
        """
        Close all HTTP clients.

        This should be called during application shutdown.
        """
        if not self._initialized:
            return

        logger.info("Shutting down ServiceCoordinator")

        # Close all clients concurrently
        close_tasks = []
        for service_name, client in self._clients.items():
            close_tasks.append(self._close_client(service_name, client))

        await asyncio.gather(*close_tasks, return_exceptions=True)

        self._clients.clear()
        self._initialized = False
        logger.info("ServiceCoordinator shut down successfully")

    async def _close_client(self, service_name: str, client: httpx.AsyncClient) -> None:
        """Close a single HTTP client."""
        try:
            await client.aclose()
            logger.info("Closed HTTP client", extra={"service": service_name})
        except Exception as e:
            logger.error("Error closing HTTP client", extra={
                "service": service_name,
                "error": str(e)
            })

    # --------------------------------------------------------------------------
    # Health Check Methods
    # --------------------------------------------------------------------------

    async def check_health(self, service: str) -> ServiceHealth:
        """
        Check the health of a specific service.

        Args:
            service: Service name (tinyclaw, memu, gondolin)

        Returns:
            ServiceHealth status object

        Raises:
            ValidationError: If service name is invalid
        """
        if service not in self._services:
            raise ValidationError(
                f"Unknown service: {service}",
                details={"service": service, "valid_services": list(self._services.keys())}
            )

        client = self._clients.get(service)
        if not client:
            return ServiceHealth(
                service=service,
                healthy=False,
                error="Client not initialized"
            )

        try:
            import time
            start_time = time.time()

            response = await client.get(
                "/health",
                timeout=self.HEALTH_CHECK_TIMEOUT
            )

            response_time_ms = (time.time() - start_time) * 1000

            is_healthy = response.status_code == 200

            return ServiceHealth(
                service=service,
                healthy=is_healthy,
                response_time_ms=response_time_ms,
                error=None if is_healthy else f"HTTP {response.status_code}"
            )

        except asyncio.TimeoutError:
            return ServiceHealth(
                service=service,
                healthy=False,
                error="Health check timed out"
            )
        except httpx.ConnectError as e:
            return ServiceHealth(
                service=service,
                healthy=False,
                error=f"Connection error: {str(e)}"
            )
        except Exception as e:
            logger.error("Health check failed", extra={
                "service": service,
                "error": str(e)
            })
            return ServiceHealth(
                service=service,
                healthy=False,
                error=str(e)
            )

    async def check_all_health(self) -> dict[str, ServiceHealth]:
        """
        Check the health of all services concurrently.

        Returns:
            Dictionary mapping service names to their health status
        """
        logger.debug("Checking health of all services")

        health_tasks = {
            service: self.check_health(service)
            for service in self._services.keys()
        }

        results = await asyncio.gather(*health_tasks.values(), return_exceptions=True)

        return dict(zip(self._services.keys(), results))

    # --------------------------------------------------------------------------
    # Generic Request Methods
    # --------------------------------------------------------------------------

    async def _make_request(
        self,
        service: str,
        method: str,
        path: str,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make an HTTP request to a service with retry logic.

        Args:
            service: Service name (tinyclaw, memu, gondolin)
            method: HTTP method (GET, POST, PUT, DELETE)
            path: Request path (e.g., "/agents")
            **kwargs: Additional arguments passed to httpx

        Returns:
            JSON response as dictionary

        Raises:
            ValidationError: If service name is invalid
            IntegrationError: If request fails after retries
        """
        if not self._initialized:
            raise IntegrationError(
                "ServiceCoordinator not initialized",
                details={"hint": "Call await initialize() first"}
            )

        if service not in self._clients:
            raise ValidationError(
                f"Unknown service: {service}",
                details={"service": service}
            )

        client = self._clients[service]
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug("Making service request", extra={
                    "service": service,
                    "method": method,
                    "path": path,
                    "attempt": attempt + 1
                })

                response = await client.request(method, path, **kwargs)

                response.raise_for_status()

                # Return JSON response
                if response.status_code == 204:
                    return {}
                try:
                    return response.json()
                except JSONDecodeError as e:
                    logger.error("Invalid JSON response from service", extra={
                        "service": service,
                        "status_code": response.status_code,
                        "attempt": attempt + 1
                    })
                    raise IntegrationError(
                        f"Service returned invalid JSON: {service}",
                        details={
                            "service": service,
                            "status_code": response.status_code,
                            "response_text": response.text[:200]  # Truncate for safety
                        }
                    )

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning("HTTP error from service", extra={
                    "service": service,
                    "status_code": e.response.status_code,
                    "attempt": attempt + 1
                })

                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    raise IntegrationError(
                        f"Service returned error: {e.response.status_code}",
                        details={
                            "service": service,
                            "status_code": e.response.status_code,
                            "response": e.response.text
                        }
                    )

                # Retry server errors (5xx)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (2 ** attempt))

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                logger.warning("Service connection error", extra={
                    "service": service,
                    "error": str(e),
                    "attempt": attempt + 1
                })

                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (2 ** attempt))

        # All retries failed
        raise IntegrationError(
            f"Failed to reach {service} after {self.MAX_RETRIES} attempts",
            details={"service": service, "error": str(last_error)}
        )

    # --------------------------------------------------------------------------
    # TinyClaw Service Methods
    # --------------------------------------------------------------------------

    async def request_tinyclaw(
        self,
        method: str,
        path: str,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make a request to the TinyClaw service.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional arguments

        Returns:
            JSON response
        """
        return await self._make_request(self.TINYCLAW, method, path, **kwargs)

    # --------------------------------------------------------------------------
    # MemU Service Methods
    # --------------------------------------------------------------------------

    async def request_memu(
        self,
        method: str,
        path: str,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make a request to the MemU service.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional arguments

        Returns:
            JSON response
        """
        return await self._make_request(self.MEMU, method, path, **kwargs)

    # --------------------------------------------------------------------------
    # Gondolin Service Methods
    # --------------------------------------------------------------------------

    async def request_gondolin(
        self,
        method: str,
        path: str,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make a request to the Gondolin service.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional arguments

        Returns:
            JSON response
        """
        return await self._make_request(self.GONDOLIN, method, path, **kwargs)

    # --------------------------------------------------------------------------
    # Utility Methods
    # --------------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        """Check if the coordinator has been initialized."""
        return self._initialized

    def get_service_url(self, service: str) -> str:
        """
        Get the base URL for a service.

        Args:
            service: Service name

        Returns:
            Base URL of the service

        Raises:
            ValidationError: If service name is invalid
        """
        if service not in self._services:
            raise ValidationError(
                f"Unknown service: {service}",
                details={"service": service}
            )

        return self._services[service].base_url


# Export the coordinator class
__all__ = ["ServiceCoordinator", "ServiceHealth", "ServiceClient"]
