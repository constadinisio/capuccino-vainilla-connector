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
├── webhook/                # FLUJO 2 — Servidor FastAPI de pedidos
│   ├── security.py         #   Validación de firma HMAC
│   └── app.py              #   Endpoint /webhooks/...
├── watcher/                # FLUJO 1 automático (sincronización continua)
│   ├── change_detector.py  #   Detección de cambios por huella (fingerprint)
│   ├── scheduler.py        #   Bucle por intervalo
│   └── service.py          #   Orquestación de un ciclo (tick)
├── viewer/                 # Visor web (dashboard) — FastAPI
│   ├── app.py              #   Rutas + API JSON
│   ├── service.py          #   Acciones contra Odoo/Woo
│   └── progress.py         #   Estado de progreso de la sincronización
└── seeder/                 # Utilidad: copia el catálogo del Odoo real -> Odoo local
    ├── cli.py              #   Entrypoint `seed-odoo`
    ├── readonly.py         #   Guardia de solo-lectura sobre el origen
    └── safety.py           #   Garantiza que el destino sea local
```

**Principio rector:** la I/O vive en `clients/`; las transformaciones en `mappers/` son
funciones puras; los `services/` orquestan ambos dependiendo de **interfaces** (`Protocols`),
lo que permite inyectar *fakes* y testear sin red.

---

## 📋 Requisitos

| Requisito | Versión | ¿Para qué? |
|---|---|---|
| **Python** | 3.10+ (recomendado 3.11+) | Ejecutar el conector. Verificá con `python --version`. |
| **pip** | Incluido con Python | Instalar el paquete y sus dependencias. |
| **Git** | Cualquiera reciente | Clonar el repositorio. |
| **Docker Desktop / Engine** | Compose v2 | **Solo entorno de prueba:** levanta Odoo 16 + WooCommerce locales. |
| **Bash** | — | **Solo entorno de prueba:** correr `scripts/woo-provision.sh`. En Windows viene con *Git Bash*. |

> 🪟 **En Windows:** Docker Desktop usa **WSL2** como motor y lo habilita automáticamente
> en su primera instalación (no es un requisito que instales por separado). No hace falta
> WSL para el flujo de **producción** —ahí no se usa Docker en tu máquina— ni para correr
> el script de aprovisionamiento, que funciona con *Git Bash*.

**Dependencias de Python** (se instalan solas con `pip install -e ".[dev]"`):
`woocommerce`, `python-dotenv`, `requests`, `fastapi`, `uvicorn[standard]`; y para
desarrollo: `pytest`, `pytest-cov`, `httpx`, `ruff`, `mypy`.

**Accesos externos** (según el entorno):

- **Producción:** un **Odoo Enterprise** con XML-RPC habilitado (URL, base, usuario y **API Key**)
  y una tienda **WooCommerce** con la **REST API** activa (claves `ck_/cs_` de Lectura/Escritura).
- **Test:** ninguno obligatorio — el stack es 100% local. El *seeder* puede leer (solo lectura)
  tu Odoo real para poblar el local, pero es opcional.

---

## 🚀 Instalación

> ⚡ **¿Querés solo probarlo?** Hay un script que monta **todo el entorno de prueba en un
> comando** (incluido el `.venv` y el `.env.local`), sin instalar nada a mano:
> `.\scripts\setup-test.ps1` — ver [Instalación automatizada](#-instalación-automatizada-un-comando).
> Los pasos de abajo son la instalación manual, necesaria para **producción**.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate en Linux/Mac)

pip install -e ".[dev]"          # paquete + herramientas de desarrollo
copy .env.example .env           # y completar credenciales (cp en Linux/Mac)
```

La instalación expone dos comandos de consola:

| Comando | Para qué |
|---|---|
| `capuccino-vainilla` | CLI principal (sincronización, webhook, watcher, visor). |
| `seed-odoo` | Utilidad para poblar un Odoo local con el catálogo del Odoo real. |

> 🔐 El `.env` nunca se versiona. En Odoo, usá una **API Key** en vez del password.

---

## ⚙️ Configuración (`.env`)

Toda la configuración se carga desde un `.env` y se **valida al arrancar** (fail fast).
Partí de [`.env.example`](.env.example), que documenta cada variable. Grupos principales:

| Grupo | Variables | Notas |
|---|---|---|
| **Odoo** | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` | Usá una **API Key** como password. |
| **WooCommerce** | `WOO_URL`, `WOO_CONSUMER_KEY`, `WOO_CONSUMER_SECRET`, `WOO_VERIFY_SSL` | `WOO_VERIFY_SSL=false` **solo** en local. |
| **Webhook** | `WEBHOOK_SECRET`, `WEBHOOK_PATH`, `WEBHOOK_HOST`, `WEBHOOK_PORT` | El secreto debe coincidir con el del webhook en Woo. |
| **Ejecución** | `BATCH_SIZE`, `MAX_RETRIES`, `RETRY_DELAY`, `HTTP_TIMEOUT`, `LOG_LEVEL`, `LOG_FILE`, `STATE_FILE` | Paginación, reintentos y logging. |
| **Watcher** | `WATCH_INTERVAL`, `WATCH_INITIAL_FULL`, `WATCH_STATE_FILE` | Intervalo y snapshot de huellas. |

> 💡 Podés tener varios entornos en archivos distintos (ej. `.env.local`) y elegirlos
> con el flag global `--env-file`:
> `capuccino-vainilla --env-file .env.local sync-catalog`.

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
- **Flujo 1:** botón *Sincronizar catálogo* (con límite o completo) → **barra de progreso
  en vivo con estimación de tiempo (ETA)** y, al terminar, el reporte.
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

**Servicios del conector** (usan tu `.env`, apuntan a tus instancias reales):

```bash
docker compose up -d webhook         # servidor de webhooks (puerto 8000)
docker compose up -d watcher         # sincronización automática y continua (Flujo 1)
docker compose run --rm sync         # corrida puntual de sincronización de catálogo
```

Ambos servicios traen `restart: unless-stopped`: si el servidor se reinicia, levantan solos.

**Stack de prueba local** (Odoo 16 + Postgres y WooCommerce + MariaDB), bajo *profiles*:

```bash
docker compose --profile odoo --profile woo up -d
#   Odoo        -> http://localhost:8069
#   WooCommerce -> http://localhost:8080
```

> Ver la guía de **inicialización** más abajo para poblar estas instancias y validar
> los dos flujos punta a punta.

---

## ⚡ Instalación automatizada (un comando)

`scripts/setup-test.ps1` monta el **entorno de prueba completo** de punta a punta, de forma
interactiva. Funciona **recién clonado del repo**: no hace falta tener el `.venv` creado, ni el
conector instalado, ni ningún `.env` con valores cargados.

```powershell
# Parado en la raíz del repo, con Docker Desktop abierto. No hace falta activar nada.
.\scripts\setup-test.ps1
```

Qué hace, en orden:

| # | Paso | Detalle |
|---|---|---|
| 0 | **Prerequisitos** | Verifica Docker corriendo, Python y *Git Bash* (evita el `bash.exe` de WSL). |
| 1 | **`.venv` + conector** | Crea el entorno virtual y corre `pip install -e ".[dev]"` si faltan. |
| 2 | **Contenedores** | `docker compose --profile odoo --profile woo up -d` y espera a que Odoo responda. |
| 3 | **Base de Odoo** | Crea la base y el usuario admin con los datos que te pregunta. |
| 4 | **Módulos de Odoo** | Instala `stock` (para `qty_available`) y `sale_management` (para `optional_product_ids`). |
| 5 | **WooCommerce** | Corre `woo-provision.sh` y captura las claves REST (`ck_`/`cs_`) de la salida. |
| 6 | **`.env.local`** | Lo escribe con todo lo anterior + un `WEBHOOK_SECRET` aleatorio (respalda el previo en `.bak`). |
| 7 | **Webhook** *(opcional)* | Crea el webhook `order.created` en Woo apuntando al conector. |
| 8 | **Catálogo** *(opcional)* | Puebla Odoo con el seeder (requiere un `.env.seed` configurado). |

Es **idempotente**: re-correrlo no recrea el `.venv`, la base ni los módulos si ya existen. Por
dentro delega en `scripts/odoo_bootstrap.py` (XML-RPC, solo *stdlib*) y en
`scripts/woo-provision.sh`. Al terminar imprime los comandos para validar (`viewer`,
`sync-catalog`, `serve`).

> ⚠️ **Solo para pruebas locales.** Todo apunta a `localhost`; nunca lo corras contra producción.
> El único paso que necesita credenciales reales es el seeder, y accede al Odoo real en **solo lectura**.

Detalle completo (y el paso a paso manual equivalente) en
[`docs/guia-prueba-test-local.md`](docs/guia-prueba-test-local.md).

---

## 🏗️ Entorno de prueba local (paso a paso manual)

El equivalente manual de lo que hace el script, útil para entenderlo o para diagnosticar si un
paso falla. Guía detallada y verificada en
[`docs/runbooks/2026-06-18-validacion-end-to-end.md`](docs/runbooks/2026-06-18-validacion-end-to-end.md).
Resumen:

1. **Levantar el stack:** `docker compose --profile odoo --profile woo up -d`.
2. **Instalar los módulos `stock` y `sale_management` en Odoo** (necesarios para
   `qty_available` y `optional_product_ids`, respectivamente): desde Apps en la UI de Odoo,
   o vía XML-RPC.
3. **Poblar Odoo** con el catálogo del Odoo real (copiá `.env.seed.example` → `.env.seed`,
   completá origen/destino, y corré):
   ```bash
   seed-odoo
   ```
   El origen se trata como **solo lectura** y el destino debe ser **local** (gate de seguridad).
4. **Aprovisionar WooCommerce y generar la API key:**
   ```bash
   bash scripts/woo-provision.sh
   ```
   Copiá el `ck_/cs_` impreso a tu `.env.local` (admin de Woo: `admin` / `admin12345`).
5. **Apuntar el `.env.local`** a `localhost` (Odoo `:8069`, Woo `:8080`) y validar:
   ```bash
   capuccino-vainilla --env-file .env.local viewer   # ambos paneles en verde
   ```

> ⚠️ **Gate de seguridad:** corré esta validación solo cuando en `.env.local` tanto
> `ODOO_URL` como `WOO_URL` apunten a `localhost`. Nunca contra producción.

---

## 🚀 Despliegue a producción

Una vez desplegado, el sistema funciona **solo en ambas direcciones** (no requiere
intervención manual). Pasos, una sola vez:

1. **Desplegar** el conector (Docker) en un servidor siempre encendido, con los servicios
   `watcher` y `webhook` corriendo (`docker compose up -d watcher webhook`).
2. **`.env` productivo:** apuntar a tu Odoo y tu tienda reales (no `localhost`), con un
   `WEBHOOK_SECRET` largo y aleatorio y `WOO_VERIFY_SSL=true`.
3. **URL pública + HTTPS** para el webhook (ej. `https://conector.tu-dominio/webhooks/woocommerce/orders`).
4. **Configurar el webhook en Woo** (ver sección siguiente), apuntando a esa URL con el mismo secreto.
5. **Cron de WordPress:** en una tienda con tráfico real, WooCommerce entrega los webhooks
   solo. Para máxima fiabilidad, desactivá el cron por-visita y usá un cron del sistema:
   ```php
   // wp-config.php
   define('DISABLE_WP_CRON', true);
   ```
   ```cron
   * * * * * curl -s https://tu-tienda/wp-cron.php >/dev/null
   ```

> **Operación:** el `watcher` mantiene el catálogo al día y el `webhook` ingresa los pedidos
> automáticamente. El visor y la importación manual quedan como respaldo/diagnóstico.

---

## ⚠️ Notas de mapeo (Odoo)

- **Accesorios:** se leen de `optional_product_ids` de `product.template`. Si tu instancia
  usa `accessory_product_ids`, agregalo a `ODOO_PRODUCT_FIELDS` y a `_read_accessory_skus`
  en `services/catalog_sync.py`.
- **Stock:** `qty_available` es consolidado; para multi-almacén conviene filtrar por
  ubicación vía `context` de Odoo.
- **Tipo de producto:** solo los productos **Almacenable** (`product`) gestionan stock real
  en Odoo. Los **Consumible** (`consu`) reportan siempre `qty_available = 0`, así que su
  stock no se sincroniza. Si un producto debe llevar stock en la tienda, marcalo como
  Almacenable en Odoo.
- **Variantes:** el conector trata los productos como `simple`. Para variantes
  (`product.product` con atributos de variación) se requiere extender el mapper.
