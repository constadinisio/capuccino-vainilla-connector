# Diseño — Sincronización automática del catálogo (Odoo → WooCommerce)

**Fecha:** 2026-06-18
**Estado:** aprobado (brainstorming), pendiente de plan de implementación
**Flujo afectado:** Flujo 1 (catálogo Odoo → Woo), ahora en modo continuo.

## 1. Problema y objetivo

Hoy el catálogo se sincroniza corriendo `sync-catalog` **a mano**. Se busca que Woo
refleje **automáticamente** los cambios de Odoo: altas de producto, ediciones
(precio, descripción, atributos) y, en particular, **cambios de stock por ventas/
consumición**.

### Restricción que define el enfoque

El Odoo de producción es **`odoo.gpinnacle.com`, versión 16.0 Enterprise**. En Odoo 16:

- No existe la acción "Webhook" nativa (llegó en Odoo 17).
- Una Automated Action con código Python **no puede hacer llamadas HTTP salientes**
  (el sandbox de `safe_eval` no incluye `requests`/`urllib`).

Por lo tanto, un **push real desde Odoo** requeriría desplegar un módulo custom en el
ERP productivo de la empresa — acceso que hoy no se tiene. Se descarta para esta versión.

### Enfoque elegido: polling rápido (scheduler propio)

Un proceso del **conector** (no se toca Odoo) corre un ciclo de sincronización
incremental cada N segundos. Latencia objetivo: ~30 s ("casi en vivo"). Si en el futuro
se consigue acceso para un módulo Odoo, se podrá sumar push sin rehacer este diseño
(quedaría un híbrido).

### Problema técnico central: el stock no mueve `write_date`

El incremental actual filtra por `product.template.write_date >= since`. Pero una
venta/consumición cambia `qty_available` a través de movimientos de inventario
(`stock.move`/`stock.quant`), que **no actualizan** el `write_date` del producto. Un
incremental por `write_date` **se pierde los cambios de stock**. La detección por huella
(sección 3) resuelve esto.

## 2. Arquitectura y componentes

Nuevo comando CLI **`watch`**, separado de `serve` (webhook, Flujo 2) y `sync-catalog`
(manual). Corre como su propio proceso y su propio servicio en `docker-compose`.

| Componente | Responsabilidad | Depende de |
|---|---|---|
| `watcher/scheduler.py` | Loop: timing, ticks sin solapamiento, shutdown limpio, aislar fallos de un tick | una función `tick()` inyectable, clock/sleep inyectable |
| `watcher/change_detector.py` | Leer la huella barata de cada producto, diff contra el snapshot, devolver `(cambiados, desaparecidos)` | `OdooApi`, store de snapshot |
| `state.py` (extendido) | Persistir el snapshot `id → huella` entre ciclos y reinicios | archivo JSON |
| `services/catalog_sync.py` (extendido) | Aceptar lista explícita de ids a sincronizar; despublicar productos dados de baja | `OdooApi`, `WooApi` |
| `config.py` (extendido) | Cargar/validar la config nueva del watcher (fail-fast) | — |
| `cli.py` (extendido) | Comando `watch` que arma y arranca el scheduler | scheduler |

**Flujo de un ciclo:**

```
scheduler despierta
  → change_detector lee huellas (Odoo, sale_ok=True) y compara contra snapshot
      → cambiados   = ids cuya huella difiere (altas + ediciones + stock)
      → desaparecidos = ids del snapshot que ya no aparecen (archivados/borrados)
  → catalog_sync.run(ids=cambiados)            # upsert en Woo
  → catalog_sync.unpublish(ids=desaparecidos)  # pasar a borrador en Woo
  → snapshot se actualiza solo para lo que sincronizó OK
  → scheduler vuelve a dormir WATCH_INTERVAL
```

## 3. Detección de cambios por huella

En lugar de confiar en `write_date`, cada ciclo se lee una **huella barata** de cada
producto vendible y se compara con la del ciclo anterior.

**Huella por producto** (una lectura batch paginada, 3 campos):

```
id → { write_date, qty_available, list_price }
```

- `write_date` → ediciones (nombre, descripción, atributos…). El `id` nuevo detecta altas.
- `qty_available` → **stock por consumición/venta** (lo que `write_date` se pierde).
- `list_price` → cambios de precio, directo y barato (redundante con `write_date` pero robusto).

**Diff por ciclo:**

```python
nuevas = leer_fingerprints(odoo, sale_ok=True)        # ~1155 productos, 3 campos
cambiados     = [i for i in nuevas if nuevas[i] != snapshot.get(i)]
desaparecidos = [i for i in snapshot if i not in nuevas]
```

**Propiedades:**

- No depende de la semántica de `write_date` para el stock → la consumición se detecta siempre.
- **Idempotente:** el snapshot del lote de `cambiados` solo avanza si el ciclo no tuvo
  fallos (`report.failed == 0`). Si algún producto del lote falla, **ningún** `cambiado` de
  ese ciclo avanza su huella, y el lote completo se reintenta en el próximo ciclo (los PUTs
  son idempotentes por SKU, así que reprocesar los que ya estaban OK no causa daño). No hay
  reintento por-producto individual: `SyncReport` expone un conteo de fallos, no qué ids
  fallaron. Es un trade-off deliberado — los lotes de cambios por ciclo son chicos.
- **Primer arranque** (sin snapshot): por defecto reconciliación completa
  (`WATCH_INITIAL_FULL=true`); arma el snapshot inicial. Si se pone en `false`, asume que
  Woo ya está al día y solo construye el snapshot sin sincronizar.

**Bajas / archivado:** los `desaparecidos` se **despublican en Woo** (pasan a borrador/
oculto), **nunca se borran físicamente**. Reversible: si el producto vuelve a `sale_ok`,
reaparece en las huellas y se vuelve a publicar.

**Caveat de escala (límite conocido):** `qty_available` es un campo computado; leerlo para
todo el catálogo cada ~30 s tiene costo en Odoo. Para ~1155 productos es tolerable. Si el
catálogo creciera a decenas de miles, migrar a detección de stock vía deltas de
`stock.move`/`stock.quant`. No se implementa ahora (YAGNI).

## 4. Extensiones a componentes existentes

**`CatalogSyncService` (`services/catalog_sync.py`):**

- `run(..., ids: list[int] | None = None)`: si se pasan `ids`, el domain pasa a
  `[("id", "in", ids), ("sale_ok", "=", True)]` en vez de full/`write_date`. El resto de
  la lógica (upsert por SKU, atributos, cross-sell) no cambia.
- `unpublish(ids: list[int])`: para cada id, resolver el SKU, buscar el producto en Woo y
  hacer `PUT products/{id}` con `{"status": "draft"}`. Loguea y omite los que no estén en Woo.

**`state.py`:** nueva clase/objeto `SnapshotStore` (o métodos en `SyncState`) para leer/
escribir el snapshot `{id: {write_date, qty, price}}` en `WATCH_STATE_FILE`. Mismo patrón
resiliente que el estado actual (si el archivo no se puede leer/escribir, loguea y degrada).

**`config.py`:** agregar y validar:

- `WATCH_INTERVAL` (int, segundos, default 30, > 0).
- `WATCH_INITIAL_FULL` (bool, default `true`).
- `WATCH_STATE_FILE` (str, default `.watch_snapshot.json`).

## 5. Ciclo de vida y manejo de errores

- **Sin solapamiento:** loop de un solo hilo; si un tick tarda más que `WATCH_INTERVAL`,
  el próximo arranca al terminar, no en paralelo.
- **Shutdown limpio:** ante `SIGINT`/`SIGTERM`, termina el tick en curso y sale sin dejar
  estado a medias.
- **Aislamiento de fallos:** un tick que falla (Odoo/Woo caído, red) se loguea y el loop
  continúa; el próximo ciclo reintenta. Nunca tumba el proceso.
- **Arranque robusto:** si Odoo/Woo no responden al iniciar, reintenta con backoff
  (reusa `retry.py`) en vez de crashear.

## 6. Deploy

Nuevo servicio en `docker-compose.yml`, mismo patrón que `webhook`:

```yaml
watcher:
  build: .
  image: capuccino-vainilla:latest
  env_file: .env
  command: ["watch"]
  restart: unless-stopped
```

## 7. Testing

Siguiendo el patrón Protocols + fakes existente, manteniendo cobertura ≥ 80%:

- **Unit `change_detector`**: dado snapshot viejo + huellas nuevas, devuelve el set
  correcto de `cambiados` (altas, ediciones, stock) y `desaparecidos`.
- **Unit `scheduler`**: con clock/sleep inyectable, llama al tick, sobrevive a un tick que
  lanza excepción, y corta ante la señal de stop.
- **Unit `catalog_sync.unpublish`**: despublica los que están en Woo, omite los que no.
- **Integración (tick completo)** con `FakeOdoo`/`FakeWoo`: cambiar un `list_price` y un
  `qty_available` → solo esos dos se sincronizan; archivar un producto → se despublica.

## 8. Fuera de alcance (esta versión)

- **Push real desde Odoo** (módulo custom / webhook saliente): requiere acceso al ERP
  de la empresa. Si se consigue, se suma como híbrido sin rehacer este diseño.
- **Detección de stock vía `stock.move`/`stock.quant`**: solo necesaria a gran escala.
- **Borrado físico en Woo**: se despublica, no se borra.
