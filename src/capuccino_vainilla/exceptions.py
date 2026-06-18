"""Jerarquía de excepciones del conector.

Tener excepciones tipadas permite que las capas superiores (servicios, webhook,
CLI) decidan con precisión qué hacer ante cada clase de error: reintentar,
omitir el ítem (*skip controlado*) o abortar.
"""

from __future__ import annotations


class ConnectorError(Exception):
    """Base de todos los errores del conector."""


class ConfigError(ConnectorError):
    """Configuración inválida o incompleta (credenciales o variables faltantes)."""


class OdooError(ConnectorError):
    """Error operando contra la API XML-RPC de Odoo."""


class OdooAuthError(OdooError):
    """Falla de autenticación contra Odoo (credenciales/DB inválidas)."""


class WooError(ConnectorError):
    """Error operando contra la WooCommerce REST API."""


class WooTransientError(WooError):
    """Error transitorio de Woo (5xx, 429 o de red): elegible para reintento."""


class MappingError(ConnectorError):
    """No se pudo transformar/validar un registro entre ambos sistemas."""


class WebhookSignatureError(ConnectorError):
    """Firma HMAC del webhook ausente o inválida."""
