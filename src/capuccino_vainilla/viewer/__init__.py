"""Visor web (dashboard) del conector: estado, catálogo y flujos en vivo."""

from __future__ import annotations

from .app import create_viewer_app
from .service import ViewerService

__all__ = ["create_viewer_app", "ViewerService"]
