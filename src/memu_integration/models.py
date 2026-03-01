"""
MemU data models for memory operations.

This module defines Pydantic models for MemU integration, including
memories, queries, results, and categorization. These models are used for
API validation, serialization, and type safety throughout the integration.
"""

from datetime import datetime
from typing import Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------

class MemoryModality(str, Enum):
    """Type of memory content modality."""

    CONVERSATION = "conversation"
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CODE = "code"
    SYSTEM = "system"


class RetrievalMethod(str, Enum):
    """Memory retrieval method."""

    RAG = "rag"  # Fast vector search
    LLM = "llm"  # Deep semantic reasoning
    HYBRID = "hybrid"  # Combination of both


class MemoryStatus(str, Enum):
    """Status of a memory in the system."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    PROCESSING = "processing"


class CategoryConfidence(str, Enum):
    """Confidence level for auto-categorization."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ------------------------------------------------------------------------------
# Base Models
# ------------------------------------------------------------------------------

class TimestampedModel(BaseModel):
    """Base model with timestamp fields."""

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the resource was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the resource was last updated"
    )

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
        "populate_by_name": True,
    }


# ------------------------------------------------------------------------------
# Memory Models
# ------------------------------------------------------------------------------

class MemoryMetadata(BaseModel):
    """Additional metadata for a memory."""

    source: str | None = Field(
        default=None,
        description="Source of the memory (e.g., agent, user, system)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags for organization"
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Importance score (0.0 to 1.0)"
    )
    access_count: int = Field(
        default=0,
        ge=0,
        description="Number of times this memory was accessed"
    )
    last_accessed_at: datetime | None = Field(
        default=None,
        description="Last time this memory was retrieved"
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model used for vectorization"
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metadata"
    )

    model_config = {"populate_by_name": True}


class Memory(TimestampedModel):
    """
    Represents a memory stored in MemU.

    A memory is a unit of information that can be stored, categorized,
    and retrieved using semantic search. Memories can represent conversations,
    documents, images, or other content types.

    Attributes:
        memory_id: Unique identifier for the memory
        resource_url: URI identifying the memory source
        modality: Type of memory content
        user: User ID associated with this memory
        agent: Agent ID associated with this memory
        content: The actual memory content
        summary: Brief summary of the memory
        categories: List of category IDs assigned to this memory
        status: Current status of the memory
        metadata: Additional memory metadata

    Example:
        >>> memory = Memory(
        ...     memory_id="mem-001",
        ...     resource_url="agent://agent-001/session/2026-03-01",
        ...     modality=MemoryModality.CONVERSATION,
        ...     user="user-123",
        ...     agent="agent-001",
        ...     content={"conversation": "User requested help with Python"},
        ...     summary="Helped user with Python code",
        ...     categories=["coding", "help"]
        ... )
    """

    memory_id: str = Field(..., description="Unique identifier for the memory")
    resource_url: str = Field(
        ...,
        description="URI identifying the memory source (e.g., agent://id/session/...)"
    )
    modality: MemoryModality = Field(
        ..., description="Type of memory content"
    )
    user: str = Field(..., description="User ID associated with this memory")
    agent: str | None = Field(
        default=None,
        description="Agent ID associated with this memory"
    )
    content: dict[str, Any] | str = Field(
        ...,
        description="The actual memory content (structured or text)"
    )
    summary: str | None = Field(
        default=None,
        description="Brief summary of the memory content"
    )
    categories: list[str] = Field(
        default_factory=list,
        description="List of category IDs assigned to this memory"
    )
    status: MemoryStatus = Field(
        default=MemoryStatus.ACTIVE,
        description="Current status of the memory"
    )
    metadata: MemoryMetadata = Field(
        default_factory=MemoryMetadata,
        description="Additional memory metadata"
    )
    vector_id: str | None = Field(
        default=None,
        description="Vector database ID for similarity search"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("memory_id", "resource_url", "user")
    @classmethod
    def validate_required_fields(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v


class MemoryCategory(TimestampedModel):
    """
    Represents a category for organizing memories.

    Categories provide hierarchical organization and help with
    auto-categorization of new memories.

    Attributes:
        category_id: Unique identifier for the category
        name: Human-readable category name
        description: Category description
        parent_id: Parent category ID for hierarchical organization
        confidence: Auto-categorization confidence level
        metadata: Additional category information

    Example:
        >>> category = MemoryCategory(
        ...     category_id="cat-001",
        ...     name="coding",
        ...     description="Programming and code-related memories",
        ...     confidence=CategoryConfidence.HIGH
        ... )
    """

    category_id: str = Field(..., description="Unique identifier for the category")
    name: str = Field(..., description="Human-readable category name")
    description: str | None = Field(
        default=None,
        description="Category description and purpose"
    )
    parent_id: str | None = Field(
        default=None,
        description="Parent category ID for hierarchical organization"
    )
    confidence: CategoryConfidence = Field(
        default=CategoryConfidence.MEDIUM,
        description="Auto-categorization confidence level"
    )
    color: str | None = Field(
        default=None,
        description="Color code for UI display (hex format)"
    )
    icon: str | None = Field(
        default=None,
        description="Icon name for UI display"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional category information"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("category_id", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


# ------------------------------------------------------------------------------
# Query and Result Models
# ------------------------------------------------------------------------------

class MemoryQuery(BaseModel):
    """
    Query for retrieving memories from MemU.

    Supports semantic search with filtering by user, agent, categories,
    and time ranges.

    Attributes:
        queries: List of natural language queries
        where: Filter conditions (user, agent, categories)
        method: Retrieval method (rag, llm, or hybrid)
        limit: Maximum number of results to return
        time_range: Optional time range filter
        threshold: Minimum similarity score threshold

    Example:
        >>> query = MemoryQuery(
        ...     queries=["What did the user ask about Python?"],
        ...     where={"user": "user-123", "agent": "agent-001"},
        ...     method=RetrievalMethod.RAG,
        ...     limit=10
        ... )
    """

    queries: list[str] = Field(
        ...,
        description="List of natural language queries for semantic search"
    )
    where: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter conditions (user, agent, categories, modality, etc.)"
    )
    method: RetrievalMethod = Field(
        default=RetrievalMethod.RAG,
        description="Retrieval method to use"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0.0 to 1.0)"
    )
    time_range: dict[str, datetime] | None = Field(
        default=None,
        description="Time range filter (start, end)"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, v: list[str]) -> list[str]:
        """Validate and normalize queries list (allows empty list)."""
        return [q.strip() for q in v if q.strip()]


class MemoryResult(BaseModel):
    """
    Represents a result from memory retrieval.

    Contains the memory along with relevance score and metadata
    about the retrieval.

    Attributes:
        memory: The retrieved memory
        score: Similarity/relevance score
        highlights: Key excerpts that matched the query
        method: Retrieval method used

    Example:
        >>> result = MemoryResult(
        ...     memory=memory,
        ...     score=0.95,
        ...     highlights=["User requested help with Python"],
        ...     method=RetrievalMethod.RAG
        ... )
    """

    memory: Memory = Field(..., description="The retrieved memory")
    score: float = Field(
        ..., ge=0.0, le=1.0, description="Similarity/relevance score"
    )
    highlights: list[str] = Field(
        default_factory=list,
        description="Key excerpts that matched the query"
    )
    method: RetrievalMethod = Field(
        ..., description="Retrieval method used"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


class MemoryListResponse(BaseModel):
    """Response model for listing memories."""

    memories: list[Memory] = Field(default_factory=list, description="List of memories")
    total: int = Field(default=0, description="Total number of memories")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=10, ge=1, description="Number of items per page")

    model_config = {"populate_by_name": True}


# ------------------------------------------------------------------------------
# Store and Categorization Models
# ------------------------------------------------------------------------------

class StoreMemoryRequest(BaseModel):
    """
    Request model for storing a new memory.

    Attributes:
        resource_url: URI identifying the memory source
        modality: Type of memory content
        user: User ID associated with this memory
        agent: Optional agent ID
        content: The memory content
        summary: Optional brief summary
        categories: Optional predefined categories
        metadata: Optional additional metadata

    Example:
        >>> request = StoreMemoryRequest(
        ...     resource_url="agent://agent-001/session/2026-03-01",
        ...     modality=MemoryModality.CONVERSATION,
        ...     user="user-123",
        ...     agent="agent-001",
        ...     content={"conversation": "User requested help with Python"},
        ...     summary="Helped user with Python code"
        ... )
    """

    resource_url: str = Field(..., description="URI identifying the memory source")
    modality: MemoryModality = Field(..., description="Type of memory content")
    user: str = Field(..., description="User ID associated with this memory")
    agent: str | None = Field(default=None, description="Agent ID")
    content: dict[str, Any] | str = Field(..., description="Memory content")
    summary: str | None = Field(default=None, description="Brief summary")
    categories: list[str] = Field(
        default_factory=list,
        description="Predefined category IDs"
    )
    metadata: MemoryMetadata | None = Field(
        default=None,
        description="Additional metadata"
    )
    auto_categorize: bool = Field(
        default=True,
        description="Whether to auto-categorize this memory"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("resource_url", "user")
    @classmethod
    def validate_required_fields(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v


class RetrieveMemoryRequest(BaseModel):
    """Request model for retrieving memories."""

    queries: list[str] = Field(
        ...,
        description="Natural language queries"
    )
    where: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter conditions"
    )
    method: RetrievalMethod = Field(
        default=RetrievalMethod.RAG,
        description="Retrieval method"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Max results")
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


class CategorizeMemoryRequest(BaseModel):
    """
    Request model for categorizing a memory.

    Can be used to manually categorize or re-categorize an existing memory.

    Attributes:
        memory_id: ID of the memory to categorize
        categories: List of category IDs to assign
        confidence: Confidence level for manual categorization

    Example:
        >>> request = CategorizeMemoryRequest(
        ...     memory_id="mem-001",
        ...     categories=["coding", "python", "help"],
        ...     confidence=CategoryConfidence.HIGH
        ... )
    """

    memory_id: str = Field(..., description="ID of the memory to categorize")
    categories: list[str] = Field(
        ...,
        description="List of category IDs to assign"
    )
    confidence: CategoryConfidence = Field(
        default=CategoryConfidence.HIGH,
        description="Confidence level for this categorization"
    )
    replace: bool = Field(
        default=False,
        description="Whether to replace existing categories or append"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, v: str) -> str:
        """Validate that memory_id is not empty."""
        if not v or not v.strip():
            raise ValueError("memory_id cannot be empty")
        return v


class CreateCategoryRequest(BaseModel):
    """Request model for creating a new category."""

    name: str = Field(..., description="Category name")
    description: str | None = Field(default=None, description="Category description")
    parent_id: str | None = Field(default=None, description="Parent category ID")
    confidence: CategoryConfidence = Field(
        default=CategoryConfidence.MEDIUM,
        description="Default confidence for auto-categorization"
    )
    color: str | None = Field(default=None, description="Color code (hex)")
    icon: str | None = Field(default=None, description="Icon name")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional category information"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ------------------------------------------------------------------------------
# Health and Stats Models
# ------------------------------------------------------------------------------

class MemoryStats(BaseModel):
    """
    Statistics about memory usage.

    Provides metrics about memory storage, retrieval, and categorization.
    """

    total_memories: int = Field(default=0, description="Total number of memories")
    active_memories: int = Field(default=0, description="Number of active memories")
    archived_memories: int = Field(default=0, description="Number of archived memories")
    total_categories: int = Field(default=0, description="Total number of categories")
    avg_retrieval_time_ms: float = Field(
        default=0.0,
        description="Average retrieval time in milliseconds"
    )
    categorization_accuracy: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Auto-categorization accuracy rate"
    )
    storage_mode: str = Field(
        default="inmemory",
        description="Storage backend (inmemory or postgres)"
    )

    model_config = {"populate_by_name": True}


# Export all models
__all__ = [
    # Enums
    "MemoryModality",
    "RetrievalMethod",
    "MemoryStatus",
    "CategoryConfidence",
    # Base
    "TimestampedModel",
    # Memory
    "Memory",
    "MemoryMetadata",
    "MemoryCategory",
    # Query/Result
    "MemoryQuery",
    "MemoryResult",
    "MemoryListResponse",
    # Requests
    "StoreMemoryRequest",
    "RetrieveMemoryRequest",
    "CategorizeMemoryRequest",
    "CreateCategoryRequest",
    # Stats
    "MemoryStats",
]
