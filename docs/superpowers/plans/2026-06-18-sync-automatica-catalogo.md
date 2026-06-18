# Sincronización automática del catálogo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Woo refleje automáticamente los cambios de Odoo (altas, ediciones y stock por consumición) mediante un proceso `watch` que sondea y sincroniza solo lo cambiado.

**Architecture:** Un comando CLI `watch` corre un `Scheduler` que cada N segundos ejecuta un ciclo (`WatchService.run_once`): un `ChangeDetector` lee una huella barata de cada producto vendible en Odoo, la compara contra un snapshot persistido, y manda los cambiados a `CatalogSyncService.run(ids=...)` y los dados de baja a `CatalogSyncService.unpublish(skus)`. El snapshot solo avanza para lo que sincronizó OK.

**Tech Stack:** Python 3.11, dataclasses inmutables, `xmlrpc`/`woocommerce` detrás de Protocols, pytest + fakes en memoria.

## Global Constraints

- Python 3.11; type hints en todo; `ruff` y `mypy` limpios (`make check`).
- Tests con pytest siguiendo el patrón Protocols + fakes de `tests/conftest.py`; cobertura ≥ 80%.
- Config con dataclasses `frozen=True`; validación fail-fast en `config.py`.
- Docstrings/comentarios en español, al tono del código existente.
- Commits convencionales (`feat:`/`test:`/`docs:`/`chore:`); atribución deshabilitada (no agregar `Co-Authored-By`).
- El loop del watcher **nunca** debe crashear por un tick fallido: loguea y continúa.
- Las bajas se **despublican** en Woo con `{"status": "draft"}` — **nunca** se borran.
- Huella (fingerprint) de un producto = campos Odoo `["default_code", "write_date", "qty_available", "list_price"]`, almacenada como `{"sku", "write_date", "qty", "price"}`.
- Defaults de config: `WATCH_INTERVAL=30`, `WATCH_INITIAL_FULL=true`, `WATCH_STATE_FILE=.watch_snapshot.json`.
- SKU normalizado siempre con `normalize_text(...).strip()` (de `models/product.py`).

---

### Task 1: Config del watcher (`WatcherConfig`)

**Files:**
- Modify: `src/capuccino_vainilla/config.py`
- Modify: `tests/conftest.py` (`make_config`)
- Modify: `tests/test_cli.py` (`_fake_config`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `WatcherConfig(interval: int, initial_full: bool, state_file: str)` (frozen dataclass) y `AppConfig.watcher: WatcherConfig`.

- [ ] **Step 1: Write the failing test**

Agregar al final de `tests/test_config.py`:

```python
def test_watcher_config_defaults(monkeypatch):
    from capuccino_vainilla.config import load_config
    for k in ("WATCH_INTERVAL", "WATCH_INITIAL_FULL", "WATCH_STATE_FILE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {
        "ODOO_URL": "http://o", "ODOO_DB": "d", "ODOO_USERNAME": "u",
        "ODOO_PASSWORD": "p", "WOO_URL": "http://w",
        "WOO_CONSUMER_KEY": "ck", "WOO_CONSUMER_SECRET": "cs",
    }.items():
        monkeypatch.setenv(k, v)

    cfg = load_config()
    assert cfg.watcher.interval == 30
    assert cfg.watcher.initial_full is True
    assert cfg.watcher.state_file == ".watch_snapshot.json"


def test_watcher_config_overrides(monkeypatch):
    from capuccino_vainilla.config import load_config
    for k, v in {
        "ODOO_URL": "http://o", "ODOO_DB": "d", "ODOO_USERNAME": "u",
        "ODOO_PASSWORD": "p", "WOO_URL": "http://w",
        "WOO_CONSUMER_KEY": "ck", "WOO_CONSUMER_SECRET": "cs",
        "WATCH_INTERVAL": "10", "WATCH_INITIAL_FULL": "false",
        "WATCH_STATE_FILE": "/tmp/snap.json",
    }.items():
        monkeypatch.setenv(k, v)

    cfg = load_config()
    assert cfg.watcher.interval == 10
    assert cfg.watcher.initial_full is False
    assert cfg.watcher.state_file == "/tmp/snap.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_watcher_config_defaults -v`
Expected: FAIL con `AttributeError: 'AppConfig' object has no attribute 'watcher'`.

- [ ] **Step 3: Write minimal implementation**

En `config.py`, agregar la dataclass después de `RuntimeConfig`:

```python
@dataclass(frozen=True)
class WatcherConfig:
    interval: int          # segundos entre ciclos del watcher
    initial_full: bool     # primer arranque: reconciliar todo el catálogo
    state_file: str        # archivo del snapshot de huellas
```

Agregar el campo a `AppConfig`:

```python
@dataclass(frozen=True)
class AppConfig:
    odoo: OdooConfig
    woo: WooConfig
    webhook: WebhookConfig
    runtime: RuntimeConfig
    watcher: WatcherConfig
```

En `load_config`, antes del `return`, construir y pasar `watcher`:

```python
    watcher = WatcherConfig(
        interval=_get_int("WATCH_INTERVAL", 30),
        initial_full=_get_bool("WATCH_INITIAL_FULL", True),
        state_file=_get_optional("WATCH_STATE_FILE", ".watch_snapshot.json"),
    )
    return AppConfig(odoo=odoo, woo=woo, webhook=webhook, runtime=runtime, watcher=watcher)
```

En `tests/conftest.py`, importar `WatcherConfig` y añadirlo en `make_config`:

```python
from capuccino_vainilla.config import (
    AppConfig,
    OdooConfig,
    RuntimeConfig,
    WatcherConfig,
    WebhookConfig,
    WooConfig,
)
```

y dentro del `AppConfig(...)` que arma `make_config`, agregar:

```python
        watcher=WatcherConfig(interval=1, initial_full=True, state_file=".watch.json"),
```

En `tests/test_cli.py`, importar `WatcherConfig` y agregar el mismo campo dentro de `_fake_config`:

```python
        watcher=WatcherConfig(interval=30, initial_full=True, state_file=".watch_snapshot.json"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_cli.py tests/conftest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/config.py tests/conftest.py tests/test_cli.py tests/test_config.py
git commit -m "feat(watcher): WatcherConfig (interval, initial_full, state_file)"
```

---

### Task 2: Persistencia del snapshot (`SnapshotStore`)

**Files:**
- Modify: `src/capuccino_vainilla/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `SnapshotStore(path: str, logger=None)` con `load() -> dict[int, dict]` y `save(snapshot: dict[int, dict]) -> None`. Las claves se persisten como string en JSON y se devuelven como `int`.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_state.py`:

```python
def test_snapshot_store_round_trip(tmp_path):
    from capuccino_vainilla.state import SnapshotStore
    path = str(tmp_path / "snap.json")
    store = SnapshotStore(path)
    snap = {1: {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0}}
    store.save(snap)
    loaded = store.load()
    assert loaded == snap
    assert list(loaded.keys()) == [1]  # claves int, no str


def test_snapshot_store_missing_file_returns_empty(tmp_path):
    from capuccino_vainilla.state import SnapshotStore
    store = SnapshotStore(str(tmp_path / "nope.json"))
    assert store.load() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_state.py::test_snapshot_store_round_trip -v`
Expected: FAIL con `ImportError: cannot import name 'SnapshotStore'`.

- [ ] **Step 3: Write minimal implementation**

En `state.py`, agregar al final (reusa `json`, `get_logger` ya importados):

```python
class SnapshotStore:
    """Lee/escribe el snapshot de huellas del watcher (id -> huella) en JSON."""

    def __init__(self, path: str, logger: logging.Logger | None = None):
        self._path = path
        self._log = logger or get_logger("watcher.snapshot")

    def load(self) -> dict[int, dict]:
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            self._log.warning(
                "No se pudo leer el snapshot '%s': %s. Se asume vacío.", self._path, exc
            )
            return {}
        return {int(k): v for k, v in raw.items()}

    def save(self, snapshot: dict[int, dict]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump({str(k): v for k, v in snapshot.items()}, fh, indent=2)
        except OSError as exc:
            self._log.error("No se pudo guardar el snapshot '%s': %s", self._path, exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_state.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/state.py tests/test_state.py
git commit -m "feat(watcher): SnapshotStore para persistir huellas entre ciclos"
```

---

### Task 3: `CatalogSyncService.run` acepta `ids` explícitos

**Files:**
- Modify: `src/capuccino_vainilla/services/catalog_sync.py` (método `run`, ~líneas 76-90)
- Test: `tests/test_catalog_sync.py`

**Interfaces:**
- Consumes: `OdooApi`, `WooApi` (sin cambios).
- Produces: `CatalogSyncService.run(*, full=True, since=None, limit=None, ids: list[int] | None = None) -> SyncReport`. Si `ids` no es `None`, el dominio pasa a `[("sale_ok","=",True),("id","in",ids)]`.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_catalog_sync.py`:

```python
def test_run_with_explicit_ids_only_syncs_those(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [
            _template(101, "AAA"), _template(102, "BBB"), _template(103, "CCC"),
        ]
    }
    report = _service(fake_odoo, fake_woo).run(ids=[102])
    assert report.total == 1
    assert "BBB" in fake_woo.products_by_sku
    assert "AAA" not in fake_woo.products_by_sku
    assert "CCC" not in fake_woo.products_by_sku
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalog_sync.py::test_run_with_explicit_ids_only_syncs_those -v`
Expected: FAIL con `TypeError: run() got an unexpected keyword argument 'ids'`.

- [ ] **Step 3: Write minimal implementation**

En `catalog_sync.py`, cambiar la firma y el armado del dominio en `run`:

```python
    def run(
        self,
        *,
        full: bool = True,
        since: str | None = None,
        limit: int | None = None,
        ids: list[int] | None = None,
    ) -> SyncReport:
        """Ejecuta la sincronización del catálogo.

        Args:
            full: si True ignora `since` (sincronización completa).
            since: fecha/hora UTC para sincronización incremental por `write_date`.
            limit: tope opcional de productos a procesar (para pruebas).
            ids: si se pasa, sincroniza exactamente esos templates (modo watcher).
        """
        domain: list = [("sale_ok", "=", True)]
        if ids is not None:
            domain.append(("id", "in", list(ids)))
        elif not full and since:
            domain.append(("write_date", ">=", since))
            self._log.info("Sincronización incremental desde %s", since)
```

(El resto del método queda igual.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalog_sync.py -q`
Expected: PASS (todos los tests previos siguen verdes).

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/services/catalog_sync.py tests/test_catalog_sync.py
git commit -m "feat(catalog): run() acepta ids explícitos para sync selectiva"
```

---

### Task 4: `CatalogSyncService.unpublish(skus)`

**Files:**
- Modify: `src/capuccino_vainilla/services/catalog_sync.py`
- Test: `tests/test_catalog_sync.py`

**Interfaces:**
- Produces: `CatalogSyncService.unpublish(skus: list[str]) -> int`. Por cada SKU presente en Woo, hace `PUT products/{id}` con `{"status": "draft"}`. Devuelve la cantidad despublicada. Omite (sin fallar) los SKUs vacíos o ausentes en Woo.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_catalog_sync.py`:

```python
def test_unpublish_sets_draft_for_known_skus(fake_odoo, fake_woo):
    fake_woo.preload_product("GONE", 200, status="publish")
    count = _service(fake_odoo, fake_woo).unpublish(["GONE", "MISSING", ""])
    assert count == 1
    assert fake_woo.products[200]["status"] == "draft"
    assert any(
        c[0] == "put" and c[1] == "products/200" and c[2] == {"status": "draft"}
        for c in fake_woo.calls
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalog_sync.py::test_unpublish_sets_draft_for_known_skus -v`
Expected: FAIL con `AttributeError: 'CatalogSyncService' object has no attribute 'unpublish'`.

- [ ] **Step 3: Write minimal implementation**

En `catalog_sync.py`, agregar el método (después de `run`, antes de la fase 1). Usa `self._find_woo_id_by_sku` y `ConnectorError` ya disponibles:

```python
    def unpublish(self, skus: list[str]) -> int:
        """Despublica en Woo (status=draft) los productos dados de baja en Odoo.

        Nunca borra: pasar a borrador es reversible. Omite SKUs vacíos o ausentes
        en Woo. Devuelve cuántos se despublicaron efectivamente.
        """
        count = 0
        for sku in skus:
            if not sku:
                continue
            woo_id = self._find_woo_id_by_sku(sku)
            if not woo_id:
                self._log.info("Baja SKU=%s: no está en Woo, nada que despublicar.", sku)
                continue
            try:
                self._woo.put(f"products/{woo_id}", {"status": "draft"})
                count += 1
                self._log.info("Producto despublicado en Woo id=%s (SKU=%s).", woo_id, sku)
            except ConnectorError as exc:
                self._log.error("Fallo despublicando SKU=%s: %s", sku, exc)
        return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalog_sync.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/services/catalog_sync.py tests/test_catalog_sync.py
git commit -m "feat(catalog): unpublish(skus) despublica bajas en Woo (status=draft)"
```

---

### Task 5: `ChangeDetector` (huellas + diff)

**Files:**
- Create: `src/capuccino_vainilla/watcher/__init__.py`
- Create: `src/capuccino_vainilla/watcher/change_detector.py`
- Create: `tests/watcher/__init__.py`
- Create: `tests/watcher/test_change_detector.py`

**Interfaces:**
- Consumes: `OdooApi`.
- Produces:
  - `ChangeSet(changed_ids: list[int], disappeared_ids: list[int])` (frozen dataclass).
  - `ChangeDetector(odoo: OdooApi, batch_size: int = 50, logger=None)` con `read_fingerprints() -> dict[int, dict]` (cada huella = `{"sku","write_date","qty","price"}`) y `diff(snapshot: dict[int, dict], current: dict[int, dict]) -> ChangeSet`.

- [ ] **Step 1: Write the failing test**

Crear `tests/watcher/__init__.py` (vacío) y `tests/watcher/test_change_detector.py`:

```python
"""Tests del detector de cambios por huella."""
from __future__ import annotations

from capuccino_vainilla.watcher.change_detector import ChangeDetector


def _tmpl(tid, sku, sale_ok=True, qty=5, price=10.0, wd="2026-01-01 00:00:00"):
    return {
        "id": tid, "default_code": sku, "sale_ok": sale_ok,
        "qty_available": qty, "list_price": price, "write_date": wd,
    }


def test_read_fingerprints_only_sale_ok(fake_odoo):
    fake_odoo.db = {"product.template": [
        _tmpl(1, "A"), _tmpl(2, "B", sale_ok=False),
    ]}
    fps = ChangeDetector(fake_odoo).read_fingerprints()
    assert set(fps.keys()) == {1}
    assert fps[1] == {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0}


def test_diff_detects_changed_added_and_disappeared(fake_odoo):
    det = ChangeDetector(fake_odoo)
    snapshot = {
        1: {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0},
        2: {"sku": "B", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0},
    }
    current = {
        1: {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 0, "price": 10.0},  # stock cambió
        3: {"sku": "C", "write_date": "2026-06-01 00:00:00", "qty": 1, "price": 9.0},   # alta
    }
    changes = det.diff(snapshot, current)
    assert sorted(changes.changed_ids) == [1, 3]
    assert changes.disappeared_ids == [2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_change_detector.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'capuccino_vainilla.watcher'`.

- [ ] **Step 3: Write minimal implementation**

Crear `src/capuccino_vainilla/watcher/__init__.py` (vacío) y `src/capuccino_vainilla/watcher/change_detector.py`:

```python
"""Detección de cambios de catálogo por huella (fingerprint).

En vez de confiar en ``write_date`` (que no cambia por movimientos de stock),
se lee una huella barata de cada producto vendible y se compara contra el
snapshot del ciclo anterior. Así se detectan altas, ediciones y stock.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..clients.protocols import OdooApi
from ..logging_config import get_logger
from ..models.product import normalize_text

# Campos baratos que componen la huella.
FINGERPRINT_FIELDS = ["default_code", "write_date", "qty_available", "list_price"]


@dataclass(frozen=True)
class ChangeSet:
    """Resultado de comparar el snapshot contra el estado actual."""

    changed_ids: list[int]      # altas + ediciones + stock
    disappeared_ids: list[int]  # archivados / borrados / no-vendibles


class ChangeDetector:
    """Lee huellas de Odoo y las compara contra un snapshot."""

    def __init__(self, odoo: OdooApi, batch_size: int = 50, logger: logging.Logger | None = None):
        self._odoo = odoo
        self._batch_size = max(1, batch_size)
        self._log = logger or get_logger("watcher.detector")

    def read_fingerprints(self) -> dict[int, dict]:
        """Devuelve ``{id: {"sku","write_date","qty","price"}}`` de los `sale_ok`."""
        domain = [("sale_ok", "=", True)]
        total = self._odoo.search_count("product.template", domain)
        result: dict[int, dict] = {}
        offset = 0
        while offset < total:
            page = self._odoo.search_read(
                "product.template", domain, FINGERPRINT_FIELDS,
                offset=offset, limit=self._batch_size, order="id asc",
            )
            if not page:
                break
            for rec in page:
                result[int(rec["id"])] = {
                    "sku": normalize_text(rec.get("default_code")).strip(),
                    "write_date": rec.get("write_date"),
                    "qty": int(rec.get("qty_available") or 0),
                    "price": float(rec.get("list_price") or 0.0),
                }
            offset += len(page)
        return result

    def diff(self, snapshot: dict[int, dict], current: dict[int, dict]) -> ChangeSet:
        """Compara huellas: devuelve ids cambiados y desaparecidos."""
        changed = [i for i, fp in current.items() if snapshot.get(i) != fp]
        disappeared = [i for i in snapshot if i not in current]
        return ChangeSet(changed_ids=changed, disappeared_ids=disappeared)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_change_detector.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/watcher/__init__.py src/capuccino_vainilla/watcher/change_detector.py tests/watcher/__init__.py tests/watcher/test_change_detector.py
git commit -m "feat(watcher): ChangeDetector con huellas y diff (altas/ediciones/stock/bajas)"
```

---

### Task 6: `Scheduler` (loop resiliente)

**Files:**
- Create: `src/capuccino_vainilla/watcher/scheduler.py`
- Create: `tests/watcher/test_scheduler.py`

**Interfaces:**
- Produces: `Scheduler(tick: Callable[[], object], interval: int, *, sleep=time.sleep, should_stop=None, logger=None)` con `run_forever() -> None`. Llama `tick()` mientras `should_stop()` sea falso; aísla excepciones del tick; duerme `interval` **entre** ticks (no después del último).

- [ ] **Step 1: Write the failing test**

Crear `tests/watcher/test_scheduler.py`:

```python
"""Tests del loop del watcher."""
from __future__ import annotations

from capuccino_vainilla.watcher.scheduler import Scheduler


def test_runs_until_should_stop_and_sleeps_between_ticks():
    state = {"ticks": 0}
    slept: list[float] = []

    def tick():
        state["ticks"] += 1

    Scheduler(
        tick, interval=5, sleep=slept.append, should_stop=lambda: state["ticks"] >= 3
    ).run_forever()

    assert state["ticks"] == 3
    assert slept == [5, 5]  # duerme entre ticks, no tras el último


def test_survives_failing_tick():
    state = {"ticks": 0}

    def tick():
        state["ticks"] += 1
        if state["ticks"] == 1:
            raise RuntimeError("boom")

    Scheduler(
        tick, interval=1, sleep=lambda s: None, should_stop=lambda: state["ticks"] >= 2
    ).run_forever()

    assert state["ticks"] == 2  # siguió tras la excepción
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_scheduler.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'capuccino_vainilla.watcher.scheduler'`.

- [ ] **Step 3: Write minimal implementation**

Crear `src/capuccino_vainilla/watcher/scheduler.py`:

```python
"""Loop de larga vida del watcher: timing, aislamiento de fallos, shutdown."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..logging_config import get_logger


class Scheduler:
    """Ejecuta un ``tick`` periódicamente hasta que ``should_stop`` sea True."""

    def __init__(
        self,
        tick: Callable[[], object],
        interval: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        should_stop: Callable[[], bool] | None = None,
        logger: logging.Logger | None = None,
    ):
        self._tick = tick
        self._interval = max(1, interval)
        self._sleep = sleep
        self._should_stop = should_stop or (lambda: False)
        self._log = logger or get_logger("watcher.scheduler")

    def run_forever(self) -> None:
        self._log.info("Watcher iniciado (intervalo %ss).", self._interval)
        while not self._should_stop():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 — un tick fallido nunca tumba el loop
                self._log.error("Tick falló: %s. Se continúa.", exc)
            if self._should_stop():
                break
            self._sleep(self._interval)
        self._log.info("Watcher detenido.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_scheduler.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/watcher/scheduler.py tests/watcher/test_scheduler.py
git commit -m "feat(watcher): Scheduler con ticks resilientes y shutdown limpio"
```

---

### Task 7: `WatchService` (orquestación de un ciclo)

**Files:**
- Create: `src/capuccino_vainilla/watcher/service.py`
- Create: `tests/watcher/test_watch_service.py`

**Interfaces:**
- Consumes: `ChangeDetector` (`read_fingerprints`, `diff`), un catálogo con `run(*, ids) -> SyncReport` y `unpublish(skus) -> int`, y `SnapshotStore` (`load`, `save`).
- Produces:
  - `WatchCycle(changed: int, disappeared: int)` (frozen dataclass).
  - `WatchService(detector, catalog, snapshot_store, *, initial_full=True, logger=None)` con `run_once() -> WatchCycle`.
- Reglas: primer ciclo (snapshot vacío) → si `initial_full`, reconcilia todo (`run(ids=all)`) y guarda snapshot; si no, solo guarda snapshot. Ciclos siguientes: sincroniza `changed` y despublica `disappeared`; el snapshot **solo avanza** para `changed` si `report.failed == 0`, y elimina `disappeared` solo si se despublicaron todos.

- [ ] **Step 1: Write the failing test**

Crear `tests/watcher/test_watch_service.py`:

```python
"""Tests del orquestador de un ciclo del watcher."""
from __future__ import annotations

from capuccino_vainilla.services.catalog_sync import SyncReport
from capuccino_vainilla.state import SnapshotStore
from capuccino_vainilla.watcher.change_detector import ChangeDetector
from capuccino_vainilla.watcher.service import WatchService


class StubCatalog:
    """Catálogo controlable: ``failed`` define cuántos productos fallan."""

    def __init__(self):
        self.failed = 0
        self.run_calls: list[list[int]] = []
        self.unpublish_calls: list[list[str]] = []

    def run(self, *, full=True, since=None, limit=None, ids=None) -> SyncReport:
        self.run_calls.append(list(ids or []))
        return SyncReport(total=len(ids or []), failed=self.failed)

    def unpublish(self, skus) -> int:
        self.unpublish_calls.append(list(skus))
        return len(skus)


def _tmpl(tid, sku, sale_ok=True, qty=5, price=10.0, wd="2026-01-01 00:00:00"):
    return {
        "id": tid, "default_code": sku, "sale_ok": sale_ok,
        "qty_available": qty, "list_price": price, "write_date": wd,
    }


def _service(fake_odoo, catalog, tmp_path, initial_full=True):
    return WatchService(
        ChangeDetector(fake_odoo), catalog,
        SnapshotStore(str(tmp_path / "snap.json")), initial_full=initial_full,
    )


def test_first_cycle_full_reconciles_and_saves_snapshot(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A"), _tmpl(2, "B")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path)

    cycle = svc.run_once()

    assert cycle.changed == 2
    assert sorted(catalog.run_calls[0]) == [1, 2]
    assert set(SnapshotStore(str(tmp_path / "snap.json")).load().keys()) == {1, 2}


def test_first_cycle_no_full_only_builds_snapshot(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path, initial_full=False)

    cycle = svc.run_once()

    assert cycle.changed == 0
    assert catalog.run_calls == []  # no sincronizó
    assert set(SnapshotStore(str(tmp_path / "snap.json")).load().keys()) == {1}


def test_incremental_syncs_changes_and_unpublishes(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A"), _tmpl(2, "B"), _tmpl(3, "C")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path)
    svc.run_once()  # bootstrap

    # editar precio de 1, archivar 3
    rows = fake_odoo.db["product.template"]
    next(r for r in rows if r["id"] == 1)["list_price"] = 99.0
    next(r for r in rows if r["id"] == 3)["sale_ok"] = False

    cycle = svc.run_once()

    assert cycle.changed == 1 and cycle.disappeared == 1
    assert catalog.run_calls[-1] == [1]
    assert catalog.unpublish_calls[-1] == ["C"]


def test_snapshot_not_advanced_when_sync_fails(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A")]}
    catalog = StubCatalog()
    store_path = str(tmp_path / "snap.json")
    svc = WatchService(ChangeDetector(fake_odoo), catalog, SnapshotStore(store_path))
    svc.run_once()  # bootstrap OK

    next(r for r in fake_odoo.db["product.template"] if r["id"] == 1)["list_price"] = 99.0
    catalog.failed = 1
    svc.run_once()
    assert SnapshotStore(store_path).load()[1]["price"] == 10.0  # no avanzó

    catalog.failed = 0
    svc.run_once()  # se reintenta y ahora sí avanza
    assert catalog.run_calls[-1] == [1]
    assert SnapshotStore(store_path).load()[1]["price"] == 99.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_watch_service.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'capuccino_vainilla.watcher.service'`.

- [ ] **Step 3: Write minimal implementation**

Crear `src/capuccino_vainilla/watcher/service.py`:

```python
"""Orquestación de un ciclo del watcher (un 'tick')."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..logging_config import get_logger
from ..state import SnapshotStore
from .change_detector import ChangeDetector


@dataclass(frozen=True)
class WatchCycle:
    """Resumen de un ciclo: cuántos se sincronizaron y cuántos se dieron de baja."""

    changed: int
    disappeared: int


class WatchService:
    """Compone detector + catálogo + snapshot y ejecuta un ciclo por llamada."""

    def __init__(
        self,
        detector: ChangeDetector,
        catalog,  # CatalogSyncService o compatible: run(*, ids) / unpublish(skus)
        snapshot_store: SnapshotStore,
        *,
        initial_full: bool = True,
        logger: logging.Logger | None = None,
    ):
        self._detector = detector
        self._catalog = catalog
        self._store = snapshot_store
        self._initial_full = initial_full
        self._log = logger or get_logger("watcher")
        self._snapshot = snapshot_store.load()
        self._first_run = not self._snapshot

    def run_once(self) -> WatchCycle:
        current = self._detector.read_fingerprints()

        if self._first_run:
            self._first_run = False
            changed = list(current.keys()) if self._initial_full else []
            if changed:
                self._log.info("Primer ciclo: reconciliando %s productos.", len(changed))
                self._catalog.run(ids=changed)
            self._snapshot = dict(current)
            self._store.save(self._snapshot)
            return WatchCycle(changed=len(changed), disappeared=0)

        changes = self._detector.diff(self._snapshot, current)
        if not changes.changed_ids and not changes.disappeared_ids:
            return WatchCycle(changed=0, disappeared=0)

        self._log.info(
            "Cambios: %s a actualizar, %s a despublicar.",
            len(changes.changed_ids), len(changes.disappeared_ids),
        )
        dirty = False

        if changes.changed_ids:
            report = self._catalog.run(ids=changes.changed_ids)
            if report.failed == 0:
                for i in changes.changed_ids:
                    self._snapshot[i] = current[i]
                dirty = True
            else:
                self._log.warning(
                    "%s productos fallaron; se reintentan el próximo ciclo.", report.failed
                )

        if changes.disappeared_ids:
            skus = [
                self._snapshot[i]["sku"]
                for i in changes.disappeared_ids
                if i in self._snapshot and self._snapshot[i].get("sku")
            ]
            unpublished = self._catalog.unpublish(skus)
            if unpublished == len(skus):
                for i in changes.disappeared_ids:
                    self._snapshot.pop(i, None)
                dirty = True

        if dirty:
            self._store.save(self._snapshot)
        return WatchCycle(changed=len(changes.changed_ids), disappeared=len(changes.disappeared_ids))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/watcher/test_watch_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/watcher/service.py tests/watcher/test_watch_service.py
git commit -m "feat(watcher): WatchService orquesta un ciclo (sync selectivo + bajas + snapshot)"
```

---

### Task 8: Comando CLI `watch` + servicio Docker + `.env.example`

**Files:**
- Modify: `src/capuccino_vainilla/cli.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `OdooWooConnector` (`.odoo`, `.catalog`), `SnapshotStore`, `ChangeDetector`, `Scheduler`, `WatchService`.
- Produces: subcomando `watch` con flags `--interval` (override) y `--once` (un ciclo y termina). `main(["watch", ...])` retorna 0.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_cli.py`:

```python
def test_watch_once_corre_un_ciclo(monkeypatch):
    from capuccino_vainilla import cli

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", lambda env_file=None: _fake_config())
    monkeypatch.setattr("capuccino_vainilla.cli.setup_logging", lambda *a, **kw: None)

    calls = {"run_once": 0}

    class FakeWatchService:
        def __init__(self, *a, **kw):
            pass

        def run_once(self):
            calls["run_once"] += 1

    # Evita construir clientes reales y el server.
    monkeypatch.setattr("capuccino_vainilla.services.connector.OdooWooConnector",
                        lambda *a, **kw: type("C", (), {"odoo": object(), "catalog": object()})())
    monkeypatch.setattr("capuccino_vainilla.watcher.service.WatchService", FakeWatchService)

    rc = cli.main(["watch", "--once"])

    assert rc == 0
    assert calls["run_once"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py::test_watch_once_corre_un_ciclo -v`
Expected: FAIL — el parser no conoce `watch` (`SystemExit: 2`).

- [ ] **Step 3: Write minimal implementation**

En `cli.py`, dentro de `_build_parser`, agregar el subparser (después del de `viewer`):

```python
    p_watch = sub.add_parser("watch", help="Sincroniza el catálogo en continuo (Flujo 1 automático)")
    p_watch.add_argument("--interval", type=int, default=None,
                         help="Segundos entre ciclos (default: WATCH_INTERVAL).")
    p_watch.add_argument("--once", action="store_true",
                         help="Corre un solo ciclo y termina (útil para pruebas/cron).")
```

Agregar el handler `_cmd_watch` (después de `_cmd_viewer`):

```python
def _cmd_watch(config: AppConfig, args: argparse.Namespace) -> int:
    import signal

    from .services.connector import OdooWooConnector
    from .state import SnapshotStore
    from .watcher.change_detector import ChangeDetector
    from .watcher.scheduler import Scheduler
    from .watcher.service import WatchService

    connector = OdooWooConnector(config)
    detector = ChangeDetector(connector.odoo, batch_size=config.runtime.batch_size)
    store = SnapshotStore(config.watcher.state_file)
    service = WatchService(detector, connector.catalog, store,
                           initial_full=config.watcher.initial_full)

    if args.once:
        service.run_once()
        return 0

    interval = args.interval or config.watcher.interval
    stop = {"flag": False}

    def _handle(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    print(f"Watcher en marcha (cada {interval}s). Ctrl-C para detener.")
    Scheduler(service.run_once, interval, should_stop=lambda: stop["flag"]).run_forever()
    return 0
```

Registrar el comando en `main` (junto a los otros `if args.command == ...`):

```python
        if args.command == "watch":
            return _cmd_watch(config, args)
```

En `docker-compose.yml`, agregar el servicio (después de `sync`):

```yaml
  # Watcher: sincronización automática y continua del catálogo (Flujo 1).
  watcher:
    build: .
    image: capuccino-vainilla:latest
    env_file: .env
    command: ["watch"]
    restart: unless-stopped
```

En `.env.example`, agregar (después de `STATE_FILE`):

```bash
# --- Watcher (sincronización automática del catálogo) ---
WATCH_INTERVAL=30              # Segundos entre ciclos del watcher
WATCH_INITIAL_FULL=true        # Primer arranque: reconciliar todo el catálogo
WATCH_STATE_FILE=.watch_snapshot.json  # Snapshot de huellas (incremental)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/capuccino_vainilla/cli.py docker-compose.yml .env.example tests/test_cli.py
git commit -m "feat(cli): comando watch + servicio docker para sync automática"
```

---

### Task 9: Verificación final, gitignore y docs

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:** —

- [ ] **Step 1: Ignorar el snapshot del watcher**

Agregar a `.gitignore` (después de `.seed_state.json`):

```
.watch_snapshot.json
```

- [ ] **Step 2: Documentar el comando en el README**

En `README.md`, en la sección "Uso (CLI)", agregar bajo el Flujo 1:

```markdown
# Flujo 1 — Sincronización automática y continua (watcher)
capuccino-vainilla watch                 # cada WATCH_INTERVAL segundos
capuccino-vainilla watch --interval 15   # override del intervalo
capuccino-vainilla watch --once          # un solo ciclo (cron/pruebas)
```

y una línea explicativa:

```markdown
> El `watch` detecta altas, ediciones y **cambios de stock por ventas** (que
> `write_date` no refleja) comparando una huella por producto contra un snapshot
> persistido. Los productos dados de baja en Odoo se **despublican** en Woo.
```

- [ ] **Step 3: Correr la suite completa con cobertura**

Run: `.venv/Scripts/python.exe -m pytest -q` y `.venv/Scripts/ruff.exe check src tests` y `.venv/Scripts/mypy.exe src`
Expected: todos los tests PASS, ruff sin errores, mypy sin errores, cobertura ≥ 80%.

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md
git commit -m "docs(watcher): documentar comando watch e ignorar el snapshot"
```

---

## Self-Review

**Spec coverage:**
- Polling scheduler → Task 6 (`Scheduler`) + Task 8 (comando `watch`). ✓
- Detección por huella (write_date + qty_available + list_price) → Task 5 (`ChangeDetector`). ✓
- Stock por consumición → cubierto por `qty_available` en la huella (Task 5, test `test_diff_detects_changed...`). ✓
- Sync selectiva por ids → Task 3. ✓
- Bajas → despublicar (status=draft, no borrar) → Task 4 + Task 7. ✓
- Snapshot persistido + idempotencia (solo avanza en éxito) → Task 2 + Task 7 (`test_snapshot_not_advanced_when_sync_fails`). ✓
- Primer arranque full / no-full → Task 7 (dos tests). ✓
- Config `WATCH_*` fail-fast con defaults → Task 1. ✓
- Ciclo de vida / shutdown / aislamiento de fallos → Task 6. ✓
- Deploy docker → Task 8. ✓
- Testing Protocols+fakes, cobertura ≥80% → todas las tareas + Task 9. ✓
- Fuera de alcance (push real, stock.move, borrado físico) → no se implementan (correcto). ✓

**Placeholder scan:** sin TBD/TODO; todos los steps de código traen el código completo. ✓

**Type consistency:** `run(*, full, since, limit, ids)` usado igual en Tasks 3/7/8; `unpublish(skus) -> int` igual en Tasks 4/7; `ChangeSet(changed_ids, disappeared_ids)` y `WatchCycle(changed, disappeared)` consistentes; huella `{"sku","write_date","qty","price"}` idéntica en detector, snapshot y service; `WatcherConfig(interval, initial_full, state_file)` consistente en config/conftest/cli. ✓
