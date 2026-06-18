"""Salvaguardas para no escribir nunca en un Odoo de producción."""

from __future__ import annotations

from urllib.parse import urlparse

from ..exceptions import ConnectorError

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "odoo", "::1"}


class TargetNotLocalError(ConnectorError):
    """El destino del seed no parece un Odoo local."""


def assert_local_target(url: str) -> None:
    """Lanza TargetNotLocalError si la URL destino no es local."""
    host = (urlparse(url).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        raise TargetNotLocalError(
            f"El destino '{url}' (host={host!r}) no parece local. "
            f"El seed solo escribe en {sorted(_LOCAL_HOSTS)}. "
            f"Abortando para proteger producción."
        )


def confirmation_banner(target_url: str, source_url: str) -> str:
    return (
        "============================================================\n"
        "  SEED ODOO -> ODOO\n"
        f"  LEE de  (origen): {source_url}\n"
        f"  ESCRIBE en (dest): {target_url}\n"
        "============================================================"
    )
