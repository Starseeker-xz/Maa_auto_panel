from __future__ import annotations


class InvalidRequest(ValueError):
    """The request is syntactically valid but invalid for the requested operation."""


class ResourceNotFound(FileNotFoundError):
    """A resource explicitly addressed by the request does not exist."""


class Conflict(RuntimeError):
    """The request conflicts with the current application state."""


class CorruptState(RuntimeError):
    """Persisted application state exists but cannot be safely interpreted."""


class RuntimeUnavailable(RuntimeError):
    """A required runtime or external execution environment is unavailable."""
