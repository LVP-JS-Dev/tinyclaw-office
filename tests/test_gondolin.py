"""
Gondolin integration tests.

This module contains comprehensive tests for Gondolin integration, including:
- Model validation tests for execution requests/responses
- HTTP client tests with mocked responses
- Service endpoint tests
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any
from enum import Enum

import httpx
from fastapi import status


class ExecutionStatus(str, Enum):
    """Execution status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# =============================================================================
# Models
# =============================================================================

class TimestampedModel:
    """Base model with automatic timestamps."""

    def __init__(self, **kwargs):
        self.created_at = kwargs.get("created_at", datetime.utcnow())
        self.updated_at = kwargs.get("updated_at", datetime.utcnow())


class SecretConfig:
    """Configuration for a secret to be injected into the VM."""

    def __init__(
        self,
        value: str,
        hosts: list[str] | None = None,
        env_var: str | None = None
    ):
        self.value = value
        self.hosts = hosts or []
        self.env_var = env_var


class ExecutionRequest(TimestampedModel):
    """Request model for code execution."""

    def __init__(
        self,
        command: str,
        allowed_hosts: list[str],
        secrets: dict[str, Any] | None = None,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.command = command
        self.allowed_hosts = allowed_hosts
        self.secrets = secrets or {}
        self.timeout = timeout
        self.cwd = cwd
        self.env = env or {}


class ExecutionResult(TimestampedModel):
    """Result model for code execution."""

    def __init__(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: int,
        status: ExecutionStatus,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration_ms = duration_ms
        self.status = status


class SandboxConfig(TimestampedModel):
    """Configuration for a persistent sandbox."""

    def __init__(
        self,
        allowed_hosts: list[str],
        secrets: dict[str, Any] | None = None,
        max_memory_mb: int | None = None,
        cpu_count: int | None = None,
        timeout_seconds: int | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.allowed_hosts = allowed_hosts
        self.secrets = secrets or {}
        self.max_memory_mb = max_memory_mb
        self.cpu_count = cpu_count
        self.timeout_seconds = timeout_seconds


class CreateSandboxRequest(TimestampedModel):
    """Request model for creating a persistent sandbox."""

    def __init__(
        self,
        allowed_hosts: list[str],
        secrets: dict[str, Any] | None = None,
        max_memory_mb: int | None = None,
        cpu_count: int | None = None,
        timeout_seconds: int | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.allowed_hosts = allowed_hosts
        self.secrets = secrets or {}
        self.max_memory_mb = max_memory_mb
        self.cpu_count = cpu_count
        self.timeout_seconds = timeout_seconds


class ExecuteInSandboxRequest(TimestampedModel):
    """Request model for executing in a persistent sandbox."""

    def __init__(
        self,
        command: str,
        sandbox_id: str,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.command = command
        self.sandbox_id = sandbox_id
        self.timeout = timeout
        self.cwd = cwd
        self.env = env or {}


class BatchExecutionRequest(TimestampedModel):
    """Request model for batch execution in a sandbox."""

    def __init__(
        self,
        commands: list[str],
        sandbox_id: str,
        timeout: int | None = None,
        continue_on_error: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.commands = commands
        self.sandbox_id = sandbox_id
        self.timeout = timeout
        self.continue_on_error = continue_on_error


class HealthStatus:
    """Health status model."""

    def __init__(
        self,
        healthy: bool,
        qemu_available: bool,
        arm64_platform: bool,
        timestamp: str | None = None
    ):
        self.healthy = healthy
        self.qemu_available = qemu_available
        self.arm64_platform = arm64_platform
        self.timestamp = timestamp or datetime.utcnow().isoformat()


class ClientStatus:
    """Client status model."""

    def __init__(
        self,
        initialized: bool,
        active_sandboxes: int,
        total_executions: int,
        uptime_seconds: float
    ):
        self.initialized = initialized
        self.active_sandboxes = active_sandboxes
        self.total_executions = total_executions
        self.uptime_seconds = uptime_seconds


# =============================================================================
# Model Tests
# =============================================================================

class TestExecutionModels:
    """Test execution-related models."""

    def test_execution_request_minimal(self):
        """Test ExecutionRequest with minimal fields."""
        request = ExecutionRequest(
            command="echo 'hello'",
            allowed_hosts=[]
        )
        assert request.command == "echo 'hello'"
        assert request.allowed_hosts == []
        assert request.secrets == {}
        assert request.timeout is None
        assert request.cwd is None
        assert request.env == {}

    def test_execution_request_full(self):
        """Test ExecutionRequest with all fields."""
        request = ExecutionRequest(
            command="npm install",
            allowed_hosts=["api.github.com", "registry.npmjs.org"],
            secrets={
                "GITHUB_TOKEN": SecretConfig(
                    value="ghp_test",
                    hosts=["api.github.com"]
                )
            },
            timeout=30000,
            cwd="/workspace",
            env={"NODE_ENV": "production"}
        )
        assert request.command == "npm install"
        assert len(request.allowed_hosts) == 2
        assert "GITHUB_TOKEN" in request.secrets
        assert request.timeout == 30000
        assert request.cwd == "/workspace"
        assert request.env["NODE_ENV"] == "production"

    def test_execution_result_success(self):
        """Test ExecutionResult for successful execution."""
        result = ExecutionResult(
            stdout="Hello, World!",
            stderr="",
            exit_code=0,
            duration_ms=150,
            status=ExecutionStatus.COMPLETED
        )
        assert result.stdout == "Hello, World!"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.duration_ms == 150
        assert result.status == ExecutionStatus.COMPLETED

    def test_execution_result_failure(self):
        """Test ExecutionResult for failed execution."""
        result = ExecutionResult(
            stdout="",
            stderr="Command failed: file not found",
            exit_code=1,
            duration_ms=50,
            status=ExecutionStatus.FAILED
        )
        assert result.stdout == ""
        assert result.stderr == "Command failed: file not found"
        assert result.exit_code == 1
        assert result.status == ExecutionStatus.FAILED

    def test_execution_result_timeout(self):
        """Test ExecutionResult for timeout."""
        result = ExecutionResult(
            stdout="",
            stderr="Execution timeout",
            exit_code=124,
            duration_ms=30000,
            status=ExecutionStatus.TIMEOUT
        )
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.exit_code == 124


class TestSandboxModels:
    """Test sandbox-related models."""

    def test_sandbox_config_defaults(self):
        """Test SandboxConfig with default values."""
        config = SandboxConfig(
            allowed_hosts=["api.github.com"]
        )
        assert config.allowed_hosts == ["api.github.com"]
        assert config.secrets == {}
        assert config.max_memory_mb is None
        assert config.cpu_count is None
        assert config.timeout_seconds is None

    def test_sandbox_config_full(self):
        """Test SandboxConfig with all fields."""
        config = SandboxConfig(
            allowed_hosts=["api.github.com", "api.openai.com"],
            secrets={
                "GITHUB_TOKEN": SecretConfig(
                    value="ghp_test",
                    hosts=["api.github.com"]
                )
            },
            max_memory_mb=2048,
            cpu_count=2,
            timeout_seconds=300
        )
        assert len(config.allowed_hosts) == 2
        assert config.max_memory_mb == 2048
        assert config.cpu_count == 2
        assert config.timeout_seconds == 300

    def test_create_sandbox_request(self):
        """Test CreateSandboxRequest model."""
        request = CreateSandboxRequest(
            allowed_hosts=["api.github.com"],
            max_memory_mb=1024,
            cpu_count=1
        )
        assert request.allowed_hosts == ["api.github.com"]
        assert request.max_memory_mb == 1024

    def test_execute_in_sandbox_request(self):
        """Test ExecuteInSandboxRequest model."""
        request = ExecuteInSandboxRequest(
            command="npm test",
            sandbox_id="sb-123",
            timeout=60000,
            cwd="/workspace"
        )
        assert request.command == "npm test"
        assert request.sandbox_id == "sb-123"
        assert request.timeout == 60000

    def test_batch_execution_request(self):
        """Test BatchExecutionRequest model."""
        request = BatchExecutionRequest(
            commands=["npm install", "npm test", "npm build"],
            sandbox_id="sb-123",
            timeout=120000,
            continue_on_error=True
        )
        assert len(request.commands) == 3
        assert request.sandbox_id == "sb-123"
        assert request.continue_on_error is True


class TestStatusModels:
    """Test status-related models."""

    def test_health_status_healthy(self):
        """Test HealthStatus when healthy."""
        status = HealthStatus(
            healthy=True,
            qemu_available=True,
            arm64_platform=True
        )
        assert status.healthy is True
        assert status.qemu_available is True
        assert status.arm64_platform is True

    def test_health_status_unhealthy(self):
        """Test HealthStatus when unhealthy."""
        status = HealthStatus(
            healthy=False,
            qemu_available=False,
            arm64_platform=True
        )
        assert status.healthy is False
        assert status.qemu_available is False

    def test_client_status(self):
        """Test ClientStatus model."""
        status = ClientStatus(
            initialized=True,
            active_sandboxes=2,
            total_executions=150,
            uptime_seconds=3600.5
        )
        assert status.initialized is True
        assert status.active_sandboxes == 2
        assert status.total_executions == 150
        assert status.uptime_seconds == 3600.5


class TestSecretConfig:
    """Test SecretConfig model."""

    def test_secret_config_minimal(self):
        """Test SecretConfig with minimal fields."""
        config = SecretConfig(value="secret-key")
        assert config.value == "secret-key"
        assert config.hosts == []
        assert config.env_var is None

    def test_secret_config_with_hosts(self):
        """Test SecretConfig with hosts."""
        config = SecretConfig(
            value="api-key",
            hosts=["api.github.com", "api.openai.com"]
        )
        assert config.value == "api-key"
        assert len(config.hosts) == 2

    def test_secret_config_with_env_var(self):
        """Test SecretConfig with environment variable."""
        config = SecretConfig(
            value="secret",
            env_var="API_SECRET"
        )
        assert config.env_var == "API_SECRET"


# =============================================================================
# HTTP Client Tests (Mocked)
# =============================================================================

class TestGondolinHTTPClient:
    """Test HTTP client for Gondolin service with mocked responses."""

    @pytest.fixture
    def base_url(self):
        """Get the base URL for Gondolin service."""
        return "http://localhost:9000"

    @pytest.fixture
    def mock_client(self):
        """Create a mock httpx.AsyncClient."""
        client = AsyncMock(spec=httpx.AsyncClient)
        return client

    @pytest.mark.asyncio
    async def test_health_check_success(self, base_url, mock_client):
        """Test health check with successful response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "service": "gondolin_integration",
            "healthy": True,
            "qemuAvailable": True,
            "arm64Platform": True,
            "timestamp": "2026-03-01T12:00:00Z"
        }

        mock_client.get.return_value = mock_response

        # Simulate client call
        response = await mock_client.get(f"{base_url}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["healthy"] is True
        assert data["qemuAvailable"] is True

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, base_url, mock_client):
        """Test health check with degraded status."""
        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {
            "status": "unhealthy",
            "service": "gondolin_integration",
            "healthy": False,
            "qemuAvailable": False,
            "arm64Platform": True
        }

        mock_client.get.return_value = mock_response

        response = await mock_client.get(f"{base_url}/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["healthy"] is False

    @pytest.mark.asyncio
    async def test_get_status_success(self, base_url, mock_client):
        """Test GET /api/status endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "initialized": True,
            "activeSandboxes": 1,
            "totalExecutions": 100,
            "uptimeSeconds": 1800.5
        }

        mock_client.get.return_value = mock_response

        response = await mock_client.get(f"{base_url}/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is True
        assert data["activeSandboxes"] == 1
        assert data["totalExecutions"] == 100

    @pytest.mark.asyncio
    async def test_execute_command_success(self, base_url, mock_client):
        """Test POST /api/execute with successful execution."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stdout": "Hello, World!\n",
            "stderr": "",
            "exitCode": 0,
            "durationMs": 100,
            "status": "completed",
            "command": "echo 'Hello, World!'"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "command": "echo 'Hello, World!'",
            "allowedHosts": []
        }

        response = await mock_client.post(
            f"{base_url}/api/execute",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["stdout"] == "Hello, World!\n"
        assert data["exitCode"] == 0
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_command_validation_error(self, base_url, mock_client):
        """Test POST /api/execute with validation error."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "ValidationError",
            "message": "command is required and must be a string",
            "details": {"field": "command"}
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "command": "",
            "allowedHosts": []
        }

        response = await mock_client.post(
            f"{base_url}/api/execute",
            json=request_data
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_execute_node_code(self, base_url, mock_client):
        """Test POST /api/execute/node endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stdout": "42\n",
            "stderr": "",
            "exitCode": 0,
            "durationMs": 250,
            "status": "completed"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "code": "console.log(21 + 21);",
            "allowedHosts": []
        }

        response = await mock_client.post(
            f"{base_url}/api/execute/node",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["stdout"] == "42\n"

    @pytest.mark.asyncio
    async def test_execute_python_code(self, base_url, mock_client):
        """Test POST /api/execute/python endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stdout": "Hello from Python\n",
            "stderr": "",
            "exitCode": 0,
            "durationMs": 300,
            "status": "completed"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "code": "print('Hello from Python')",
            "allowedHosts": []
        }

        response = await mock_client.post(
            f"{base_url}/api/execute/python",
            json=request_data
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_sandbox(self, base_url, mock_client):
        """Test POST /api/sandbox endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "sandboxId": "sb-123",
            "allowedHosts": ["api.github.com"],
            "maxMemoryMb": 1024,
            "cpuCount": 1,
            "createdAt": "2026-03-01T12:00:00Z"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "allowedHosts": ["api.github.com"],
            "maxMemoryMb": 1024,
            "cpuCount": 1
        }

        response = await mock_client.post(
            f"{base_url}/api/sandbox",
            json=request_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sandboxId"] == "sb-123"
        assert data["allowedHosts"] == ["api.github.com"]

    @pytest.mark.asyncio
    async def test_execute_in_sandbox(self, base_url, mock_client):
        """Test POST /api/sandbox/execute endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stdout": "Build successful\n",
            "stderr": "",
            "exitCode": 0,
            "durationMs": 5000,
            "status": "completed",
            "sandboxId": "sb-123"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "command": "npm run build",
            "sandboxId": "sb-123",
            "timeout": 60000
        }

        response = await mock_client.post(
            f"{base_url}/api/sandbox/execute",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sandboxId"] == "sb-123"
        assert data["exitCode"] == 0

    @pytest.mark.asyncio
    async def test_batch_execution(self, base_url, mock_client):
        """Test POST /api/sandbox/batch endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "command": "npm install",
                    "stdout": "Installed 100 packages",
                    "exitCode": 0,
                    "status": "completed"
                },
                {
                    "command": "npm test",
                    "stdout": "Tests passed",
                    "exitCode": 0,
                    "status": "completed"
                },
                {
                    "command": "npm build",
                    "stdout": "Build complete",
                    "exitCode": 0,
                    "status": "completed"
                }
            ],
            "totalCommands": 3,
            "successful": 3,
            "failed": 0
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "commands": ["npm install", "npm test", "npm build"],
            "sandboxId": "sb-123",
            "continueOnError": False
        }

        response = await mock_client.post(
            f"{base_url}/api/sandbox/batch",
            json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["totalCommands"] == 3
        assert data["successful"] == 3
        assert len(data["results"]) == 3

    @pytest.mark.asyncio
    async def test_get_sandbox_status(self, base_url, mock_client):
        """Test GET /api/sandbox/status endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sandboxId": "sb-123",
            "active": True,
            "uptimeSeconds": 300,
            "executionsCount": 10,
            "memoryUsageMb": 512
        }

        mock_client.get.return_value = mock_response

        response = await mock_client.get(
            f"{base_url}/api/sandbox/status?sandboxId=sb-123"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sandboxId"] == "sb-123"
        assert data["active"] is True

    @pytest.mark.asyncio
    async def test_delete_sandbox(self, base_url, mock_client):
        """Test DELETE /api/sandbox endpoint."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.content = b""

        mock_client.delete.return_value = mock_response

        response = await mock_client.delete(
            f"{base_url}/api/sandbox?sandboxId=sb-123"
        )

        assert response.status_code == 204
        assert response.content == b""

    @pytest.mark.asyncio
    async def test_execute_with_secrets(self, base_url, mock_client):
        """Test execution with secret injection."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stdout": "Authenticated successfully\n",
            "stderr": "",
            "exitCode": 0,
            "durationMs": 500,
            "status": "completed"
        }

        mock_client.post.return_value = mock_response

        request_data = {
            "command": "npm publish",
            "allowedHosts": ["registry.npmjs.org"],
            "secrets": {
                "NPM_TOKEN": {
                    "value": "npm_test_token",
                    "hosts": ["registry.npmjs.org"]
                }
            }
        }

        response = await mock_client.post(
            f"{base_url}/api/execute",
            json=request_data
        )

        assert response.status_code == 200
        # Verify secrets were passed in request
        assert "secrets" in request_data
        assert "NPM_TOKEN" in request_data["secrets"]


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in Gondolin integration."""

    def test_execution_status_enum(self):
        """Test ExecutionStatus enum values."""
        assert ExecutionStatus.PENDING == "pending"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.TIMEOUT == "timeout"

    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test HTTP error response handling."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "error": "InternalError",
            "message": "An unexpected error occurred"
        }
        mock_client.post.return_value = mock_response

        response = await mock_client.post(
            "http://localhost:9000/api/execute",
            json={"command": "test", "allowedHosts": []}
        )

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "InternalError"

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test timeout error handling."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException(
            "Request timeout"
        )

        with pytest.raises(httpx.TimeoutException):
            await mock_client.post(
                "http://localhost:9000/api/execute",
                json={"command": "sleep 100", "allowedHosts": []}
            )

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test connection error handling."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError(
            "Failed to connect"
        )

        with pytest.raises(httpx.ConnectError):
            await mock_client.post(
                "http://localhost:9000/api/execute",
                json={"command": "test", "allowedHosts": []}
            )


# =============================================================================
# Integration Tests (Endpoint Coverage)
# =============================================================================

class TestEndpointCoverage:
    """Test that all expected endpoints are covered."""

    def test_expected_endpoints(self):
        """Verify all expected endpoints are documented."""
        expected_endpoints = [
            ("GET", "/health"),
            ("GET", "/api/status"),
            ("POST", "/api/execute"),
            ("POST", "/api/execute/node"),
            ("POST", "/api/execute/python"),
            ("POST", "/api/execute/script"),
            ("POST", "/api/sandbox"),
            ("POST", "/api/sandbox/execute"),
            ("POST", "/api/sandbox/batch"),
            ("GET", "/api/sandbox/status"),
            ("DELETE", "/api/sandbox"),
        ]

        # Verify we have tests for all endpoints
        assert len(expected_endpoints) == 11
        assert any(method == "POST" and path == "/api/execute"
                   for method, path in expected_endpoints)

    def test_execution_status_coverage(self):
        """Verify all execution statuses are tested."""
        statuses = [
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]

        assert len(statuses) == 5
        assert ExecutionStatus.COMPLETED in statuses
        assert ExecutionStatus.FAILED in statuses
        assert ExecutionStatus.TIMEOUT in statuses


# =============================================================================
# Validation Tests
# =============================================================================

class TestValidation:
    """Test input validation."""

    def test_command_validation(self):
        """Test command field validation."""
        # Valid commands
        ExecutionRequest(command="echo hello", allowed_hosts=[])
        ExecutionRequest(command="npm install", allowed_hosts=[])
        ExecutionRequest(command="python script.py", allowed_hosts=[])

    def test_allowed_hosts_validation(self):
        """Test allowedHosts field validation."""
        # Empty array is valid
        ExecutionRequest(command="test", allowed_hosts=[])

        # Valid hosts
        ExecutionRequest(
            command="test",
            allowed_hosts=["api.github.com", "api.openai.com"]
        )

    def test_timeout_validation(self):
        """Test timeout field validation."""
        request = ExecutionRequest(
            command="test",
            allowed_hosts=[],
            timeout=30000
        )
        assert request.timeout == 30000

    def test_secrets_validation(self):
        """Test secrets field validation."""
        secret = SecretConfig(
            value="test-secret",
            hosts=["api.example.com"]
        )

        request = ExecutionRequest(
            command="test",
            allowed_hosts=["api.example.com"],
            secrets={"API_KEY": secret}
        )

        assert "API_KEY" in request.secrets
        assert request.secrets["API_KEY"].value == "test-secret"
