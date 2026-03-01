"""
TinyClaw API client for multi-agent messaging integration.

This module provides an async HTTP client for interacting with the TinyClaw API,
supporting agent management, message routing, and team coordination operations.
"""

import asyncio
from typing import Any
from datetime import datetime

import httpx

from src.shared.config import settings
from src.shared.errors import TinyClawError, ValidationError
from src.shared.logging import get_logger
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
)

logger = get_logger(__name__)


class TinyClawClient:
    """
    Async HTTP client for TinyClaw multi-agent messaging API.

    This client provides methods to manage agents, send messages, and coordinate
    agent teams through the TinyClaw API. All methods are async and use httpx
    for non-blocking HTTP operations.

    Attributes:
        base_url: Base URL of the TinyClaw API
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds
        _client: Internal httpx.AsyncClient instance

    Example:
        >>> client = TinyClawClient()
        >>> await client.initialize()
        >>> agents = await client.list_agents()
        >>> await client.shutdown()
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the TinyClaw client.

        Args:
            base_url: TinyClaw API base URL (defaults to settings.TINYCLAW_API_URL)
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.TINYCLAW_API_URL
        self.api_key = api_key or settings.TINYCLAW_API_KEY
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._initialized = False

        # Remove trailing slash for consistent URL handling
        self.base_url = self.base_url.rstrip("/")

        logger.info(
            "TinyClaw client initialized",
            extra={"base_url": self.base_url, "timeout": timeout},
        )

    async def initialize(self) -> None:
        """
        Initialize the HTTP client.

        This method must be called before making any API requests. It creates
        the underlying httpx.AsyncClient with proper configuration.

        Raises:
            TinyClawError: If client initialization fails
        """
        if self._initialized:
            logger.debug("Client already initialized")
            return

        try:
            # Configure httpx client with timeouts and limits
            limits = httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0,
            )

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                limits=limits,
            )

            self._initialized = True
            logger.info("TinyClaw client HTTP session created")

        except Exception as e:
            logger.exception("Failed to initialize TinyClaw client")
            raise TinyClawError(
                "Failed to initialize client",
                details={"error": str(e), "base_url": self.base_url},
            ) from e

    async def shutdown(self) -> None:
        """
        Close the HTTP client and cleanup resources.

        This method should be called when the client is no longer needed.
        It gracefully closes the HTTP connection.
        """
        if self._client:
            try:
                await self._client.aclose()
                logger.info("TinyClaw client HTTP session closed")
            except Exception as e:
                logger.warning("Error closing HTTP client", extra={"error": str(e)})
            finally:
                self._client = None
                self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure the client has been initialized."""
        if not self._initialized or self._client is None:
            raise TinyClawError(
                "Client not initialized. Call initialize() first.",
                details={"method": "check_init"},
            )

    def _get_headers(self) -> dict[str, str]:
        """
        Get request headers including authentication.

        Returns:
            Dictionary of HTTP headers
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def health_check(self) -> bool:
        """
        Check if the TinyClaw API is accessible.

        Returns:
            True if the API is healthy, False otherwise

        Example:
            >>> client = TinyClawClient()
            >>> await client.initialize()
            >>> is_healthy = await client.health_check()
            >>> print(f"API Healthy: {is_healthy}")
        """
        try:
            if not self._initialized:
                await self.initialize()

            response = await self._client.get(
                "/health",
                headers=self._get_headers(),
            )

            is_healthy = response.status_code == 200
            logger.debug(
                "Health check completed",
                extra={"healthy": is_healthy, "status_code": response.status_code},
            )
            return is_healthy

        except Exception as e:
            logger.warning("Health check failed", extra={"error": str(e)})
            return False

    # ------------------------------------------------------------------------------
    # Agent Management
    # ------------------------------------------------------------------------------

    async def list_agents(
        self,
        status: AgentStatus | None = None,
        team_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AgentListResponse:
        """
        List all agents with optional filtering.

        Args:
            status: Filter by agent status
            team_id: Filter by team ID
            limit: Maximum number of agents to return
            offset: Number of agents to skip (for pagination)

        Returns:
            AgentListResponse containing list of agents and total count

        Raises:
            TinyClawError: If the API request fails
            ValidationError: If request parameters are invalid

        Example:
            >>> response = await client.list_agents(status=AgentStatus.ACTIVE)
            >>> for agent in response.agents:
            ...     print(f"{agent.name}: {agent.status}")
        """
        self._ensure_initialized()

        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}

            if status:
                params["status"] = status.value
            if team_id:
                params["team_id"] = team_id

            logger.debug(
                "Listing agents",
                extra={"params": params},
            )

            response = await self._client.get(
                "/api/agents",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            return AgentListResponse(**data)

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to list agents")
            raise TinyClawError(
                f"Failed to list agents: {e.response.status_code}",
                details={"status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error listing agents")
            raise TinyClawError(
                "Unexpected error listing agents",
                details={"error": str(e)},
            ) from e

    async def get_agent(self, agent_id: str) -> Agent:
        """
        Get details of a specific agent.

        Args:
            agent_id: Unique identifier of the agent

        Returns:
            Agent object with full details

        Raises:
            TinyClawError: If the agent is not found or API request fails
            ValidationError: If agent_id is invalid

        Example:
            >>> agent = await client.get_agent("agent-123")
            >>> print(f"{agent.name}: {agent.description}")
        """
        self._ensure_initialized()

        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required", details={"field": "agent_id"})

        try:
            logger.debug("Getting agent", extra={"agent_id": agent_id})

            response = await self._client.get(
                f"/api/agents/{agent_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            data = response.json()
            return Agent(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Agent not found", extra={"agent_id": agent_id})
                raise TinyClawError(
                    f"Agent {agent_id} not found",
                    details={"agent_id": agent_id, "status_code": 404},
                ) from e
            logger.exception("Failed to get agent")
            raise TinyClawError(
                f"Failed to get agent: {e.response.status_code}",
                details={"agent_id": agent_id, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error getting agent")
            raise TinyClawError(
                "Unexpected error getting agent",
                details={"agent_id": agent_id, "error": str(e)},
            ) from e

    async def create_agent(self, request: CreateAgentRequest) -> Agent:
        """
        Create a new agent.

        Args:
            request: Agent creation request with name, description, channels, etc.

        Returns:
            Created Agent object

        Raises:
            TinyClawError: If agent creation fails
            ValidationError: If request data is invalid

        Example:
            >>> request = CreateAgentRequest(
            ...     name="CodeAssistant",
            ...     description="Helps with coding tasks",
            ...     channels=["ch-123"],
            ... )
            >>> agent = await client.create_agent(request)
        """
        self._ensure_initialized()

        try:
            logger.info(
                "Creating agent",
                extra={"name": request.name, "channels": request.channels},
            )

            response = await self._client.post(
                "/api/agents",
                headers=self._get_headers(),
                json=request.model_dump(mode="json", exclude_unset=True),
            )
            response.raise_for_status()

            data = response.json()
            agent = Agent(**data)

            logger.info("Agent created successfully", extra={"agent_id": agent.agent_id})
            return agent

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to create agent")
            raise TinyClawError(
                f"Failed to create agent: {e.response.status_code}",
                details={"name": request.name, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error creating agent")
            raise TinyClawError(
                "Unexpected error creating agent",
                details={"name": request.name, "error": str(e)},
            ) from e

    async def update_agent(
        self,
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
        status: AgentStatus | None = None,
        channels: list[str] | None = None,
    ) -> Agent:
        """
        Update an existing agent.

        Args:
            agent_id: Unique identifier of the agent to update
            name: New name for the agent
            description: New description for the agent
            status: New status for the agent
            channels: New list of channel IDs

        Returns:
            Updated Agent object

        Raises:
            TinyClawError: If update fails
            ValidationError: If agent_id is invalid

        Example:
            >>> agent = await client.update_agent(
            ...     "agent-123",
            ...     description="Updated description",
            ...     status=AgentStatus.ACTIVE,
            ... )
        """
        self._ensure_initialized()

        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required", details={"field": "agent_id"})

        try:
            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = name
            if description is not None:
                updates["description"] = description
            if status is not None:
                updates["status"] = status.value
            if channels is not None:
                updates["channels"] = channels

            if not updates:
                raise ValidationError("No updates provided", details={"agent_id": agent_id})

            logger.debug("Updating agent", extra={"agent_id": agent_id, "updates": updates})

            response = await self._client.patch(
                f"/api/agents/{agent_id}",
                headers=self._get_headers(),
                json=updates,
            )
            response.raise_for_status()

            data = response.json()
            return Agent(**data)

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to update agent")
            raise TinyClawError(
                f"Failed to update agent: {e.response.status_code}",
                details={"agent_id": agent_id, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error updating agent")
            raise TinyClawError(
                "Unexpected error updating agent",
                details={"agent_id": agent_id, "error": str(e)},
            ) from e

    async def delete_agent(self, agent_id: str) -> None:
        """
        Delete an agent.

        Args:
            agent_id: Unique identifier of the agent to delete

        Raises:
            TinyClawError: If deletion fails
            ValidationError: If agent_id is invalid

        Example:
            >>> await client.delete_agent("agent-123")
        """
        self._ensure_initialized()

        if not agent_id or not agent_id.strip():
            raise ValidationError("agent_id is required", details={"field": "agent_id"})

        try:
            logger.info("Deleting agent", extra={"agent_id": agent_id})

            response = await self._client.delete(
                f"/api/agents/{agent_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            logger.info("Agent deleted successfully", extra={"agent_id": agent_id})

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to delete agent")
            raise TinyClawError(
                f"Failed to delete agent: {e.response.status_code}",
                details={"agent_id": agent_id, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error deleting agent")
            raise TinyClawError(
                "Unexpected error deleting agent",
                details={"agent_id": agent_id, "error": str(e)},
            ) from e

    # ------------------------------------------------------------------------------
    # Message Operations
    # ------------------------------------------------------------------------------

    async def send_message(self, request: CreateMessageRequest) -> Message:
        """
        Send a message through an agent.

        Args:
            request: Message creation request

        Returns:
            Created Message object with status

        Raises:
            TinyClawError: If sending fails
            ValidationError: If request data is invalid

        Example:
            >>> request = CreateMessageRequest(
            ...     agent_id="agent-123",
            ...     channel_id="ch-456",
            ...     content="Hello, world!",
            ... )
            >>> message = await client.send_message(request)
            >>> print(f"Message sent: {message.message_id}")
        """
        self._ensure_initialized()

        try:
            logger.info(
                "Sending message",
                extra={
                    "agent_id": request.agent_id,
                    "channel_id": request.channel_id,
                    "content_length": len(request.content),
                },
            )

            response = await self._client.post(
                "/api/messages",
                headers=self._get_headers(),
                json=request.model_dump(mode="json", exclude_unset=True),
            )
            response.raise_for_status()

            data = response.json()
            message = Message(**data)

            logger.info(
                "Message sent successfully",
                extra={"message_id": message.message_id, "status": message.status},
            )
            return message

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to send message")
            raise TinyClawError(
                f"Failed to send message: {e.response.status_code}",
                details={
                    "agent_id": request.agent_id,
                    "channel_id": request.channel_id,
                    "status_code": e.response.status_code,
                },
            ) from e
        except Exception as e:
            logger.exception("Unexpected error sending message")
            raise TinyClawError(
                "Unexpected error sending message",
                details={
                    "agent_id": request.agent_id,
                    "channel_id": request.channel_id,
                    "error": str(e),
                },
            ) from e

    async def list_messages(
        self,
        agent_id: str | None = None,
        channel_id: str | None = None,
        direction: MessageDirection | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> MessageListResponse:
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

        Raises:
            TinyClawError: If the API request fails

        Example:
            >>> response = await client.list_messages(agent_id="agent-123", limit=50)
            >>> for message in response.messages:
            ...     print(f"{message.direction}: {message.content[:50]}...")
        """
        self._ensure_initialized()

        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}

            if agent_id:
                params["agent_id"] = agent_id
            if channel_id:
                params["channel_id"] = channel_id
            if direction:
                params["direction"] = direction.value

            logger.debug("Listing messages", extra={"params": params})

            response = await self._client.get(
                "/api/messages",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            return MessageListResponse(**data)

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to list messages")
            raise TinyClawError(
                f"Failed to list messages: {e.response.status_code}",
                details={"status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error listing messages")
            raise TinyClawError(
                "Unexpected error listing messages",
                details={"error": str(e)},
            ) from e

    # ------------------------------------------------------------------------------
    # Team Management
    # ------------------------------------------------------------------------------

    async def create_team(self, request: CreateTeamRequest) -> AgentTeam:
        """
        Create a new agent team.

        Args:
            request: Team creation request

        Returns:
            Created AgentTeam object

        Raises:
            TinyClawError: If team creation fails
            ValidationError: If request data is invalid

        Example:
            >>> request = CreateTeamRequest(
            ...     name="CustomerSupport",
            ...     agent_ids=["agent-123", "agent-456"],
            ... )
            >>> team = await client.create_team(request)
        """
        self._ensure_initialized()

        try:
            logger.info(
                "Creating team",
                extra={"name": request.name, "agent_ids": request.agent_ids},
            )

            response = await self._client.post(
                "/api/teams",
                headers=self._get_headers(),
                json=request.model_dump(mode="json", exclude_unset=True),
            )
            response.raise_for_status()

            data = response.json()
            team = AgentTeam(**data)

            logger.info("Team created successfully", extra={"team_id": team.team_id})
            return team

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to create team")
            raise TinyClawError(
                f"Failed to create team: {e.response.status_code}",
                details={"name": request.name, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error creating team")
            raise TinyClawError(
                "Unexpected error creating team",
                details={"name": request.name, "error": str(e)},
            ) from e

    async def list_teams(
        self,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> TeamListResponse:
        """
        List all agent teams with optional filtering.

        Args:
            active: Filter by active status
            limit: Maximum number of teams to return
            offset: Number of teams to skip

        Returns:
            TeamListResponse containing list of teams and total count

        Raises:
            TinyClawError: If the API request fails

        Example:
            >>> response = await client.list_teams(active=True)
            >>> for team in response.teams:
            ...     print(f"{team.name}: {len(team.agent_ids)} agents")
        """
        self._ensure_initialized()

        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}

            if active is not None:
                params["active"] = active

            logger.debug("Listing teams", extra={"params": params})

            response = await self._client.get(
                "/api/teams",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            return TeamListResponse(**data)

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to list teams")
            raise TinyClawError(
                f"Failed to list teams: {e.response.status_code}",
                details={"status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error listing teams")
            raise TinyClawError(
                "Unexpected error listing teams",
                details={"error": str(e)},
            ) from e

    async def get_team(self, team_id: str) -> AgentTeam:
        """
        Get details of a specific team.

        Args:
            team_id: Unique identifier of the team

        Returns:
            AgentTeam object with full details

        Raises:
            TinyClawError: If the team is not found or API request fails
            ValidationError: If team_id is invalid

        Example:
            >>> team = await client.get_team("team-123")
            >>> print(f"{team.name}: {team.description}")
        """
        self._ensure_initialized()

        if not team_id or not team_id.strip():
            raise ValidationError("team_id is required", details={"field": "team_id"})

        try:
            logger.debug("Getting team", extra={"team_id": team_id})

            response = await self._client.get(
                f"/api/teams/{team_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            data = response.json()
            return AgentTeam(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Team not found", extra={"team_id": team_id})
                raise TinyClawError(
                    f"Team {team_id} not found",
                    details={"team_id": team_id, "status_code": 404},
                ) from e
            logger.exception("Failed to get team")
            raise TinyClawError(
                f"Failed to get team: {e.response.status_code}",
                details={"team_id": team_id, "status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error getting team")
            raise TinyClawError(
                "Unexpected error getting team",
                details={"team_id": team_id, "error": str(e)},
            ) from e

    # ------------------------------------------------------------------------------
    # Channel Operations
    # ------------------------------------------------------------------------------

    async def list_channels(
        self,
        channel_type: ChannelType | None = None,
        status: ChannelStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Channel]:
        """
        List all channels with optional filtering.

        Args:
            channel_type: Filter by channel type
            status: Filter by connection status
            limit: Maximum number of channels to return
            offset: Number of channels to skip

        Returns:
            List of Channel objects

        Raises:
            TinyClawError: If the API request fails

        Example:
            >>> channels = await client.list_channels(
            ...     channel_type=ChannelType.DISCORD,
            ...     status=ChannelStatus.CONNECTED,
            ... )
            >>> for channel in channels:
            ...     print(f"{channel.name}: {channel.status}")
        """
        self._ensure_initialized()

        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}

            if channel_type:
                params["channel_type"] = channel_type.value
            if status:
                params["status"] = status.value

            logger.debug("Listing channels", extra={"params": params})

            response = await self._client.get(
                "/api/channels",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            # TinyClaw API might return a dict with 'channels' key or a list directly
            if isinstance(data, dict) and "channels" in data:
                return [Channel(**ch) for ch in data["channels"]]
            return [Channel(**ch) for ch in data]

        except httpx.HTTPStatusError as e:
            logger.exception("Failed to list channels")
            raise TinyClawError(
                f"Failed to list channels: {e.response.status_code}",
                details={"status_code": e.response.status_code},
            ) from e
        except Exception as e:
            logger.exception("Unexpected error listing channels")
            raise TinyClawError(
                "Unexpected error listing channels",
                details={"error": str(e)},
            ) from e


# Export the client class
__all__ = ["TinyClawClient"]
