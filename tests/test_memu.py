"""
MemU integration tests.

This module contains comprehensive tests for MemU integration, including:
- Model validation tests
- Client API tests with mocked SDK responses
- Service endpoint tests
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from fastapi import status
from fastapi.testclient import TestClient

from src.memu_integration.models import (
    MemoryModality,
    RetrievalMethod,
    MemoryStatus,
    CategoryConfidence,
    TimestampedModel,
    MemoryMetadata,
    Memory,
    MemoryCategory,
    MemoryQuery,
    MemoryResult,
    MemoryListResponse,
    StoreMemoryRequest,
    RetrieveMemoryRequest,
    CategorizeMemoryRequest,
    CreateCategoryRequest,
    MemoryStats,
)
from src.memu_integration.client import MemUClient
from src.memu_integration.service import app, get_memu_client
from src.shared.errors import MemUError, ValidationError


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


class TestMemoryMetadata:
    """Test MemoryMetadata model."""

    def test_metadata_defaults(self):
        """Test MemoryMetadata with default values."""
        metadata = MemoryMetadata()
        assert metadata.source is None
        assert metadata.tags == []
        assert metadata.importance == 0.5
        assert metadata.access_count == 0
        assert metadata.last_accessed_at is None
        assert metadata.embedding_model is None
        assert metadata.extra == {}

    def test_metadata_with_values(self):
        """Test MemoryMetadata with explicit values."""
        metadata = MemoryMetadata(
            source="agent-001",
            tags=["python", "coding"],
            importance=0.8,
            access_count=5,
            embedding_model="text-embedding-3-small",
            extra={"custom_field": "value"}
        )
        assert metadata.source == "agent-001"
        assert metadata.tags == ["python", "coding"]
        assert metadata.importance == 0.8
        assert metadata.access_count == 5
        assert metadata.embedding_model == "text-embedding-3-small"
        assert metadata.extra == {"custom_field": "value"}

    def test_importance_validation(self):
        """Test importance bounds validation."""
        # Valid values
        MemoryMetadata(importance=0.0)
        MemoryMetadata(importance=0.5)
        MemoryMetadata(importance=1.0)

        # Invalid values should raise Pydantic validation error
        with pytest.raises(ValueError):
            MemoryMetadata(importance=-0.1)

        with pytest.raises(ValueError):
            MemoryMetadata(importance=1.1)


class TestMemoryModels:
    """Test memory-related models."""

    def test_memory_creation_minimal(self):
        """Test Memory creation with minimal required fields."""
        memory = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content={"conversation": "User requested help with Python"}
        )
        assert memory.memory_id == "mem-001"
        assert memory.resource_url == "agent://agent-001/session/2026-03-01"
        assert memory.modality == MemoryModality.CONVERSATION
        assert memory.user == "user-123"
        assert memory.agent is None
        assert memory.summary is None
        assert memory.categories == []
        assert memory.status == MemoryStatus.ACTIVE
        assert isinstance(memory.metadata, MemoryMetadata)

    def test_memory_creation_full(self):
        """Test Memory creation with all fields."""
        metadata = MemoryMetadata(
            source="agent-001",
            tags=["python", "help"],
            importance=0.8
        )
        memory = Memory(
            memory_id="mem-002",
            resource_url="agent://agent-002/session/2026-03-01",
            modality=MemoryModality.CODE,
            user="user-456",
            agent="agent-002",
            content={"code": "def hello(): print('world')"},
            summary="Python hello world function",
            categories=["coding", "python"],
            status=MemoryStatus.ACTIVE,
            metadata=metadata,
            vector_id="vec-123"
        )
        assert memory.memory_id == "mem-002"
        assert memory.modality == MemoryModality.CODE
        assert memory.agent == "agent-002"
        assert len(memory.categories) == 2
        assert memory.vector_id == "vec-123"
        assert memory.metadata.importance == 0.8

    def test_memory_validation_empty_memory_id(self):
        """Test that empty memory_id raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Memory(
                memory_id="   ",
                resource_url="agent://agent-001/session/2026-03-01",
                modality=MemoryModality.CONVERSATION,
                user="user-123",
                content="Test"
            )

    def test_memory_validation_empty_resource_url(self):
        """Test that empty resource_url raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Memory(
                memory_id="mem-001",
                resource_url="   ",
                modality=MemoryModality.CONVERSATION,
                user="user-123",
                content="Test"
            )

    def test_memory_validation_empty_user(self):
        """Test that empty user raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Memory(
                memory_id="mem-001",
                resource_url="agent://agent-001/session/2026-03-01",
                modality=MemoryModality.CONVERSATION,
                user="   ",
                content="Test"
            )


class TestMemoryCategoryModels:
    """Test memory category models."""

    def test_category_creation_minimal(self):
        """Test MemoryCategory creation with minimal fields."""
        category = MemoryCategory(
            category_id="cat-001",
            name="coding"
        )
        assert category.category_id == "cat-001"
        assert category.name == "coding"
        assert category.description is None
        assert category.parent_id is None
        assert category.confidence == CategoryConfidence.MEDIUM

    def test_category_creation_full(self):
        """Test MemoryCategory creation with all fields."""
        category = MemoryCategory(
            category_id="cat-002",
            name="python",
            description="Python programming related memories",
            parent_id="cat-001",
            confidence=CategoryConfidence.HIGH,
            color="#3498db",
            icon="python",
            metadata={"language": "python"}
        )
        assert category.category_id == "cat-002"
        assert category.description == "Python programming related memories"
        assert category.parent_id == "cat-001"
        assert category.confidence == CategoryConfidence.HIGH
        assert category.color == "#3498db"
        assert category.icon == "python"

    def test_category_validation_empty_name(self):
        """Test that empty category name raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            MemoryCategory(category_id="cat-001", name="   ")

    def test_category_validation_empty_category_id(self):
        """Test that empty category_id raises validation error."""
        with pytest.raises(ValueError, match="Field cannot be empty"):
            MemoryCategory(category_id="   ", name="coding")


class TestMemoryQueryModels:
    """Test memory query and result models."""

    def test_memory_query_defaults(self):
        """Test MemoryQuery with default values."""
        query = MemoryQuery(queries=["Python programming"])
        assert query.queries == ["Python programming"]
        assert query.where == {}
        assert query.method == RetrievalMethod.RAG
        assert query.limit == 10
        assert query.threshold is None
        assert query.time_range is None

    def test_memory_query_full(self):
        """Test MemoryQuery with all fields."""
        query = MemoryQuery(
            queries=["What did the user ask about Python?"],
            where={"user": "user-123", "agent": "agent-001"},
            method=RetrievalMethod.LLM,
            limit=20,
            threshold=0.7,
            time_range={"start": datetime(2026, 1, 1), "end": datetime(2026, 3, 1)}
        )
        assert len(query.queries) == 1
        assert query.method == RetrievalMethod.LLM
        assert query.limit == 20
        assert query.threshold == 0.7

    def test_memory_query_validation_empty_queries(self):
        """Test that empty queries list raises validation error."""
        with pytest.raises(ValueError, match="At least one query is required"):
            MemoryQuery(queries=[])

    def test_memory_query_validation_whitespace_only(self):
        """Test that whitespace-only queries are filtered out."""
        with pytest.raises(ValueError, match="At least one query is required"):
            MemoryQuery(queries=["   ", "\t"])

    def test_memory_result_creation(self):
        """Test MemoryResult model."""
        memory = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test content"
        )
        result = MemoryResult(
            memory=memory,
            score=0.95,
            highlights=["User asked about Python"],
            method=RetrievalMethod.RAG
        )
        assert result.memory.memory_id == "mem-001"
        assert result.score == 0.95
        assert len(result.highlights) == 1
        assert result.method == RetrievalMethod.RAG

    def test_memory_result_score_validation(self):
        """Test score bounds validation."""
        memory = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test"
        )

        # Valid scores
        MemoryResult(memory=memory, score=0.0, method=RetrievalMethod.RAG)
        MemoryResult(memory=memory, score=0.5, method=RetrievalMethod.RAG)
        MemoryResult(memory=memory, score=1.0, method=RetrievalMethod.RAG)

        # Invalid scores
        with pytest.raises(ValueError):
            MemoryResult(memory=memory, score=-0.1, method=RetrievalMethod.RAG)

        with pytest.raises(ValueError):
            MemoryResult(memory=memory, score=1.1, method=RetrievalMethod.RAG)


class TestRequestModels:
    """Test request/response models."""

    def test_store_memory_request(self):
        """Test StoreMemoryRequest model."""
        request = StoreMemoryRequest(
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            agent="agent-001",
            content={"conversation": "Test content"},
            summary="Test summary",
            categories=["coding"],
            auto_categorize=True
        )
        assert request.resource_url == "agent://agent-001/session/2026-03-01"
        assert request.modality == MemoryModality.CONVERSATION
        assert request.auto_categorize is True

    def test_retrieve_memory_request(self):
        """Test RetrieveMemoryRequest model."""
        request = RetrieveMemoryRequest(
            queries=["What did the user ask about Python?"],
            where={"user": "user-123"},
            method=RetrievalMethod.HYBRID,
            limit=15,
            threshold=0.8
        )
        assert len(request.queries) == 1
        assert request.method == RetrievalMethod.HYBRID
        assert request.limit == 15

    def test_categorize_memory_request(self):
        """Test CategorizeMemoryRequest model."""
        request = CategorizeMemoryRequest(
            memory_id="mem-001",
            categories=["python", "coding", "help"],
            confidence=CategoryConfidence.HIGH,
            replace=False
        )
        assert request.memory_id == "mem-001"
        assert len(request.categories) == 3
        assert request.replace is False

    def test_categorize_memory_request_validation(self):
        """Test that empty memory_id raises validation error."""
        with pytest.raises(ValueError, match="memory_id cannot be empty"):
            CategorizeMemoryRequest(
                memory_id="   ",
                categories=["coding"]
            )

    def test_create_category_request(self):
        """Test CreateCategoryRequest model."""
        request = CreateCategoryRequest(
            name="python",
            description="Python related memories",
            parent_id="cat-001",
            confidence=CategoryConfidence.HIGH,
            color="#3498db",
            icon="python"
        )
        assert request.name == "python"
        assert request.parent_id == "cat-001"
        assert request.confidence == CategoryConfidence.HIGH

    def test_memory_stats(self):
        """Test MemoryStats model."""
        stats = MemoryStats(
            total_memories=1000,
            active_memories=800,
            archived_memories=200,
            total_categories=15,
            avg_retrieval_time_ms=45.5,
            categorization_accuracy=0.92,
            storage_mode="postgres"
        )
        assert stats.total_memories == 1000
        assert stats.active_memories == 800
        assert stats.archived_memories == 200
        assert stats.categorization_accuracy == 0.92
        assert stats.storage_mode == "postgres"


# =============================================================================
# Client Tests
# =============================================================================

class TestMemUClient:
    """Test MemUClient with mocked SDK responses."""

    @pytest.fixture
    def client(self):
        """Create a client instance for testing."""
        return MemUClient(
            mode="inmemory",
            openai_api_key="test-api-key"
        )

    @pytest.fixture
    def mock_memu_service(self):
        """Create a mock MemU SDK service."""
        mock_service = MagicMock()
        return mock_service

    @pytest.mark.asyncio
    async def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.mode == "inmemory"
        assert client.openai_api_key == "test-api-key"
        assert client._service is None
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_client_initialize_success(self, client, mock_memu_service):
        """Test successful client initialization."""
        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()
            assert client._initialized is True
            assert client._service is not None

    @pytest.mark.asyncio
    async def test_client_initialize_no_api_key(self):
        """Test initialization fails without OpenAI API key."""
        client = MemUClient(mode="inmemory", openai_api_key=None)

        with pytest.raises(MemUError, match="OPENAI_API_KEY is required"):
            await client.initialize()

    @pytest.mark.asyncio
    async def test_client_initialize_postgres_no_db_url(self):
        """Test postgres mode fails without DATABASE_URL."""
        client = MemUClient(
            mode="postgres",
            database_url=None,
            openai_api_key="test-key"
        )

        with pytest.raises(MemUError, match="DATABASE_URL is required for postgres mode"):
            await client.initialize()

    @pytest.mark.asyncio
    async def test_client_double_initialize(self, client, mock_memu_service):
        """Test that calling initialize twice is idempotent."""
        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()
            first_service = client._service
            await client.initialize()
            assert client._service is first_service

    @pytest.mark.asyncio
    async def test_client_shutdown(self, client, mock_memu_service):
        """Test client shutdown."""
        mock_memu_service.close = MagicMock()

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()
            await client.shutdown()

            assert client._initialized is False
            assert client._service is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_memu_service):
        """Test health_check with successful response."""
        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, client):
        """Test health_check initializes client if needed."""
        with patch("src.memu_integration.client.MemUService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            result = await client.health_check()
            assert result is True
            assert client._initialized is True

    @pytest.mark.asyncio
    async def test_store_memory_success(self, client, mock_memu_service):
        """Test store_memory with successful response."""
        mock_memu_service.memorize = MagicMock(
            return_value={"memory_id": "mem-001"}
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            request = StoreMemoryRequest(
                resource_url="agent://agent-001/session/2026-03-01",
                modality=MemoryModality.CONVERSATION,
                user="user-123",
                content="Test content",
                summary="Test summary"
            )

            memory = await client.store_memory(request)

            assert memory.memory_id == "mem-001"
            assert memory.resource_url == request.resource_url
            assert memory.user == request.user

    @pytest.mark.asyncio
    async def test_store_memory_not_initialized(self, client):
        """Test store_memory fails when client not initialized."""
        client._initialized = False
        client._service = None

        request = StoreMemoryRequest(
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test"
        )

        with pytest.raises(MemUError, match="not initialized"):
            await client.store_memory(request)

    @pytest.mark.asyncio
    async def test_retrieve_memory_success(self, client, mock_memu_service):
        """Test retrieve_memory with successful response."""
        mock_memu_service.retrieve = MagicMock(
            return_value={
                "items": [
                    {
                        "memory_id": "mem-001",
                        "resource_url": "agent://agent-001/session/2026-03-01",
                        "modality": "conversation",
                        "user": "user-123",
                        "content": {"text": "Test content"},
                        "score": 0.9
                    }
                ]
            }
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            request = RetrieveMemoryRequest(
                queries=["Python programming"],
                where={"user": "user-123"},
                limit=10
            )

            results = await client.retrieve_memory(request)

            assert len(results) == 1
            assert results[0].score == 0.9
            assert results[0].memory.memory_id == "mem-001"

    @pytest.mark.asyncio
    async def test_list_memories_success(self, client, mock_memu_service):
        """Test list_memories with successful response."""
        mock_memu_service.retrieve = MagicMock(
            return_value={
                "items": [
                    {
                        "memory_id": "mem-001",
                        "resource_url": "agent://agent-001/session/2026-03-01",
                        "modality": "conversation",
                        "user": "user-123",
                        "content": "Test"
                    },
                    {
                        "memory_id": "mem-002",
                        "resource_url": "agent://agent-002/session/2026-03-01",
                        "modality": "code",
                        "user": "user-123",
                        "content": "Code"
                    }
                ]
            }
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            response = await client.list_memories(user="user-123", limit=50)

            assert len(response.memories) == 2
            assert response.total == 2
            assert response.page_size == 50

    @pytest.mark.asyncio
    async def test_get_memory_success(self, client, mock_memu_service):
        """Test get_memory with successful response."""
        mock_memu_service.retrieve = MagicMock(
            return_value={
                "items": [
                    {
                        "memory_id": "mem-001",
                        "resource_url": "agent://agent-001/session/2026-03-01",
                        "modality": "conversation",
                        "user": "user-123",
                        "content": "Test content"
                    }
                ]
            }
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            memory = await client.get_memory("mem-001")

            assert memory.memory_id == "mem-001"

    @pytest.mark.asyncio
    async def test_get_memory_not_found(self, client, mock_memu_service):
        """Test get_memory when memory is not found."""
        mock_memu_service.retrieve = MagicMock(return_value={"items": []})

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            with pytest.raises(MemUError, match="not found"):
                await client.get_memory("mem-999")

    @pytest.mark.asyncio
    async def test_get_memory_validation_error(self, client):
        """Test get_memory with empty memory_id."""
        client._initialized = True

        with pytest.raises(ValidationError, match="memory_id is required"):
            await client.get_memory("   ")

    @pytest.mark.asyncio
    async def test_delete_memory_success(self, client, mock_memu_service):
        """Test delete_memory with successful response."""
        mock_memu_service.delete = MagicMock()

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            # Should not raise any exception
            await client.delete_memory("mem-001")

    @pytest.mark.asyncio
    async def test_categorize_memory_success(self, client, mock_memu_service):
        """Test categorize_memory with successful response."""
        mock_memu_service.retrieve = MagicMock(
            return_value={
                "items": [
                    {
                        "memory_id": "mem-001",
                        "resource_url": "agent://agent-001/session/2026-03-01",
                        "modality": "conversation",
                        "user": "user-123",
                        "content": "Test",
                        "categories": []
                    }
                ]
            }
        )
        mock_memu_service.categorize = MagicMock()

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            request = CategorizeMemoryRequest(
                memory_id="mem-001",
                categories=["python", "coding"]
            )

            memory = await client.categorize_memory(request)

            assert memory.memory_id == "mem-001"
            assert "python" in memory.categories
            assert "coding" in memory.categories

    @pytest.mark.asyncio
    async def test_categorize_memory_replace(self, client, mock_memu_service):
        """Test categorize_memory with replace=True."""
        mock_memu_service.retrieve = MagicMock(
            return_value={
                "items": [
                    {
                        "memory_id": "mem-001",
                        "resource_url": "agent://agent-001/session/2026-03-01",
                        "modality": "conversation",
                        "user": "user-123",
                        "content": "Test",
                        "categories": ["old", "categories"]
                    }
                ]
            }
        )
        mock_memu_service.categorize = MagicMock()

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            request = CategorizeMemoryRequest(
                memory_id="mem-001",
                categories=["new", "categories"],
                replace=True
            )

            memory = await client.categorize_memory(request)

            assert memory.categories == ["new", "categories"]

    @pytest.mark.asyncio
    async def test_create_category_success(self, client, mock_memu_service):
        """Test create_category with successful response."""
        mock_memu_service.create_category = MagicMock()

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            request = CreateCategoryRequest(
                name="python",
                description="Python programming"
            )

            category = await client.create_category(request)

            assert category.name == "python"
            assert category.description == "Python programming"
            assert "cat-" in category.category_id

    @pytest.mark.asyncio
    async def test_list_categories_success(self, client, mock_memu_service):
        """Test list_categories with successful response."""
        mock_memu_service.list_categories = MagicMock(
            return_value=[
                {
                    "category_id": "cat-001",
                    "name": "coding",
                    "description": "Coding related",
                    "confidence": "high"
                },
                {
                    "category_id": "cat-002",
                    "name": "help",
                    "description": "Help requests",
                    "confidence": "medium"
                }
            ]
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            categories = await client.list_categories()

            assert len(categories) == 2
            assert categories[0].name == "coding"
            assert categories[1].name == "help"

    @pytest.mark.asyncio
    async def test_get_stats_success(self, client, mock_memu_service):
        """Test get_stats with successful response."""
        mock_memu_service.get_stats = MagicMock(
            return_value={
                "total_memories": 1000,
                "active_memories": 800,
                "archived_memories": 200,
                "total_categories": 15,
                "avg_retrieval_time_ms": 45.5,
                "categorization_accuracy": 0.92
            }
        )

        with patch("src.memu_integration.client.MemUService", return_value=mock_memu_service):
            await client.initialize()

            stats = await client.get_stats()

            assert stats.total_memories == 1000
            assert stats.storage_mode == "inmemory"


# =============================================================================
# Service Tests
# =============================================================================

class TestMemUService:
    """Test MemU FastAPI service endpoints."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MemUClient."""
        client = AsyncMock(spec=MemUClient)
        return client

    @pytest.fixture
    def test_app(self, mock_client):
        """Create a test app with mocked client."""
        def override_get_client():
            return mock_client

        app.dependency_overrides[get_memu_client] = override_get_client
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
        assert data["service"] == "memu_integration"

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

    def test_store_memory(self, client, mock_client):
        """Test POST /api/memories endpoint."""
        mock_client.store_memory.return_value = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test content"
        )

        request_data = {
            "resource_url": "agent://agent-001/session/2026-03-01",
            "modality": "conversation",
            "user": "user-123",
            "content": "Test content"
        }

        response = client.post("/api/memories", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["memory_id"] == "mem-001"

    def test_retrieve_memory(self, client, mock_client):
        """Test POST /api/memories/retrieve endpoint."""
        mock_client.retrieve_memory.return_value = [
            MemoryResult(
                memory=Memory(
                    memory_id="mem-001",
                    resource_url="agent://agent-001/session/2026-03-01",
                    modality=MemoryModality.CONVERSATION,
                    user="user-123",
                    content="Test content"
                ),
                score=0.9,
                method=RetrievalMethod.RAG
            )
        ]

        request_data = {
            "queries": ["Python programming"],
            "method": "rag",
            "limit": 10
        }

        response = client.post("/api/memories/retrieve", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["score"] == 0.9

    def test_list_memories(self, client, mock_client):
        """Test GET /api/memories endpoint."""
        mock_client.list_memories.return_value = MemoryListResponse(
            memories=[
                Memory(
                    memory_id="mem-001",
                    resource_url="agent://agent-001/session/2026-03-01",
                    modality=MemoryModality.CONVERSATION,
                    user="user-123",
                    content="Test"
                )
            ],
            total=1
        )

        response = client.get("/api/memories?user=user-123&limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["memories"]) == 1

    def test_get_memory(self, client, mock_client):
        """Test GET /api/memories/{memory_id} endpoint."""
        mock_client.get_memory.return_value = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test content",
            summary="Test summary"
        )

        response = client.get("/api/memories/mem-001")
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == "mem-001"
        assert data["summary"] == "Test summary"

    def test_delete_memory(self, client, mock_client):
        """Test DELETE /api/memories/{memory_id} endpoint."""
        mock_client.delete_memory.return_value = None

        response = client.delete("/api/memories/mem-001")
        assert response.status_code == 204
        assert response.content == b""

    def test_categorize_memory(self, client, mock_client):
        """Test POST /api/memories/{memory_id}/categorize endpoint."""
        mock_client.categorize_memory.return_value = Memory(
            memory_id="mem-001",
            resource_url="agent://agent-001/session/2026-03-01",
            modality=MemoryModality.CONVERSATION,
            user="user-123",
            content="Test",
            categories=["python", "coding"]
        )

        request_data = {
            "memory_id": "mem-001",
            "categories": ["python", "coding"],
            "confidence": "high"
        }

        response = client.post("/api/memories/mem-001/categorize", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "python" in data["categories"]
        assert "coding" in data["categories"]

    def test_list_categories(self, client, mock_client):
        """Test GET /api/categories endpoint."""
        mock_client.list_categories.return_value = [
            MemoryCategory(
                category_id="cat-001",
                name="coding",
                description="Coding memories"
            )
        ]

        response = client.get("/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "coding"

    def test_create_category(self, client, mock_client):
        """Test POST /api/categories endpoint."""
        mock_client.create_category.return_value = MemoryCategory(
            category_id="cat-001",
            name="python",
            description="Python memories"
        )

        request_data = {
            "name": "python",
            "description": "Python memories"
        }

        response = client.post("/api/categories", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["category_id"] == "cat-001"
        assert data["name"] == "python"

    def test_get_stats(self, client, mock_client):
        """Test GET /api/stats endpoint."""
        mock_client.get_stats.return_value = MemoryStats(
            total_memories=1000,
            active_memories=800,
            storage_mode="inmemory"
        )

        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_memories"] == 1000
        assert data["storage_mode"] == "inmemory"


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in MemU integration."""

    def test_memu_error_to_dict(self):
        """Test MemUError conversion to dict."""
        error = MemUError(
            "Test error",
            details={"memory_id": "mem-001"}
        )
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "MemUError"
        assert error_dict["message"] == "Test error"
        assert error_dict["memory_id"] == "mem-001"
        assert "service" in error_dict

    def test_validation_error_to_dict(self):
        """Test ValidationError conversion to dict."""
        error = ValidationError("Invalid input", details={"field": "memory_id"})
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "ValidationError"
        assert error_dict["message"] == "Invalid input"
        assert error_dict["field"] == "memory_id"

    def test_memu_error_status_code(self):
        """Test MemUError status code property."""
        error = MemUError("Service unavailable")
        assert error.status_code == 503

    def test_validation_error_status_code(self):
        """Test ValidationError status code property."""
        error = ValidationError("Invalid input")
        assert error.status_code == 400

    def test_client_not_initialized(self):
        """Test error when client is not initialized."""
        client = MemUClient()
        client._initialized = False
        client._service = None

        with pytest.raises(MemUError, match="not initialized"):
            client._ensure_initialized()

    def test_modality_enum_values(self):
        """Test MemoryModality enum values."""
        assert MemoryModality.CONVERSATION == "conversation"
        assert MemoryModality.DOCUMENT == "document"
        assert MemoryModality.IMAGE == "image"
        assert MemoryModality.VIDEO == "video"
        assert MemoryModality.AUDIO == "audio"
        assert MemoryModality.CODE == "code"
        assert MemoryModality.SYSTEM == "system"

    def test_retrieval_method_enum_values(self):
        """Test RetrievalMethod enum values."""
        assert RetrievalMethod.RAG == "rag"
        assert RetrievalMethod.LLM == "llm"
        assert RetrievalMethod.HYBRID == "hybrid"

    def test_memory_status_enum_values(self):
        """Test MemoryStatus enum values."""
        assert MemoryStatus.ACTIVE == "active"
        assert MemoryStatus.ARCHIVED == "archived"
        assert MemoryStatus.DELETED == "deleted"
        assert MemoryStatus.PROCESSING == "processing"

    def test_category_confidence_enum_values(self):
        """Test CategoryConfidence enum values."""
        assert CategoryConfidence.HIGH == "high"
        assert CategoryConfidence.MEDIUM == "medium"
        assert CategoryConfidence.LOW == "low"
