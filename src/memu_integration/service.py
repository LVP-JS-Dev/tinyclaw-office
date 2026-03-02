"""
MemU integration service with FastAPI endpoints.

This module provides the main FastAPI application for the MemU integration,
exposing endpoints for memory storage, retrieval, categorization, and statistics.
"""

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from src.shared.config import settings
from src.shared.errors import (
    BaseError,
    ValidationError,
    IntegrationError,
    MemUError,
    http_status_from_error,
)
from src.shared.logging import get_logger, configure_logging
from src.shared.auth import verify_api_key_optional
from src.memu_integration.client import MemUClient
from src.memu_integration.models import (
    Memory,
    MemoryCategory,
    MemoryResult,
    MemoryListResponse,
    StoreMemoryRequest,
    RetrieveMemoryRequest,
    CategorizeMemoryRequest,
    CreateCategoryRequest,
    MemoryStats,
    MemoryModality,
    RetrievalMethod,
    MemoryStatus,
)

# Configure module logger
logger = get_logger(__name__)

# Global client instance
_memu_client: MemUClient | None = None


def get_memu_client() -> MemUClient:
    """
    Get the global MemU client instance.

    Returns:
        MemUClient instance

    Raises:
        MemUError: If client is not initialized
    """
    global _memu_client
    if _memu_client is None:
        raise MemUError(
            "MemU client not initialized",
            details={"service": "memu_integration"},
        )
    return _memu_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    This function handles startup and shutdown events for the FastAPI application,
    ensuring proper initialization and cleanup of the MemU client.

    Yields:
        None
    """
    global _memu_client

    # Startup
    logger.info("Starting MemU integration service")
    configure_logging(settings.LOG_LEVEL)

    try:
        # Initialize MemU client
        _memu_client = MemUClient()
        await _memu_client.initialize()

        # Perform health check
        is_healthy = await _memu_client.health_check()
        if is_healthy:
            logger.info("MemU service connection healthy")
        else:
            logger.warning("MemU service health check failed, but continuing")

        logger.info("MemU integration service started successfully")

    except Exception as e:
        logger.exception("Failed to start MemU integration service")
        # Don't raise - allow service to start in degraded mode
        _memu_client = None

    yield

    # Shutdown
    logger.info("Shutting down MemU integration service")
    if _memu_client:
        try:
            await _memu_client.shutdown()
            logger.info("MemU client shutdown complete")
        except Exception as e:
            logger.warning("Error during shutdown", extra={"error": str(e)})


# Create FastAPI application
app = FastAPI(
    title="MemU Integration API",
    description="Persistent memory integration service for MemU",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
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

@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns the health status of the MemU integration service.

    Returns:
        JSON response with health status
    """
    try:
        client = get_memu_client()
        is_healthy = await client.health_check()

        return {
            "status": "healthy" if is_healthy else "degraded",
            "service": "memu_integration",
            "version": "1.0.0",
            "storage_mode": settings.MEMU_MODE,
        }
    except Exception as e:
        logger.warning("Health check failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "service": "memu_integration",
            "error": str(e),
        }


# ------------------------------------------------------------------------------
# Memory Storage Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/memories", response_model=Memory, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key_optional)])
async def store_memory(request: StoreMemoryRequest):
    """
    Store a new memory in MemU.

    Args:
        request: Memory storage request

    Returns:
        Created Memory object

    Raises:
        HTTPException: If storage fails
    """
    try:
        client = get_memu_client()
        return await client.store_memory(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error storing memory")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to store memory"},
        )


# ------------------------------------------------------------------------------
# Memory Retrieval Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/memories/retrieve", response_model=list[MemoryResult])
async def retrieve_memory(request: RetrieveMemoryRequest):
    """
    Retrieve memories based on semantic search queries.

    Args:
        request: Memory retrieval request

    Returns:
        List of MemoryResult objects with relevance scores

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        client = get_memu_client()
        return await client.retrieve_memory(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error retrieving memories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to retrieve memories"},
        )


@app.get("/api/memories", response_model=MemoryListResponse, dependencies=[Depends(verify_api_key_optional)])
async def list_memories(
    user: str | None = None,
    agent: str | None = None,
    modality: MemoryModality | None = None,
    memory_status: MemoryStatus = MemoryStatus.ACTIVE,
    limit: int = 100,
    offset: int = 0,
):
    """
    List memories with optional filtering.

    Args:
        user: Filter by user ID
        agent: Filter by agent ID
        modality: Filter by content modality
        status: Filter by status (default: ACTIVE)
        limit: Maximum number of memories to return
        offset: Number of memories to skip

    Returns:
        MemoryListResponse containing list of memories and total count

    Raises:
        HTTPException: If listing fails
    """
    try:
        client = get_memu_client()
        return await client.list_memories(
            user=user,
            agent=agent,
            modality=modality,
            status=memory_status,
            limit=limit,
            offset=offset,
        )
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing memories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list memories"},
        )


@app.get("/api/memories/{memory_id}", response_model=Memory, dependencies=[Depends(verify_api_key_optional)])
async def get_memory(memory_id: str):
    """
    Get details of a specific memory.

    Args:
        memory_id: Unique identifier of the memory

    Returns:
        Memory object with full details

    Raises:
        HTTPException: If memory not found or retrieval fails
    """
    try:
        client = get_memu_client()
        return await client.get_memory(memory_id)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error getting memory")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to get memory"},
        )


@app.delete("/api/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_api_key_optional)])
async def delete_memory(memory_id: str):
    """
    Delete a memory.

    Args:
        memory_id: Unique identifier of the memory to delete

    Raises:
        HTTPException: If deletion fails
    """
    try:
        client = get_memu_client()
        await client.delete_memory(memory_id)
        return None
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error deleting memory")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to delete memory"},
        )


# ------------------------------------------------------------------------------
# Categorization Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/memories/{memory_id}/categorize", response_model=Memory, dependencies=[Depends(verify_api_key_optional)])
async def categorize_memory(memory_id: str, request: CategorizeMemoryRequest):
    """
    Categorize or re-categorize a memory.

    Args:
        memory_id: Unique identifier of the memory
        request: Categorization request

    Returns:
        Updated Memory with new categories

    Raises:
        HTTPException: If categorization fails
    """
    try:
        client = get_memu_client()
        # Override memory_id in request with path parameter
        request.memory_id = memory_id
        return await client.categorize_memory(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error categorizing memory")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to categorize memory"},
        )


# ------------------------------------------------------------------------------
# Category Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/categories", response_model=list[MemoryCategory])
async def list_categories(
    parent_id: str | None = None,
    limit: int = 100,
):
    """
    List memory categories with optional filtering.

    Args:
        parent_id: Filter by parent category ID
        limit: Maximum number of categories to return

    Returns:
        List of MemoryCategory objects

    Raises:
        HTTPException: If listing fails
    """
    try:
        client = get_memu_client()
        return await client.list_categories(
            parent_id=parent_id,
            limit=limit,
        )
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing categories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list categories"},
        )


@app.post("/api/categories", response_model=MemoryCategory, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key_optional)])
async def create_category(request: CreateCategoryRequest):
    """
    Create a new memory category.

    Args:
        request: Category creation request

    Returns:
        Created MemoryCategory object

    Raises:
        HTTPException: If category creation fails
    """
    try:
        client = get_memu_client()
        return await client.create_category(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error creating category")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to create category"},
        )


# ------------------------------------------------------------------------------
# Statistics Endpoint
# ------------------------------------------------------------------------------

@app.get("/api/stats", response_model=MemoryStats, dependencies=[Depends(verify_api_key_optional)])
async def get_stats():
    """
    Get statistics about memory usage.

    Returns:
        MemoryStats object with storage and retrieval metrics

    Raises:
        HTTPException: If stats retrieval fails
    """
    try:
        client = get_memu_client()
        return await client.get_stats()
    except MemUError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error getting statistics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to get statistics"},
        )


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for running the MemU integration service.

    This function starts the uvicorn server on the configured port.
    """
    port = 8000  # MemU API port (hardcoded as per spec)

    logger.info(
        "Starting MemU integration service",
        extra={"port": port},
    )

    uvicorn.run(
        "src.memu_integration.service:app",
        host="0.0.0.0",
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
