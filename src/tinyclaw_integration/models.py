"""
TinyClaw data models for agents and messages.

This module defines Pydantic models for TinyClaw integration, including
agents, messages, channels, and agent teams. These models are used for
API validation, serialization, and type safety throughout the integration.
"""

from datetime import datetime
from typing import Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------

class AgentStatus(str, Enum):
    """Status of an agent in the TinyClaw system."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"


class ChannelType(str, Enum):
    """Supported communication channel types."""

    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SLACK = "slack"
    WEB = "web"


class MessageDirection(str, Enum):
    """Direction of message flow."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    INTERNAL = "internal"


class ChannelStatus(str, Enum):
    """Connection status of a channel."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


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
# Channel Models
# ------------------------------------------------------------------------------

class ChannelConfig(BaseModel):
    """Channel-specific configuration."""

    webhook_url: str | None = Field(
        default=None,
        description="Webhook URL for incoming messages"
    )
    api_key: str | None = Field(
        default=None,
        description="API key for channel authentication"
    )
    server_id: str | None = Field(
        default=None,
        description="Server/guild ID (for Discord)"
    )
    phone_number: str | None = Field(
        default=None,
        description="Phone number (for WhatsApp)"
    )
    bot_token: str | None = Field(
        default=None,
        description="Bot token (for Telegram/Slack)"
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional channel-specific settings"
    )

    model_config = {"populate_by_name": True}


class Channel(TimestampedModel):
    """
    Represents a communication channel in TinyClaw.

    A channel is a connection to a messaging platform like Discord,
    WhatsApp, or Telegram that agents can use to send and receive messages.

    Attributes:
        channel_id: Unique identifier for the channel
        channel_type: Type of messaging platform
        name: Human-readable channel name
        status: Current connection status
        config: Channel-specific configuration

    Example:
        >>> channel = Channel(
        ...     channel_id="ch-123",
        ...     channel_type=ChannelType.DISCORD,
        ...     name="general",
        ...     status=ChannelStatus.CONNECTED,
        ...     config={"server_id": "123456789"}
        ... )
    """

    channel_id: str = Field(
        ..., description="Unique identifier for the channel"
    )
    channel_type: ChannelType = Field(
        ..., description="Type of messaging platform"
    )
    name: str = Field(
        ..., description="Human-readable channel name"
    )
    status: ChannelStatus = Field(
        default=ChannelStatus.DISCONNECTED,
        description="Current connection status"
    )
    config: ChannelConfig = Field(
        default_factory=ChannelConfig,
        description="Channel-specific configuration"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ------------------------------------------------------------------------------
# Agent Models
# ------------------------------------------------------------------------------

class AgentCapability(BaseModel):
    """Represents a capability or skill of an agent."""

    name: str = Field(..., description="Capability name (e.g., 'code_execution')")
    description: str | None = Field(
        default=None,
        description="Human-readable description"
    )
    enabled: bool = Field(
        default=True,
        description="Whether this capability is currently enabled"
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Capability-specific configuration"
    )

    model_config = {"populate_by_name": True}


class Agent(TimestampedModel):
    """
    Represents an AI agent in the TinyClaw system.

    An agent is an autonomous AI entity that can send/receive messages
    through configured channels and perform tasks using its capabilities.

    Attributes:
        agent_id: Unique identifier for the agent
        name: Human-readable agent name
        description: Agent description/purpose
        status: Current operational status
        channels: List of channel IDs this agent can use
        capabilities: List of agent capabilities/skills
        config: Agent-specific configuration

    Example:
        >>> agent = Agent(
        ...     agent_id="agent-001",
        ...     name="CodeAssistant",
        ...     description="Helps with coding tasks",
        ...     status=AgentStatus.ACTIVE,
        ...     channels=["ch-123", "ch-456"],
        ...     capabilities=[{"name": "code_execution", "enabled": True}]
        ... )
    """

    agent_id: str = Field(..., description="Unique identifier for the agent")
    name: str = Field(..., description="Human-readable agent name")
    description: str | None = Field(
        default=None,
        description="Agent description or purpose"
    )
    status: AgentStatus = Field(
        default=AgentStatus.INACTIVE,
        description="Current operational status"
    )
    channels: list[str] = Field(
        default_factory=list,
        description="List of channel IDs this agent is connected to"
    )
    capabilities: list[AgentCapability] = Field(
        default_factory=list,
        description="Agent capabilities and skills"
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific configuration"
    )
    team_id: str | None = Field(
        default=None,
        description="ID of the team this agent belongs to"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("agent_id", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


# ------------------------------------------------------------------------------
# Message Models
# ------------------------------------------------------------------------------

class Message(TimestampedModel):
    """
    Represents a message in the TinyClaw system.

    Messages are routed between channels and can be sent by or received
    by agents. The system supports cross-channel message routing.

    Attributes:
        message_id: Unique identifier for the message
        agent_id: ID of the agent associated with this message
        channel_id: ID of the channel where this message was sent/received
        content: Message content/text
        direction: Whether message is incoming, outgoing, or internal
        status: Message delivery status
        metadata: Additional message context and metadata

    Example:
        >>> message = Message(
        ...     message_id="msg-001",
        ...     agent_id="agent-001",
        ...     channel_id="ch-123",
        ...     content="Hello, world!",
        ...     direction=MessageDirection.OUTGOING,
        ...     metadata={"source": "user_request"}
        ... )
    """

    message_id: str = Field(..., description="Unique identifier for the message")
    agent_id: str = Field(..., description="ID of the agent associated with this message")
    channel_id: str = Field(..., description="ID of the channel for this message")
    content: str = Field(..., description="Message content/text")
    direction: MessageDirection = Field(
        ..., description="Message direction (incoming/outgoing/internal)"
    )
    status: str = Field(
        default="pending",
        description="Message delivery status (pending, sent, failed)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message context and metadata"
    )
    parent_message_id: str | None = Field(
        default=None,
        description="ID of parent message if this is a reply"
    )
    thread_id: str | None = Field(
        default=None,
        description="ID of the thread this message belongs to"
    )

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @field_validator("message_id", "agent_id", "channel_id", "content")
    @classmethod
    def validate_required_fields(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v


# ------------------------------------------------------------------------------
# Team Models
# ------------------------------------------------------------------------------

class RoutingConfig(BaseModel):
    """Configuration for routing messages within an agent team."""

    strategy: str = Field(
        default="round_robin",
        description="Routing strategy: round_robin, load_balanced, specialized"
    )
    fallback_agent: str | None = Field(
        default=None,
        description="Agent to use as fallback if primary is unavailable"
    )
    timeout_seconds: int = Field(
        default=30,
        description="Timeout for agent response in seconds"
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts on failure"
    )

    model_config = {"populate_by_name": True}


class AgentTeam(TimestampedModel):
    """
    Represents a team of agents working together in TinyClaw.

    Agent teams allow multiple agents to collaborate on tasks, with
    configurable routing strategies for distributing messages.

    Attributes:
        team_id: Unique identifier for the team
        name: Human-readable team name
        description: Team description/purpose
        agent_ids: List of agent IDs in this team
        routing_config: Configuration for message routing within team

    Example:
        >>> team = AgentTeam(
        ...     team_id="team-001",
        ...     name="CustomerSupport",
        ...     agent_ids=["agent-001", "agent-002"],
        ...     routing_config={"strategy": "load_balanced"}
        ... )
    """

    team_id: str = Field(..., description="Unique identifier for the team")
    name: str = Field(..., description="Human-readable team name")
    description: str | None = Field(
        default=None,
        description="Team description or purpose"
    )
    agent_ids: list[str] = Field(
        default_factory=list,
        description="List of agent IDs in this team"
    )
    routing_config: RoutingConfig = Field(
        default_factory=RoutingConfig,
        description="Configuration for message routing within team"
    )
    active: bool = Field(
        default=True,
        description="Whether the team is currently active"
    )

    model_config = {"populate_by_name": True}

    @field_validator("team_id", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


# ------------------------------------------------------------------------------
# Request/Response Models
# ------------------------------------------------------------------------------

class CreateAgentRequest(BaseModel):
    """Request model for creating a new agent."""

    name: str = Field(..., description="Agent name")
    description: str | None = Field(default=None, description="Agent description")
    channels: list[str] = Field(default_factory=list, description="Channel IDs to connect")
    capabilities: list[AgentCapability] = Field(
        default_factory=list,
        description="Agent capabilities"
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Agent configuration")
    team_id: str | None = Field(default=None, description="Team ID to assign agent to")

    model_config = {"populate_by_name": True}


class CreateMessageRequest(BaseModel):
    """Request model for sending a message."""

    agent_id: str = Field(..., description="Agent ID to send message as")
    channel_id: str = Field(..., description="Channel ID to send message to")
    content: str = Field(..., description="Message content")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message metadata"
    )
    parent_message_id: str | None = Field(
        default=None,
        description="Parent message ID if replying"
    )

    model_config = {"populate_by_name": True}


class CreateTeamRequest(BaseModel):
    """Request model for creating an agent team."""

    name: str = Field(..., description="Team name")
    description: str | None = Field(default=None, description="Team description")
    agent_ids: list[str] = Field(default_factory=list, description="Agent IDs to add to team")
    routing_config: RoutingConfig | None = Field(
        default=None,
        description="Team routing configuration"
    )

    model_config = {"populate_by_name": True}


class AgentListResponse(BaseModel):
    """Response model for listing agents."""

    agents: list[Agent] = Field(default_factory=list, description="List of agents")
    total: int = Field(default=0, description="Total number of agents")

    model_config = {"populate_by_name": True}


class MessageListResponse(BaseModel):
    """Response model for listing messages."""

    messages: list[Message] = Field(default_factory=list, description="List of messages")
    total: int = Field(default=0, description="Total number of messages")

    model_config = {"populate_by_name": True}


class TeamListResponse(BaseModel):
    """Response model for listing teams."""

    teams: list[AgentTeam] = Field(default_factory=list, description="List of teams")
    total: int = Field(default=0, description="Total number of teams")

    model_config = {"populate_by_name": True}


# Export all models
__all__ = [
    # Enums
    "AgentStatus",
    "ChannelType",
    "MessageDirection",
    "ChannelStatus",
    # Models
    "Channel",
    "ChannelConfig",
    "Agent",
    "AgentCapability",
    "Message",
    "AgentTeam",
    "RoutingConfig",
    # Request/Response
    "CreateAgentRequest",
    "CreateMessageRequest",
    "CreateTeamRequest",
    "AgentListResponse",
    "MessageListResponse",
    "TeamListResponse",
    # Base
    "TimestampedModel",
]
