"""Configuración del seeder: dos conexiones Odoo (origen real, destino local).

Lee un archivo .env.seed con bloques ODOO_SRC_* y ODOO_DST_*. Reusa OdooConfig
y la validación de URL del módulo de configuración principal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from ..config import OdooConfig, _get_optional_int, _validate_url
from ..exceptions import ConfigError


@dataclass(frozen=True)
class SeederConfig:
    source: OdooConfig  # Odoo real (solo lectura)
    target: OdooConfig  # Odoo local (destino de escritura)


def _required(key: str) -> str:
    value = os.getenv(key)
    if not value or not value.strip():
        raise ConfigError(
            f"Falta la variable obligatoria '{key}' en .env.seed "
            f"(guiate por .env.seed.example)."
        )
    return value.strip()


def _odoo_config(prefix: str) -> OdooConfig:
    return OdooConfig(
        url=_validate_url(f"{prefix}_URL", _required(f"{prefix}_URL")),
        db=_required(f"{prefix}_DB"),
        username=_required(f"{prefix}_USERNAME"),
        password=_required(f"{prefix}_PASSWORD"),
        company_id=_get_optional_int(f"{prefix}_COMPANY_ID"),
    )


def load_seeder_config(env_file: str | None = None) -> SeederConfig:
    """Carga la config del seeder desde un .env.seed (o el entorno)."""
    load_dotenv(dotenv_path=env_file, override=True)
    return SeederConfig(
        source=_odoo_config("ODOO_SRC"),
        target=_odoo_config("ODOO_DST"),
    )
