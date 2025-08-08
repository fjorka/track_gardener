"""Custom exceptions for the configuration loading pipeline."""


class ConfigFormatError(Exception):
    """Raised for errors in the config file's structure, syntax, or types."""


class ConfigEnvironmentError(Exception):
    """Raised for errors related to the runtime environment (files, DB, etc.)."""
