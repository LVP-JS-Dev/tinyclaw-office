"""
TinyClaw integration tests.

This module contains comprehensive tests for TinyClaw integration, including:
- Model validation tests
- Client API tests with mocked HTTP responses
- Service endpoint tests
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import httpx
from fastapi import status
from fastapi.testclient import TestClient

from src.tinyclaw_integration.models import (
    AgentStatus,
    ChannelType,
    MessageDirection,
    ChannelStatus,
    TimestampedModel,
    Channel,
    ChannelConfig,
    Agent,
    AgentCapability,
    Message,
    AgentTeam,
    RoutingConfig,
    CreateAgentRequest,
    CreateMessageRequest,
    CreateTeamRequest,
    AgentListResponse,
    MessageListResponse,
    TeamListResponse,
)
from src.tinyclaw_integration.client import TinyClawClient
from src.tinyclaw_integration.service import app, get_tinyclaw_client
from src.shared.errors import TinyClawError, ValidationError


# =============================================================================
# Model Tests
# =============================================================================

class TestTimestampedModel:
    """Test the TimestampedModel base class."""

    def test_timestamps_auto_generated(self):
        """Test that timestamps are automatically generated."""
        model = TimestampedModel()
        assert isinstance(model.created_at, datetime)
        assert isinstance(model.updated_at, datetime)

    def test_timestamps_can_be_set(self):
        """Test that timestamps can be explicitly set."""
        now = datetime.utcnow()
        model = TimestampedModel(created_at=now, updated_at=now)
        assert model.created_at == now
        assert model.updated_at == now


class TestChannelModels:
    """Test channel-related models."""

    def test_channel_config_defaults(self):
        """Test ChannelConfig with default values."""
        config = ChannelConfig()
        assert config.webhook_url is None
        assert config.api_key is None
        assert config.server_id is None
        assert config.phone_number is None
        assert config.bot_token is None
        assert config.extra == {}

    def test_channel_config_with_values(self):
        """Test ChannelConfig with explicit values."""
        config = ChannelConfig(
            webhook_url="https://example.com/webhook",
            api_key="test-key",
            server_id="123456",
            extra={"custom_field": "value"}
        )
        assert config.webhook_url == "https://example.com/webhook"
        assert config.api_key == "test-key"
        assert config.server_id == "123456"
        assert config.extra == {"custom_field": "value"}

    def test_channel_creation(self):
        """Test Channel model creation."""
        channel = Channel(
            channel_id="ch-123",
            channel_type=ChannelType.DISCORD,
            name="general",
            status=ChannelStatus.CONNECTED,
            config={"webhook_url": "https://example.com"}
        )
        assert channel.channel_id == "ch-123"
        assert channel.channel_type == ChannelType.DISCORD
        assert channel.name == "general"
        assert channel.status == ChannelStatus.CONNECTED


class TestAgentModels:
    """Test agent-related models."""

    def test_agent_capability_creation(self):
        """Test AgentCapability model."""
        capability = AgentCapability(
            name="code_execution",
            description="Execute code in sandbox",
            enabled=True,
            config={"timeout": 30}
        )
        assert capability.name == "code_execution"
        assert capability.description == "Execute code in sandbox"
        assert capability.enabled is True
        assert capability.config == {"timeout": 30}

    def test_agent_creation_minimal(self):
        """Test Agent creation with minimal fields."""
        agent = Agent(
            agent_id="agent-001",
            name="TestAgent"
        )
        assert agent.agent_id == "agent-001"
        assert agent.name == "TestAgent"
        assert agent.description is None
        assert agent.status == AgentStatus.INACTIVE
        assert agent.channels == []
        assert agent.capabilities == []

    def test_agent_creation_full(self):
        """Test Agent creation with all fields."""
        agent = Agent(
            agent_id="agent-002",
            name="CodeAssistant",
            description="Helps with coding tasks",
            status=AgentStatus.ACTIVE,
            channels=["ch-123", "ch-456"],
            capabilities=[
                AgentCapability(name="code_execution"),
                AgentCapability(name="file_access")
            ],
            config={"model": "gpt-4"},
            team_id="team-001"
        )
        assert agent.agent_id == "agent-002"
        assert agent.name == "CodeAssistant"
        assert agent.status == AgentStatus.ACTIVE
        assert len(agent.channels) == 2
        assert len(agent.capabilities) == 2
        assert agent.team_id == "team-001"

    def test_agent_validation_empty_name(self):
        """Test that empty agent name raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Agent(agent_id="agent-001", name="   ")

    def test_agent_validation_empty_id(self):
        """Test that empty agent_id raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Agent(agent_id="   ", name="TestAgent")


class TestMessageModels:
    """Test message-related models."""

    def test_message_creation(self):
        """Test Message model creation."""
        message = Message(
            message_id="msg-001",
            agent_id="agent-001",
            channel_id="ch-123",
            content="Hello, world!",
            direction=MessageDirection.OUTGOING,
            status="sent",
            metadata={"source": "user_request"}
        )
        assert message.message_id == "msg-001"
        assert message.agent_id == "agent-001"
        assert message.channel_id == "ch-123"
        assert message.content == "Hello, world!"
        assert message.direction == MessageDirection.OUTGOING
        assert message.status == "sent"
        assert message.metadata == {"source": "user_request"}

    def test_message_with_thread(self):
        """Test Message with threading support."""
        message = Message(
            message_id="msg-002",
            agent_id="agent-001",
            channel_id="ch-123",
            content="Reply to thread",
            direction=MessageDirection.OUTGOING,
            parent_message_id="msg-001",
            thread_id="thread-001"
        )
        assert message.parent_message_id == "msg-001"
        assert message.thread_id == "thread-001"

    def test_message_validation_empty_content(self):
        """Test that empty content raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Message(
                message_id="msg-001",
                agent_id="agent-001",
                channel_id="ch-123",
                content="   ",
                direction=MessageDirection.OUTGOING
            )


class TestTeamModels:
    """Test team-related models."""

    def test_routing_config_defaults(self):
        """Test RoutingConfig with default values."""
        config = RoutingConfig()
        assert config.strategy == "round_robin"
        assert config.fallback_agent is None
        assert config.timeout_seconds == 30
        assert config.retry_attempts == 3

    def test_agent_team_creation(self):
        """Test AgentTeam model creation."""
        team = AgentTeam(
            team_id="team-001",
            name="CustomerSupport",
            description="Customer service team",
            agent_ids=["agent-001", "agent-002"],
            routing_config={"strategy": "load_balanced"},
            active=True
        )
        assert team.team_id == "team-001"
        assert team.name == "CustomerSupport"
        assert len(team.agent_ids) == 2
        assert team.routing_config.strategy == "load_balanced"
        assert team.active is True

    def test_team_validation_empty_name(self):
        """Test that empty team name raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            AgentTeam(team_id="team-001", name="   ")


class TestRequestModels:
    """Test request/response models."""

    def test_create_agent_request(self):
        """Test CreateAgentRequest model."""
        request = CreateAgentRequest(
            name="NewAgent",
            description="A new test agent",
            channels=["ch-123"],
            capabilities=[AgentCapability(name="test")],
            team_id="team-001"
        )
        assert request.name == "NewAgent"
        assert request.description == "A new test agent"
        assert len(request.channels) == 1

    def test_create_message_request(self):
        """Test CreateMessageRequest model."""
        request = CreateMessageRequest(
            agent_id="agent-001",
            channel_id="ch-123",
            content="Test message",
            metadata={"priority": "high"}
        )
        assert request.agent_id == "agent-001"
        assert request.channel_id == "ch-123"
        assert request.content == "Test message"

    def test_create_team_request(self):
        """Test CreateTeamRequest model."""
        request = CreateTeamRequest(
            name="NewTeam",
            agent_ids=["agent-001", "agent-002"],
            routing_config=RoutingConfig(strategy="specialized")
        )
        assert request.name == "NewTeam"
        assert len(request.agent_ids) == 2
        assert request.routing_config.strategy == "specialized"

    def test_agent_list_response(self):
        """Test AgentListResponse model."""
        response = AgentListResponse(
            agents=[
                Agent(agent_id="agent-001", name="Agent1"),
                Agent(agent_id="agent-002", name="Agent2")
            ],
            total=2
        )
        assert len(response.agents) == 2
        assert response.total == 2

    def test_message_list_response(self):
        """Test MessageListResponse model."""
        response = MessageListResponse(
            messages=[
                Message(
                    message_id="msg-001",
                    agent_id="agent-001",
                    channel_id="ch-123",
                    content="Test",
                    direction=MessageDirection.OUTGOING
                )
            ],
            total=1
        )
        assert len(response.messages) == 1
        assert response.total == 1

    def test_team_list_response(self):
        """Test TeamListResponse model."""
        response = TeamListResponse(
            teams=[
                AgentTeam(
                    team_id="team-001",
                    name="Team1",
                    agent_ids=["agent-001"]
                )
            ],
            total=1
        )
        assert len(response.teams) == 1
        assert response.total == 1


# =============================================================================
# Client Tests
# =============================================================================

class TestTinyClawClient:
    """Test TinyClawClient with mocked HTTP responses."""

    @pytest.fixture
    def client(self):
        """Create a client instance for testing."""
        return TinyClawClient(base_url="http://test.example.com", api_key="test-key")

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx.AsyncClient."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        return mock_client

    @pytest.mark.asyncio
    async def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.base_url == "http://test.example.com"
        assert client.api_key == "test-key"
        assert client.timeout == 30.0
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_client_initialize(self, client):
        """Test client.initialize() creates HTTP client."""
        with patch("httpx.AsyncClient") as mock_async_client:
            await client.initialize()
            assert client._initialized is True
            assert client._client is not None

    @pytest.mark.asyncio
    async def test_client_double_initialize(self, client):
        """Test that calling initialize twice is idempotent."""
        with patch("httpx.AsyncClient") as mock_async_client:
            await client.initialize()
            first_client = client._client
            await client.initialize()
            assert client._client is first_client

    @pytest.mark.asyncio
    async def test_client_shutdown(self, client):
        """Test client shutdown."""
        with patch("httpx.AsyncClient") as mock_async_client:
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance

            await client.initialize()
            await client.shutdown()

            assert client._initialized is False
            assert client._client is None
            mock_instance.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test health_check with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            result = await client.health_check()
            assert result is True
            client._client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Test health_check with failed response."""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, client):
        """Test health_check with exception."""
        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.side_effect = Exception("Connection error")
            client._initialized = True

            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_list_agents_success(self, client):
        """Test list_agents with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agents": [
                {
                    "agent_id": "agent-001",
                    "name": "Agent1",
                    "status": "active",
                    "channels": [],
                    "capabilities": []
                }
            ],
            "total": 1
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            result = await client.list_agents()
            assert len(result.agents) == 1
            assert result.total == 1
            assert result.agents[0].name == "Agent1"

    @pytest.mark.asyncio
    async def test_list_agents_with_filters(self, client):
        """Test list_agents with status and team filters."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"agents": [], "total": 0}

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            await client.list_agents(status=AgentStatus.ACTIVE, team_id="team-001")

            # Verify params were passed correctly
            call_args = client._client.get.call_args
            assert "params" in call_args.kwargs
            assert call_args.kwargs["params"]["status"] == "active"
            assert call_args.kwargs["params"]["team_id"] == "team-001"

    @pytest.mark.asyncio
    async def test_list_agents_http_error(self, client):
        """Test list_agents with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            with pytest.raises(TinyClawError):
                await client.list_agents()

    @pytest.mark.asyncio
    async def test_get_agent_success(self, client):
        """Test get_agent with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "agent-001",
            "name": "TestAgent",
            "status": "active",
            "channels": [],
            "capabilities": []
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            agent = await client.get_agent("agent-001")
            assert agent.agent_id == "agent-001"
            assert agent.name == "TestAgent"

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, client):
        """Test get_agent with 404 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            with pytest.raises(TinyClawError, match="not found"):
                await client.get_agent("agent-001")

    @pytest.mark.asyncio
    async def test_get_agent_validation_error(self, client):
        """Test get_agent with empty agent_id."""
        with patch.object(client, "_ensure_initialized"):
            client._initialized = True

            with pytest.raises(ValidationError, match="agent_id is required"):
                await client.get_agent("   ")

    @pytest.mark.asyncio
    async def test_create_agent_success(self, client):
        """Test create_agent with successful response."""
        request = CreateAgentRequest(
            name="NewAgent",
            description="A test agent"
        )

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "agent_id": "agent-001",
            "name": "NewAgent",
            "description": "A test agent",
            "status": "inactive",
            "channels": [],
            "capabilities": []
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.post.return_value = mock_response
            client._initialized = True

            agent = await client.create_agent(request)
            assert agent.name == "NewAgent"
            assert agent.description == "A test agent"

    @pytest.mark.asyncio
    async def test_update_agent_success(self, client):
        """Test update_agent with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "agent-001",
            "name": "UpdatedAgent",
            "description": "Updated description",
            "status": "active",
            "channels": ["ch-123"],
            "capabilities": []
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.patch.return_value = mock_response
            client._initialized = True

            agent = await client.update_agent(
                "agent-001",
                name="UpdatedAgent",
                description="Updated description",
                status=AgentStatus.ACTIVE
            )
            assert agent.name == "UpdatedAgent"
            assert agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_update_agent_no_updates(self, client):
        """Test update_agent with no updates provided."""
        with patch.object(client, "_ensure_initialized"):
            client._initialized = True

            with pytest.raises(ValidationError, match="No updates provided"):
                await client.update_agent("agent-001")

    @pytest.mark.asyncio
    async def test_delete_agent_success(self, client):
        """Test delete_agent with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.delete.return_value = mock_response
            client._initialized = True

            # Should not raise any exception
            await client.delete_agent("agent-001")
            client._client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_success(self, client):
        """Test send_message with successful response."""
        request = CreateMessageRequest(
            agent_id="agent-001",
            channel_id="ch-123",
            content="Hello, world!"
        )

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "message_id": "msg-001",
            "agent_id": "agent-001",
            "channel_id": "ch-123",
            "content": "Hello, world!",
            "direction": "outgoing",
            "status": "sent"
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.post.return_value = mock_response
            client._initialized = True

            message = await client.send_message(request)
            assert message.message_id == "msg-001"
            assert message.content == "Hello, world!"
            assert message.status == "sent"

    @pytest.mark.asyncio
    async def test_list_messages_success(self, client):
        """Test list_messages with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [
                {
                    "message_id": "msg-001",
                    "agent_id": "agent-001",
                    "channel_id": "ch-123",
                    "content": "Test message",
                    "direction": "outgoing"
                }
            ],
            "total": 1
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            result = await client.list_messages(agent_id="agent-001")
            assert len(result.messages) == 1
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_create_team_success(self, client):
        """Test create_team with successful response."""
        request = CreateTeamRequest(
            name="TestTeam",
            agent_ids=["agent-001", "agent-002"]
        )

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "team_id": "team-001",
            "name": "TestTeam",
            "agent_ids": ["agent-001", "agent-002"],
            "active": True
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.post.return_value = mock_response
            client._initialized = True

            team = await client.create_team(request)
            assert team.team_id == "team-001"
            assert team.name == "TestTeam"
            assert len(team.agent_ids) == 2

    @pytest.mark.asyncio
    async def test_list_teams_success(self, client):
        """Test list_teams with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "teams": [
                {
                    "team_id": "team-001",
                    "name": "Team1",
                    "agent_ids": ["agent-001"],
                    "active": True
                }
            ],
            "total": 1
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            result = await client.list_teams(active=True)
            assert len(result.teams) == 1
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_team_success(self, client):
        """Test get_team with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "team_id": "team-001",
            "name": "TestTeam",
            "agent_ids": ["agent-001"],
            "active": True
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            team = await client.get_team("team-001")
            assert team.team_id == "team-001"
            assert team.name == "TestTeam"

    @pytest.mark.asyncio
    async def test_list_channels_success(self, client):
        """Test list_channels with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "channel_id": "ch-001",
                "channel_type": "discord",
                "name": "general",
                "status": "connected"
            }
        ]

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            channels = await client.list_channels()
            assert len(channels) == 1
            assert channels[0].channel_id == "ch-001"

    @pytest.mark.asyncio
    async def test_list_channels_with_dict_response(self, client):
        """Test list_channels when API returns dict with 'channels' key."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "channels": [
                {
                    "channel_id": "ch-001",
                    "channel_type": "discord",
                    "name": "general",
                    "status": "connected"
                }
            ]
        }

        with patch.object(client, "_ensure_initialized"):
            client._client = AsyncMock()
            client._client.get.return_value = mock_response
            client._initialized = True

            channels = await client.list_channels()
            assert len(channels) == 1
            assert channels[0].channel_id == "ch-001"


# =============================================================================
# Service Tests
# =============================================================================

class TestTinyClawService:
    """Test TinyClaw FastAPI service endpoints."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock TinyClawClient."""
        client = AsyncMock(spec=TinyClawClient)
        return client

    @pytest.fixture
    def test_app(self, mock_client):
        """Create a test app with mocked client."""
        # Override the get_tinyclaw_client dependency
        def override_get_client():
            return mock_client

        app.dependency_overrides[get_tinyclaw_client] = override_get_client
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the app."""
        return TestClient(test_app)

    def test_health_check_healthy(self, client, mock_client):
        """Test health check endpoint when service is healthy."""
        mock_client.health_check.return_value = True

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tinyclaw_integration"

    def test_health_check_degraded(self, client, mock_client):
        """Test health check endpoint when service is degraded."""
        mock_client.health_check.return_value = False

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    def test_health_check_exception(self, client, mock_client):
        """Test health check endpoint when client raises exception."""
        mock_client.health_check.side_effect = Exception("Client error")

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "error" in data

    def test_list_agents(self, client, mock_client):
        """Test GET /api/agents endpoint."""
        mock_client.list_agents.return_value = AgentListResponse(
            agents=[
                Agent(
                    agent_id="agent-001",
                    name="TestAgent",
                    status=AgentStatus.ACTIVE
                )
            ],
            total=1
        )

        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "TestAgent"

    def test_list_agents_with_filters(self, client, mock_client):
        """Test GET /api/agents with query parameters."""
        mock_client.list_agents.return_value = AgentListResponse(agents=[], total=0)

        response = client.get("/api/agents?status=active&team_id=team-001&limit=50")
        assert response.status_code == 200

        # Verify the client was called with correct parameters
        mock_client.list_agents.assert_called_once()
        call_kwargs = mock_client.list_agents.call_args.kwargs
        assert call_kwargs["status"] == AgentStatus.ACTIVE
        assert call_kwargs["team_id"] == "team-001"
        assert call_kwargs["limit"] == 50

    def test_get_agent(self, client, mock_client):
        """Test GET /api/agents/{agent_id} endpoint."""
        mock_client.get_agent.return_value = Agent(
            agent_id="agent-001",
            name="TestAgent",
            description="Test description"
        )

        response = client.get("/api/agents/agent-001")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-001"
        assert data["name"] == "TestAgent"

    def test_create_agent(self, client, mock_client):
        """Test POST /api/agents endpoint."""
        mock_client.create_agent.return_value = Agent(
            agent_id="agent-001",
            name="NewAgent",
            status=AgentStatus.INACTIVE
        )

        request_data = {
            "name": "NewAgent",
            "description": "A new agent"
        }

        response = client.post("/api/agents", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == "agent-001"
        assert data["name"] == "NewAgent"

    def test_update_agent(self, client, mock_client):
        """Test PATCH /api/agents/{agent_id} endpoint."""
        mock_client.update_agent.return_value = Agent(
            agent_id="agent-001",
            name="UpdatedAgent",
            status=AgentStatus.ACTIVE
        )

        request_data = {
            "name": "UpdatedAgent",
            "status": "active"
        }

        response = client.patch("/api/agents/agent-001", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "UpdatedAgent"

    def test_delete_agent(self, client, mock_client):
        """Test DELETE /api/agents/{agent_id} endpoint."""
        mock_client.delete_agent.return_value = None

        response = client.delete("/api/agents/agent-001")
        assert response.status_code == 204
        assert response.content == b""

    def test_send_message(self, client, mock_client):
        """Test POST /api/messages endpoint."""
        mock_client.send_message.return_value = Message(
            message_id="msg-001",
            agent_id="agent-001",
            channel_id="ch-123",
            content="Hello, world!",
            direction=MessageDirection.OUTGOING,
            status="sent"
        )

        request_data = {
            "agent_id": "agent-001",
            "channel_id": "ch-123",
            "content": "Hello, world!"
        }

        response = client.post("/api/messages", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["message_id"] == "msg-001"
        assert data["content"] == "Hello, world!"

    def test_list_messages(self, client, mock_client):
        """Test GET /api/messages endpoint."""
        mock_client.list_messages.return_value = MessageListResponse(
            messages=[
                Message(
                    message_id="msg-001",
                    agent_id="agent-001",
                    channel_id="ch-123",
                    content="Test",
                    direction=MessageDirection.OUTGOING
                )
            ],
            total=1
        )

        response = client.get("/api/messages?agent_id=agent-001")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["messages"]) == 1

    def test_list_teams(self, client, mock_client):
        """Test GET /api/teams endpoint."""
        mock_client.list_teams.return_value = TeamListResponse(
            teams=[
                AgentTeam(
                    team_id="team-001",
                    name="TestTeam",
                    agent_ids=["agent-001"]
                )
            ],
            total=1
        )

        response = client.get("/api/teams")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["teams"]) == 1

    def test_get_team(self, client, mock_client):
        """Test GET /api/teams/{team_id} endpoint."""
        mock_client.get_team.return_value = AgentTeam(
            team_id="team-001",
            name="TestTeam",
            agent_ids=["agent-001"]
        )

        response = client.get("/api/teams/team-001")
        assert response.status_code == 200
        data = response.json()
        assert data["team_id"] == "team-001"

    def test_create_team(self, client, mock_client):
        """Test POST /api/teams endpoint."""
        mock_client.create_team.return_value = AgentTeam(
            team_id="team-001",
            name="NewTeam",
            agent_ids=["agent-001"]
        )

        request_data = {
            "name": "NewTeam",
            "agent_ids": ["agent-001"]
        }

        response = client.post("/api/teams", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["team_id"] == "team-001"

    def test_list_channels(self, client, mock_client):
        """Test GET /api/channels endpoint."""
        mock_client.list_channels.return_value = [
            Channel(
                channel_id="ch-001",
                channel_type=ChannelType.DISCORD,
                name="general",
                status=ChannelStatus.CONNECTED
            )
        ]

        response = client.get("/api/channels")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["channel_id"] == "ch-001"

    def test_list_channels_with_filters(self, client, mock_client):
        """Test GET /api/channels with query parameters."""
        mock_client.list_channels.return_value = []

        response = client.get("/api/channels?channel_type=discord&status=connected")
        assert response.status_code == 200

        # Verify the client was called with correct parameters
        mock_client.list_channels.assert_called_once()
        call_kwargs = mock_client.list_channels.call_args.kwargs
        assert call_kwargs["channel_type"] == ChannelType.DISCORD
        assert call_kwargs["status"] == ChannelStatus.CONNECTED


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in TinyClaw integration."""

    def test_tinyclaw_error_to_dict(self):
        """Test TinyClawError conversion to dict."""
        error = TinyClawError(
            "Test error",
            details={"agent_id": "agent-001"}
        )
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "TinyClawError"
        assert error_dict["message"] == "Test error"
        assert error_dict["agent_id"] == "agent-001"
        assert "service" in error_dict

    def test_validation_error_to_dict(self):
        """Test ValidationError conversion to dict."""
        error = ValidationError("Invalid input", details={"field": "name"})
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "ValidationError"
        assert error_dict["message"] == "Invalid input"
        assert error_dict["field"] == "name"

    def test_tinyclaw_error_status_code(self):
        """Test TinyClawError status code property."""
        error = TinyClawError("Service unavailable")
        assert error.status_code == 503

    def test_validation_error_status_code(self):
        """Test ValidationError status code property."""
        error = ValidationError("Invalid input")
        assert error.status_code == 400

    def test_service_not_initialized(self):
        """Test error when client is not initialized."""
        client = TinyClawClient()
        with pytest.raises(TinyClawError, match="not initialized"):
            client._ensure_initialized()
