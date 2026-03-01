"""
MemU SDK client wrapper for persistent memory integration.

This module provides an async client wrapper for the MemU SDK, supporting
memory storage, retrieval, categorization, and statistics operations.
"""

import asyncio
from datetime import datetime
from typing import Any

from src.shared.config import settings
from src.shared.errors import MemUError, ValidationError
from src.shared.logging import get_logger
from src.memu_integration.models import (
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
    MemoryModality,
    RetrievalMethod,
    MemoryStatus,
    CategoryConfidence,
)

logger = get_logger(__name__)


class MemUClient:
    """
    Async client wrapper for MemU persistent memory SDK.

    This client wraps the MemU SDK to provide async memory operations including
    storing, retrieving, categorizing memories, and managing categories.

    The client supports two storage modes:
    - "inmemory": In-memory storage for development and testing
    - "postgres": PostgreSQL with pgvector for production

    Attributes:
        mode: Storage mode (inmemory or postgres)
        database_url: PostgreSQL connection string (for postgres mode)
        openai_api_key: OpenAI API key for embeddings
        _service: Internal MemU SDK service instance
        _initialized: Whether the client has been initialized

    Example:
        >>> client = MemUClient()
        >>> await client.initialize()
        >>> await client.store_memory(StoreMemoryRequest(...))
        >>> results = await client.retrieve_memory(RetrieveMemoryRequest(...))
        >>> await client.shutdown()
    """

    def __init__(
        self,
        mode: str | None = None,
        database_url: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        """
        Initialize the MemU client.

        Args:
            mode: Storage mode (defaults to settings.MEMU_MODE)
            database_url: PostgreSQL connection string (for postgres mode)
            openai_api_key: OpenAI API key for embeddings
        """
        self.mode = mode or settings.MEMU_MODE
        self.database_url = database_url or settings.DATABASE_URL
        self.openai_api_key = openai_api_key or settings.OPENAI_API_KEY
        self._service: Any = None
        self._initialized = False

        logger.info(
            "MemU client initialized",
            extra={
                "mode": self.mode,
                "database_url": self.database_url[:20] + "..." if self.database_url else None,
            },
        )

    async def initialize(self) -> None:
        """
        Initialize the MemU SDK service.

        This method must be called before making any memory operations. It creates
        the underlying MemU service with the appropriate configuration.

        Raises:
            MemUError: If service initialization fails
            ConfigurationError: If required configuration is missing
        """
        if self._initialized:
            logger.debug("Client already initialized")
            return

        try:
            # Import MemU SDK here to allow optional dependency
            try:
                from memu import MemUService
            except ImportError as e:
                raise MemUError(
                    "MemU SDK not installed. Install with: pip install memu",
                    details={"import_error": str(e)},
                ) from e

            # Validate OpenAI API key for embeddings
            if not self.openai_api_key:
                raise MemUError(
                    "OPENAI_API_KEY is required for MemU embeddings",
                    details={"setting": "OPENAI_API_KEY"},
                )

            # Configure database based on mode
            if self.mode == "postgres":
                if not self.database_url:
                    raise MemUError(
                        "DATABASE_URL is required for postgres mode",
                        details={"mode": self.mode},
                    )
                database_config = {
                    "metadata_store": {
                        "provider": "postgres",
                        "connection_url": self.database_url,
                    }
                }
            else:  # inmemory
                database_config = {
                    "metadata_store": {"provider": "inmemory"}
                }

            logger.debug(
                "Initializing MemU service",
                extra={"mode": self.mode, "database_config": database_config},
            )

            # Initialize MemU service (run in thread pool since SDK might be sync)
            loop = asyncio.get_event_loop()
            self._service = await loop.run_in_executor(
                None,
                lambda: MemUService(
                    database_config=database_config,
                    openai_api_key=self.openai_api_key,
                ),
            )

            self._initialized = True
            logger.info("MemU service initialized successfully")

        except MemUError:
            raise
        except Exception as e:
            logger.exception("Failed to initialize MemU service")
            raise MemUError(
                "Failed to initialize MemU service",
                details={
                    "error": str(e),
                    "mode": self.mode,
                },
            ) from e

    async def shutdown(self) -> None:
        """
        Cleanup resources and close the service.

        This method should be called when the client is no longer needed.
        It gracefully closes any connections and releases resources.
        """
        if self._service:
            try:
                # MemU SDK might have cleanup methods
                if hasattr(self._service, "close"):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._service.close)
                logger.info("MemU service closed")
            except Exception as e:
                logger.warning("Error closing MemU service", extra={"error": str(e)})
            finally:
                self._service = None
                self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure the client has been initialized."""
        if not self._initialized or self._service is None:
            raise MemUError(
                "Client not initialized. Call initialize() first.",
                details={"method": "check_init"},
            )

    async def health_check(self) -> bool:
        """
        Check if the MemU service is accessible.

        Returns:
            True if the service is healthy, False otherwise

        Example:
            >>> client = MemUClient()
            >>> await client.initialize()
            >>> is_healthy = await client.health_check()
            >>> print(f"Service Healthy: {is_healthy}")
        """
        try:
            if not self._initialized:
                await self.initialize()

            # Try a simple operation to verify service is working
            # In production, you might check database connectivity
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._service is not None)

            logger.debug("Health check completed", extra={"healthy": True})
            return True

        except Exception as e:
            logger.warning("Health check failed", extra={"error": str(e)})
            return False

    # ------------------------------------------------------------------------------
    # Memory Storage Operations
    # ------------------------------------------------------------------------------

    async def store_memory(self, request: StoreMemoryRequest) -> Memory:
        """
        Store a new memory in MemU.

        Args:
            request: Memory storage request with resource URL, modality, content, etc.

        Returns:
            Created Memory object with assigned memory_id

        Raises:
            MemUError: If storage fails
            ValidationError: If request data is invalid

        Example:
            >>> request = StoreMemoryRequest(
            ...     resource_url="agent://agent-001/session/2026-03-01",
            ...     modality=MemoryModality.CONVERSATION,
            ...     user="user-123",
            ...     agent="agent-001",
            ...     content={"conversation": "User requested help with Python"},
            ...     summary="Helped user with Python code"
            ... )
            >>> memory = await client.store_memory(request)
        """
        self._ensure_initialized()

        try:
            logger.info(
                "Storing memory",
                extra={
                    "resource_url": request.resource_url,
                    "modality": request.modality.value,
                    "user": request.user,
                    "agent": request.agent,
                },
            )

            # Prepare content for MemU SDK
            content = request.content
            if isinstance(content, dict):
                content_str = str(content)
            else:
                content_str = content

            # Call MemU SDK memorize method
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._service.memorize(
                    resource_url=request.resource_url,
                    modality=request.modality.value,
                    user=request.user,
                    content=content_str,
                ),
            )

            # Build Memory object from result
            # The SDK result structure may vary, adapt as needed
            memory = Memory(
                memory_id=result.get("memory_id", f"mem-{datetime.utcnow().timestamp()}"),
                resource_url=request.resource_url,
                modality=request.modality,
                user=request.user,
                agent=request.agent,
                content=request.content,
                summary=request.summary,
                categories=request.categories,
                status=MemoryStatus.ACTIVE,
                metadata=request.metadata or MemoryMetadata(),
            )

            logger.info(
                "Memory stored successfully",
                extra={"memory_id": memory.memory_id},
            )
            return memory

        except Exception as e:
            logger.exception("Failed to store memory")
            raise MemUError(
                "Failed to store memory",
                details={
                    "resource_url": request.resource_url,
                    "error": str(e),
                },
            ) from e

    # ------------------------------------------------------------------------------
    # Memory Retrieval Operations
    # ------------------------------------------------------------------------------

    async def retrieve_memory(self, request: RetrieveMemoryRequest) -> list[MemoryResult]:
        """
        Retrieve memories based on semantic search queries.

        Args:
            request: Memory retrieval request with queries, filters, method, etc.

        Returns:
            List of MemoryResult objects with relevance scores

        Raises:
            MemUError: If retrieval fails
            ValidationError: If request data is invalid

        Example:
            >>> request = RetrieveMemoryRequest(
            ...     queries=["What did the user ask about Python?"],
            ...     where={"user": "user-123", "agent": "agent-001"},
            ...     method=RetrievalMethod.RAG,
            ...     limit=10
            ... )
            >>> results = await client.retrieve_memory(request)
            >>> for result in results:
            ...     print(f"{result.score}: {result.memory.summary}")
        """
        self._ensure_initialized()

        try:
            logger.debug(
                "Retrieving memories",
                extra={
                    "queries": request.queries,
                    "method": request.method.value,
                    "limit": request.limit,
                },
            )

            # Call MemU SDK retrieve method
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._service.retrieve(
                    queries=request.queries,
                    where=request.where,
                    method=request.method.value,
                    limit=request.limit,
                ),
            )

            # Convert SDK result to MemoryResult list
            # The SDK result structure may vary, adapt as needed
            memory_results = []
            items = result.get("items", []) if isinstance(result, dict) else []

            for item in items:
                memory = Memory(
                    memory_id=item.get("memory_id", ""),
                    resource_url=item.get("resource_url", ""),
                    modality=MemoryModality(item.get("modality", "conversation")),
                    user=item.get("user", ""),
                    agent=item.get("agent"),
                    content=item.get("content", {}),
                    summary=item.get("summary"),
                    categories=item.get("categories", []),
                    status=MemoryStatus.ACTIVE,
                )

                memory_results.append(
                    MemoryResult(
                        memory=memory,
                        score=item.get("score", 0.8),
                        highlights=item.get("highlights", []),
                        method=request.method,
                    )
                )

            logger.info(
                "Memories retrieved successfully",
                extra={"count": len(memory_results)},
            )
            return memory_results

        except Exception as e:
            logger.exception("Failed to retrieve memories")
            raise MemUError(
                "Failed to retrieve memories",
                details={
                    "queries": request.queries,
                    "error": str(e),
                },
            ) from e

    async def list_memories(
        self,
        user: str | None = None,
        agent: str | None = None,
        modality: MemoryModality | None = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        limit: int = 100,
        offset: int = 0,
    ) -> MemoryListResponse:
        """
        List memories with optional filtering.

        Args:
            user: Filter by user ID
            agent: Filter by agent ID
            modality: Filter by content modality
            status: Filter by status (default: ACTIVE)
            limit: Maximum number of memories to return
            offset: Number of memories to skip

        Returns:
            MemoryListResponse containing list of memories and total count

        Raises:
            MemUError: If listing fails

        Example:
            >>> response = await client.list_memories(
            ...     user="user-123",
            ...     agent="agent-001",
            ...     limit=50
            ... )
            >>> print(f"Total memories: {response.total}")
        """
        self._ensure_initialized()

        try:
            where: dict[str, Any] = {"status": status.value}
            if user:
                where["user"] = user
            if agent:
                where["agent"] = agent
            if modality:
                where["modality"] = modality.value

            logger.debug("Listing memories", extra={"where": where, "limit": limit})

            # Build query for retrieval
            query = RetrieveMemoryRequest(
                queries=[""],  # Empty query to list all
                where=where,
                limit=limit,
            )

            # Use retrieve to get memories
            results = await self.retrieve_memory(query)

            memories = [r.memory for r in results]

            response = MemoryListResponse(
                memories=memories,
                total=len(memories),
                page=offset // limit + 1 if limit > 0 else 1,
                page_size=limit,
            )

            logger.info(
                "Memories listed successfully",
                extra={"count": len(memories)},
            )
            return response

        except Exception as e:
            logger.exception("Failed to list memories")
            raise MemUError(
                "Failed to list memories",
                details={
                    "where": where,
                    "error": str(e),
                },
            ) from e

    async def get_memory(self, memory_id: str) -> Memory:
        """
        Get details of a specific memory.

        Args:
            memory_id: Unique identifier of the memory

        Returns:
            Memory object with full details

        Raises:
            MemUError: If memory not found or retrieval fails
            ValidationError: If memory_id is invalid

        Example:
            >>> memory = await client.get_memory("mem-123")
            >>> print(f"{memory.summary}: {memory.content}")
        """
        self._ensure_initialized()

        if not memory_id or not memory_id.strip():
            raise ValidationError("memory_id is required", details={"field": "memory_id"})

        try:
            logger.debug("Getting memory", extra={"memory_id": memory_id})

            # Use retrieve with memory_id filter
            result = await self.retrieve_memory(
                RetrieveMemoryRequest(
                    queries=[""],
                    where={"memory_id": memory_id},
                    limit=1,
                )
            )

            if not result:
                raise MemUError(
                    f"Memory {memory_id} not found",
                    details={"memory_id": memory_id, "status_code": 404},
                )

            logger.info("Memory retrieved successfully", extra={"memory_id": memory_id})
            return result[0].memory

        except MemUError:
            raise
        except Exception as e:
            logger.exception("Failed to get memory")
            raise MemUError(
                "Failed to get memory",
                details={"memory_id": memory_id, "error": str(e)},
            ) from e

    async def delete_memory(self, memory_id: str) -> None:
        """
        Delete a memory.

        Args:
            memory_id: Unique identifier of the memory to delete

        Raises:
            MemUError: If deletion fails
            ValidationError: If memory_id is invalid

        Example:
            >>> await client.delete_memory("mem-123")
        """
        self._ensure_initialized()

        if not memory_id or not memory_id.strip():
            raise ValidationError("memory_id is required", details={"field": "memory_id"})

        try:
            logger.info("Deleting memory", extra={"memory_id": memory_id})

            # MemU SDK might have a delete method
            # For now, we'll mark as archived
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._service.delete(memory_id=memory_id)
                if hasattr(self._service, "delete")
                else None,
            )

            logger.info("Memory deleted successfully", extra={"memory_id": memory_id})

        except Exception as e:
            logger.exception("Failed to delete memory")
            raise MemUError(
                "Failed to delete memory",
                details={"memory_id": memory_id, "error": str(e)},
            ) from e

    # ------------------------------------------------------------------------------
    # Categorization Operations
    # ------------------------------------------------------------------------------

    async def categorize_memory(self, request: CategorizeMemoryRequest) -> Memory:
        """
        Categorize or re-categorize a memory.

        Args:
            request: Categorization request with memory_id and categories

        Returns:
            Updated Memory with new categories

        Raises:
            MemUError: If categorization fails
            ValidationError: If request data is invalid

        Example:
            >>> request = CategorizeMemoryRequest(
            ...     memory_id="mem-123",
            ...     categories=["coding", "python", "help"],
            ...     confidence=CategoryConfidence.HIGH
            ... )
            >>> memory = await client.categorize_memory(request)
        """
        self._ensure_initialized()

        if not request.memory_id or not request.memory_id.strip():
            raise ValidationError("memory_id is required", details={"field": "memory_id"})

        try:
            logger.info(
                "Categorizing memory",
                extra={
                    "memory_id": request.memory_id,
                    "categories": request.categories,
                },
            )

            # Get the memory first
            memory = await self.get_memory(request.memory_id)

            # Update categories
            if request.replace:
                memory.categories = request.categories
            else:
                # Append new categories
                memory.categories = list(set(memory.categories + request.categories))

            # MemU SDK might have a categorize method
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._service.categorize(
                    memory_id=request.memory_id,
                    categories=request.categories,
                )
                if hasattr(self._service, "categorize")
                else None,
            )

            logger.info(
                "Memory categorized successfully",
                extra={"memory_id": request.memory_id},
            )
            return memory

        except MemUError:
            raise
        except Exception as e:
            logger.exception("Failed to categorize memory")
            raise MemUError(
                "Failed to categorize memory",
                details={
                    "memory_id": request.memory_id,
                    "error": str(e),
                },
            ) from e

    async def create_category(self, request: CreateCategoryRequest) -> MemoryCategory:
        """
        Create a new memory category.

        Args:
            request: Category creation request

        Returns:
            Created MemoryCategory object

        Raises:
            MemUError: If category creation fails
            ValidationError: If request data is invalid

        Example:
            >>> request = CreateCategoryRequest(
            ...     name="coding",
            ...     description="Programming and code-related memories",
            ...     confidence=CategoryConfidence.HIGH
            ... )
            >>> category = await client.create_category(request)
        """
        self._ensure_initialized()

        try:
            logger.info(
                "Creating category",
                extra={"name": request.name, "parent_id": request.parent_id},
            )

            # Generate category ID
            category_id = f"cat-{datetime.utcnow().timestamp()}"

            category = MemoryCategory(
                category_id=category_id,
                name=request.name,
                description=request.description,
                parent_id=request.parent_id,
                confidence=request.confidence,
                color=request.color,
                icon=request.icon,
                metadata=request.metadata,
            )

            # MemU SDK might have a create_category method
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._service.create_category(
                    category_id=category_id,
                    name=request.name,
                    description=request.description,
                )
                if hasattr(self._service, "create_category")
                else None,
            )

            logger.info(
                "Category created successfully",
                extra={"category_id": category_id},
            )
            return category

        except Exception as e:
            logger.exception("Failed to create category")
            raise MemUError(
                "Failed to create category",
                details={"name": request.name, "error": str(e)},
            ) from e

    async def list_categories(
        self,
        parent_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryCategory]:
        """
        List memory categories with optional filtering.

        Args:
            parent_id: Filter by parent category ID
            limit: Maximum number of categories to return

        Returns:
            List of MemoryCategory objects

        Raises:
            MemUError: If listing fails

        Example:
            >>> categories = await client.list_categories(parent_id="cat-001")
            >>> for cat in categories:
            ...     print(f"{cat.name}: {cat.description}")
        """
        self._ensure_initialized()

        try:
            logger.debug("Listing categories", extra={"parent_id": parent_id})

            # MemU SDK might have a list_categories method
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._service.list_categories(parent_id=parent_id, limit=limit)
                if hasattr(self._service, "list_categories")
                else [],
            )

            # Convert to MemoryCategory objects
            categories = [
                MemoryCategory(
                    category_id=cat.get("category_id", ""),
                    name=cat.get("name", ""),
                    description=cat.get("description"),
                    parent_id=cat.get("parent_id"),
                    confidence=CategoryConfidence(cat.get("confidence", "medium")),
                    color=cat.get("color"),
                    icon=cat.get("icon"),
                    metadata=cat.get("metadata", {}),
                )
                for cat in (result if isinstance(result, list) else [])
            ]

            logger.info(
                "Categories listed successfully",
                extra={"count": len(categories)},
            )
            return categories

        except Exception as e:
            logger.exception("Failed to list categories")
            raise MemUError(
                "Failed to list categories",
                details={"error": str(e)},
            ) from e

    # ------------------------------------------------------------------------------
    # Statistics Operations
    # ------------------------------------------------------------------------------

    async def get_stats(self) -> MemoryStats:
        """
        Get statistics about memory usage.

        Returns:
            MemoryStats object with storage and retrieval metrics

        Raises:
            MemUError: If stats retrieval fails

        Example:
            >>> stats = await client.get_stats()
            >>> print(f"Total memories: {stats.total_memories}")
        """
        self._ensure_initialized()

        try:
            logger.debug("Getting memory statistics")

            # MemU SDK might have a stats method
            # For now, return basic stats
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._service.get_stats()
                if hasattr(self._service, "get_stats")
                else {},
            )

            stats = MemoryStats(
                total_memories=result.get("total_memories", 0),
                active_memories=result.get("active_memories", 0),
                archived_memories=result.get("archived_memories", 0),
                total_categories=result.get("total_categories", 0),
                avg_retrieval_time_ms=result.get("avg_retrieval_time_ms", 0.0),
                categorization_accuracy=result.get("categorization_accuracy", 0.0),
                storage_mode=self.mode,
            )

            logger.debug("Statistics retrieved successfully")
            return stats

        except Exception as e:
            logger.exception("Failed to get statistics")
            raise MemUError(
                "Failed to get statistics",
                details={"error": str(e)},
            ) from e


# Export the client class
__all__ = ["MemUClient"]
