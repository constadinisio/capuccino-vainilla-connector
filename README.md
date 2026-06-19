# Capuccino Vainilla — Conector Odoo ⇄ WooCommerce

Integración **bidireccional** de nivel producción entre **Odoo Enterprise** (ERP) y
**WordPress / WooCommerce**, para la tienda de equipos audiovisuales profesionales de **Pinnacle**.

[![CI](https://img.shields.io/badge/CI-ruff%20%7C%20mypy%20%7C%20pytest-blue)](.github/workflows/ci.yml)

---

## ✨ Características

- **Flujo 1 — Catálogo Odoo → WooCommerce:** productos, precios, stock, descripción,
  **atributos globales** (para filtros nativos) y **ventas cruzadas** (cross-sell).
- **Flujo 2 — Pedidos WooCommerce → Odoo:** alta/búsqueda de cliente y creación de la
  orden de venta, vía un **webhook real** con **validación de firma HMAC**.
- **Sincronización incremental** por `write_date` con estado persistido.
- **Robustez:** reintentos con *backoff* exponencial, *skip controlado* por ítem,
  paginación por lotes y logging con rotación.
- **Calidad:** arquitectura en capas, tipado estático (mypy), linting (ruff), y
  **suite de tests** con cobertura ≥ 80% en CI.

---

## 🧱 Arquitectura

```
src/capuccino_vainilla/
├── cli.py                  # Interfaz de línea de comandos
├── config.py               # Carga + validación del .env (fail fast)
├── logging_config.py       # Logging con rotación
├── retry.py                # Reintentos con backoff (reutilizable)
├── exceptions.py           # Jerarquía de excepciones tipadas
├── state.py                # Estado para sincronización incremental
├── clients/                # I/O de bajo nivel
│   ├── protocols.py        #   Interfaces (Protocols) -> testeabilidad
│   ├── odoo_client.py      #   XML-RPC de Odoo
│   └── woo_client.py       #   WooCommerce REST API
├── models/                 # DTOs inmutables de dominio
│   ├── product.py
│   └── order.py
├── mappers/                # Transformaciones PURAS (sin I/O)
│   ├── product_mapper.py
│   └── order_mapper.py
├── services/               # Lógica de negocio
│   ├── attribute_sync.py   #   Atributos globales + términos
│   ├── catalog_sync.py     #   FLUJO 1
│   ├── order_import.py     #   FLUJO 2
│   └── connector.py        #   Fachada OdooWooConnector
└── webhook/                # Servidor FastAPI
    ├── security.py         #   Validación HMAC
    └── app.py              #   Endpoint /webhooks/...
```

**Principio rector:** la I/O vive en `clients/`; las transformaciones en `mappers/` son
funciones puras; los `services/` orquestan ambos dependiendo de **interfaces** (`Protocols`),
lo que permite inyectar *fakes* y testear sin red.

---

## 🚀 Instalación

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate en Linux/Mac)

pip install -e ".[dev]"          # paquete + herramientas de desarrollo
copy .env.example .env           # y completar credenciales (cp en Linux/Mac)
```

> 🔐 El `.env` nunca se versiona. En Odoo, usá una **API Key** en vez del password.

---

## 🧭 Uso (CLI)

```bash
# Flujo 1 — Sincronización automática y continua (watcher)
capuccino-vainilla watch                 # cada WATCH_INTERVAL segundos
capuccino-vainilla watch --interval 15   # override del intervalo
capuccino-vainilla watch --once          # un solo ciclo (cron/pruebas)
```

> El `watch` detecta altas, ediciones y **cambios de stock por ventas** (que
> `write_date` no refleja) comparando una huella por producto contra un snapshot
> persistido. Los productos dados de baja en Odoo se **despublican** en Woo.

```bash
# Flujo 1 — Catálogo (manual)
capuccino-vainilla sync-catalog              # incremental (usa el último estado)
capuccino-vainilla sync-catalog --full       # completo
capuccino-vainilla sync-catalog --limit 20   # acotado (pruebas)

# Flujo 2 — Importar un pedido desde un JSON
capuccino-vainilla import-order --file examples/sample_order.json

# Servidor de webhooks (recibe order.created de WooCommerce)
capuccino-vainilla serve
```

También: `python -m capuccino_vainilla sync-catalog`.

---

## 🖥️ Visor web (dashboard)

Un panel para **ver y disparar** los flujos contra tus instancias reales:

```bash
capuccino-vainilla viewer            # http://127.0.0.1:8050
capuccino-vainilla viewer --port 9000
```

Incluye:
- **Estado de conexión** Odoo / WooCommerce en vivo (se actualiza solo).
- **Catálogo lado a lado**: productos de Odoo (origen) vs WooCommerce (destino), con
  match por SKU y visualización del meta `_odoo_product_id`.
- **Flujo 1:** botón *Sincronizar catálogo* (con límite o completo) → muestra el reporte.
- **Flujo 2:** lista de pedidos recientes de la tienda con botón *Importar a Odoo* →
  muestra el `sale.order` creado.
- **Consola de logs** reales del backend.

> El visor arranca aunque Odoo o Woo estén caídos: en ese caso muestra el error de
> conexión en cada panel en vez de fallar. Solo requiere las credenciales de Odoo y
> WooCommerce en el `.env` (no necesita `WEBHOOK_SECRET`).

---

## 🔌 Webhook de WooCommerce

1. Levantá el servidor: `capuccino-vainilla serve` (o `docker compose up webhook`).
2. En **WooCommerce → Ajustes → Avanzado → Webhooks**, creá uno:
   - **Tema:** `Order created`
   - **URL de entrega:** `https://tu-dominio/webhooks/woocommerce/orders`
   - **Secreto:** el mismo valor que `WEBHOOK_SECRET` en tu `.env`.
3. El endpoint valida la firma `X-WC-Webhook-Signature` (HMAC-SHA256) antes de procesar.

Respuestas: `201` (orden creada), `401` (firma inválida), `422` (pedido no mapeable,
no reintentar), `502` (error contra Odoo, WooCommerce reintenta).

---

## 🧪 Calidad

```bash
make check      # ruff + mypy + pytest con cobertura (igual que la CI)
make test       # solo tests
make cov        # tests con cobertura y umbral 80%
make lint       # ruff
make type       # mypy
```

---

## 🐳 Docker

```bash
docker compose up webhook            # servidor de webhooks (puerto 8000)
docker compose run --rm sync         # corrida puntual de sincronización
```

---

## ⚠️ Notas de mapeo (Odoo)

- **Accesorios:** se leen de `optional_product_ids` de `product.template`. Si tu instancia
  usa `accessory_product_ids`, agregalo a `ODOO_PRODUCT_FIELDS` y a `_read_accessory_skus`
  en `services/catalog_sync.py`.
- **Stock:** `qty_available` es consolidado; para multi-almacén conviene filtrar por
  ubicación vía `context` de Odoo.
- **Variantes:** el conector trata los productos como `simple`. Para variantes
  (`product.product` con atributos de variación) se requiere extender el mapper.
