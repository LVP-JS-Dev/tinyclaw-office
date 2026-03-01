"""
Memory operations API routes.

This module provides FastAPI routes for managing AI agent memories using MemU,
including storing, retrieving, and listing memories with semantic search capabilities.
"""

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field

from src.shared.auth import verify_api_key
from src.shared.errors import (
    ValidationError,
    IntegrationError,
    NotFoundError,
    http_status_from_error,
)
from src.shared.logging import get_logger
from src.memu_integration.models import (
    Memory,
    MemoryModality,
    RetrievalMethod,
    MemoryResult,
    MemoryListResponse,
    StoreMemoryRequest,
    RetrieveMemoryRequest,
)

logger = get_logger(__name__)

# The router will be initialized with coordinator dependency
router = APIRouter(
    prefix="/api/memories",
    tags=["memories"],
)


# ------------------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------------------

async def get_coordinator(request: Request):
    """
    Dependency to get the service coordinator from the app state.

    The coordinator is initialized during application startup and stored
    in the FastAPI app.state for dependency injection.

    Args:
        request: FastAPI request object

    Returns:
        ServiceCoordinator instance from app.state
    """
    return request.app.state.coordinator


# ------------------------------------------------------------------------------
# Request/Response Models
# ------------------------------------------------------------------------------

class StoreMemoryRequestAPI(BaseModel):
    """Request model for storing a new memory via API."""

    resource_url: str = Field(
        ...,
        description="URI identifying the memory source (e.g., agent://id/session/...)"
    )
    modality: MemoryModality = Field(..., description="Type of memory content")
    user: str = Field(..., description="User ID associated with this memory")
    agent: str | None = Field(default=None, description="Agent ID")
    content: dict[str, Any] | str = Field(..., description="Memory content")
    summary: str | None = Field(default=None, description="Brief summary")
    categories: list[str] = Field(
        default_factory=list,
        description="Predefined category IDs"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    auto_categorize: bool = Field(
        default=True,
        description="Whether to auto-categorize this memory"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


class RetrieveMemoryRequestAPI(BaseModel):
    """Request model for retrieving memories via API."""

    queries: list[str] = Field(
        ...,
        description="Natural language queries for semantic search",
        min_length=1
    )
    where: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter conditions (user, agent, categories, modality, etc.)"
    )
    method: RetrievalMethod = Field(
        default=RetrievalMethod.RAG,
        description="Retrieval method (rag, llm, or hybrid)"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0.0 to 1.0)"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


class MemoryResponse(BaseModel):
    """Response model for memory operations."""

    memory_id: str = Field(..., description="Unique identifier for the memory")
    resource_url: str = Field(..., description="URI identifying the memory source")
    modality: MemoryModality = Field(..., description="Type of memory content")
    user: str = Field(..., description="User ID")
    agent: str | None = Field(default=None, description="Agent ID")
    content: dict[str, Any] | str = Field(..., description="Memory content")
    summary: str | None = Field(default=None, description="Brief summary")
    categories: list[str] = Field(
        default_factory=list,
        description="List of category IDs"
    )
    memory_status: str = Field(default="active", description="Memory status")
    created_at: str = Field(..., description="Memory creation timestamp")
    updated_at: str = Field(..., description="Memory last update timestamp")

    model_config = {"populate_by_name": True, "use_enum_values": True}


class MemoryRetrieveResponse(BaseModel):
    """Response model for memory retrieval operations."""

    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of retrieved memories with scores"
    )
    total: int = Field(default=0, description="Total number of results")
    method: RetrievalMethod = Field(..., description="Retrieval method used")
    query_time_ms: float | None = Field(
        default=None,
        description="Query execution time in milliseconds"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ------------------------------------------------------------------------------
# Route Handlers
# ------------------------------------------------------------------------------

@router.post(
    "/store",
    response_model=MemoryResponse,
    summary="Store a memory",
    description="Store a new memory in MemU for an agent or user",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Memory stored successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized - invalid API key"},
        503: {"description": "MemU service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def store_memory(
    request: StoreMemoryRequestAPI,
    coordinator = Depends(get_coordinator)
) -> MemoryResponse:
    """
    Store a new memory in the MemU system.

    Args:
        request: Memory storage request
        coordinator: Service coordinator dependency

    Returns:
        MemoryResponse with stored memory details

    Raises:
        HTTPException: If validation fails or service is unavailable
    """
    try:
        # Validate request
        if not request.resource_url or not request.resource_url.strip():
            raise ValidationError("resource_url is required")

        if not request.user or not request.user.strip():
            raise ValidationError("user is required")

        if not request.content:
            raise ValidationError("content is required")

        logger.info("Storing memory", extra={
            "resource_url_present": bool(request.resource_url),
            "user": request.user,
            "agent": request.agent,
            "modality": request.modality.value if hasattr(request.modality, "value") else request.modality
        })

        # Convert to MemU model format
        store_request = StoreMemoryRequest(
            resource_url=request.resource_url,
            modality=request.modality,
            user=request.user,
            agent=request.agent,
            content=request.content,
            summary=request.summary,
            categories=request.categories,
            metadata=request.metadata,
            auto_categorize=request.auto_categorize
        )

        # Make request to MemU service
        response = await coordinator.request_memu(
            "POST",
            "/api/memories",
            json=store_request.model_dump(exclude_none=True, by_alias=True)
        )

        logger.info("Memory stored successfully", extra={
            "memory_id": response.get("memory_id"),
            "user": request.user
        })

        return MemoryResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error storing memory", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        logger.error("Integration error storing memory", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error storing memory")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.post(
    "/retrieve",
    response_model=MemoryRetrieveResponse,
    summary="Retrieve memories",
    description="Retrieve memories using semantic search with RAG or LLM methods",
    responses={
        200: {"description": "Memories retrieved successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized - invalid API key"},
        503: {"description": "MemU service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def retrieve_memories(
    request: RetrieveMemoryRequestAPI,
    coordinator = Depends(get_coordinator)
) -> MemoryRetrieveResponse:
    """
    Retrieve memories from the MemU system using semantic search.

    Args:
        request: Memory retrieval request
        coordinator: Service coordinator dependency

    Returns:
        MemoryRetrieveResponse with retrieved memories

    Raises:
        HTTPException: If validation fails or service is unavailable
    """
    try:
        # Validate request
        if not request.queries or len(request.queries) == 0:
            raise ValidationError("At least one query is required")

        for query in request.queries:
            if not query or not query.strip():
                raise ValidationError("Queries cannot be empty")

        if request.limit < 1 or request.limit > 100:
            raise ValidationError(
                "Limit must be between 1 and 100",
                details={"limit": request.limit}
            )

        logger.info("Retrieving memories", extra={
            "queries_present": True,
            "query_count": len(request.queries),
            "method": request.method.value if hasattr(request.method, "value") else request.method,
            "limit": request.limit
        })

        # Convert to MemU model format
        retrieve_request = RetrieveMemoryRequest(
            queries=request.queries,
            where=request.where,
            method=request.method,
            limit=request.limit,
            threshold=request.threshold
        )

        # Make request to MemU service
        response = await coordinator.request_memu(
            "POST",
            "/api/memories/retrieve",
            json=retrieve_request.model_dump(exclude_none=True, by_alias=True)
        )

        logger.info("Memories retrieved successfully", extra={
            "total": response.get("total", 0),
            "method": request.method.value if hasattr(request.method, "value") else request.method
        })

        return MemoryRetrieveResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error retrieving memories", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        logger.error("Integration error retrieving memories", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error retrieving memories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.get(
    "/{agent_id}",
    response_model=MemoryListResponse,
    summary="List agent memories",
    description="Retrieve all memories associated with a specific agent",
    responses={
        200: {"description": "Memories listed successfully"},
        400: {"description": "Invalid agent ID"},
        401: {"description": "Unauthorized - invalid API key"},
        404: {"description": "Agent not found"},
        503: {"description": "MemU service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def list_agent_memories(
    agent_id: str,
    limit: int = 100,
    offset: int = 0,
    coordinator = Depends(get_coordinator)
) -> MemoryListResponse:
    """
    List all memories for a specific agent.

    Args:
        agent_id: ID of the agent to retrieve memories for
        limit: Maximum number of memories to return
        offset: Number of memories to skip
        coordinator: Service coordinator dependency

    Returns:
        MemoryListResponse containing list of memories

    Raises:
        HTTPException: If validation fails, agent not found, or service is unavailable
    """
    try:
        # Validate agent_id
        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required")

        if limit < 1 or limit > 1000:
            raise ValidationError(
                "Limit must be between 1 and 1000",
                details={"limit": limit}
            )

        if offset < 0:
            raise ValidationError(
                "Offset must be non-negative",
                details={"offset": offset}
            )

        logger.info("Listing agent memories", extra={
            "agent_id": agent_id,
            "limit": limit,
            "offset": offset
        })

        # Build query parameters
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "where": {"agent": agent_id}
        }

        # Make request to MemU service
        response = await coordinator.request_memu(
            "GET",
            "/api/memories",
            params=params
        )

        logger.info("Agent memories listed successfully", extra={
            "agent_id": agent_id,
            "count": len(response.get("memories", [])),
            "total": response.get("total", 0)
        })

        return MemoryListResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error listing agent memories", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        # Check if it's a 404 error
        if e.details.get("status_code") == 404:
            logger.info("Agent not found", extra={"agent_id": agent_id})
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=NotFoundError(f"Agent {agent_id} not found").to_dict()
            )

        logger.error("Integration error listing agent memories", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error listing agent memories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


# Export the router
__all__ = ["router"]
