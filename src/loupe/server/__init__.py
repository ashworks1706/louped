"""The HTTP API the UI reads from: read-only over existing stores, plus the Playground."""

from loupe.server.app import create_app

__all__ = ["create_app"]
