"""
TinyClaw integration service with FastAPI endpoints.

This module provides the main FastAPI application for the TinyClaw integration,
exposing endpoints for agent management, message routing, and team coordination.
"""

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from src.shared.config import settings
from src.shared.errors import (
    BaseError,
    ValidationError,
    IntegrationError,
    TinyClawError,
    http_status_from_error,
)
from src.shared.logging import get_logger, configure_logging
from src.tinyclaw_integration.client import TinyClawClient
from src.tinyclaw_integration.models import (
    Agent,
    Message,
    AgentTeam,
    Channel,
    CreateAgentRequest,
    CreateMessageRequest,
    CreateTeamRequest,
    AgentListResponse,
    MessageListResponse,
    TeamListResponse,
    AgentStatus,
    ChannelStatus,
    MessageDirection,
    ChannelType,
)

# Configure module logger
logger = get_logger(__name__)

# Global client instance
_tinyclaw_client: TinyClawClient | None = None


def get_tinyclaw_client() -> TinyClawClient:
    """
    Get the global TinyClaw client instance.

    Returns:
        TinyClawClient instance

    Raises:
        TinyClawError: If client is not initialized
    """
    global _tinyclaw_client
    if _tinyclaw_client is None:
        raise TinyClawError(
            "TinyClaw client not initialized",
            details={"service": "tinyclaw_integration"},
        )
    return _tinyclaw_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    This function handles startup and shutdown events for the FastAPI application,
    ensuring proper initialization and cleanup of the TinyClaw client.

    Yields:
        None
    """
    global _tinyclaw_client

    # Startup
    logger.info("Starting TinyClaw integration service")
    configure_logging(settings.LOG_LEVEL)

    try:
        # Initialize TinyClaw client
        _tinyclaw_client = TinyClawClient(
            base_url=settings.TINYCLAW_API_URL,
            api_key=settings.TINYCLAW_API_KEY,
        )
        await _tinyclaw_client.initialize()

        # Perform health check
        is_healthy = await _tinyclaw_client.health_check()
        if is_healthy:
            logger.info("TinyClaw API connection healthy")
        else:
            logger.warning("TinyClaw API health check failed, but continuing")

        logger.info("TinyClaw integration service started successfully")

    except Exception as e:
        logger.exception("Failed to start TinyClaw integration service")
        # Don't raise - allow service to start in degraded mode
        _tinyclaw_client = None

    yield

    # Shutdown
    logger.info("Shutting down TinyClaw integration service")
    if _tinyclaw_client:
        try:
            await _tinyclaw_client.shutdown()
            logger.info("TinyClaw client shutdown complete")
        except Exception as e:
            logger.warning("Error during shutdown", extra={"error": str(e)})


# Create FastAPI application
app = FastAPI(
    title="TinyClaw Integration API",
    description="Multi-agent messaging integration service for TinyClaw",
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

    Returns the health status of the TinyClaw integration service.

    Returns:
        JSON response with health status
    """
    try:
        client = get_tinyclaw_client()
        is_healthy = await client.health_check()

        return {
            "status": "healthy" if is_healthy else "degraded",
            "service": "tinyclaw_integration",
            "version": "1.0.0",
        }
    except Exception as e:
        logger.warning("Health check failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "service": "tinyclaw_integration",
            "error": str(e),
        }


# ------------------------------------------------------------------------------
# Agent Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/agents", response_model=AgentListResponse)
async def list_agents(
    status: AgentStatus | None = None,
    team_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all agents with optional filtering.

    Args:
        status: Filter by agent status
        team_id: Filter by team ID
        limit: Maximum number of agents to return
        offset: Number of agents to skip

    Returns:
        AgentListResponse containing list of agents and total count
    """
    try:
        client = get_tinyclaw_client()
        return await client.list_agents(
            status=status,
            team_id=team_id,
            limit=limit,
            offset=offset,
        )
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing agents")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list agents"},
        )


@app.get("/api/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    """
    Get details of a specific agent.

    Args:
        agent_id: Unique identifier of the agent

    Returns:
        Agent object with full details
    """
    try:
        client = get_tinyclaw_client()
        return await client.get_agent(agent_id)
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error getting agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to get agent"},
        )


@app.post("/api/agents", response_model=Agent, status_code=status.HTTP_201_CREATED)
async def create_agent(request: CreateAgentRequest):
    """
    Create a new agent.

    Args:
        request: Agent creation request

    Returns:
        Created Agent object
    """
    try:
        client = get_tinyclaw_client()
        return await client.create_agent(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error creating agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to create agent"},
        )


@app.patch("/api/agents/{agent_id}", response_model=Agent)
async def update_agent(
    agent_id: str,
    name: str | None = None,
    description: str | None = None,
    status: AgentStatus | None = None,
    channels: list[str] | None = None,
):
    """
    Update an existing agent.

    Args:
        agent_id: Unique identifier of the agent
        name: New name for the agent
        description: New description for the agent
        status: New status for the agent
        channels: New list of channel IDs

    Returns:
        Updated Agent object
    """
    try:
        client = get_tinyclaw_client()
        return await client.update_agent(
            agent_id=agent_id,
            name=name,
            description=description,
            status=status,
            channels=channels,
        )
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error updating agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to update agent"},
        )


@app.delete("/api/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str):
    """
    Delete an agent.

    Args:
        agent_id: Unique identifier of the agent to delete
    """
    try:
        client = get_tinyclaw_client()
        await client.delete_agent(agent_id)
        return None
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error deleting agent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to delete agent"},
        )


# ------------------------------------------------------------------------------
# Message Endpoints
# ------------------------------------------------------------------------------

@app.post("/api/messages", response_model=Message, status_code=status.HTTP_201_CREATED)
async def send_message(request: CreateMessageRequest):
    """
    Send a message through an agent.

    Args:
        request: Message creation request

    Returns:
        Created Message object with status
    """
    try:
        client = get_tinyclaw_client()
        return await client.send_message(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error sending message")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to send message"},
        )


@app.get("/api/messages", response_model=MessageListResponse)
async def list_messages(
    agent_id: str | None = None,
    channel_id: str | None = None,
    direction: MessageDirection | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List messages with optional filtering.

    Args:
        agent_id: Filter by agent ID
        channel_id: Filter by channel ID
        direction: Filter by message direction
        limit: Maximum number of messages to return
        offset: Number of messages to skip

    Returns:
        MessageListResponse containing list of messages and total count
    """
    try:
        client = get_tinyclaw_client()
        return await client.list_messages(
            agent_id=agent_id,
            channel_id=channel_id,
            direction=direction,
            limit=limit,
            offset=offset,
        )
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing messages")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list messages"},
        )


# ------------------------------------------------------------------------------
# Team Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/teams", response_model=TeamListResponse)
async def list_teams(
    active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all agent teams with optional filtering.

    Args:
        active: Filter by active status
        limit: Maximum number of teams to return
        offset: Number of teams to skip

    Returns:
        TeamListResponse containing list of teams and total count
    """
    try:
        client = get_tinyclaw_client()
        return await client.list_teams(
            active=active,
            limit=limit,
            offset=offset,
        )
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing teams")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list teams"},
        )


@app.get("/api/teams/{team_id}", response_model=AgentTeam)
async def get_team(team_id: str):
    """
    Get details of a specific team.

    Args:
        team_id: Unique identifier of the team

    Returns:
        AgentTeam object with full details
    """
    try:
        client = get_tinyclaw_client()
        return await client.get_team(team_id)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error getting team")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to get team"},
        )


@app.post("/api/teams", response_model=AgentTeam, status_code=status.HTTP_201_CREATED)
async def create_team(request: CreateTeamRequest):
    """
    Create a new agent team.

    Args:
        request: Team creation request

    Returns:
        Created AgentTeam object
    """
    try:
        client = get_tinyclaw_client()
        return await client.create_team(request)
    except ValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error creating team")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to create team"},
        )


# ------------------------------------------------------------------------------
# Channel Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/channels", response_model=list[Channel])
async def list_channels(
    channel_type: ChannelType | None = None,
    status: ChannelStatus | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all channels with optional filtering.

    Args:
        channel_type: Filter by channel type
        status: Filter by connection status
        limit: Maximum number of channels to return
        offset: Number of channels to skip

    Returns:
        List of Channel objects
    """
    try:
        client = get_tinyclaw_client()
        return await client.list_channels(
            channel_type=channel_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    except TinyClawError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error listing channels")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to list channels"},
        )


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for running the TinyClaw integration service.

    This function starts the uvicorn server on the configured port.
    """
    port = 3777  # TinyClaw API port (hardcoded as per spec)

    logger.info(
        "Starting TinyClaw integration service",
        extra={"port": port},
    )

    uvicorn.run(
        "src.tinyclaw_integration.service:app",
        host="0.0.0.0",
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
