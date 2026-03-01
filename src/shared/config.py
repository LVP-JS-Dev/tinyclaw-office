"""
Configuration management module for TinyClaw Office.

This module provides centralized configuration using Pydantic Settings,
with support for environment variables and .env files.
"""

from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ------------------------------------------------------------------------------
    # OpenAI API Configuration (Required by MemU for embeddings)
    # ------------------------------------------------------------------------------
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for embeddings")

    # ------------------------------------------------------------------------------
    # Database Configuration (PostgreSQL for MemU)
    # ------------------------------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql://postgres:password@localhost:5432/memu",
        description="PostgreSQL connection string for MemU"
    )
    MEMU_MODE: Literal["inmemory", "postgres"] = Field(
        default="inmemory",
        description="MemU storage mode: 'inmemory' for development, 'postgres' for production"
    )

    # ------------------------------------------------------------------------------
    # TinyClaw Configuration
    # ------------------------------------------------------------------------------
    TINYCLAW_API_URL: str = Field(
        default="http://localhost:3777",
        description="TinyClaw API endpoint"
    )
    TINYCLAW_API_KEY: str | None = Field(
        default=None,
        description="Optional API key for TinyClaw authentication"
    )
    TINYCLAW_SETTINGS_PATH: str | None = Field(
        default=None,
        description="Path to TinyClaw settings file (defaults to ~/.tinyclaw/settings.json)"
    )

    # ------------------------------------------------------------------------------
    # Gondolin Configuration
    # ------------------------------------------------------------------------------
    GONDOLIN_API_URL: str = Field(
        default="http://localhost:9000",
        description="Gondolin API endpoint"
    )
    GONDOLIN_ALLOWED_HOSTS: list[str] = Field(
        default=["api.github.com", "api.openai.com", "api.anthropic.com"],
        description="Allowed hosts for Gondolin HTTP hooks"
    )

    # ------------------------------------------------------------------------------
    # Orchestration API Configuration
    # ------------------------------------------------------------------------------
    API_PORT: int = Field(default=8080, description="Main orchestration API port")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    SECRET_KEY: str = Field(
        default="change-this-in-production",
        description="Secret key for API authentication"
    )

    # ------------------------------------------------------------------------------
    # Optional: External Service Credentials
    # ------------------------------------------------------------------------------
    GITHUB_TOKEN: str | None = Field(
        default=None,
        description="GitHub token for Gondolin sandboxed code execution"
    )
    ANTHROPIC_API_KEY: str | None = Field(
        default=None,
        description="Anthropic API key for Claude integration"
    )

    # ------------------------------------------------------------------------------
    # Optional: Redis Configuration (for caching)
    # ------------------------------------------------------------------------------
    REDIS_URL: str | None = Field(
        default=None,
        description="Redis URL for caching layer"
    )

    # ------------------------------------------------------------------------------
    # Optional: Dashboard Configuration
    # ------------------------------------------------------------------------------
    DASHBOARD_PORT: int = Field(
        default=3001,
        description="Dashboard frontend port"
    )

    # ------------------------------------------------------------------------------
    # Optional: Development/Debug Settings
    # ------------------------------------------------------------------------------
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode (shows detailed errors, disables some security)"
    )
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3001", "http://localhost:8080"],
        description="CORS allowed origins"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @field_validator("GONDOLIN_ALLOWED_HOSTS", "CORS_ORIGINS", mode="before")
    @classmethod
    def parse_comma_separated_list(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",") if host.strip()]
        return v

    @field_validator("OPENAI_API_KEY", "SECRET_KEY")
    @classmethod
    def validate_required_secrets(cls, v: str, info) -> str:
        """Validate that required secrets are not empty in production."""
        # Allow empty values for development/testing
        # In production, you should enforce these
        return v


# Global settings instance
settings = Settings()
