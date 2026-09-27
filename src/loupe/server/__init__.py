"""The HTTP API the UI reads from. Read-only over existing stores."""

from loupe.server.app import create_app

__all__ = ["create_app"]
