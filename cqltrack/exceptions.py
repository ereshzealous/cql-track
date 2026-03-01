class CqlTrackError(Exception):
    """Base exception for cqltrack."""


class LockError(CqlTrackError):
    """Failed to acquire or release the migration lock."""


class MigrationError(CqlTrackError):
    """Something went wrong running a migration."""


class ChecksumMismatch(CqlTrackError):
    """An applied migration file was modified after it ran."""


class ParseError(CqlTrackError):
    """Could not parse a migration file."""


class ConfigError(CqlTrackError):
    """Bad or missing configuration."""
