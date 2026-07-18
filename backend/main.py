"""Compatibility entry point for ``uvicorn backend.main:app``."""

from .app.main import app

__all__ = ["app"]

