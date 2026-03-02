"""
Test endpoint path consistency across services.

This test module verifies that orchestration routes call the correct
endpoint paths on the integration services (TinyClaw, MemU, Gondolin).

The verification ensures that:
1. Orchestration /api/agents routes to TinyClaw /api/agents
2. Orchestration /api/memories routes to MemU /api/memories
3. Orchestration /api/execute routes to Gondolin /api/execute

This is critical for the orchestration layer to correctly proxy requests
to the underlying integration services.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import Request
from fastapi.testclient import TestClient

from src.orchestration.api import app
from src.orchestration.coordinator import ServiceCoordinator


class TestEndpointPathConsistency:
    """
    Test that orchestration routes use correct endpoint paths when calling
    integration services through the coordinator.
    """

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock service coordinator."""
        coordinator = Mock(spec=ServiceCoordinator)

        # Mock async methods
        coordinator.request_tinyclaw = AsyncMock()
        coordinator.request_memu = AsyncMock()
        coordinator.request_gondolin = AsyncMock()

        return coordinator

    @pytest.fixture
    def client(self, mock_coordinator):
        """Create a test client with mocked coordinator."""
        # Add coordinator to app state
        app.state.coordinator = mock_coordinator
        app.state.SECRET_KEY = "test-secret-key"

        return TestClient(app)

    # =========================================================================
    # TinyClaw Endpoint Path Tests
    # =========================================================================

    class TestTinyClawEndpointPaths:
        """Test that /api/agents routes correctly to TinyClaw service."""

        def test_list_agents_routes_to_tinyclaw(self, client, mock_coordinator):
            """Verify GET /api/agents calls TinyClaw /api/agents."""
            # Setup mock response
            mock_coordinator.request_tinyclaw.return_value = {
                "agents": [],
                "total": 0
            }

            # Make request
            response = client.get(
                "/api/agents",
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_tinyclaw.assert_called_once()
            call_args = mock_coordinator.request_tinyclaw.call_args

            # Check method and path
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/api/agents"

        def test_create_agent_routes_to_tinyclaw(self, client, mock_coordinator):
            """Verify POST /api/agents calls TinyClaw /api/agents."""
            # Setup mock response
            mock_coordinator.request_tinyclaw.return_value = {
                "agent_id": "agent-123",
                "name": "Test Agent",
                "status": "active"
            }

            # Make request
            response = client.post(
                "/api/agents",
                json={"name": "Test Agent"},
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_tinyclaw.assert_called_once()
            call_args = mock_coordinator.request_tinyclaw.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/agents"

        def test_get_agent_routes_to_tinyclaw(self, client, mock_coordinator):
            """Verify GET /api/agents/{id} calls TinyClaw /api/agents/{id}."""
            # Setup mock response
            mock_coordinator.request_tinyclaw.return_value = {
                "agent_id": "agent-123",
                "name": "Test Agent",
                "status": "active"
            }

            # Make request
            response = client.get(
                "/api/agents/agent-123",
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_tinyclaw.assert_called_once()
            call_args = mock_coordinator.request_tinyclaw.call_args

            # Check method and path
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/api/agents/agent-123"

        def test_delete_agent_routes_to_tinyclaw(self, client, mock_coordinator):
            """Verify DELETE /api/agents/{id} calls TinyClaw /api/agents/{id}."""
            # Setup mock response (204 No Content)
            mock_coordinator.request_tinyclaw.return_value = {}

            # Make request
            response = client.delete(
                "/api/agents/agent-123",
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_tinyclaw.assert_called_once()
            call_args = mock_coordinator.request_tinyclaw.call_args

            # Check method and path
            assert call_args[0][0] == "DELETE"
            assert call_args[0][1] == "/api/agents/agent-123"

        def test_send_message_routes_to_tinyclaw(self, client, mock_coordinator):
            """Verify POST /api/agents/{id}/message calls TinyClaw /api/agents/{id}/message."""
            # Setup mock response
            mock_coordinator.request_tinyclaw.return_value = {
                "message_id": "msg-456",
                "agent_id": "agent-123",
                "content": "Test message"
            }

            # Make request
            response = client.post(
                "/api/agents/agent-123/message",
                json={
                    "channel_id": "channel-789",
                    "content": "Test message"
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_tinyclaw.assert_called_once()
            call_args = mock_coordinator.request_tinyclaw.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/agents/agent-123/message"

    # =========================================================================
    # MemU Endpoint Path Tests
    # =========================================================================

    class TestMemUEndpointPaths:
        """Test that /api/memories routes correctly to MemU service."""

        def test_store_memory_routes_to_memu(self, client, mock_coordinator):
            """Verify POST /api/memories/store calls MemU /api/memories."""
            # Setup mock response
            mock_coordinator.request_memu.return_value = {
                "memory_id": "mem-123",
                "resource_url": "agent://test/123",
                "user": "user-1"
            }

            # Make request
            response = client.post(
                "/api/memories/store",
                json={
                    "resource_url": "agent://test/123",
                    "user": "user-1",
                    "content": "Test memory",
                    "modality": "text"
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_memu.assert_called_once()
            call_args = mock_coordinator.request_memu.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/memories"

        def test_retrieve_memories_routes_to_memu(self, client, mock_coordinator):
            """Verify POST /api/memories/retrieve calls MemU /api/memories/retrieve."""
            # Setup mock response
            mock_coordinator.request_memu.return_value = {
                "results": [],
                "total": 0,
                "method": "rag"
            }

            # Make request
            response = client.post(
                "/api/memories/retrieve",
                json={
                    "queries": ["test query"],
                    "limit": 10
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_memu.assert_called_once()
            call_args = mock_coordinator.request_memu.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/memories/retrieve"

        def test_list_agent_memories_routes_to_memu(self, client, mock_coordinator):
            """Verify GET /api/memories/{agent_id} calls MemU /api/memories."""
            # Setup mock response
            mock_coordinator.request_memu.return_value = {
                "memories": [],
                "total": 0
            }

            # Make request
            response = client.get(
                "/api/memories/agent-123",
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_memu.assert_called_once()
            call_args = mock_coordinator.request_memu.call_args

            # Check method and path
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/api/memories"

    # =========================================================================
    # Gondolin Endpoint Path Tests
    # =========================================================================

    class TestGondolinEndpointPaths:
        """Test that /api/execute routes correctly to Gondolin service."""

        def test_execute_python_routes_to_gondolin(self, client, mock_coordinator):
            """Verify POST /api/execute with Python calls Gondolin /api/execute/python."""
            # Setup mock response
            mock_coordinator.request_gondolin.return_value = {
                "result": {
                    "exitCode": 0,
                    "stdout": "Hello, World!",
                    "stderr": "",
                    "duration": 100
                }
            }

            # Make request
            response = client.post(
                "/api/execute",
                json={
                    "code": "print('Hello, World!')",
                    "language": "python",
                    "timeout": 30
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_gondolin.assert_called_once()
            call_args = mock_coordinator.request_gondolin.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/execute/python"

            # Verify payload structure
            payload = call_args[1]["json"]
            assert "code" in payload
            assert "allowedHosts" in payload
            assert "timeout" in payload
            assert "env" in payload
            # Timeout should be in milliseconds
            assert payload["timeout"] == 30000

        def test_execute_node_routes_to_gondolin(self, client, mock_coordinator):
            """Verify POST /api/execute with JavaScript calls Gondolin /api/execute/node."""
            # Setup mock response
            mock_coordinator.request_gondolin.return_value = {
                "result": {
                    "exitCode": 0,
                    "stdout": "Hello, World!",
                    "stderr": "",
                    "duration": 100
                }
            }

            # Make request
            response = client.post(
                "/api/execute",
                json={
                    "code": "console.log('Hello, World!');",
                    "language": "javascript",
                    "timeout": 30
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_gondolin.assert_called_once()
            call_args = mock_coordinator.request_gondolin.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/execute/node"

        def test_execute_bash_routes_to_gondolin(self, client, mock_coordinator):
            """Verify POST /api/execute with Bash calls Gondolin /api/execute/script."""
            # Setup mock response
            mock_coordinator.request_gondolin.return_value = {
                "result": {
                    "exitCode": 0,
                    "stdout": "Hello, World!",
                    "stderr": "",
                    "duration": 100
                }
            }

            # Make request
            response = client.post(
                "/api/execute",
                json={
                    "code": "echo 'Hello, World!'",
                    "language": "bash",
                    "timeout": 30
                },
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_gondolin.assert_called_once()
            call_args = mock_coordinator.request_gondolin.call_args

            # Check method and path
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/execute/script"

            # Verify payload uses 'script' instead of 'code'
            payload = call_args[1]["json"]
            assert "script" in payload
            assert payload["script"] == "echo 'Hello, World!'"

        def test_get_execution_status_routes_to_gondolin(self, client, mock_coordinator):
            """Verify GET /api/execute/{task_id} calls Gondolin /api/execute/{task_id}."""
            # Setup mock response
            mock_coordinator.request_gondolin.return_value = {
                "task_id": "task-123",
                "status": "completed",
                "language": "python",
                "stdout": "Hello, World!",
                "stderr": "",
                "exit_code": 0
            }

            # Make request
            response = client.get(
                "/api/execute/task-123",
                headers={"X-API-Key": "test-secret-key"}
            )

            # Verify call was made with correct path
            mock_coordinator.request_gondolin.assert_called_once()
            call_args = mock_coordinator.request_gondolin.call_args

            # Check method and path
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/api/execute/task-123"


class TestEndpointPathIntegration:
    """
    Integration tests for endpoint path consistency.

    These tests verify that the complete request flow works correctly
    from orchestration through to the integration services.

    NOTE: These tests require running integration services to execute.
    They are documented here for manual E2E verification.
    """

    # =========================================================================
    # Manual E2E Verification Instructions
    # =========================================================================

    """
    Manual E2E Verification Steps:

    1. Start all services:
       ```bash
       # Start infrastructure
       docker-compose up -d

       # Start TinyClaw service
       uvicorn src.tinyclaw_integration.service:app --port 8001

       # Start MemU service
       uvicorn src.memu_integration.service:app --port 8002

       # Start Gondolin service
       cd src/gondolin_integration && npm start

       # Start Orchestration service
       uvicorn src.orchestration.api:app --port 8080
       ```

    2. Test TinyClaw endpoints through orchestration:
       ```bash
       export SECRET_KEY="your-secret-key"

       # List agents - should route to TinyClaw /api/agents
       curl -H "X-API-Key: $SECRET_KEY" \
         http://localhost:8080/api/agents

       # Create agent - should route to TinyClaw /api/agents
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{"name": "Test Agent"}' \
         http://localhost:8080/api/agents

       # Get agent - should route to TinyClaw /api/agents/{id}
       curl -H "X-API-Key: $SECRET_KEY" \
         http://localhost:8080/api/agents/agent-123

       # Delete agent - should route to TinyClaw /api/agents/{id}
       curl -X DELETE -H "X-API-Key: $SECRET_KEY" \
         http://localhost:8080/api/agents/agent-123
       ```

    3. Test MemU endpoints through orchestration:
       ```bash
       # Store memory - should route to MemU /api/memories
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{
           "resource_url": "agent://test/123",
           "user": "user-1",
           "content": "Test memory",
           "modality": "text"
         }' \
         http://localhost:8080/api/memories/store

       # Retrieve memories - should route to MemU /api/memories/retrieve
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{"queries": ["test query"], "limit": 10}' \
         http://localhost:8080/api/memories/retrieve

       # List agent memories - should route to MemU /api/memories
       curl -H "X-API-Key: $SECRET_KEY" \
         http://localhost:8080/api/memories/agent-123
       ```

    4. Test Gondolin endpoints through orchestration:
       ```bash
       # Execute Python - should route to Gondolin /api/execute/python
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{"code": "print(42)", "language": "python"}' \
         http://localhost:8080/api/execute

       # Execute JavaScript - should route to Gondolin /api/execute/node
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{"code": "console.log(42)", "language": "javascript"}' \
         http://localhost:8080/api/execute

       # Execute Bash - should route to Gondolin /api/execute/script
       curl -X POST -H "X-API-Key: $SECRET_KEY" \
         -H "Content-Type: application/json" \
         -d '{"code": "echo 42", "language": "bash"}' \
         http://localhost:8080/api/execute
       ```

    Expected Results:
    - All requests should return 2xx status codes (not 404)
    - TinyClaw requests should route to service on port 8001
    - MemU requests should route to service on port 8002
    - Gondolin requests should route to service on port 9000
    - No routing errors or path mismatches in logs
    """


# Export test classes for pytest discovery
__all__ = [
    "TestEndpointPathConsistency",
    "TestEndpointPathIntegration"
]
