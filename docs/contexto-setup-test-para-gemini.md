# Contexto completo del proyecto — Conector Odoo ⇄ WooCommerce ("Capuccino Vainilla")

> **Documento de traspaso para otra IA (Gemini).** Es **autocontenido**: explica el
> proyecto entero, su arquitectura, los dos flujos, el script `setup-test.ps1` y todas las
> piezas que orquesta, el despliegue a producción y los resultados de la validación
> end-to-end. Sintetiza **todo** el material del repo: `README.md`, las dos guías
> (`docs/guia-prueba-test-local.md`, `docs/guia-despliegue-produccion.md`), el runbook
> (`docs/runbooks/2026-06-18-validacion-end-to-end.md`), los `.env.example`,
> `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Makefile` y los scripts.
> Objetivo: que puedas razonar sobre cualquier parte del sistema sin re-leer el repo.

---

## 1. Qué es y para quién

**Capuccino Vainilla** es un **conector bidireccional de nivel producción** entre:

- **Odoo Enterprise** (ERP) — fuente de verdad del **catálogo** (productos, precios, stock,
  atributos, cross-sell). Se habla por **XML-RPC**.
- **WordPress / WooCommerce** (tienda online) — donde se publican los productos y entran los
  **pedidos**. Se habla por la **REST API v3**.

Es para la tienda de **equipos audiovisuales profesionales de Pinnacle**. Es un paquete
Python (`capuccino_vainilla`, versión `1.0.0`, `requires-python >=3.10`) que se instala con
`pip install -e ".[dev]"` y expone **dos comandos de consola**:

| Comando | Para qué |
|---|---|
| `capuccino-vainilla` | CLI principal: `sync-catalog`, `watch`, `serve`, `import-order`, `viewer`. |
| `seed-odoo` | Utilidad: copia el catálogo del Odoo **real** (solo lectura) a un Odoo **local**. |

**Principio de diseño central:** la instalación del conector es **una sola**. Lo único que
distingue "test" de "producción" es **qué archivo `.env` se usa** (vía el flag global
`--env-file`):
- **test** → `.env.local` (todo apunta a `localhost`, contenedores Docker descartables).
- **producción** → `.env` (instancias reales de Odoo y Woo).

---

## 2. Los dos flujos

### Flujo 1 — Catálogo (Odoo → WooCommerce)
Lee productos de Odoo y los crea/actualiza en WooCommerce: **precio, stock, descripción,
atributos globales** (para los filtros nativos de la tienda) y **ventas cruzadas
(cross-sell)**. Usa un meta `_odoo_product_id` en cada producto Woo para mantener
**idempotencia** (match por SKU + ese meta, no duplica).

- `sync-catalog` → corrida manual. Flags: `--full` (completo), `--limit N` (acotado, para
  pruebas), sin flags = **incremental** (usa el watermark del último estado por `write_date`).
- `watch` → sincronización **automática y continua**. Cada `WATCH_INTERVAL` segundos.
  Flags: `--interval N`, `--once`. Detecta altas, ediciones y **cambios de stock por ventas**
  (que `write_date` no refleja) comparando una **huella/fingerprint** por producto contra un
  snapshot persistido. Los productos dados de baja en Odoo se **despublican** en Woo.

### Flujo 2 — Pedidos (WooCommerce → Odoo)
Un **servidor de webhooks FastAPI** recibe el evento `order.created` de WooCommerce, **valida
la firma HMAC-SHA256** (header `X-WC-Webhook-Signature`), da de alta/busca el cliente y crea
el `sale.order` en Odoo.

- `serve` → levanta el server (por defecto puerto 8000).
- `import-order --file examples/sample_order.json` → importar un pedido desde un JSON (manual).

**Códigos de respuesta del webhook:**
| Código | Significado | ¿WooCommerce reintenta? |
|---|---|---|
| `201` | Orden creada en Odoo. | — |
| `401` | Firma HMAC inválida (no se procesa). | No |
| `422` | Pedido no mapeable (ej. SKU inexistente). No reintentar. | No |
| `502` | Error contra Odoo (caído/credenciales). | Sí |

### Utilidad — Visor web (dashboard)
`capuccino-vainilla viewer` → http://127.0.0.1:8050 (flag `--port`). Panel FastAPI para
**ver y disparar** los flujos: estado de conexión en vivo de Odoo/Woo, catálogo lado a lado
(match por SKU + meta `_odoo_product_id`), botón de sincronizar con **barra de progreso y
ETA**, lista de pedidos recientes con botón "Importar a Odoo", y consola de logs del backend.
Arranca aunque Odoo o Woo estén caídos (muestra el error en cada panel). **No** requiere
`WEBHOOK_SECRET`, solo credenciales de Odoo y Woo.

---

## 3. Arquitectura del paquete

```
src/capuccino_vainilla/
├── cli.py                  # Interfaz de línea de comandos (entrypoint capuccino-vainilla)
├── config.py               # Carga + validación del .env (FAIL FAST al arrancar)
├── logging_config.py       # Logging con rotación
├── retry.py                # Reintentos con backoff exponencial (reutilizable)
├── exceptions.py           # Jerarquía de excepciones tipadas
├── state.py                # Estado para sincronización incremental (watermark)
├── clients/                # I/O de bajo nivel
│   ├── protocols.py        #   Interfaces (Protocols) -> testeabilidad / fakes
│   ├── odoo_client.py      #   XML-RPC de Odoo
│   └── woo_client.py       #   WooCommerce REST API
├── models/                 # DTOs inmutables de dominio (product.py, order.py)
├── mappers/                # Transformaciones PURAS, sin I/O (product_mapper, order_mapper)
├── services/               # Lógica de negocio
│   ├── attribute_sync.py   #   Atributos globales + términos
│   ├── catalog_sync.py     #   FLUJO 1
│   ├── order_import.py     #   FLUJO 2
│   └── connector.py        #   Fachada OdooWooConnector
├── webhook/                # FLUJO 2 — Servidor FastAPI
│   ├── security.py         #   Validación de firma HMAC
│   └── app.py              #   Endpoint /webhooks/woocommerce/orders + /health
├── watcher/                # FLUJO 1 automático
│   ├── change_detector.py  #   Detección de cambios por huella (fingerprint)
│   ├── scheduler.py        #   Bucle por intervalo
│   └── service.py          #   Orquestación de un ciclo (tick)
├── viewer/                 # Visor web (dashboard) FastAPI (app, service, progress)
└── seeder/                 # Utilidad: copia catálogo Odoo real -> Odoo local
    ├── cli.py              #   Entrypoint seed-odoo
    ├── readonly.py         #   Guardia de solo-lectura sobre el origen
    └── safety.py           #   Garantiza que el destino sea local
```

**Principio rector:** la I/O vive en `clients/`; las transformaciones en `mappers/` son
**funciones puras**; los `services/` orquestan ambos dependiendo de **interfaces**
(`Protocols`), lo que permite inyectar *fakes* y testear sin red.

**Dependencias** (de `pyproject.toml`): runtime → `woocommerce>=3.0.0`,
`python-dotenv>=1.0.1`, `requests>=2.32.0`, `fastapi>=0.110.0`, `uvicorn[standard]>=0.29.0`.
Dev → `pytest`, `pytest-cov`, `httpx`, `ruff`, `mypy`, `types-requests`.

**Calidad / CI:** `make check` = `ruff` + `mypy` + `pytest` con cobertura **≥ 80%**
(`--cov-fail-under=80`). Ruff line-length 100, target py310, reglas `E,F,I,UP,B,W`.
mypy con `ignore_missing_imports` (woocommerce no trae stubs). La CLI y `__main__.py` se
excluyen de cobertura (se prueban e2e/manual). CI badge: `ruff | mypy | pytest`.

---

## 4. Configuración (`.env`) — todas las variables

Toda la config se carga del `.env` y se **valida al arrancar (fail fast)**. Hay tres
plantillas en el repo:

- **`.env.example`** → producción (instancias reales).
- **`.env.test.example`** → entorno de prueba local (copiar a `.env.local`).
- **`.env.seed.example`** → solo para el seeder (copiar a `.env.seed`).

| Grupo | Variables | Notas |
|---|---|---|
| **Odoo** | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` | En `ODOO_PASSWORD` va una **API Key**, no el password de la cuenta. |
| **WooCommerce** | `WOO_URL`, `WOO_CONSUMER_KEY`, `WOO_CONSUMER_SECRET`, `WOO_API_VERSION` (`wc/v3`), `WOO_VERIFY_SSL`, `HTTP_TIMEOUT` | `WOO_VERIFY_SSL=false` **solo** en local; `true` en producción. |
| **Webhook** | `WEBHOOK_SECRET`, `WEBHOOK_PATH` (`/webhooks/woocommerce/orders`), `WEBHOOK_HOST` (`0.0.0.0`), `WEBHOOK_PORT` (`8000`) | El secreto debe coincidir con el del webhook en Woo. |
| **Runtime** | `BATCH_SIZE` (50), `MAX_RETRIES` (3), `RETRY_DELAY` (2, backoff exp.), `LOG_LEVEL`, `LOG_FILE`, `STATE_FILE` | Paginación, reintentos, logging y watermark incremental. |
| **Watcher** | `WATCH_INTERVAL` (30), `WATCH_INITIAL_FULL` (true), `WATCH_STATE_FILE` | Intervalo y snapshot de huellas. |

**Seeder (`.env.seed`):** dos bloques — **ORIGEN** (`ODOO_SRC_URL/DB/USERNAME/PASSWORD`,
el Odoo real, tratado como **solo lectura**) y **DESTINO** (`ODOO_DST_URL/DB/USERNAME/PASSWORD`,
el Odoo local, **debe ser local** o el seeder se niega a correr).

> ⚠️ Detalle del `.env.test.example`: el `ODOO_URL` de ejemplo apunta a una **copia de
> prueba** del Odoo (`https://odoo.gpinnacle.com`, base `pinnacle_test`), no necesariamente
> a `localhost`. El runbook y `setup-test.ps1`, en cambio, usan un **Odoo local en Docker**
> (`http://localhost:8069`, base `capuccino_test`). Ambos enfoques son válidos para test,
> siempre que **no sea producción**.

---

## 5. El script estrella: `scripts/setup-test.ps1`

### 5.1 Qué resuelve
Montar el entorno de prueba a mano son ~9 pasos. Este **orquestador interactivo de
PowerShell** hace **todo de una corrida** y es **idempotente** (re-correrlo no recrea lo que
ya existe). **Funciona recién clonado de GitHub**: crea el `.venv`, instala el conector y
genera el `.env.local` solo. Imprescindible: **Docker Desktop abierto** + **Python + Git
Bash** en el PATH. Parámetro: `-EnvFile` (default `.env.local`).

### 5.2 Restricciones de plataforma que condicionan el diseño
- **SO:** Windows 11. **Shell:** **PowerShell 5.1** (Windows PowerShell, no 7+).
- **`$ErrorActionPreference = "Continue"` a propósito:** con `"Stop"`, cualquier comando
  **nativo** (`python`, `docker`, `bash`) que escriba a **stderr** abortaría el script. El
  control de errores real se hace **chequeando `$LASTEXITCODE`** tras cada comando nativo.
- **Usa Git Bash, no el `bash.exe` de WSL** (en `System32`, que falla con
  `execvpe(/bin/bash) failed` si no hay distro WSL). La función `Get-GitBash` lo localiza:
  primero deriva la ruta desde donde está instalado `git` (`<gitRoot>\bin\bash.exe`); si no,
  prueba `%ProgramFiles%\Git\bin`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%\Programs\Git`.
- Dentro de `woo-provision.sh` se usa `MSYS_NO_PATHCONV=1` para que Git Bash **no convierta**
  rutas Unix (`/%postname%/`, `/var/www/...`) a rutas Windows.

### 5.3 Recorrido paso a paso
Funciones de salida: `Write-Step` (cyan), `Write-Ok` (verde), `Write-Warn` (amarillo),
`Write-Err` (rojo). `Read-Default` (Enter = default). `Confirm-YesNo` (acepta s/si/sí/y/yes).

**Paso 0 — Prerequisitos:**
1. Verifica raíz del repo (existe `docker-compose.yml`), si no `exit 1`.
2. Verifica `docker` en el PATH.
3. `Get-GitBash` (ver arriba); si no hay, `exit 1`.
4. `Get-VenvPython` → `.venv\Scripts\python.exe`. Si el `.venv` no existe, lo crea
   (`python -m venv .venv`).
5. **Instala el conector si falta** (idempotente): chequea con
   `importlib.util.find_spec('capuccino_vainilla')` (no `import`, para no tirar traceback a
   stderr). Si falta: `pip install --upgrade pip` + `pip install -e ".[dev]"`.
6. Define rutas a entrypoints del `.venv` que funcionan **sin activarlo**:
   `capuccino-vainilla.exe` y `seed-odoo.exe`.
7. Verifica que Docker responde (`docker info`); si no, `exit 1`.

**Recolección de inputs (todo de una):** `odooDb` (default `capuccino_test`), `odooLogin`
(`admin@example.com`), `odooPassword` (`admin`), `odooMaster` (master pwd del database
manager, `admin`); `doSeed` (default **No**), `doWebhook` (default **Sí**); `webhookSecret`
generado con `secrets.token_hex(32)`; `odooUrl=http://localhost:8069`,
`wooUrl=http://localhost:8080`.

**Paso 1 — Levantar contenedores:** `docker compose --profile odoo --profile woo up -d`.

**Paso 2 — Configurar Odoo** (vía `scripts/odoo_bootstrap.py`):
- `wait --timeout 240`
- `create-db --db-name --admin-login --admin-password --master-pwd --lang es_AR`
- `install-module --module stock`
  > ⚠️ **Crítico:** sin `stock`, el campo `qty_available` no existe y el **Flujo 1 falla**
  > con `Invalid field 'qty_available'`. Es el tropezón más común.

**Paso 3 — Aprovisionar WooCommerce:** corre `& $bash "scripts/woo-provision.sh" 2>&1` y
**captura las claves** de la salida con regex (`ck_[0-9a-fA-F]+`, `cs_[0-9a-fA-F]+`, última
coincidencia). Si no las encuentra, `exit 1`.

**Paso 4 — Escribir `.env.local`** (here-string, `Set-Content -Encoding UTF8`; respalda en
`.env.local.bak` si ya existía). Contenido: bloque Odoo, bloque Woo (con
`WOO_VERIFY_SSL=false`), bloque Webhook, bloque Runtime (`LOG_LEVEL=DEBUG`,
`LOG_FILE=sync-test.log`, `STATE_FILE=.sync_state.test.json`).

**Paso 5 — (Opcional) Crear el webhook en Woo** (si `doWebhook`): POST a
`${wooUrl}/wp-json/wc/v3/webhooks` con Basic Auth (`ck:cs` en base64), body
`topic="order.created"`, `delivery_url="http://host.docker.internal:8000/webhooks/woocommerce/orders"`,
`secret=webhookSecret`, `status="active"`. Usa `host.docker.internal` porque el contenedor de
Woo tiene que alcanzar el `serve` que corre en el **host**. Si falla, avisa para crearlo a mano.

**Paso 6 — (Opcional) Poblar el catálogo** (si `doSeed`): si no existe `.env.seed`, avisa de
copiarlo de `.env.seed.example`; si existe, corre `seed-odoo.exe`.

**Cierre:** imprime los próximos pasos (`viewer`, `sync-catalog --limit 5 --full`, `serve`,
`docker compose ... down`) y apunta a `docs/guia-prueba-test-local.md`.

---

## 6. Piezas que orquesta el script

```
scripts/
  setup-test.ps1        <- EL ORQUESTADOR (PowerShell 5.1).
  odoo_bootstrap.py     <- helper Python (stdlib, XML-RPC): wait / create-db / install-module.
  woo-provision.sh      <- Bash (Git Bash): instala WordPress+WooCommerce y crea la API key REST.
  woo-create-apikey.php <- PHP que corre dentro del contenedor Woo para crear la key read_write.
  woo-force-ssl.php     <- mu-plugin PHP: permite Basic Auth sobre HTTP (test sin TLS).
docker-compose.yml      <- servicios (Odoo+PG, Woo+MariaDB+CLI, y el conector bajo profiles).
```

### 6.1 `docker-compose.yml` (profiles)
- **`--profile odoo`**: `odoo` (`odoo:16`, puerto **8069**) + `odoo-db` (`postgres:15`,
  healthcheck `pg_isready`). Vars: `HOST=odoo-db USER=odoo PASSWORD=odoo`.
- **`--profile woo`**: `woo` (`wordpress:6-php8.3-apache`, puerto **8080**) + `woo-db`
  (`mariadb:11`, healthcheck) + `woo-cli` (`wordpress:cli-php8.3`, se usa con
  `docker compose run --rm woo-cli wp ...`, **no** se levanta con `up`).
- **`--profile connector`**: `webhook` (corre `serve`, puerto **8000**, healthcheck a
  `/health`, `restart: unless-stopped`) y `watcher` (corre `watch`). **NO se levantan en
  test** (en test el conector corre en el **host**); existen para **producción**.
- **`--profile tools`**: `sync` (una sincronización de catálogo on-demand, `restart: no`).
- Todos los servicios del conector usan `image: capuccino-vainilla:latest` (`build: .`) y
  `env_file: .env`. Volúmenes nombrados: `odoo-db-data`, `odoo-data`, `woo-db-data`, `woo-data`.

### 6.2 `scripts/odoo_bootstrap.py`
Python puro (stdlib `xmlrpc.client`), sin dependencias nuevas. Tres subcomandos idempotentes:
- **`wait --timeout --interval`**: bloquea hasta que `common.version()` responde, o falla al
  agotar el timeout. Tolera errores transitorios.
- **`create-db ...`**: crea base + admin con `db.create_database(...)`. **No-op si ya existe**
  (`db.list()`). Si Odoo rechaza por master password, lo dice explícito. **Gate:** rechaza
  (`return 2`) si la URL no es local (`_is_local`: contiene `localhost`/`127.0.0.1`/
  `host.docker.internal`).
- **`install-module ...`**: autentica, busca el módulo en `ir.module.module`, y si no está
  `installed` corre `button_immediate_install`. **No-op si ya instalado.**

### 6.3 `scripts/woo-provision.sh`
Bash (`set -euo pipefail`) con WP-CLI dentro de Docker
(`docker compose --profile woo run --rm -T woo-cli wp`). Pasos idempotentes:
1. Espera a que WordPress acepte WP-CLI (`wp db check` en loop).
2. `wp core install` (admin `admin`/`admin12345`, URL `http://localhost:8080`).
3. `chmod -R 777 wp-content` (deliberado: contenedor local descartable; resuelve desajuste
   de uid entre `woo-cli` uid 82 y apache).
4. `wp plugin install woocommerce --activate`.
5. Copia el mu-plugin `woo-force-ssl.php` (Basic Auth sobre HTTP).
6. Fija permalinks 'pretty' (`/%postname%/`, requerido por la REST API).
7. Ejecuta `woo-create-apikey.php` → genera una **API key REST `read_write`** e imprime el
   par **`ck_/cs_`** por stdout (Woo lo muestra **una sola vez**).

---

## 7. Gates de seguridad (clave para razonar sobre cambios)

1. `odoo_bootstrap.py create-db` rechaza URLs no-locales (`_is_local`).
2. El **seeder** trata el origen como **solo lectura** (`seeder/readonly.py`) y exige que el
   **destino sea local** (`seeder/safety.py`); si no, se niega a correr.
3. El `.env.local` apunta a `localhost`; las guías recalcan verificar `ODOO_URL`/`WOO_URL`
   antes de cualquier sync.
4. `woo-force-ssl.php` habilita Basic Auth sobre HTTP **solo** porque es entorno local
   descartable (en producción se usa HTTPS real con `WOO_VERIFY_SSL=true`).
5. El `.env` / `.env.local` / `.env.seed` **nunca** se versionan (`.gitignore`).
6. El Dockerfile corre como **usuario no-root** (`appuser` uid 1000) con dir de logs propio.

---

## 8. Resultados de la validación end-to-end (runbook 2026-06-18)

Validado contra el stack 100% local (Odoo seedeado + WooCommerce en Docker). **Ambos flujos
funcionando punta a punta.** Hechos concretos:

- **Seed:** ~**1155** templates copiados del Odoo real al local.
- **Flujo 1 acotado** (`--limit 5 --full`): `5 created / 0 failed`; meta `_odoo_product_id`
  presente en los 5.
- **Flujo 1 completo** (`--full`): `total 1155 / created 1148 / updated 6 / failed 1` →
  **1153 productos en Woo**.
- **Incremental sin cambios:** `0 a procesar`; conteo estable (1153 → 1153); watermark avanzado.
- **Incremental con cambio:** cambiar precio de `ALQUILER` (1 → 1000) → `1 a procesar /
  updated 1`; solo ese producto tocado.
- **Webhook arriba:** `/health` → `200` con el server en el host.
- **Flujo 2 OK:** `201` → `sale.order` **S00001** (`client_order_ref=WC-5001`), cliente
  "Juana Pérez" creado, línea `ALQUILER` x2 @ 1000, total 2420 (IVA 21% aplicado por Odoo).
- **Flujo 2 firma inválida:** `401 unauthorized`, nada creado.
- **Flujo 2 no mapeable:** `422 skipped` ("ninguna línea pudo mapearse"), 0 órdenes creadas.

**Limitaciones conocidas (solo local, no bugs del conector):**
- Cross-sell `0`: el catálogo seedeado no traía `optional_product_ids` (no hay datos que
  enlazar). Encoding verificado OK (ej. `CAÑEIM003` con ñ).
- 1 SKU con caracteres especiales (`C/V U$D`, con `/ $` y espacio) falla con
  `401 Invalid signature`. Causa: sobre **HTTP** la librería `woocommerce` firma con **OAuth
  1.0a** y esos caracteres rompen la firma. En **producción (HTTPS → Basic Auth, sin firma)**
  ese SKU sincroniza normal.

La fórmula de firma del webhook (Flujo 2):
`X-WC-Webhook-Signature = Base64(HMAC-SHA256(raw_body, WEBHOOK_SECRET))`.

---

## 9. Despliegue a producción (resumen de la guía)

**Diferencia con test:** la instalación del conector es **la misma**; cambia el `.env` (real,
no `localhost`) y que **Docker solo corre el conector** — Odoo y Woo ya existen, son los reales.

Pasos (una sola vez): servidor 24/7 con Docker + dominio/HTTPS → `.env` productivo (API Key
de Odoo, `WOO_VERIFY_SSL=true`, `WEBHOOK_SECRET` largo: `openssl rand -hex 32`) →
`docker compose up -d watcher webhook` (`restart: unless-stopped`) → **reverse proxy con
HTTPS** (Caddy/Nginx/Traefik, infra del servidor, no del repo) que termina TLS y reenvía al
puerto 8000 → configurar el webhook en Woo (`Order created`, URL
`https://conector.tu-dominio/webhooks/woocommerce/orders`, mismo secreto) → **cron real de
WordPress** (`define('DISABLE_WP_CRON', true)` + `* * * * * curl -s .../wp-cron.php`).

**Operación:** `docker compose ps`, `docker compose logs -f webhook|watcher`,
`docker compose restart`, actualizar con `git pull && docker compose up -d --build watcher
webhook`, sync manual `docker compose run --rm sync`. El `watcher` persiste su snapshot
(`WATCH_STATE_FILE`) y la sync su watermark (`STATE_FILE`) — no borrarlos salvo forzar
full-resync.

---

## 10. Notas de mapeo de Odoo (limitaciones de dominio)

- **Accesorios / cross-sell:** se leen de `optional_product_ids` de `product.template`. Si la
  instancia usa `accessory_product_ids`, hay que agregarlo a `ODOO_PRODUCT_FIELDS` y a
  `_read_accessory_skus` en `services/catalog_sync.py`.
- **Stock:** `qty_available` es consolidado; para multi-almacén conviene filtrar por ubicación
  vía `context` de Odoo.
- **Tipo de producto:** solo **Almacenable** (`product`) gestiona stock real. Los
  **Consumible** (`consu`) reportan siempre `qty_available = 0` (su stock no se sincroniza).
- **Variantes:** el conector trata los productos como `simple`. Para variantes
  (`product.product` con atributos de variación) hay que extender el mapper.

---

## 11. Troubleshooting consolidado

| Síntoma | Causa | Solución |
|---|---|---|
| `Invalid field 'qty_available'` | Falta el módulo `stock` en Odoo | Instalar **Inventario** (el script lo hace en Paso 2). |
| Webhook responde `401` siempre | `WEBHOOK_SECRET` distinto entre `.env` y Woo | Igualar el secreto en ambos lados. |
| Pedidos en `422` | SKU del pedido no existe en Odoo | Sincronizar el producto con su SKU primero. |
| Reintentos `502` | Odoo caído o credenciales mal | Revisar `ODOO_*` y disponibilidad; ver logs. |
| `Activate.ps1` no se ejecuta | Execution policy de Windows | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. |
| Paneles del visor en rojo | Credenciales/URLs mal en `.env.local` | Revisar `ODOO_URL`/`WOO_URL` (localhost) y claves. |
| `curl` a Woo no da `200` | Permalinks o API key | Re-correr `woo-provision.sh`; regenerar API key. |
| Perdí el `ck_/cs_` | Woo los muestra una sola vez | `docker compose run --rm woo-cli wp eval-file /var/www/html/woo-create-apikey.php`. |
| El webhook no llega a Odoo | URL del webhook | Usar `http://host.docker.internal:8000/...` y correr `serve` en el host. |
| Puerto 8000 ocupado | Contenedor `webhook` corriendo | `docker compose stop webhook` antes de `serve`. |
| `execvpe(/bin/bash) failed` | Se usó el bash de WSL, no Git Bash | El script lo evita con `Get-GitBash`. |
| WooCommerce no entrega webhooks (prod) | URL no pública / sin HTTPS válido | Verificar reverse proxy y certificado. |
| El watcher no toma cambios de stock | Producto **Consumible** en Odoo | Solo los **Almacenable** reportan stock real. |
| Docker no responde | Docker Desktop apagado | Abrir Docker Desktop, esperar la ballena verde. |

---

## 12. Comandos de referencia

**Test local (un comando):** `.\scripts\setup-test.ps1`

**Test manual / validación:**
```powershell
docker compose --profile odoo --profile woo up -d        # levantar stack
bash scripts/woo-provision.sh                            # aprovisionar Woo (Git Bash)
seed-odoo                                                # poblar Odoo local (opcional)
capuccino-vainilla --env-file .env.local viewer          # estado (http://127.0.0.1:8050)
capuccino-vainilla --env-file .env.local sync-catalog --limit 5 --full   # Flujo 1 acotado
capuccino-vainilla --env-file .env.local sync-catalog --full             # Flujo 1 completo
capuccino-vainilla --env-file .env.local sync-catalog                    # incremental
docker compose stop webhook                              # liberar puerto 8000
capuccino-vainilla --env-file .env.local serve           # Flujo 2 (server en el host)
docker compose --profile odoo --profile woo down         # apagar (-v borra datos)
```

**Producción:** `docker compose up -d watcher webhook` / `docker compose run --rm sync` /
`git pull && docker compose up -d --build watcher webhook`.

**Calidad:** `make check` (ruff+mypy+pytest cov≥80) / `make test` / `make lint` / `make type`.

---

## 13. Resumen en una frase

`setup-test.ps1` es un orquestador idempotente de PowerShell 5.1 que, en una sola corrida
interactiva, monta de cero el entorno de prueba local del conector bidireccional Odoo 16 ⇄
WooCommerce: prepara el `.venv` y el conector, levanta los contenedores Docker de prueba,
configura Odoo (base + módulo `stock`) vía `odoo_bootstrap.py`, aprovisiona WooCommerce vía
`woo-provision.sh`, captura las claves REST, escribe el `.env.local`, y opcionalmente crea el
webhook y puebla el catálogo con `seed-odoo` — todo apuntando a `localhost`, con gates de
seguridad que impiden tocar producción, y validado end-to-end (1153 productos sincronizados,
ambos flujos OK) en el runbook del 2026-06-18.
