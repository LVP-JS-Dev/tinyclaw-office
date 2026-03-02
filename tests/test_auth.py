"""
End-to-end authentication flow tests.

This module contains comprehensive tests for authentication flow across all services,
testing the verify_api_key dependency integration with protected endpoints.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.orchestration.api import app, get_coordinator
from src.orchestration.coordinator import ServiceCoordinator


# =============================================================================
# End-to-End Authentication Flow Tests
# =============================================================================

class TestAuthenticationFlowE2E:
    """
    Test authentication flow end-to-end across protected endpoints.

    Tests cover:
    1. Accessing protected endpoint without API key - expect 401
    2. Accessing protected endpoint with invalid API key - expect 401
    3. Accessing protected endpoint with valid API key - expect success
    """

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock ServiceCoordinator."""
        coordinator = AsyncMock(spec=ServiceCoordinator)
        # Mock health check to return healthy status
        coordinator.check_all_health.return_value = {
            "tinyclaw": MagicMock(healthy=True, response_time_ms=10, error=None),
            "memu": MagicMock(healthy=True, response_time_ms=10, error=None),
            "gondolin": MagicMock(healthy=True, response_time_ms=10, error=None),
        }
        # Mock list_agents to return empty list
        coordinator.request_tinyclaw.return_value = {"agents": [], "total": 0}
        return coordinator

    @pytest.fixture
    def test_app_with_mock_coordinator(self, mock_coordinator):
        """
        Create a test app with mocked coordinator and valid SECRET_KEY.

        This fixture sets up the FastAPI app with:
        1. A mocked coordinator that doesn't require actual services
        2. A valid SECRET_KEY environment variable for authentication testing
        """
        # Set a valid SECRET_KEY for testing (must be >= 32 characters)
        os.environ["SECRET_KEY"] = "test-secret-key-for-authentication-testing-32chars-min"

        # Override the get_coordinator dependency
        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator
        yield app
        app.dependency_overrides.clear()

        # Clean up environment
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]

    @pytest.fixture
    def client(self, test_app_with_mock_coordinator):
        """Create a test client for the app."""
        return TestClient(test_app_with_mock_coordinator)

    def test_protected_endpoint_without_api_key_returns_401(self, client):
        """
        Test: Call endpoint without API key - expect 401.

        This test verifies that protected endpoints reject requests that
        don't include the X-API-Key header.
        """
        response = client.get("/api/agents")

        # Should return 401 Unauthorized
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Verify error response structure
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], dict)
        assert data["detail"]["message"] == "Invalid API key"
        assert data["detail"]["error_type"] == "AuthenticationError"

    def test_protected_endpoint_with_invalid_api_key_returns_401(self, client):
        """
        Test: Call endpoint with invalid API key - expect 401.

        This test verifies that protected endpoints reject requests that
        include an incorrect X-API-Key header value.
        """
        invalid_api_key = "invalid-api-key-that-does-not-match"
        headers = {"X-API-Key": invalid_api_key}

        response = client.get("/api/agents", headers=headers)

        # Should return 401 Unauthorized
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Verify error response structure
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], dict)
        assert data["detail"]["message"] == "Invalid API key"
        assert data["detail"]["error_type"] == "AuthenticationError"

    def test_protected_endpoint_with_valid_api_key_succeeds(self, client, mock_coordinator):
        """
        Test: Call endpoint with valid API key - expect success.

        This test verifies that protected endpoints accept requests that
        include the correct X-API-Key header value.
        """
        valid_api_key = "test-secret-key-for-authentication-testing-32chars-min"
        headers = {"X-API-Key": valid_api_key}

        response = client.get("/api/agents", headers=headers)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        # Verify response structure
        data = response.json()
        assert "agents" in data
        assert "total" in data
        assert data["agents"] == []
        assert data["total"] == 0

        # Verify the coordinator was called (meaning auth passed)
        mock_coordinator.request_tinyclaw.assert_called_once()

    def test_multiple_protected_endpoints_require_authentication(self, client):
        """
        Test that all protected endpoints require authentication.

        This test verifies that authentication is enforced across multiple
        protected endpoints in the orchestration API.
        """
        # Test various protected endpoints without auth
        endpoints = [
            ("GET", "/api/agents"),
            ("GET", "/api/agents/agent-001"),
            ("POST", "/api/agents"),
            ("DELETE", "/api/agents/agent-001"),
            ("GET", "/api/memories"),
            ("POST", "/api/memories"),
        ]

        for method, path in endpoints:
            if method == "GET":
                response = client.get(path)
            elif method == "POST":
                response = client.post(path, json={})
            elif method == "DELETE":
                response = client.delete(path)

            # All should return 401 without authentication
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Endpoint {method} {path} should require authentication"
            )

    def test_health_endpoint_works_without_authentication(self, client, mock_coordinator):
        """
        Test that the health check endpoint works without authentication.

        The /health endpoint uses verify_api_key_optional which allows
        anonymous access for monitoring and health checks.
        """
        response = client.get("/health")

        # Should return 200 OK even without X-API-Key header
        assert response.status_code == status.HTTP_200_OK

        # Verify response structure
        data = response.json()
        assert "status" in data
        assert "service" in data

    def test_root_endpoint_works_without_authentication(self, client):
        """
        Test that the root endpoint works without authentication.

        The root endpoint (/) returns API information and doesn't require
        authentication.
        """
        response = client.get("/")

        # Should return 200 OK without X-API-Key header
        assert response.status_code == status.HTTP_200_OK

        # Verify response structure
        data = response.json()
        assert "name" in data
        assert "version" in data


# =============================================================================
# Authentication Error Response Tests
# =============================================================================

class TestAuthenticationErrorResponses:
    """
    Test the structure and content of authentication error responses.

    These tests ensure that authentication errors are returned in a consistent,
        structured format that clients can parse and handle appropriately.
    """

    @pytest.fixture
    def client_with_invalid_secret_key(self):
        """
        Create a test client with weak/placeholder SECRET_KEY.

        This simulates a misconfigured server where SECRET_KEY is not
        properly set, which should return a 500 error instead of 401.
        """
        # Set a weak/placeholder SECRET_KEY
        os.environ["SECRET_KEY"] = "change-this-in-production"

        # Mock coordinator to avoid initialization errors
        mock_coordinator = AsyncMock(spec=ServiceCoordinator)

        def override_get_coordinator():
            return mock_coordinator

        app.dependency_overrides[get_coordinator] = override_get_coordinator

        yield TestClient(app)

        app.dependency_overrides.clear()
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]

    def test_misconfigured_server_returns_500_not_401(self, client_with_invalid_secret_key):
        """
        Test that a misconfigured server (weak SECRET_KEY) returns 500.

        When SECRET_KEY is set to a weak placeholder value, the server
        should return 500 Internal Server Error instead of 401 Unauthorized,
        as this indicates a configuration problem, not an authentication failure.
        """
        headers = {"X-API-Key": "any-key"}

        response = client_with_invalid_secret_key.get("/api/agents", headers=headers)

        # Should return 500 Internal Server Error
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify error response structure
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], dict)
        assert data["detail"]["message"] == "Server not configured properly"
        assert data["detail"]["error_type"] == "ConfigurationError"


# =============================================================================
# Integration Service Authentication Tests
# ==============================================================================

class TestIntegrationServiceAuthentication:
    """
    Test that authentication is properly enforced across all services.

    These tests verify that the authentication middleware is correctly
    integrated into all integration services (TinyClaw, MemU, Gondolin).
    """

    def test_tinyclaw_service_endpoints_protected(self):
        """Verify that TinyClaw service endpoints are protected by authentication."""
        # This test would require importing the TinyClaw service app
        # and verifying that its endpoints require authentication.
        # Skipping for now as it would require additional setup.
        pytest.skip("Requires TinyClaw service app setup")

    def test_memu_service_endpoints_protected(self):
        """Verify that MemU service endpoints are protected by authentication."""
        # This test would require importing the MemU service app
        # and verifying that its endpoints require authentication.
        # Skipping for now as it would require additional setup.
        pytest.skip("Requires MemU service app setup")

    def test_gondolin_service_endpoints_protected(self):
        """Verify that Gondolin service endpoints are protected by authentication."""
        # This test would require importing the Gondolin service app
        # and verifying that its endpoints require authentication.
        # Skipping for now as it would require additional setup.
        pytest.skip("Requires Gondolin service app setup")
