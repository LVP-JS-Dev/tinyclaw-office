"""
Main FastAPI orchestration application for TinyClaw Office.

This module provides the unified API that coordinates all three integration services:
- TinyClaw: Multi-agent messaging and collaboration
- MemU: Persistent hierarchical memory storage
- Gondolin: Sandboxed code execution

The orchestration layer acts as a single entry point for the dashboard and clients,
routing requests to the appropriate integration service.
"""

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.shared.config import settings
from src.shared.errors import (
    BaseError,
    ValidationError,
    IntegrationError,
    http_status_from_error,
)
from src.shared.logging import get_logger, configure_logging
from src.shared.auth import verify_api_key_optional
from src.orchestration.coordinator import ServiceCoordinator

# Import route routers
from src.orchestration.routes.agents import router as agents_router
from src.orchestration.routes.memory import router as memory_router
from src.orchestration.routes.execution import router as execution_router

# Configure module logger
logger = get_logger(__name__)

# Global coordinator instance
_coordinator: ServiceCoordinator | None = None


def get_coordinator() -> ServiceCoordinator:
    """
    Get the global service coordinator instance.

    Returns:
        ServiceCoordinator instance

    Raises:
        IntegrationError: If coordinator is not initialized
    """
    global _coordinator
    if _coordinator is None:
        raise IntegrationError(
            "Service coordinator not initialized",
            details={"hint": "Call await initialize() first"},
        )
    return _coordinator


# Note: The routers use get_coordinator as a dependency, which will be properly
# injected via FastAPI's dependency system when routes are called.
# The routers import get_coordinator from their local module, but we override it
# by adding it to app.dependency_overrides after the routers are included.


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    This function handles startup and shutdown events for the FastAPI application,
    ensuring proper initialization and cleanup of the service coordinator.

    Yields:
        None
    """
    global _coordinator

    # Startup
    logger.info("Starting orchestration service")
    configure_logging(settings.LOG_LEVEL)

    try:
        # Initialize service coordinator
        _coordinator = ServiceCoordinator()
        await _coordinator.initialize()

        # Check health of all services
        health_status = await _coordinator.check_all_health()

        for service_name, health in health_status.items():
            if health.healthy:
                logger.info(
                    "Service healthy",
                    extra={
                        "service": service_name,
                        "response_time_ms": health.response_time_ms,
                    },
                )
            else:
                logger.warning(
                    "Service health check failed",
                    extra={
                        "service": service_name,
                        "error": health.error,
                    },
                )

        # Determine overall health
        all_healthy = all(h.healthy for h in health_status.values())
        if all_healthy:
            logger.info("Orchestration service started successfully - all services healthy")
        else:
            logger.warning(
                "Orchestration service started in degraded mode - some services unavailable"
            )

    except Exception as e:
        logger.exception("Failed to start orchestration service")
        # Don't raise - allow service to start in degraded mode
        _coordinator = None

    yield

    # Shutdown
    logger.info("Shutting down orchestration service")
    if _coordinator:
        try:
            await _coordinator.shutdown()
            logger.info("Service coordinator shutdown complete")
        except Exception as e:
            logger.warning("Error during shutdown", extra={"error": str(e)})


# Create FastAPI application
app = FastAPI(
    title="TinyClaw Office Orchestration API",
    description=(
        "Unified API coordinating TinyClaw (multi-agent messaging), "
        "MemU (persistent memory), and Gondolin (sandboxed execution)"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ------------------------------------------------------------------------------
# CORS Middleware
# ------------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Exception Handlers
# ------------------------------------------------------------------------------

@app.exception_handler(BaseError)
async def base_error_handler(request: Any, exc: BaseError) -> JSONResponse:
    """
    Handle custom application errors.

    Args:
        request: The incoming request
        exc: The raised exception

    Returns:
        JSON response with error details
    """
    status_code = http_status_from_error(exc)
    content = exc.to_dict()
    logger.warning(
        "Application error",
        extra={
            "error_type": exc.__class__.__name__,
            "message": exc.message,
            "status_code": status_code,
        },
    )
    return JSONResponse(status_code=status_code, content=content)


@app.exception_handler(Exception)
async def general_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Args:
        request: The incoming request
        exc: The raised exception

    Returns:
        JSON response with generic error message
    """
    logger.exception("Unexpected error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error_type": "InternalError", "message": "Internal server error"},
    )


# ------------------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check endpoint",
    description="Returns the health status of the orchestration service and all dependencies",
    dependencies=[Depends(verify_api_key_optional)],
)
async def health_check():
    """
    Health check endpoint.

    Returns the health status of the orchestration service and all
    integrated services (TinyClaw, MemU, Gondolin).

    Returns:
        JSON response with overall status and individual service health
    """
    try:
        coordinator = get_coordinator()
        health_status = await coordinator.check_all_health()

        # Determine overall health
        all_healthy = all(h.healthy for h in health_status.values())
        any_healthy = any(h.healthy for h in health_status.values())

        if all_healthy:
            overall_status = "healthy"
        elif any_healthy:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        # Build response
        response = {
            "status": overall_status,
            "service": "orchestration",
            "version": "1.0.0",
            "services": {
                name: {
                    "healthy": health.healthy,
                    "response_time_ms": health.response_time_ms,
                    "error": health.error,
                }
                for name, health in health_status.items()
            },
        }

        return response

    except IntegrationError as e:
        logger.warning("Health check failed - coordinator not initialized", extra={"error": e.message})
        return {
            "status": "unhealthy",
            "service": "orchestration",
            "version": "1.0.0",
            "error": "Service coordinator not initialized",
        }
    except Exception as e:
        logger.warning("Health check failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "service": "orchestration",
            "version": "1.0.0",
            "error": str(e),
        }


# ------------------------------------------------------------------------------
# Root Endpoint
# ------------------------------------------------------------------------------

@app.get(
    "/",
    summary="API root",
    description="Returns information about the orchestration API",
)
async def root():
    """
    Root endpoint.

    Returns basic information about the orchestration API.

    Returns:
        JSON response with API information
    """
    return {
        "name": "TinyClaw Office Orchestration API",
        "version": "1.0.0",
        "description": "Unified API for multi-agent collaboration, persistent memory, and sandboxed execution",
        "services": {
            "tinyclaw": "Multi-agent messaging and collaboration",
            "memu": "Persistent hierarchical memory storage",
            "gondolin": "Sandboxed code execution",
        },
        "docs_url": "/docs",
        "health_url": "/health",
    }


# ------------------------------------------------------------------------------
# Include Route Routers
# ------------------------------------------------------------------------------

# Import the dependency functions from routers to override them
from src.orchestration.routes.agents import get_coordinator as get_agents_coordinator
from src.orchestration.routes.memory import get_coordinator as get_memory_coordinator
from src.orchestration.routes.execution import get_coordinator as get_execution_coordinator

# Include agent management routes
app.include_router(agents_router)

# Include memory management routes
app.include_router(memory_router)

# Include code execution routes
app.include_router(execution_router)

# Override the get_coordinator dependency in all routers to use the real coordinator
app.dependency_overrides[get_agents_coordinator] = get_coordinator
app.dependency_overrides[get_memory_coordinator] = get_coordinator
app.dependency_overrides[get_execution_coordinator] = get_coordinator


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for running the orchestration service.

    This function starts the uvicorn server on the configured port.
    """
    port = settings.API_PORT

    logger.info(
        "Starting orchestration service",
        extra={"port": port},
    )

    uvicorn.run(
        "src.orchestration.api:app",
        host="0.0.0.0",
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
