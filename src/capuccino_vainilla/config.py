"""Carga y validación de la configuración desde variables de entorno / .env.

Aplica *fail fast*: si falta una credencial obligatoria, la aplicación se
detiene en el arranque con un mensaje claro. La configuración se modela con
dataclasses inmutables (``frozen=True``) para evitar mutaciones accidentales.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .exceptions import ConfigError

# --------------------------------------------------------------------------- #
#  Helpers de lectura tipada de variables de entorno
# --------------------------------------------------------------------------- #

def _get_required(key: str) -> str:
    value = os.getenv(key)
    if not value or not value.strip():
        raise ConfigError(
            f"Falta la variable de entorno obligatoria '{key}'. "
            f"Revisá tu archivo .env (guiate por .env.example)."
        )
    return value.strip()


def _get_optional(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return value.strip() if value and value.strip() else default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"La variable '{key}' debe ser un entero; se recibió {raw!r}.") from exc


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"La variable '{key}' debe ser numérica; se recibió {raw!r}.") from exc


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "si", "sí", "on"}


def _validate_url(key: str, url: str) -> str:
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"La URL de '{key}' debe comenzar con http:// o https:// (valor: {url}).")
    return url.rstrip("/")


# --------------------------------------------------------------------------- #
#  Modelos de configuración
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class OdooConfig:
    url: str
    db: str
    username: str
    password: str


@dataclass(frozen=True)
class WooConfig:
    url: str
    consumer_key: str
    consumer_secret: str
    api_version: str
    verify_ssl: bool
    timeout: int


@dataclass(frozen=True)
class WebhookConfig:
    secret: str          # vacío => el servidor de webhooks se negará a arrancar
    path: str
    host: str
    port: int


@dataclass(frozen=True)
class RuntimeConfig:
    batch_size: int
    max_retries: int
    retry_delay: float
    log_level: str
    log_file: str
    state_file: str


@dataclass(frozen=True)
class WatcherConfig:
    interval: int          # segundos entre ciclos del watcher
    initial_full: bool     # primer arranque: reconciliar todo el catálogo
    state_file: str        # archivo del snapshot de huellas


@dataclass(frozen=True)
class AppConfig:
    odoo: OdooConfig
    woo: WooConfig
    webhook: WebhookConfig
    runtime: RuntimeConfig
    watcher: WatcherConfig


def load_config(env_file: str | None = None) -> AppConfig:
    """Construye la configuración inmutable validando lo obligatorio.

    Args:
        env_file: ruta opcional a un .env específico. Si es None, python-dotenv
            busca un .env en el árbol de directorios habitual.
    """
    load_dotenv(dotenv_path=env_file, override=False)

    odoo = OdooConfig(
        url=_validate_url("ODOO_URL", _get_required("ODOO_URL")),
        db=_get_required("ODOO_DB"),
        username=_get_required("ODOO_USERNAME"),
        password=_get_required("ODOO_PASSWORD"),
    )
    woo = WooConfig(
        url=_validate_url("WOO_URL", _get_required("WOO_URL")),
        consumer_key=_get_required("WOO_CONSUMER_KEY"),
        consumer_secret=_get_required("WOO_CONSUMER_SECRET"),
        api_version=_get_optional("WOO_API_VERSION", "wc/v3"),
        verify_ssl=_get_bool("WOO_VERIFY_SSL", True),
        timeout=_get_int("HTTP_TIMEOUT", 30),
    )
    webhook = WebhookConfig(
        secret=_get_optional("WEBHOOK_SECRET", ""),
        path=_get_optional("WEBHOOK_PATH", "/webhooks/woocommerce/orders"),
        host=_get_optional("WEBHOOK_HOST", "0.0.0.0"),
        port=_get_int("WEBHOOK_PORT", 8000),
    )
    runtime = RuntimeConfig(
        batch_size=_get_int("BATCH_SIZE", 50),
        max_retries=_get_int("MAX_RETRIES", 3),
        retry_delay=_get_float("RETRY_DELAY", 2.0),
        log_level=_get_optional("LOG_LEVEL", "INFO").upper(),
        log_file=_get_optional("LOG_FILE", "sync.log"),
        state_file=_get_optional("STATE_FILE", ".sync_state.json"),
    )
    interval = _get_int("WATCH_INTERVAL", 30)
    if interval <= 0:
        raise ConfigError(f"WATCH_INTERVAL debe ser mayor que 0; se recibió {interval}.")
    watcher = WatcherConfig(
        interval=interval,
        initial_full=_get_bool("WATCH_INITIAL_FULL", True),
        state_file=_get_optional("WATCH_STATE_FILE", ".watch_snapshot.json"),
    )
    return AppConfig(odoo=odoo, woo=woo, webhook=webhook, runtime=runtime, watcher=watcher)
