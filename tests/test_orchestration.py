"""
Orchestration layer tests.

This module contains comprehensive tests for the orchestration layer, including:
- ServiceCoordinator tests for inter-service communication
- API endpoint tests for health, root, agents, memory, and execution routes
- Request routing and retry logic tests
- Error handling and validation tests
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any
from dataclasses import asdict
from uuid import uuid4

import httpx
from fastapi import status
from fastapi.testclient import TestClient

from src.orchestration.api import app, get_coordinator, lifespan, _coordinator
from src.orchestration.coordinator import (
    ServiceCoordinator,
    ServiceHealth,
    ServiceClient,
)
from src.shared.errors import IntegrationError, ValidationError, NotFoundError
from src.shared.config import settings


# =============================================================================
# ServiceCoordinator Tests
# =============================================================================

class TestServiceHealth:
    """Test ServiceHealth dataclass."""

    def test_service_health_creation(self):
        """Test ServiceHealth object creation."""
        health = ServiceHealth(
            service="tinyclaw",
            healthy=True,
            response_time_ms=50.5,
            error=None
        )
        assert health.service == "tinyclaw"
        assert health.healthy is True
        assert health.response_time_ms == 50.5
        assert health.error is None

    def test_service_health_unhealthy(self):
        """Test ServiceHealth for unhealthy service."""
        health = ServiceHealth(
            service="memu",
            healthy=False,
            response_time_ms=None,
            error="Connection refused"
        )
        assert health.service == "memu"
        assert health.healthy is False
        assert health.response_time_ms is None
        assert health.error == "Connection refused"


class TestServiceClient:
    """Test ServiceClient dataclass."""

    def test_service_client_creation(self):
        """Test ServiceClient object creation."""
        client = ServiceClient(
            name="tinyclaw",
            base_url="http://localhost:3777",
            timeout=30.0
        )
        assert client.name == "tinyclaw"
        assert client.base_url == "http://localhost:3777"
        assert client.timeout == 30.0


class TestServiceCoordinatorInit:
    """Test ServiceCoordinator initialization."""

    def test_coordinator_initialization(self):
        """Test coordinator object initialization."""
        coordinator = ServiceCoordinator()
        assert coordinator._initialized is False
        assert coordinator._clients == {}
        assert ServiceCoordinator.TINYCLAW in coordinator._services
        assert ServiceCoordinator.MEMU in coordinator._services
        assert ServiceCoordinator.GONDOLIN in coordinator._services

    @pytest.mark.asyncio
    async def test_coordinator_initialize(self):
        """Test coordinator.initialize() creates HTTP clients."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()
        assert coordinator._initialized is True
        assert ServiceCoordinator.TINYCLAW in coordinator._clients
        assert ServiceCoordinator.MEMU in coordinator._clients
        assert ServiceCoordinator.GONDOLIN in coordinator._clients

        # Cleanup
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_coordinator_double_initialize(self):
        """Test that calling initialize twice is idempotent."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()
        first_clients = coordinator._clients.copy()
        await coordinator.initialize()
        assert coordinator._clients == first_clients
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_coordinator_shutdown(self):
        """Test coordinator shutdown closes all clients."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()
        assert coordinator._initialized is True

        await coordinator.shutdown()
        assert coordinator._initialized is False
        assert coordinator._clients == {}

    @pytest.mark.asyncio
    async def test_coordinator_shutdown_when_not_initialized(self):
        """Test shutdown when coordinator is not initialized."""
        coordinator = ServiceCoordinator()
        # Should not raise any exception
        await coordinator.shutdown()
        assert coordinator._initialized is False

    @pytest.mark.asyncio
    async def test_is_initialized_property(self):
        """Test is_initialized property."""
        coordinator = ServiceCoordinator()
        assert coordinator.is_initialized is False
        await coordinator.initialize()
        assert coordinator.is_initialized is True
        await coordinator.shutdown()
        assert coordinator.is_initialized is False


class TestServiceCoordinatorHealthChecks:
    """Test ServiceCoordinator health check methods."""

    @pytest.fixture
    async def coordinator(self):
        """Create an initialized coordinator for testing."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()
        yield coordinator
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, coordinator):
        """Test check_health with healthy service."""
        # Mock the health check response
        with patch.object(coordinator._clients[ServiceCoordinator.TINYCLAW], 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            health = await coordinator.check_health(ServiceCoordinator.TINYCLAW)

            assert health.service == ServiceCoordinator.TINYCLAW
            assert health.healthy is True
            assert health.response_time_ms is not None
            assert health.error is None

    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self, coordinator):
        """Test check_health with unhealthy service."""
        with patch.object(coordinator._clients[ServiceCoordinator.TINYCLAW], 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response

            health = await coordinator.check_health(ServiceCoordinator.TINYCLAW)

            assert health.service == ServiceCoordinator.TINYCLAW
            assert health.healthy is False
            assert health.error == "HTTP 503"

    @pytest.mark.asyncio
    async def test_check_health_timeout(self, coordinator):
        """Test check_health with timeout."""
        with patch.object(coordinator._clients[ServiceCoordinator.TINYCLAW], 'get') as mock_get:
            import asyncio
            mock_get.side_effect = asyncio.TimeoutError()

            health = await coordinator.check_health(ServiceCoordinator.TINYCLAW)

            assert health.healthy is False
            assert health.error == "Health check timed out"

    @pytest.mark.asyncio
    async def test_check_health_connection_error(self, coordinator):
        """Test check_health with connection error."""
        with patch.object(coordinator._clients[ServiceCoordinator.TINYCLAW], 'get') as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            health = await coordinator.check_health(ServiceCoordinator.TINYCLAW)

            assert health.healthy is False
            assert "Connection error" in health.error

    @pytest.mark.asyncio
    async def test_check_health_invalid_service(self, coordinator):
        """Test check_health with invalid service name."""
        with pytest.raises(ValidationError, match="Unknown service"):
            await coordinator.check_health("invalid_service")

    @pytest.mark.asyncio
    async def test_check_all_health(self, coordinator):
        """Test check_all_health checks all services."""
        # Mock all health checks
        for service_name, client in coordinator._clients.items():
            with patch.object(client, 'get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_get.return_value = mock_response

        health_status = await coordinator.check_all_health()

        assert len(health_status) == 3
        assert ServiceCoordinator.TINYCLAW in health_status
        assert ServiceCoordinator.MEMU in health_status
        assert ServiceCoordinator.GONDOLIN in health_status

        # All should be healthy
        assert all(h.healthy for h in health_status.values())


class TestServiceCoordinatorRequests:
    """Test ServiceCoordinator request methods."""

    @pytest.fixture
    async def coordinator(self):
        """Create an initialized coordinator for testing."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()
        yield coordinator
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_make_request_success(self, coordinator):
        """Test _make_request with successful response."""
        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_client.request.return_value = mock_response

        result = await coordinator._make_request(
            ServiceCoordinator.TINYCLAW,
            "GET",
            "/test"
        )

        assert result == {"result": "success"}
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_not_initialized(self):
        """Test _make_request when coordinator is not initialized."""
        coordinator = ServiceCoordinator()
        coordinator._initialized = False

        with pytest.raises(IntegrationError, match="not initialized"):
            await coordinator._make_request(
                ServiceCoordinator.TINYCLAW,
                "GET",
                "/test"
            )

    @pytest.mark.asyncio
    async def test_make_request_invalid_service(self, coordinator):
        """Test _make_request with invalid service."""
        with pytest.raises(ValidationError, match="Unknown service"):
            await coordinator._make_request(
                "invalid_service",
                "GET",
                "/test"
            )

    @pytest.mark.asyncio
    async def test_make_request_204_no_content(self, coordinator):
        """Test _make_request with 204 No Content response."""
        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_client.request.return_value = mock_response

        result = await coordinator._make_request(
            ServiceCoordinator.TINYCLAW,
            "DELETE",
            "/test"
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_make_request_client_error_no_retry(self, coordinator):
        """Test _make_request does not retry 4xx errors."""
        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_client.request.return_value = mock_response

        with pytest.raises(IntegrationError, match="Service returned error: 404"):
            await coordinator._make_request(
                ServiceCoordinator.TINYCLAW,
                "GET",
                "/test"
            )

        # Should only attempt once (no retry for 4xx)
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_make_request_server_error_retry(self, coordinator):
        """Test _make_request retries 5xx errors."""
        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]

        # First two attempts fail with 500, third succeeds
        mock_error_response = AsyncMock()
        mock_error_response.status_code = 500
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_error_response
        )

        mock_success_response = AsyncMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"result": "success"}

        mock_client.request.side_effect = [
            mock_error_response,
            mock_error_response,
            mock_success_response
        ]

        with patch('asyncio.sleep'):  # Skip sleep delays
            result = await coordinator._make_request(
                ServiceCoordinator.TINYCLAW,
                "GET",
                "/test"
            )

        assert result == {"result": "success"}
        assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_request_tinyclaw(self, coordinator):
        """Test request_tinyclaw method."""
        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"agents": []}
        mock_client.request.return_value = mock_response

        result = await coordinator.request_tinyclaw("GET", "/agents")

        assert result == {"agents": []}
        mock_client.request.assert_called_once_with("GET", "/agents")

    @pytest.mark.asyncio
    async def test_request_memu(self, coordinator):
        """Test request_memu method."""
        mock_client = coordinator._clients[ServiceCoordinator.MEMU]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"memories": []}
        mock_client.request.return_value = mock_response

        result = await coordinator.request_memu("POST", "/memory/store", json={"test": "data"})

        assert result == {"memories": []}
        mock_client.request.assert_called_once_with("POST", "/memory/store", json={"test": "data"})

    @pytest.mark.asyncio
    async def test_request_gondolin(self, coordinator):
        """Test request_gondolin method."""
        mock_client = coordinator._clients[ServiceCoordinator.GONDOLIN]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"task_id": "task-123"}
        mock_client.request.return_value = mock_response

        result = await coordinator.request_gondolin("POST", "/execute", json={"code": "test"})

        assert result == {"task_id": "task-123"}
        mock_client.request.assert_called_once_with("POST", "/execute", json={"code": "test"})

    def test_get_service_url(self, coordinator):
        """Test get_service_url method."""
        tinyclaw_url = coordinator.get_service_url(ServiceCoordinator.TINYCLAW)
        assert tinyclaw_url == settings.TINYCLAW_API_URL

        memu_url = coordinator.get_service_url(ServiceCoordinator.MEMU)
        assert memu_url == "http://localhost:8000"

        gondolin_url = coordinator.get_service_url(ServiceCoordinator.GONDOLIN)
        assert gondolin_url == settings.GONDOLIN_API_URL

    def test_get_service_url_invalid(self, coordinator):
        """Test get_service_url with invalid service."""
        with pytest.raises(ValidationError, match="Unknown service"):
            coordinator.get_service_url("invalid_service")


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestAPIEndpoints:
    """Test orchestration API endpoints."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = AsyncMock(spec=ServiceCoordinator)
        coordinator.check_all_health.return_value = {
            ServiceCoordinator.TINYCLAW: ServiceHealth(
                service=ServiceCoordinator.TINYCLAW,
                healthy=True,
                response_time_ms=50.0
            ),
            ServiceCoordinator.MEMU: ServiceHealth(
                service=ServiceCoordinator.MEMU,
                healthy=True,
                response_time_ms=30.0
            ),
            ServiceCoordinator.GONDOLIN: ServiceHealth(
                service=ServiceCoordinator.GONDOLIN,
                healthy=True,
                response_time_ms=100.0
            ),
        }
        return coordinator

    @pytest.fixture
    def test_app(self, mock_coordinator):
        """Create a test app with mocked coordinator."""
        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the app."""
        return TestClient(test_app)

    def test_root_endpoint(self, client):
        """Test GET / endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TinyClaw Office Orchestration API"
        assert data["version"] == "1.0.0"
        assert "tinyclaw" in data["services"]
        assert "memu" in data["services"]
        assert "gondolin" in data["services"]
        assert data["docs_url"] == "/docs"
        assert data["health_url"] == "/health"

    def test_health_check_all_healthy(self, client, mock_coordinator):
        """Test GET /health when all services are healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "orchestration"
        assert "services" in data
        assert data["services"]["tinyclaw"]["healthy"] is True
        assert data["services"]["memu"]["healthy"] is True
        assert data["services"]["gondolin"]["healthy"] is True

    def test_health_check_degraded(self, client, mock_coordinator):
        """Test GET /health when some services are unhealthy."""
        mock_coordinator.check_all_health.return_value = {
            ServiceCoordinator.TINYCLAW: ServiceHealth(
                service=ServiceCoordinator.TINYCLAW,
                healthy=True,
                response_time_ms=50.0
            ),
            ServiceCoordinator.MEMU: ServiceHealth(
                service=ServiceCoordinator.MEMU,
                healthy=False,
                error="Connection refused"
            ),
            ServiceCoordinator.GONDOLIN: ServiceHealth(
                service=ServiceCoordinator.GONDOLIN,
                healthy=True,
                response_time_ms=100.0
            ),
        }

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["memu"]["healthy"] is False
        assert data["services"]["memu"]["error"] == "Connection refused"

    def test_health_check_unhealthy(self, client, mock_coordinator):
        """Test GET /health when all services are unhealthy."""
        mock_coordinator.check_all_health.return_value = {
            ServiceCoordinator.TINYCLAW: ServiceHealth(
                service=ServiceCoordinator.TINYCLAW,
                healthy=False,
                error="Connection refused"
            ),
            ServiceCoordinator.MEMU: ServiceHealth(
                service=ServiceCoordinator.MEMU,
                healthy=False,
                error="Timeout"
            ),
            ServiceCoordinator.GONDOLIN: ServiceHealth(
                service=ServiceCoordinator.GONDOLIN,
                healthy=False,
                error="Connection refused"
            ),
        }

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_health_check_coordinator_error(self, client, mock_coordinator):
        """Test GET /health when coordinator raises error."""
        mock_coordinator.check_all_health.side_effect = Exception("Test error")

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "error" in data


# =============================================================================
# Agent Routes Tests
# =============================================================================

class TestAgentRoutes:
    """Test agent management routes."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = AsyncMock(spec=ServiceCoordinator)
        coordinator.check_all_health.return_value = {
            s: ServiceHealth(service=s, healthy=True)
            for s in [ServiceCoordinator.TINYCLAW, ServiceCoordinator.MEMU, ServiceCoordinator.GONDOLIN]
        }
        return coordinator

    @pytest.fixture
    def test_app(self, mock_coordinator):
        """Create a test app with mocked coordinator."""
        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the app."""
        return TestClient(test_app)

    def test_list_agents(self, client, mock_coordinator):
        """Test GET /api/agents."""
        mock_coordinator.request_tinyclaw.return_value = {
            "agents": [
                {
                    "agent_id": "agent-001",
                    "name": "TestAgent",
                    "status": "active"
                }
            ],
            "total": 1
        }

        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "TestAgent"

    def test_list_agents_with_filters(self, client, mock_coordinator):
        """Test GET /api/agents with query parameters."""
        mock_coordinator.request_tinyclaw.return_value = {"agents": [], "total": 0}

        response = client.get("/api/agents?status=active&team_id=team-001&limit=50&offset=10")
        assert response.status_code == 200

        # Verify params were passed
        call_args = mock_coordinator.request_tinyclaw.call_args
        assert "params" in call_args.kwargs
        assert call_args.kwargs["params"]["status"] == "active"
        assert call_args.kwargs["params"]["team_id"] == "team-001"
        assert call_args.kwargs["params"]["limit"] == 50
        assert call_args.kwargs["params"]["offset"] == 10

    def test_list_agents_invalid_limit(self, client, mock_coordinator):
        """Test GET /api/agents with invalid limit."""
        response = client.get("/api/agents?limit=2000")
        assert response.status_code == 400
        data = response.json()
        assert "Limit must be between 1 and 1000" in data["detail"]["message"]

    def test_list_agents_invalid_offset(self, client, mock_coordinator):
        """Test GET /api/agents with invalid offset."""
        response = client.get("/api/agents?offset=-1")
        assert response.status_code == 400
        data = response.json()
        assert "Offset must be non-negative" in data["detail"]["message"]

    def test_create_agent(self, client, mock_coordinator):
        """Test POST /api/agents."""
        mock_coordinator.request_tinyclaw.return_value = {
            "agent_id": "agent-001",
            "name": "NewAgent",
            "status": "inactive",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        request_data = {
            "name": "NewAgent",
            "description": "A new test agent"
        }

        response = client.post("/api/agents", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == "agent-001"
        assert data["name"] == "NewAgent"

    def test_create_agent_empty_name(self, client, mock_coordinator):
        """Test POST /api/agents with empty name."""
        request_data = {
            "name": "   ",
            "description": "Test"
        }

        response = client.post("/api/agents", json=request_data)
        assert response.status_code == 400

    def test_get_agent(self, client, mock_coordinator):
        """Test GET /api/agents/{agent_id}."""
        mock_coordinator.request_tinyclaw.return_value = {
            "agent_id": "agent-001",
            "name": "TestAgent",
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = client.get("/api/agents/agent-001")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-001"
        assert data["name"] == "TestAgent"

    def test_get_agent_not_found(self, client, mock_coordinator):
        """Test GET /api/agents/{agent_id} when agent not found."""
        mock_coordinator.request_tinyclaw.side_effect = IntegrationError(
            "Agent not found",
            details={"status_code": 404}
        )

        response = client.get("/api/agents/agent-999")
        assert response.status_code == 404

    def test_delete_agent(self, client, mock_coordinator):
        """Test DELETE /api/agents/{agent_id}."""
        mock_coordinator.request_tinyclaw.return_value = {}

        response = client.delete("/api/agents/agent-001")
        assert response.status_code == 204
        assert response.content == b""

    def test_delete_agent_not_found(self, client, mock_coordinator):
        """Test DELETE /api/agents/{agent_id} when agent not found."""
        mock_coordinator.request_tinyclaw.side_effect = IntegrationError(
            "Agent not found",
            details={"status_code": 404}
        )

        response = client.delete("/api/agents/agent-999")
        assert response.status_code == 404

    def test_send_message(self, client, mock_coordinator):
        """Test POST /api/agents/{agent_id}/message."""
        mock_coordinator.request_tinyclaw.return_value = {
            "message_id": "msg-001",
            "agent_id": "agent-001",
            "channel_id": "ch-123",
            "content": "Hello, world!",
            "status": "sent",
            "created_at": datetime.utcnow().isoformat()
        }

        request_data = {
            "channel_id": "ch-123",
            "content": "Hello, world!"
        }

        response = client.post("/api/agents/agent-001/message", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == "msg-001"
        assert data["content"] == "Hello, world!"

    def test_send_message_empty_content(self, client, mock_coordinator):
        """Test POST /api/agents/{agent_id}/message with empty content."""
        request_data = {
            "channel_id": "ch-123",
            "content": "   "
        }

        response = client.post("/api/agents/agent-001/message", json=request_data)
        assert response.status_code == 400


# =============================================================================
# Memory Routes Tests
# =============================================================================

class TestMemoryRoutes:
    """Test memory management routes."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = AsyncMock(spec=ServiceCoordinator)
        coordinator.check_all_health.return_value = {
            s: ServiceHealth(service=s, healthy=True)
            for s in [ServiceCoordinator.TINYCLAW, ServiceCoordinator.MEMU, ServiceCoordinator.GONDOLIN]
        }
        return coordinator

    @pytest.fixture
    def test_app(self, mock_coordinator):
        """Create a test app with mocked coordinator."""
        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the app."""
        return TestClient(test_app)

    def test_store_memory(self, client, mock_coordinator):
        """Test POST /api/memory/store."""
        mock_coordinator.request_memu.return_value = {
            "memory_id": "mem-001",
            "resource_url": "agent://agent-001/session/2026-03-01",
            "modality": "conversation",
            "user": "user-123",
            "content": {"text": "Test content"},
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        request_data = {
            "resource_url": "agent://agent-001/session/2026-03-01",
            "modality": "conversation",
            "user": "user-123",
            "content": {"text": "Test content"}
        }

        response = client.post("/api/memory/store", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["memory_id"] == "mem-001"
        assert data["user"] == "user-123"

    def test_store_memory_empty_resource_url(self, client, mock_coordinator):
        """Test POST /api/memory/store with empty resource_url."""
        request_data = {
            "resource_url": "   ",
            "modality": "conversation",
            "user": "user-123",
            "content": "Test"
        }

        response = client.post("/api/memory/store", json=request_data)
        assert response.status_code == 400

    def test_store_memory_empty_user(self, client, mock_coordinator):
        """Test POST /api/memory/store with empty user."""
        request_data = {
            "resource_url": "agent://agent-001/session/2026-03-01",
            "modality": "conversation",
            "user": "   ",
            "content": "Test"
        }

        response = client.post("/api/memory/store", json=request_data)
        assert response.status_code == 400

    def test_retrieve_memories(self, client, mock_coordinator):
        """Test POST /api/memory/retrieve."""
        mock_coordinator.request_memu.return_value = {
            "results": [
                {
                    "memory": {
                        "memory_id": "mem-001",
                        "content": "Test memory"
                    },
                    "score": 0.95
                }
            ],
            "total": 1,
            "method": "rag"
        }

        request_data = {
            "queries": ["What did the user ask about Python?"],
            "method": "rag",
            "limit": 10
        }

        response = client.post("/api/memory/retrieve", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1

    def test_retrieve_memories_empty_queries(self, client, mock_coordinator):
        """Test POST /api/memory/retrieve with empty queries."""
        request_data = {
            "queries": [],
            "method": "rag"
        }

        response = client.post("/api/memory/retrieve", json=request_data)
        assert response.status_code == 400

    def test_retrieve_memories_invalid_limit(self, client, mock_coordinator):
        """Test POST /api/memory/retrieve with invalid limit."""
        request_data = {
            "queries": ["Test query"],
            "limit": 200
        }

        response = client.post("/api/memory/retrieve", json=request_data)
        assert response.status_code == 400

    def test_list_agent_memories(self, client, mock_coordinator):
        """Test GET /api/memory/{agent_id}."""
        mock_coordinator.request_memu.return_value = {
            "memories": [
                {
                    "memory_id": "mem-001",
                    "content": "Test memory",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            ],
            "total": 1
        }

        response = client.get("/api/memory/agent-001?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["memories"]) == 1

    def test_list_agent_memories_empty_agent_id(self, client, mock_coordinator):
        """Test GET /api/memory/{agent_id} with empty agent_id."""
        response = client.get("/api/memory/   ?limit=50")
        assert response.status_code == 400

    def test_list_agent_memories_invalid_limit(self, client, mock_coordinator):
        """Test GET /api/memory/{agent_id} with invalid limit."""
        response = client.get("/api/memory/agent-001?limit=2000")
        assert response.status_code == 400

    def test_list_agent_memories_not_found(self, client, mock_coordinator):
        """Test GET /api/memory/{agent_id} when agent not found."""
        mock_coordinator.request_memu.side_effect = IntegrationError(
            "Agent not found",
            details={"status_code": 404}
        )

        response = client.get("/api/memory/agent-999")
        assert response.status_code == 404


# =============================================================================
# Execution Routes Tests
# =============================================================================

class TestExecutionRoutes:
    """Test code execution routes."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = AsyncMock(spec=ServiceCoordinator)
        coordinator.check_all_health.return_value = {
            s: ServiceHealth(service=s, healthy=True)
            for s in [ServiceCoordinator.TINYCLAW, ServiceCoordinator.MEMU, ServiceCoordinator.GONDOLIN]
        }
        return coordinator

    @pytest.fixture
    def test_app(self, mock_coordinator):
        """Create a test app with mocked coordinator."""
        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the app."""
        return TestClient(test_app)

    def test_execute_code(self, client, mock_coordinator):
        """Test POST /api/execute."""
        task_id = str(uuid4())
        mock_coordinator.request_gondolin.return_value = {
            "task_id": task_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }

        request_data = {
            "code": "print('Hello, World!')",
            "language": "python",
            "timeout": 30
        }

        response = client.post("/api/execute", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending"

    def test_execute_code_empty_code(self, client, mock_coordinator):
        """Test POST /api/execute with empty code."""
        request_data = {
            "code": "   ",
            "language": "python"
        }

        response = client.post("/api/execute", json=request_data)
        assert response.status_code == 400

    def test_execute_code_invalid_timeout(self, client, mock_coordinator):
        """Test POST /api/execute with invalid timeout."""
        request_data = {
            "code": "print('test')",
            "timeout": 500  # Exceeds max of 300
        }

        response = client.post("/api/execute", json=request_data)
        assert response.status_code == 400

    def test_get_execution_status(self, client, mock_coordinator):
        """Test GET /api/execute/{task_id}."""
        mock_coordinator.request_gondolin.return_value = {
            "task_id": "task-123",
            "status": "completed",
            "language": "python",
            "stdout": "Hello, World!\n",
            "stderr": "",
            "exit_code": 0,
            "created_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat()
        }

        response = client.get("/api/execute/task-123")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
        assert data["status"] == "completed"
        assert data["exit_code"] == 0

    def test_get_execution_status_empty_task_id(self, client, mock_coordinator):
        """Test GET /api/execute/{task_id} with empty task_id."""
        response = client.get("/api/execute/   ")
        assert response.status_code == 400

    def test_get_execution_status_not_found(self, client, mock_coordinator):
        """Test GET /api/execute/{task_id} when task not found."""
        mock_coordinator.request_gondolin.side_effect = IntegrationError(
            "Task not found",
            details={"status_code": 404}
        )

        response = client.get("/api/execute/task-999")
        assert response.status_code == 404


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in orchestration layer."""

    def test_integration_error_to_dict(self):
        """Test IntegrationError conversion to dict."""
        error = IntegrationError(
            "Service unavailable",
            details={"service": "tinyclaw"}
        )
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "IntegrationError"
        assert error_dict["message"] == "Service unavailable"
        assert error_dict["service"] == "tinyclaw"

    def test_validation_error_to_dict(self):
        """Test ValidationError conversion to dict."""
        error = ValidationError("Invalid input", details={"field": "agent_id"})
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "ValidationError"
        assert error_dict["message"] == "Invalid input"
        assert error_dict["field"] == "agent_id"

    def test_not_found_error_to_dict(self):
        """Test NotFoundError conversion to dict."""
        error = NotFoundError("Agent not found")
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "NotFoundError"
        assert error_dict["message"] == "Agent not found"

    @pytest.mark.asyncio
    async def test_coordinator_request_all_retries_failed(self):
        """Test request when all retries fail."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()

        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_client.request.side_effect = httpx.ConnectError("Connection refused")

        with patch('asyncio.sleep'):  # Skip sleep delays
            with pytest.raises(IntegrationError, match="Failed to reach tinyclaw after 3 attempts"):
                await coordinator._make_request(
                    ServiceCoordinator.TINYCLAW,
                    "GET",
                    "/test"
                )

        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_coordinator_request_with_timeout(self):
        """Test request with timeout exception."""
        coordinator = ServiceCoordinator()
        await coordinator.initialize()

        mock_client = coordinator._clients[ServiceCoordinator.TINYCLAW]
        mock_client.request.side_effect = httpx.TimeoutException("Request timeout")

        with patch('asyncio.sleep'):  # Skip sleep delays
            with pytest.raises(IntegrationError, match="Failed to reach tinyclaw after 3 attempts"):
                await coordinator._make_request(
                    ServiceCoordinator.TINYCLAW,
                    "GET",
                    "/test"
                )

        await coordinator.shutdown()


# =============================================================================
# Model Validation Tests
# =============================================================================

class TestRequestModels:
    """Test request/response model validation."""

    def test_store_memory_request_api_validation(self):
        """Test StoreMemoryRequestAPI model validation."""
        from src.orchestration.routes.memory import StoreMemoryRequestAPI

        # Valid request
        request = StoreMemoryRequestAPI(
            resource_url="agent://agent-001/session/2026-03-01",
            modality="conversation",
            user="user-123",
            content="Test content"
        )
        assert request.resource_url == "agent://agent-001/session/2026-03-01"
        assert request.auto_categorize is True

    def test_retrieve_memory_request_api_validation(self):
        """Test RetrieveMemoryRequestAPI model validation."""
        from src.orchestration.routes.memory import RetrieveMemoryRequestAPI

        # Valid request
        request = RetrieveMemoryRequestAPI(
            queries=["What did the user ask?"],
            method="rag",
            limit=10
        )
        assert len(request.queries) == 1
        assert request.method == "rag"
        assert request.threshold is None

    def test_execute_code_request_validation(self):
        """Test ExecuteCodeRequest model validation."""
        from src.orchestration.routes.execution import ExecuteCodeRequest

        # Valid request
        request = ExecuteCodeRequest(
            code="print('test')",
            language="python",
            timeout=30
        )
        assert request.code == "print('test')"
        assert request.allowed_hosts == []
        assert request.agent_id is None

    def test_create_agent_request_api_validation(self):
        """Test CreateAgentRequestAPI model validation."""
        from src.orchestration.routes.agents import CreateAgentRequestAPI

        # Valid request
        request = CreateAgentRequestAPI(
            name="TestAgent",
            description="A test agent",
            channels=["ch-123"]
        )
        assert request.name == "TestAgent"
        assert request.capabilities == []

    def test_send_message_request_api_validation(self):
        """Test SendMessageRequestAPI model validation."""
        from src.orchestration.routes.agents import SendMessageRequestAPI

        # Valid request
        request = SendMessageRequestAPI(
            channel_id="ch-123",
            content="Hello, world!",
            metadata={"priority": "high"}
        )
        assert request.channel_id == "ch-123"
        assert request.parent_message_id is None
