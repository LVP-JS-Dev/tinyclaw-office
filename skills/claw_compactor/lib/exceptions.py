#!/usr/bin/env python3
"""Custom exceptions for claw-compactor."""


class MemCompressError(Exception):
    """Base exception for memory compression errors."""

    pass


class FileNotFoundError_(MemCompressError):
    """File not found during compression."""

    pass


class WorkspaceError(MemCompressError):
    """Workspace validation error."""

    pass


class DictionaryError(MemCompressError):
    """Dictionary compression error."""

    pass


class CompressionError(MemCompressError):
    """General compression error."""

    pass
