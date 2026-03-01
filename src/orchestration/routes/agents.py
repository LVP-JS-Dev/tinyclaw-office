"""
Agent management API routes.

This module provides FastAPI routes for managing AI agents in the TinyClaw system,
including listing, creating, retrieving, updating, and deleting agents, as well as
sending messages to agents.
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
from src.tinyclaw_integration.models import (
    Agent,
    CreateAgentRequest,
    CreateMessageRequest,
    AgentListResponse,
    Message,
    AgentStatus,
)

logger = get_logger(__name__)

# The router will be initialized with coordinator dependency
router = APIRouter(
    prefix="/api/agents",
    tags=["agents"],
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

class CreateAgentRequestAPI(BaseModel):
    """Request model for creating a new agent via API."""

    name: str = Field(..., description="Agent name", min_length=1, max_length=100)
    description: str | None = Field(
        default=None,
        description="Agent description",
        max_length=500
    )
    channels: list[str] = Field(
        default_factory=list,
        description="Channel IDs to connect agent to"
    )
    capabilities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Agent capabilities and skills"
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific configuration"
    )
    team_id: str | None = Field(
        default=None,
        description="Team ID to assign agent to"
    )

    model_config = {"populate_by_name": True}


class SendMessageRequestAPI(BaseModel):
    """Request model for sending a message to an agent."""

    channel_id: str = Field(..., description="Channel ID to send message to")
    content: str = Field(..., description="Message content", min_length=1)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message metadata"
    )
    parent_message_id: str | None = Field(
        default=None,
        description="Parent message ID if this is a reply"
    )

    model_config = {"populate_by_name": True}


class UpdateAgentRequestAPI(BaseModel):
    """Request model for updating an existing agent."""

    name: str | None = Field(default=None, description="Agent name", min_length=1, max_length=100)
    description: str | None = Field(default=None, description="Agent description", max_length=500)
    status: AgentStatus | None = Field(default=None, description="Agent operational status")
    channels: list[str] | None = Field(default=None, description="Channel IDs to connect agent to")
    capabilities: list[dict[str, Any]] | None = Field(
        default=None,
        description="Agent capabilities and skills"
    )
    config: dict[str, Any] | None = Field(default=None, description="Agent-specific configuration")
    team_id: str | None = Field(default=None, description="Team ID to assign agent to")

    model_config = {"populate_by_name": True}


class MessageResponse(BaseModel):
    """Response model for message operations."""

    message_id: str = Field(..., description="Message ID")
    agent_id: str = Field(..., description="Agent ID")
    channel_id: str = Field(..., description="Channel ID")
    content: str = Field(..., description="Message content")
    status: str = Field(default="pending", description="Message delivery status")
    created_at: str = Field(..., description="Message creation timestamp")

    model_config = {"populate_by_name": True}


class AgentResponse(BaseModel):
    """Response model for agent operations."""

    agent_id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent name")
    description: str | None = Field(default=None, description="Agent description")
    status: AgentStatus = Field(..., description="Agent operational status")
    channels: list[str] = Field(default_factory=list, description="Connected channel IDs")
    capabilities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Agent capabilities"
    )
    team_id: str | None = Field(default=None, description="Team ID")
    created_at: str = Field(..., description="Agent creation timestamp")
    updated_at: str = Field(..., description="Agent last update timestamp")

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ------------------------------------------------------------------------------
# Route Handlers
# ------------------------------------------------------------------------------

@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all agents",
    description="Retrieve a list of all agents in the system with optional filtering",
    responses={
        200: {"description": "Agents retrieved successfully"},
        401: {"description": "Unauthorized - invalid API key"},
        503: {"description": "TinyClaw service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def list_agents(
    status_filter: AgentStatus | None = None,
    team_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    coordinator = Depends(get_coordinator)
) -> AgentListResponse:
    """
    List all agents in the TinyClaw system.

    Args:
        status_filter: Optional filter by agent status
        team_id: Optional filter by team ID
        limit: Maximum number of agents to return
        offset: Number of agents to skip
        coordinator: Service coordinator dependency

    Returns:
        AgentListResponse containing list of agents

    Raises:
        HTTPException: If the service is unavailable
    """
    try:
        # Validate parameters
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

        logger.info("Listing agents", extra={
            "status_filter": status_filter,
            "team_id": team_id,
            "limit": limit,
            "offset": offset
        })

        # Build query parameters
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status_filter:
            params["status"] = status_filter.value
        if team_id:
            params["team_id"] = team_id

        # Make request to TinyClaw service
        response = await coordinator.request_tinyclaw("GET", "/api/agents", params=params)

        logger.info("Agents listed successfully", extra={
            "count": len(response.get("agents", [])),
            "total": response.get("total", 0)
        })

        return AgentListResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error listing agents", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        logger.error("Integration error listing agents", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error listing agents")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.post(
    "",
    response_model=AgentResponse,
    summary="Create a new agent",
    description="Create a new AI agent with specified configuration",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Agent created successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized - invalid API key"},
        503: {"description": "TinyClaw service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def create_agent(
    request: CreateAgentRequestAPI,
    coordinator = Depends(get_coordinator)
) -> AgentResponse:
    """
    Create a new agent in the TinyClaw system.

    Args:
        request: Agent creation request
        coordinator: Service coordinator dependency

    Returns:
        AgentResponse with created agent details

    Raises:
        HTTPException: If validation fails or service is unavailable
    """
    try:
        # Validate request
        if not request.name or not request.name.strip():
            raise ValidationError("Agent name is required")

        logger.info("Creating agent", extra={"name": request.name})

        # Convert to TinyClaw model format
        create_request = CreateAgentRequest(
            name=request.name,
            description=request.description,
            channels=request.channels,
            capabilities=request.capabilities,
            config=request.config,
            team_id=request.team_id
        )

        # Make request to TinyClaw service
        response = await coordinator.request_tinyclaw(
            "POST",
            "/api/agents",
            json=create_request.model_dump(exclude_none=True, by_alias=True)
        )

        logger.info("Agent created successfully", extra={
            "agent_id": response.get("agent_id"),
            "name": response.get("name")
        })

        return AgentResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error creating agent", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        logger.error("Integration error creating agent", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error creating agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent details",
    description="Retrieve detailed information about a specific agent",
    responses={
        200: {"description": "Agent retrieved successfully"},
        401: {"description": "Unauthorized - invalid API key"},
        404: {"description": "Agent not found"},
        503: {"description": "TinyClaw service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def get_agent(
    agent_id: str,
    coordinator = Depends(get_coordinator)
) -> AgentResponse:
    """
    Get details of a specific agent.

    Args:
        agent_id: ID of the agent to retrieve
        coordinator: Service coordinator dependency

    Returns:
        AgentResponse with agent details

    Raises:
        HTTPException: If agent not found or service is unavailable
    """
    try:
        # Validate agent_id
        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required")

        logger.info("Getting agent", extra={"agent_id": agent_id})

        # Make request to TinyClaw service
        response = await coordinator.request_tinyclaw("GET", f"/api/agents/{agent_id}")

        logger.info("Agent retrieved successfully", extra={"agent_id": agent_id})

        return AgentResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error getting agent", extra={"error": e.message})
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

        logger.error("Integration error getting agent", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error getting agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.delete(
    "/{agent_id}",
    summary="Delete an agent",
    description="Delete an agent from the system",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Agent deleted successfully"},
        401: {"description": "Unauthorized - invalid API key"},
        404: {"description": "Agent not found"},
        503: {"description": "TinyClaw service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def delete_agent(
    agent_id: str,
    coordinator = Depends(get_coordinator)
) -> None:
    """
    Delete an agent from the TinyClaw system.

    Args:
        agent_id: ID of the agent to delete
        coordinator: Service coordinator dependency

    Raises:
        HTTPException: If agent not found or service is unavailable
    """
    try:
        # Validate agent_id
        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required")

        logger.info("Deleting agent", extra={"agent_id": agent_id})

        # Make request to TinyClaw service
        await coordinator.request_tinyclaw("DELETE", f"/api/agents/{agent_id}")

        logger.info("Agent deleted successfully", extra={"agent_id": agent_id})

    except ValidationError as e:
        logger.warning("Validation error deleting agent", extra={"error": e.message})
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

        logger.error("Integration error deleting agent", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error deleting agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


@router.post(
    "/{agent_id}/message",
    response_model=MessageResponse,
    summary="Send message to agent",
    description="Send a message to an agent through a specified channel",
    responses={
        200: {"description": "Message sent successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized - invalid API key"},
        404: {"description": "Agent or channel not found"},
        503: {"description": "TinyClaw service unavailable"},
    },
    dependencies=[Depends(verify_api_key)]
)
async def send_message(
    agent_id: str,
    request: SendMessageRequestAPI,
    coordinator = Depends(get_coordinator)
) -> MessageResponse:
    """
    Send a message to an agent.

    Args:
        agent_id: ID of the agent to send message as
        request: Message send request
        coordinator: Service coordinator dependency

    Returns:
        MessageResponse with sent message details

    Raises:
        HTTPException: If validation fails, agent/channel not found, or service is unavailable
    """
    try:
        # Validate inputs
        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required")

        if not request.content or not request.content.strip():
            raise ValidationError("Message content is required")

        if not request.channel_id or not request.channel_id.strip():
            raise ValidationError("channel_id is required")

        logger.info("Sending message", extra={
            "agent_id": agent_id,
            "channel_id": request.channel_id
        })

        # Convert to TinyClaw model format
        create_message_request = CreateMessageRequest(
            agent_id=agent_id,
            channel_id=request.channel_id,
            content=request.content,
            metadata=request.metadata,
            parent_message_id=request.parent_message_id
        )

        # Make request to TinyClaw service
        response = await coordinator.request_tinyclaw(
            "POST",
            f"/api/agents/{agent_id}/message",
            json=create_message_request.model_dump(exclude_none=True, by_alias=True)
        )

        logger.info("Message sent successfully", extra={
            "message_id": response.get("message_id"),
            "agent_id": agent_id
        })

        return MessageResponse(**response)

    except ValidationError as e:
        logger.warning("Validation error sending message", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict()
        )
    except IntegrationError as e:
        # Check if it's a 404 error
        if e.details.get("status_code") == 404:
            logger.info("Agent or channel not found", extra={
                "agent_id": agent_id,
                "channel_id": request.channel_id
            })
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=NotFoundError("Agent or channel not found").to_dict()
            )

        logger.error("Integration error sending message", extra={"error": e.message})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.to_dict()
        )
    except Exception as e:
        logger.exception("Unexpected error sending message")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Internal server error", "error_type": "InternalServerError"}
        )


# Export the router
__all__ = ["router"]
