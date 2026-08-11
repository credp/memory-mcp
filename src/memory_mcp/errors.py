class MemoryError(Exception):
    """A safe, user-facing memory repository error."""


class InvalidPathError(MemoryError):
    """A path was invalid or escaped the configured repository."""


class RepositoryError(MemoryError):
    """The configured repository or a Git operation was invalid."""

