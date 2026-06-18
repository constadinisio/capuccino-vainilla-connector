# Odoo local en Docker + seed de productos — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levantar un Odoo 16 local en Docker y poblarlo con una copia fiel (productos + atributos + ventas cruzadas) del Odoo de producción, leyendo el real en modo solo-lectura, para testear el conector sin riesgo.

**Architecture:** Se agrega un profile `odoo` al `docker-compose.yml` (Postgres + Odoo 16 Community). Un nuevo módulo `seeder` (independiente del CLI principal) abre **dos** conexiones `OdooClient`: el origen se envuelve en un wrapper de solo-lectura, el destino recibe las escrituras. La copia se hace en tres pasadas (atributos → productos → cross-sells) con remapeo explícito de IDs entre instancias e idempotencia por `name`/`default_code`.

**Tech Stack:** Python 3.10+, `xmlrpc.client` (vía el `OdooClient` existente), pytest, Docker Compose, imagen `odoo:16`, `postgres:15`.

## Global Constraints

- Python `>=3.10`; layout `src/` (paquete `capuccino_vainilla`). Tests en `tests/`.
- Estilo inmutable: configuración con `@dataclass(frozen=True)`; nunca mutar registros leídos, construir dicts nuevos.
- El conector ya define el protocolo `OdooApi` en `src/capuccino_vainilla/clients/protocols.py` con: `search_count`, `search_read`, `read`, `create`, `write`. Todo doble de prueba debe cumplirlo.
- Campos de producto a copiar (verbatim de `catalog_sync.py`): `id`, `name`, `default_code`, `list_price`, `description_sale`, `qty_available`, `attribute_line_ids`, `optional_product_ids`.
- **`qty_available` es un campo calculado de stock en Odoo: NO se escribe vía `create`/`write`.** Se lee pero no se replica el stock exacto (limitación documentada).
- Ruff line-length 100; correr `ruff check` y `pytest` antes de cada commit.
- **Git:** el proyecto NO es un repo git todavía. Si no se corre `git init`, omití los pasos de commit (`git add/commit`) — el resto del plan es válido igual.
- Cobertura objetivo ≥80% en el módulo `seeder`.

---

## File Structure

**Nuevos:**
- `src/capuccino_vainilla/seeder/__init__.py` — exporta API pública del módulo.
- `src/capuccino_vainilla/seeder/config.py` — `SeederConfig`, `load_seeder_config()` (lee `.env.seed`, dos `OdooConfig`).
- `src/capuccino_vainilla/seeder/readonly.py` — `ReadOnlyOdoo`, `ReadOnlyViolation` (garantía de no escribir en origen).
- `src/capuccino_vainilla/seeder/safety.py` — `assert_local_target()`, `TargetNotLocalError`, banner de confirmación.
- `src/capuccino_vainilla/seeder/product_seeder.py` — `ProductSeeder`, `AttributeMaps`, `SeedReport`.
- `src/capuccino_vainilla/seeder/cli.py` — `main()` (entrypoint `seed-odoo`).
- `.env.seed.example` — plantilla de credenciales origen/destino.
- `tests/seeder/__init__.py`, `tests/seeder/fakes.py` — doble `FakeOdoo`.
- `tests/seeder/test_config.py`, `test_readonly.py`, `test_product_seeder.py`, `test_safety.py`.

**Modificados:**
- `docker-compose.yml` — profile `odoo` (servicios `odoo-db`, `odoo`).
- `pyproject.toml:32-33` — agregar script `seed-odoo`.
- `.gitignore` — agregar `.env.seed`.

---

## Task 1: Profile `odoo` en Docker + plantillas de entorno

**Files:**
- Modify: `docker-compose.yml` (agregar servicios y volúmenes)
- Create: `.env.seed.example`
- Modify: `.gitignore` (crear si no existe)

**Interfaces:**
- Produces: servicio Odoo accesible en `http://localhost:8069`; archivo `.env.seed.example` con las variables `ODOO_SRC_*` y `ODOO_DST_*`.

- [ ] **Step 1: Agregar servicios `odoo-db` y `odoo` al `docker-compose.yml`**

Insertar antes de la sección `volumes:` (después del bloque `woo-cli`):

```yaml
  # --- Entorno de prueba Odoo (solo con --profile odoo) ---
  odoo-db:
    image: postgres:15
    profiles: ["odoo"]
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
    volumes:
      - odoo-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 10s
      timeout: 5s
      retries: 10

  odoo:
    image: odoo:16
    profiles: ["odoo"]
    depends_on:
      odoo-db:
        condition: service_healthy
    ports:
      - "8069:8069"
    environment:
      HOST: odoo-db
      USER: odoo
      PASSWORD: odoo
    volumes:
      - odoo-data:/var/lib/odoo
```

- [ ] **Step 2: Declarar los volúmenes nuevos**

Modificar la sección `volumes:` al final del archivo para que quede:

```yaml
volumes:
  woo-db-data:
  woo-data:
  odoo-db-data:
  odoo-data:
```

- [ ] **Step 3: Crear `.env.seed.example`**

```bash
# ==============================================================================
#  SEED ODOO -> ODOO  (copia de productos del real al local)
#  Copiá este archivo a ".env.seed" y completá. NUNCA subas .env.seed al repo.
# ==============================================================================

# ----- ORIGEN: Odoo real de la empresa (SOLO LECTURA) -----
# Usá idealmente una API key de un usuario de solo lectura.
ODOO_SRC_URL=https://capuccino-vainilla.odoo.com
ODOO_SRC_DB=capuccino_vainilla
ODOO_SRC_USERNAME=integraciones@pinnacle.com
ODOO_SRC_PASSWORD=tu_api_key_de_odoo

# ----- DESTINO: Odoo local en Docker (se escribe acá) -----
ODOO_DST_URL=http://localhost:8069
ODOO_DST_DB=capuccino_test
ODOO_DST_USERNAME=admin
ODOO_DST_PASSWORD=admin
```

- [ ] **Step 4: Agregar `.env.seed` al `.gitignore`**

Agregar la línea (crear el archivo si no existe):

```
.env.seed
```

- [ ] **Step 5: Verificación manual — levantar Odoo**

Run: `docker compose --profile odoo up -d`
Luego: `docker compose ps`
Expected: servicios `odoo-db` (healthy) y `odoo` (running). Abrir `http://localhost:8069` en el navegador muestra el asistente de creación de base de datos de Odoo. Crear una base llamada `capuccino_test` con email `admin` / contraseña `admin` (master password la que pida el asistente). Anotar esos datos en `.env.seed`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.seed.example .gitignore
git commit -m "feat: add odoo local docker profile and seed env template"
```

---

## Task 2: Configuración dual del seeder (`SeederConfig`)

**Files:**
- Create: `src/capuccino_vainilla/seeder/__init__.py`
- Create: `src/capuccino_vainilla/seeder/config.py`
- Test: `tests/seeder/__init__.py`, `tests/seeder/test_config.py`

**Interfaces:**
- Consumes: `OdooConfig` (frozen dataclass: `url`, `db`, `username`, `password`) de `capuccino_vainilla.config`; helper `_validate_url` del mismo módulo; `ConfigError` de `capuccino_vainilla.exceptions`.
- Produces: `SeederConfig(source: OdooConfig, target: OdooConfig)` y `load_seeder_config(env_file: str | None = None) -> SeederConfig`.

- [ ] **Step 1: Crear `tests/seeder/__init__.py` vacío**

```python
```

- [ ] **Step 2: Escribir el test que falla**

Crear `tests/seeder/test_config.py`:

```python
import pytest

from capuccino_vainilla.exceptions import ConfigError
from capuccino_vainilla.seeder.config import SeederConfig, load_seeder_config


def _write_env(tmp_path, body: str) -> str:
    path = tmp_path / ".env.seed"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_load_seeder_config_parses_source_and_target(tmp_path):
    env = _write_env(tmp_path, (
        "ODOO_SRC_URL=https://real.odoo.com\n"
        "ODOO_SRC_DB=real_db\n"
        "ODOO_SRC_USERNAME=bot@x.com\n"
        "ODOO_SRC_PASSWORD=key123\n"
        "ODOO_DST_URL=http://localhost:8069\n"
        "ODOO_DST_DB=test_db\n"
        "ODOO_DST_USERNAME=admin\n"
        "ODOO_DST_PASSWORD=admin\n"
    ))
    cfg = load_seeder_config(env)
    assert isinstance(cfg, SeederConfig)
    assert cfg.source.url == "https://real.odoo.com"
    assert cfg.source.db == "real_db"
    assert cfg.target.url == "http://localhost:8069"
    assert cfg.target.username == "admin"


def test_load_seeder_config_missing_var_raises(tmp_path):
    env = _write_env(tmp_path, "ODOO_SRC_URL=https://real.odoo.com\n")
    with pytest.raises(ConfigError):
        load_seeder_config(env)
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capuccino_vainilla.seeder'`.

- [ ] **Step 4: Crear `src/capuccino_vainilla/seeder/__init__.py`**

```python
"""Herramientas de seed: copia de productos del Odoo real a un Odoo local."""
```

- [ ] **Step 5: Implementar `config.py`**

Crear `src/capuccino_vainilla/seeder/config.py`:

```python
"""Configuración del seeder: dos conexiones Odoo (origen real, destino local).

Lee un archivo .env.seed con bloques ODOO_SRC_* y ODOO_DST_*. Reusa OdooConfig
y la validación de URL del módulo de configuración principal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from ..config import OdooConfig, _validate_url
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
    )


def load_seeder_config(env_file: str | None = None) -> SeederConfig:
    """Carga la config del seeder desde un .env.seed (o el entorno)."""
    load_dotenv(dotenv_path=env_file, override=True)
    return SeederConfig(
        source=_odoo_config("ODOO_SRC"),
        target=_odoo_config("ODOO_DST"),
    )
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add src/capuccino_vainilla/seeder/ tests/seeder/
git commit -m "feat(seeder): dual odoo config loader from .env.seed"
```

---

## Task 3: Wrapper de solo-lectura (`ReadOnlyOdoo`)

**Files:**
- Create: `src/capuccino_vainilla/seeder/readonly.py`
- Test: `tests/seeder/test_readonly.py`

**Interfaces:**
- Consumes: protocolo `OdooApi` (cualquier objeto con `search_count`/`search_read`/`read`/`create`/`write`).
- Produces: `ReadOnlyOdoo(inner: OdooApi)` que delega lectura y lanza `ReadOnlyViolation` en `create`/`write`. Cumple `OdooApi`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/seeder/test_readonly.py`:

```python
import pytest

from capuccino_vainilla.seeder.readonly import ReadOnlyOdoo, ReadOnlyViolation


class _Spy:
    def __init__(self):
        self.calls = []

    def search_count(self, model, domain):
        self.calls.append(("search_count", model))
        return 0

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        self.calls.append(("search_read", model))
        return [{"id": 1}]

    def read(self, model, ids, fields):
        self.calls.append(("read", model))
        return [{"id": ids[0]}]

    def create(self, model, values):
        self.calls.append(("create", model))
        return 99

    def write(self, model, ids, values):
        self.calls.append(("write", model))
        return True


def test_read_methods_delegate():
    spy = _Spy()
    ro = ReadOnlyOdoo(spy)
    assert ro.search_read("product.template", [], ["id"]) == [{"id": 1}]
    assert ro.read("product.template", [5], ["id"]) == [{"id": 5}]
    assert ro.search_count("product.template", []) == 0
    assert ("create", "product.template") not in spy.calls


def test_create_raises_readonly_violation():
    ro = ReadOnlyOdoo(_Spy())
    with pytest.raises(ReadOnlyViolation):
        ro.create("product.template", {"name": "x"})


def test_write_raises_readonly_violation():
    ro = ReadOnlyOdoo(_Spy())
    with pytest.raises(ReadOnlyViolation):
        ro.write("product.template", [1], {"name": "x"})
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_readonly.py -v`
Expected: FAIL — `ModuleNotFoundError: ... seeder.readonly`.

- [ ] **Step 3: Implementar `readonly.py`**

```python
"""Wrapper que garantiza, por contrato, que el origen nunca se modifica."""

from __future__ import annotations

from ..clients.protocols import OdooApi
from ..exceptions import ConnectorError


class ReadOnlyViolation(ConnectorError):
    """Se intentó escribir a través de una conexión marcada como solo-lectura."""


class ReadOnlyOdoo:
    """Envuelve un OdooApi exponiendo solo lectura; create/write fallan."""

    def __init__(self, inner: OdooApi):
        self._inner = inner

    def search_count(self, model: str, domain: list) -> int:
        return self._inner.search_count(model, domain)

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        return self._inner.search_read(model, domain, fields, offset, limit, order)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self._inner.read(model, ids, fields)

    def create(self, model: str, values: dict) -> int:
        raise ReadOnlyViolation(
            f"Intento de create en conexión de solo-lectura (model={model})."
        )

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        raise ReadOnlyViolation(
            f"Intento de write en conexión de solo-lectura (model={model})."
        )
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_readonly.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/seeder/readonly.py tests/seeder/test_readonly.py
git commit -m "feat(seeder): read-only odoo wrapper to protect production"
```

---

## Task 4: Doble `FakeOdoo` + pasada de atributos

**Files:**
- Create: `tests/seeder/fakes.py`
- Create: `src/capuccino_vainilla/seeder/product_seeder.py`
- Test: `tests/seeder/test_product_seeder.py`

**Interfaces:**
- Produces: `FakeOdoo` (cumple `OdooApi`, almacena registros por modelo, soporta dominios de igualdad). `AttributeMaps(attribute_ids: dict[int, int], value_ids: dict[int, int])`. `ProductSeeder(source, target, logger=None)` con método `seed_attributes() -> AttributeMaps`.

- [ ] **Step 1: Crear el doble `FakeOdoo`**

Crear `tests/seeder/fakes.py`:

```python
"""Doble de Odoo en memoria para tests del seeder.

Soporta solo dominios de igualdad: [("campo", "=", valor), ...] (los únicos
que el seeder usa). create() asigna ids incrementales por modelo.
"""

from __future__ import annotations


class FakeOdoo:
    def __init__(self, seed: dict[str, list[dict]] | None = None):
        # tables[model] = lista de dicts (cada uno con "id")
        self.tables: dict[str, list[dict]] = {}
        self._next_id: dict[str, int] = {}
        self.write_calls: list[tuple] = []
        for model, rows in (seed or {}).items():
            for row in rows:
                self._insert(model, dict(row))

    def _insert(self, model: str, row: dict) -> int:
        rid = row.get("id") or self._alloc(model)
        row["id"] = rid
        self.tables.setdefault(model, []).append(row)
        return rid

    def _alloc(self, model: str) -> int:
        nxt = self._next_id.get(model, 1)
        self._next_id[model] = nxt + 1
        return nxt

    def _matches(self, row: dict, domain: list) -> bool:
        for field, op, value in domain:
            if op != "=":
                raise NotImplementedError(f"FakeOdoo solo soporta '=', no {op!r}")
            if row.get(field) != value:
                return False
        return True

    def search_count(self, model, domain):
        return sum(1 for r in self.tables.get(model, []) if self._matches(r, domain))

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        rows = [r for r in self.tables.get(model, []) if self._matches(r, domain)]
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return [{f: r.get(f) for f in (["id"] + fields)} for r in rows]

    def read(self, model, ids, fields):
        by_id = {r["id"]: r for r in self.tables.get(model, [])}
        return [
            {f: by_id[i].get(f) for f in (["id"] + fields)}
            for i in ids if i in by_id
        ]

    def create(self, model, values):
        return self._insert(model, dict(values))

    def write(self, model, ids, values):
        self.write_calls.append((model, list(ids), dict(values)))
        by_id = {r["id"]: r for r in self.tables.get(model, [])}
        for i in ids:
            if i in by_id:
                by_id[i].update(values)
        return True
```

- [ ] **Step 2: Escribir el test que falla**

Crear `tests/seeder/test_product_seeder.py`:

```python
from capuccino_vainilla.seeder.product_seeder import AttributeMaps, ProductSeeder
from tests.seeder.fakes import FakeOdoo


def _source_with_attributes() -> FakeOdoo:
    return FakeOdoo({
        "product.attribute": [
            {"id": 10, "name": "Color"},
            {"id": 11, "name": "Tamaño"},
        ],
        "product.attribute.value": [
            {"id": 100, "name": "Rojo", "attribute_id": [10, "Color"]},
            {"id": 101, "name": "Azul", "attribute_id": [10, "Color"]},
            {"id": 102, "name": "Grande", "attribute_id": [11, "Tamaño"]},
        ],
    })


def test_seed_attributes_creates_and_maps_ids():
    source, target = _source_with_attributes(), FakeOdoo()
    maps = ProductSeeder(source, target).seed_attributes()

    assert isinstance(maps, AttributeMaps)
    # Todos los atributos y valores fueron mapeados.
    assert set(maps.attribute_ids.keys()) == {10, 11}
    assert set(maps.value_ids.keys()) == {100, 101, 102}
    # El valor "Rojo" en destino apunta al atributo destino mapeado de "Color".
    dst_color = maps.attribute_ids[10]
    rojo = [r for r in target.tables["product.attribute.value"]
            if r["name"] == "Rojo"][0]
    assert rojo["attribute_id"] == dst_color


def test_seed_attributes_is_idempotent():
    source, target = _source_with_attributes(), FakeOdoo()
    ProductSeeder(source, target).seed_attributes()
    ProductSeeder(source, target).seed_attributes()  # segunda corrida
    # No se duplican atributos ni valores.
    assert len(target.tables["product.attribute"]) == 2
    assert len(target.tables["product.attribute.value"]) == 3
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_product_seeder.py -v`
Expected: FAIL — `ModuleNotFoundError: ... seeder.product_seeder`.

- [ ] **Step 4: Implementar `product_seeder.py` (parte: atributos)**

Crear `src/capuccino_vainilla/seeder/product_seeder.py`:

```python
"""Copia de productos del Odoo origen al destino, en tres pasadas.

1) atributos  2) productos (con líneas de atributo)  3) ventas cruzadas.
Remapea IDs entre instancias e idempotencia por name/default_code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..clients.protocols import OdooApi
from ..logging_config import get_logger


@dataclass
class AttributeMaps:
    attribute_ids: dict[int, int] = field(default_factory=dict)
    value_ids: dict[int, int] = field(default_factory=dict)


@dataclass
class SeedReport:
    attributes_created: int = 0
    values_created: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0
    cross_sells_linked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "attributes_created": self.attributes_created,
            "values_created": self.values_created,
            "products_created": self.products_created,
            "products_updated": self.products_updated,
            "products_skipped": self.products_skipped,
            "cross_sells_linked": self.cross_sells_linked,
        }


class ProductSeeder:
    def __init__(self, source: OdooApi, target: OdooApi,
                 logger: logging.Logger | None = None):
        self._src = source
        self._dst = target
        self._log = logger or get_logger("seeder")
        self.report = SeedReport()

    def _find_or_create(self, model: str, domain: list, values: dict) -> tuple[int, bool]:
        """Devuelve (id_destino, creado?). Idempotente por el dominio dado."""
        existing = self._dst.search_read(model, domain, ["id"], limit=1)
        if existing:
            return int(existing[0]["id"]), False
        return int(self._dst.create(model, values)), True

    def seed_attributes(self) -> AttributeMaps:
        maps = AttributeMaps()

        for attr in self._src.search_read("product.attribute", [], ["name"]):
            dst_id, created = self._find_or_create(
                "product.attribute", [("name", "=", attr["name"])],
                {"name": attr["name"]},
            )
            maps.attribute_ids[int(attr["id"])] = dst_id
            if created:
                self.report.attributes_created += 1

        for val in self._src.search_read(
            "product.attribute.value", [], ["name", "attribute_id"]
        ):
            src_attr_id = val["attribute_id"][0]  # many2one -> [id, name]
            dst_attr_id = maps.attribute_ids[src_attr_id]
            dst_id, created = self._find_or_create(
                "product.attribute.value",
                [("name", "=", val["name"]), ("attribute_id", "=", dst_attr_id)],
                {"name": val["name"], "attribute_id": dst_attr_id},
            )
            maps.value_ids[int(val["id"])] = dst_id
            if created:
                self.report.values_created += 1

        self._log.info("Atributos copiados: %s, valores: %s",
                       self.report.attributes_created, self.report.values_created)
        return maps
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_product_seeder.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/capuccino_vainilla/seeder/product_seeder.py tests/seeder/fakes.py tests/seeder/test_product_seeder.py
git commit -m "feat(seeder): copy product attributes with id remapping"
```

---

## Task 5: Pasada de productos (`seed_products`)

**Files:**
- Modify: `src/capuccino_vainilla/seeder/product_seeder.py`
- Test: `tests/seeder/test_product_seeder.py` (agregar tests)

**Interfaces:**
- Consumes: `AttributeMaps` de Task 4.
- Produces: `ProductSeeder.seed_products(maps: AttributeMaps) -> dict[int, int]` (mapa template_id origen → destino). Crea productos por `default_code`, omite los sin SKU, escribe `attribute_line_ids` solo al crear (no al actualizar, para idempotencia).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/seeder/test_product_seeder.py`:

```python
def _source_with_products() -> FakeOdoo:
    return FakeOdoo({
        "product.attribute": [{"id": 10, "name": "Color"}],
        "product.attribute.value": [
            {"id": 100, "name": "Rojo", "attribute_id": [10, "Color"]},
        ],
        "product.template": [
            {"id": 1, "name": "Remera", "default_code": "REM-001",
             "list_price": 5000.0, "description_sale": "Algodón",
             "qty_available": 7.0, "attribute_line_ids": [500],
             "optional_product_ids": []},
            {"id": 2, "name": "Sin SKU", "default_code": False,
             "list_price": 100.0, "description_sale": "",
             "qty_available": 0.0, "attribute_line_ids": [],
             "optional_product_ids": []},
        ],
        "product.template.attribute.line": [
            {"id": 500, "attribute_id": [10, "Color"], "value_ids": [100]},
        ],
    })


def test_seed_products_creates_with_sku_and_skips_without():
    source, target = _source_with_products(), FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    tmpl_map = seeder.seed_products(maps)

    dst_products = target.tables["product.template"]
    assert len(dst_products) == 1                      # el sin SKU se omitió
    assert dst_products[0]["default_code"] == "REM-001"
    assert seeder.report.products_created == 1
    assert seeder.report.products_skipped == 1
    assert 1 in tmpl_map                               # template origen 1 mapeado
    # qty_available NO se escribe (campo calculado).
    assert "qty_available" not in dst_products[0]
    # La línea de atributo usa el value_id remapeado al destino.
    line_cmd = dst_products[0]["attribute_line_ids"][0]
    assert line_cmd[0] == 0  # comando (0, 0, {...})
    assert line_cmd[2]["value_ids"] == [(6, 0, [maps.value_ids[100]])]


def test_seed_products_idempotent_updates_not_duplicates():
    source, target = _source_with_products(), FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    seeder.seed_products(maps)

    seeder2 = ProductSeeder(source, target)
    seeder2.seed_products(seeder2.seed_attributes())
    assert len(target.tables["product.template"]) == 1   # no duplica
    assert seeder2.report.products_updated == 1
    # En update NO se reenvían attribute_line_ids (evita duplicar líneas).
    update_call = [c for c in target.write_calls if c[0] == "product.template"][-1]
    assert "attribute_line_ids" not in update_call[2]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_product_seeder.py -v`
Expected: FAIL — `AttributeError: 'ProductSeeder' object has no attribute 'seed_products'`.

- [ ] **Step 3: Implementar `seed_products` en `product_seeder.py`**

Agregar el import de los campos arriba del archivo (después de los imports existentes):

```python
from ..services.catalog_sync import ODOO_PRODUCT_FIELDS
```

Agregar estos métodos a la clase `ProductSeeder`:

```python
    def _attribute_line_commands(self, line_ids: list[int],
                                 maps: AttributeMaps) -> list:
        """Construye comandos (0,0,{...}) para attribute_line_ids remapeados."""
        if not line_ids:
            return []
        lines = self._src.read(
            "product.template.attribute.line", line_ids,
            ["attribute_id", "value_ids"],
        )
        commands = []
        for line in lines:
            dst_attr = maps.attribute_ids.get(line["attribute_id"][0])
            if dst_attr is None:
                continue
            dst_values = [maps.value_ids[v] for v in line["value_ids"]
                          if v in maps.value_ids]
            commands.append((0, 0, {
                "attribute_id": dst_attr,
                "value_ids": [(6, 0, dst_values)],
            }))
        return commands

    def seed_products(self, maps: AttributeMaps) -> dict[int, int]:
        template_map: dict[int, int] = {}
        products = self._src.search_read(
            "product.template", [], ODOO_PRODUCT_FIELDS, order="id",
        )
        for prod in products:
            sku = prod.get("default_code")
            if not sku:
                self.report.products_skipped += 1
                self._log.warning("Producto origen id=%s sin SKU. Se omite.", prod["id"])
                continue

            scalar = {
                "name": prod["name"],
                "default_code": sku,
                "list_price": prod.get("list_price") or 0.0,
                "description_sale": prod.get("description_sale") or "",
            }
            existing = self._dst.search_read(
                "product.template", [("default_code", "=", sku)], ["id"], limit=1,
            )
            if existing:
                dst_id = int(existing[0]["id"])
                self._dst.write("product.template", [dst_id], scalar)  # sin líneas
                self.report.products_updated += 1
            else:
                values = dict(scalar)
                values["attribute_line_ids"] = self._attribute_line_commands(
                    prod.get("attribute_line_ids") or [], maps,
                )
                dst_id = int(self._dst.create("product.template", values))
                self.report.products_created += 1
            template_map[int(prod["id"])] = dst_id

        self._log.info("Productos creados: %s, actualizados: %s, omitidos: %s",
                       self.report.products_created, self.report.products_updated,
                       self.report.products_skipped)
        return template_map
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_product_seeder.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/seeder/product_seeder.py tests/seeder/test_product_seeder.py
git commit -m "feat(seeder): copy product templates idempotently by SKU"
```

---

## Task 6: Pasada de ventas cruzadas (`seed_cross_sells`)

**Files:**
- Modify: `src/capuccino_vainilla/seeder/product_seeder.py`
- Test: `tests/seeder/test_product_seeder.py` (agregar test)

**Interfaces:**
- Consumes: `template_map: dict[int, int]` de `seed_products`.
- Produces: `ProductSeeder.seed_cross_sells(template_map: dict[int, int]) -> None`. Linkea `optional_product_ids` remapeados con comando `(6, 0, [ids])`; ignora referencias no mapeadas.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/seeder/test_product_seeder.py`:

```python
def test_seed_cross_sells_links_remapped_templates():
    source = FakeOdoo({
        "product.template": [
            {"id": 1, "name": "A", "default_code": "A-1", "list_price": 10.0,
             "description_sale": "", "qty_available": 0.0,
             "attribute_line_ids": [], "optional_product_ids": [2]},
            {"id": 2, "name": "B", "default_code": "B-1", "list_price": 20.0,
             "description_sale": "", "qty_available": 0.0,
             "attribute_line_ids": [], "optional_product_ids": []},
        ],
    })
    target = FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    tmpl_map = seeder.seed_products(maps)
    seeder.seed_cross_sells(tmpl_map)

    dst_a = [r for r in target.tables["product.template"]
             if r["default_code"] == "A-1"][0]
    assert dst_a["optional_product_ids"] == [(6, 0, [tmpl_map[2]])]
    assert seeder.report.cross_sells_linked == 1
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_product_seeder.py::test_seed_cross_sells_links_remapped_templates -v`
Expected: FAIL — `AttributeError: ... 'seed_cross_sells'`.

- [ ] **Step 3: Implementar `seed_cross_sells`**

Agregar a la clase `ProductSeeder`:

```python
    def seed_cross_sells(self, template_map: dict[int, int]) -> None:
        rows = self._src.search_read(
            "product.template", [], ["id", "optional_product_ids"],
        )
        for row in rows:
            src_opts = row.get("optional_product_ids") or []
            if not src_opts or int(row["id"]) not in template_map:
                continue
            dst_opts = [template_map[o] for o in src_opts if o in template_map]
            if not dst_opts:
                continue
            self._dst.write(
                "product.template", [template_map[int(row["id"])]],
                {"optional_product_ids": [(6, 0, dst_opts)]},
            )
            self.report.cross_sells_linked += 1
        self._log.info("Ventas cruzadas linkeadas: %s", self.report.cross_sells_linked)

    def run(self, *, limit: int | None = None) -> SeedReport:
        """Orquesta las tres pasadas y devuelve el reporte."""
        maps = self.seed_attributes()
        template_map = self.seed_products(maps)
        self.seed_cross_sells(template_map)
        return self.report
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_product_seeder.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/seeder/product_seeder.py tests/seeder/test_product_seeder.py
git commit -m "feat(seeder): link cross-sells in third pass and add run()"
```

---

## Task 7: Guard de destino local (`assert_local_target`)

**Files:**
- Create: `src/capuccino_vainilla/seeder/safety.py`
- Test: `tests/seeder/test_safety.py`

**Interfaces:**
- Produces: `TargetNotLocalError(ConnectorError)`; `assert_local_target(url: str) -> None` (lanza si la URL no es local); `confirmation_banner(target_url: str, source_url: str) -> str`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/seeder/test_safety.py`:

```python
import pytest

from capuccino_vainilla.seeder.safety import (
    TargetNotLocalError,
    assert_local_target,
    confirmation_banner,
)


@pytest.mark.parametrize("url", [
    "http://localhost:8069",
    "http://127.0.0.1:8069",
    "http://odoo:8069",          # nombre de servicio docker
])
def test_assert_local_target_accepts_local(url):
    assert_local_target(url)  # no lanza


@pytest.mark.parametrize("url", [
    "https://capuccino-vainilla.odoo.com",
    "https://produccion.empresa.com",
])
def test_assert_local_target_rejects_remote(url):
    with pytest.raises(TargetNotLocalError):
        assert_local_target(url)


def test_confirmation_banner_mentions_both_urls():
    banner = confirmation_banner("http://localhost:8069", "https://real.odoo.com")
    assert "http://localhost:8069" in banner
    assert "https://real.odoo.com" in banner
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `pytest tests/seeder/test_safety.py -v`
Expected: FAIL — `ModuleNotFoundError: ... seeder.safety`.

- [ ] **Step 3: Implementar `safety.py`**

```python
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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `pytest tests/seeder/test_safety.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/seeder/safety.py tests/seeder/test_safety.py
git commit -m "feat(seeder): abort seed if target is not a local odoo"
```

---

## Task 8: Entrypoint CLI `seed-odoo`

**Files:**
- Create: `src/capuccino_vainilla/seeder/cli.py`
- Modify: `src/capuccino_vainilla/seeder/__init__.py` (re-exportar)
- Modify: `pyproject.toml:32-33` (script)

**Interfaces:**
- Consumes: `load_seeder_config`, `ReadOnlyOdoo`, `ProductSeeder`, `assert_local_target`, `confirmation_banner`, `OdooClient`, `RuntimeConfig`.
- Produces: `main(argv: list[str] | None = None) -> int`; comando de consola `seed-odoo`.

- [ ] **Step 1: Implementar `cli.py`**

```python
"""Entrypoint `seed-odoo`: copia productos del Odoo real a un Odoo local.

Uso:
    seed-odoo --env-file .env.seed [--limit N] [--yes]
"""

from __future__ import annotations

import argparse
import sys

from ..clients.odoo_client import OdooClient
from ..config import RuntimeConfig
from ..exceptions import ConnectorError
from ..logging_config import get_logger, setup_logging
from .config import load_seeder_config
from .product_seeder import ProductSeeder
from .readonly import ReadOnlyOdoo
from .safety import assert_local_target, confirmation_banner

# Runtime mínimo para los reintentos del OdooClient (no se lee de .env.seed).
_RUNTIME = RuntimeConfig(
    batch_size=50, max_retries=3, retry_delay=2.0,
    log_level="INFO", log_file="seed.log", state_file=".seed_state.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed-odoo",
        description="Copia productos del Odoo real (lectura) a un Odoo local.",
    )
    parser.add_argument("--env-file", default=".env.seed",
                        help="Ruta al .env.seed (default: .env.seed).")
    parser.add_argument("--yes", action="store_true",
                        help="No pedir confirmación interactiva.")
    args = parser.parse_args(argv)

    setup_logging(_RUNTIME.log_level, _RUNTIME.log_file)
    log = get_logger("seed")

    try:
        cfg = load_seeder_config(args.env_file)
        assert_local_target(cfg.target.url)  # protege producción
    except ConnectorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(confirmation_banner(cfg.target.url, cfg.source.url))
    if not args.yes:
        if input("¿Continuar? [s/N] ").strip().lower() not in {"s", "si", "sí"}:
            print("Cancelado.")
            return 1

    try:
        source = ReadOnlyOdoo(OdooClient(cfg.source, _RUNTIME, log))
        target = OdooClient(cfg.target, _RUNTIME, log)
        report = ProductSeeder(source, target, log).run()
    except ConnectorError as exc:
        print(f"El seed falló: {exc}", file=sys.stderr)
        return 1

    print(f"\nSeed completo: {report.as_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Re-exportar la API pública en `__init__.py`**

Reemplazar el contenido de `src/capuccino_vainilla/seeder/__init__.py`:

```python
"""Herramientas de seed: copia de productos del Odoo real a un Odoo local."""

from .config import SeederConfig, load_seeder_config
from .product_seeder import AttributeMaps, ProductSeeder, SeedReport
from .readonly import ReadOnlyOdoo, ReadOnlyViolation
from .safety import TargetNotLocalError, assert_local_target

__all__ = [
    "SeederConfig", "load_seeder_config",
    "ProductSeeder", "AttributeMaps", "SeedReport",
    "ReadOnlyOdoo", "ReadOnlyViolation",
    "TargetNotLocalError", "assert_local_target",
]
```

- [ ] **Step 3: Registrar el script en `pyproject.toml`**

Modificar la sección `[project.scripts]` (línea 32-33) para que quede:

```toml
[project.scripts]
capuccino-vainilla = "capuccino_vainilla.cli:main"
seed-odoo = "capuccino_vainilla.seeder.cli:main"
```

- [ ] **Step 4: Reinstalar el paquete en modo editable (registra el script)**

Run: `pip install -e .`
Expected: instala sin errores; `seed-odoo` queda disponible en el PATH del venv.

- [ ] **Step 5: Verificar que el guard funciona (smoke test sin red)**

Run: `seed-odoo --env-file .env.seed.example --yes`
Expected: como `.env.seed.example` apunta el destino a `http://localhost:8069`, NO debe abortar por el guard; intentará conectar y fallará con un `ConnectorError` de conexión (return code 1) si Odoo no está levantado. Si editás temporalmente `ODOO_DST_URL` a `https://x.odoo.com`, debe abortar con `TargetNotLocalError` (return code 2) **antes** de tocar la red.

- [ ] **Step 6: Verificación end-to-end (con Odoo levantado y `.env.seed` real)**

Run:
```bash
docker compose --profile odoo up -d
seed-odoo --env-file .env.seed --yes
```
Expected: imprime el banner y al final `Seed completo: {...}` con `products_created > 0`. Verificar en `http://localhost:8069` (módulo Inventario/Ventas → Productos) que aparecieron los productos con sus SKU y atributos.

- [ ] **Step 7: Correr toda la suite + ruff**

Run: `pytest tests/seeder/ -v && ruff check src/capuccino_vainilla/seeder tests/seeder`
Expected: todos los tests PASS; ruff sin findings.

- [ ] **Step 8: Commit**

```bash
git add src/capuccino_vainilla/seeder/cli.py src/capuccino_vainilla/seeder/__init__.py pyproject.toml
git commit -m "feat(seeder): seed-odoo CLI entrypoint with safety confirmation"
```

---

## Self-Review

**Spec coverage:**
- Infra Docker profile `odoo` → Task 1 ✅
- Credenciales origen/destino (`.env.seed`) → Task 1 (plantilla) + Task 2 (carga) ✅
- Origen solo-lectura por contrato → Task 3 (`ReadOnlyOdoo`) + usado en Task 8 ✅
- Tres pasadas (atributos → productos → cross-sells) → Tasks 4, 5, 6 ✅
- Remapeo de IDs → Task 4 (atributos) + Task 5 (líneas) + Task 6 (cross-sells) ✅
- Idempotencia por name/SKU → Tasks 4 y 5 ✅
- `qty_available` no se escribe → Task 5 (regla + test) ✅
- Banner + aborto si destino no local → Task 7 + Task 8 ✅
- Test de garantía "origen nunca recibe create/write" → Task 3 (tests de `ReadOnlyOdoo`) ✅
- Reporte final → `SeedReport` (Task 4) impreso en CLI (Task 8) ✅
- Comando `seed-odoo` → Task 8 ✅

**Placeholder scan:** Sin TBD/TODO; todos los steps tienen código o comandos concretos.

**Type consistency:** `AttributeMaps.attribute_ids`/`value_ids` (Task 4) usados igual en Tasks 5 y 6. `template_map: dict[int,int]` producido por `seed_products` (Task 5) y consumido por `seed_cross_sells` (Task 6). `ReadOnlyOdoo` (Task 3) y `OdooClient` ambos cumplen `OdooApi`, usados en Task 8. `SeedReport.as_dict()` definido en Task 4, usado en Task 8. Comandos Odoo `(0,0,{...})` y `(6,0,[...])` consistentes entre Tasks 5 y 6.
