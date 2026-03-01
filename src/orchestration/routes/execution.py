"""
Code execution API routes.

This module provides FastAPI routes for executing code in Gondolin sandboxes,
including submitting execution tasks, querying task status, and retrieving results.
"""

from typing import Any
from uuid import uuid4
from enum import Enum

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.shared.auth import verify_api_key
from src.shared.errors import (
    ValidationError,
    IntegrationError,
    NotFoundError,
    http_status_from_error,
)
from src.shared.logging import get_logger

logger = get_logger(__name__)

# The router will be initialized with coordinator dependency
router = APIRouter(
    prefix="/api/execute",
    tags=["execution"],
)


# ------------------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------------------

async def get_coordinator():
    """
    Dependency to get the service coordinator.

    In a real implementation, this would be injected from the main app state.
    For now, this is a placeholder that will be replaced by the actual dependency.
    """
    from src.orchestration.coordinator import ServiceCoordinator

    # This will be replaced by FastAPI's dependency injection system
    # when the router is mounted in the main API
    return None


# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------

class ExecutionStatus(str, Enum):
    """Status of a code execution task."""

    PENDING = "pending"
    """Task is queued and waiting to start"""

    RUNNING = "running"
    """Task is currently executing"""

    COMPLETED = "completed"
    """Task completed successfully"""

    FAILED = "failed"
    """Task failed with an error"""

    TIMEOUT = "timeout"
    """Task exceeded time limit"""

    CANCELLED = "cancelled"
    """Task was cancelled by user"""


# ------------------------------------------------------------------------------
# Request/Response Models
# ------------------------------------------------------------------------------

class ExecuteCodeRequest(BaseModel):
    """Request model for executing code in a sandbox."""

    code: str = Field(
        ...,
        description="Code to execute",
        min_length=1
    )
    language: str = Field(
        default="python",
        description="Programming language (python, javascript, bash, etc.)"
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Execution timeout in seconds"
    )
    allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Allowed hosts for network access (whitelist)"
    )
    environment_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to inject into sandbox"
    )
    agent_id: str | None = Field(
        default=None,
        description="Optional agent ID requesting the execution"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional execution metadata"
    )

    model_config = {"populate_by_name": True}


class ExecutionResponse(BaseModel):
    """Response model for execution task creation."""

    task_id: str = Field(..., description="Unique execution task ID")
    status: ExecutionStatus = Field(..., description="Task status")
    code: str = Field(..., description="Code that was submitted")
    language: str = Field(..., description="Programming language")
    timeout: int = Field(..., description="Execution timeout in seconds")
    created_at: str = Field(..., description="Task creation timestamp")
    agent_id: str | None = Field(default=None, description="Agent ID")

    model_config = {"populate_by_name": True, "use_enum_values": True}


class ExecutionStatusResponse(BaseModel):
    """Response model for execution task status queries."""

    task_id: str = Field(..., description="Unique execution task ID")
    status: ExecutionStatus = Field(..., description="Current task status")
    language: str = Field(..., description="Programming language")
    stdout: str | None = Field(default=None, description="Standard output")
    stderr: str | None = Field(default=None, description="Standard error")
    exit_code: int | None = Field(default=None, description="Process exit code")
    error: str | None = Field(default=None, description="Error message if failed")
    execution_time_ms: float | None = Field(
        default=None,
        description="Execution time in milliseconds"
    )
    created_at: str = Field(..., description="Task creation timestamp")
    started_at: str | None = Field(default=None, description="Task start timestamp")
    completed_at: str | None = Field(default=None, description="Task completion timestamp")

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ------------------------------------------------------------------------------
# Route Handlers
# ------------------------------------------------------------------------------

@router.post(
    "",
    response_model=ExecutionResponse,
    summary="Execute code in sandbox",
    description="Submit code for execution in an isolated Gondolin sandbox",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Execution task created successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized - invalid API key"},
        503: {"description": "Gondolin service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def execute_code(
    request: ExecuteCodeRequest,
    coordinator = Depends(get_coordinator)
) -> ExecutionResponse:
    """
    Submit code for execution in a Gondolin sandbox.

    Args:
        request: Code execution request
        coordinator: Service coordinator dependency

    Returns:
        ExecutionResponse with task ID and initial status

    Raises:
        HTTPException: If validation fails or service is unavailable
    """
    try:
        # Validate request
        if not request.code or not request.code.strip():
            raise ValidationError("Code is required")

        if request.timeout < 1 or request.timeout > 300:
            raise ValidationError(
                "Timeout must be between 1 and 300 seconds",
                details={"timeout": request.timeout}
            )

        logger.info("Creating execution task", extra={
            "language": request.language,
            "timeout": request.timeout,
            "agent_id": request.agent_id
        })

        # Generate task ID
        task_id = str(uuid4())

        # Prepare execution request for Gondolin service
        gondolin_request = {
            "task_id": task_id,
            "code": request.code,
            "language": request.language,
            "timeout": request.timeout,
            "allowed_hosts": request.allowed_hosts,
            "environment_vars": request.environment_vars,
            "agent_id": request.agent_id,
            "metadata": request.metadata
        }

        # Make request to Gondolin service
        response = await coordinator.request_gondolin(
            "POST",
            "/api/execute",
            json=gondolin_request
        )

        logger.info("Execution task created successfully", extra={
            "task_id": task_id,
            "status": response.get("status", "pending")
        })

        return ExecutionResponse(
            task_id=task_id,
            status=ExecutionStatus.PENDING,
            code=request.code,
            language=request.language,
            timeout=request.timeout,
            created_at=response.get("created_at", ""),
            agent_id=request.agent_id
        )

    except ValidationError as e:
        logger.warning("Validation error creating execution task", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        logger.error("Integration error creating execution task", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error creating execution task")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.get(
    "/{task_id}",
    response_model=ExecutionStatusResponse,
    summary="Get execution status",
    description="Retrieve the status and results of an execution task",
    responses={
        200: {"description": "Execution status retrieved successfully"},
        401: {"description": "Unauthorized - invalid API key"},
        404: {"description": "Task not found"},
        503: {"description": "Gondolin service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def get_execution_status(
    task_id: str,
    coordinator = Depends(get_coordinator)
) -> ExecutionStatusResponse:
    """
    Get the status and results of an execution task.

    Args:
        task_id: ID of the execution task to query
        coordinator: Service coordinator dependency

    Returns:
        ExecutionStatusResponse with task status and results

    Raises:
        HTTPException: If task not found or service is unavailable
    """
    try:
        # Validate task_id
        if not task_id or not task_id.strip():
            raise ValidationError("task_id is required")

        logger.info("Getting execution status", extra={"task_id": task_id})

        # Make request to Gondolin service
        response = await coordinator.request_gondolin("GET", f"/api/execute/{task_id}")

        logger.info("Execution status retrieved successfully", extra={
            "task_id": task_id,
            "status": response.get("status")
        })

        return ExecutionStatusResponse(
            task_id=task_id,
            status=ExecutionStatus(response.get("status", "pending")),
            language=response.get("language", "unknown"),
            stdout=response.get("stdout"),
            stderr=response.get("stderr"),
            exit_code=response.get("exit_code"),
            error=response.get("error"),
            execution_time_ms=response.get("execution_time_ms"),
            created_at=response.get("created_at", ""),
            started_at=response.get("started_at"),
            completed_at=response.get("completed_at")
        )

    except ValidationError as e:
        logger.warning("Validation error getting execution status", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        # Check if it's a 404 error
        if e.details.get("status_code") == 404:
            logger.info("Execution task not found", extra={"task_id": task_id})
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=NotFoundError(f"Execution task {task_id} not found").to_dict()
            )

        logger.error("Integration error getting execution status", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error getting execution status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


# Export the router
__all__ = ["router"]
