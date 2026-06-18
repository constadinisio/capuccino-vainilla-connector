# Validación end-to-end Odoo ⇄ WooCommerce — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Montar un entorno de prueba (WooCommerce en Docker + copia de Odoo) y un runbook ejecutable para validar de punta a punta el conector antes de producción.

**Architecture:** Solo WooCommerce vive en Docker (WordPress + MariaDB + WP-CLI), expuesto en `localhost:8080`. El conector y el webhook corren en el host. Odoo es la copia remota `pinnacle_test` en `odoo.gpinnacle.com`. Un `.env.test` separado evita apuntar a producción por error.

**Tech Stack:** Docker Compose, imágenes oficiales `wordpress` / `wordpress:cli` / `mariadb`, WP-CLI, la CLI existente `capuccino-vainilla`, `curl`.

## Global Constraints

- El conector y el webhook corren en el **host (Windows)**; solo Woo va en Docker.
- Las definiciones de Woo van bajo el **perfil Docker `woo`**, para no afectar los servicios `webhook`/`sync` ya existentes en `docker-compose.yml`.
- `ODOO_DB` del `.env.test` debe ser **`pinnacle_test`** (la copia), **nunca** la productiva.
- `WOO_URL=http://localhost:8080` y `WOO_VERIFY_SSL=false` (Woo local es HTTP sin certificado).
- El webhook de Woo apunta a `http://host.docker.internal:8000/webhooks/woocommerce/orders`.
- Los archivos `.env*` reales **no se versionan** (solo se versiona `.env.test.example`).
- **Git:** si el proyecto aún no es un repo git (`git status` falla), corré `git init` antes de la primera tarea; los pasos de commit asumen git inicializado.

---

### Task 1: Stack Docker de WooCommerce bajo el perfil `woo`

**Files:**
- Modify: `docker-compose.yml` (agregar servicios `woo-db`, `woo`, `woo-cli` y la sección `volumes`)

**Interfaces:**
- Produces: servicio web Woo accesible en `http://localhost:8080`; servicio `woo-cli` para ejecutar WP-CLI compartiendo el volumen `woo-data` con `woo`; volúmenes nombrados `woo-db-data` y `woo-data`.

- [ ] **Step 1: Agregar los servicios y volúmenes al `docker-compose.yml`**

Agregá estos servicios dentro del bloque `services:` existente (sin tocar `webhook` ni `sync`), y la sección `volumes:` al final del archivo:

```yaml
  # --- Entorno de prueba WooCommerce (solo con --profile woo) ---
  woo-db:
    image: mariadb:11
    profiles: ["woo"]
    environment:
      MARIADB_DATABASE: wordpress
      MARIADB_USER: wordpress
      MARIADB_PASSWORD: wordpress
      MARIADB_ROOT_PASSWORD: rootpass
    volumes:
      - woo-db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 10

  woo:
    image: wordpress:6-php8.3-apache
    profiles: ["woo"]
    depends_on:
      woo-db:
        condition: service_healthy
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: woo-db
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - woo-data:/var/www/html

  woo-cli:
    image: wordpress:cli-php8.3
    profiles: ["woo"]
    depends_on:
      woo:
        condition: service_started
    environment:
      WORDPRESS_DB_HOST: woo-db
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - woo-data:/var/www/html
    # Se usa con `docker compose run --rm woo-cli <args wp>`; no se levanta con `up`.

volumes:
  woo-db-data:
  woo-data:
```

- [ ] **Step 2: Validar la sintaxis del compose**

Run: `docker compose --profile woo config`
Expected: imprime la config combinada sin errores (se ven `woo`, `woo-db`, `woo-cli`).

- [ ] **Step 3: Levantar el stack**

Run: `docker compose --profile woo up -d woo-db woo`
Expected: ambos contenedores `Started`/`healthy`. (La primera vez tarda en bajar las imágenes.)

- [ ] **Step 4: Verificar que WordPress responde**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/`
Expected: `200` o `302` (pantalla de instalación de WordPress).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add WooCommerce test stack under docker profile woo"
```

---

### Task 2: Plantilla `.env.test.example`

**Files:**
- Create: `.env.test.example`
- Modify: `.gitignore` (asegurar que `.env.test` esté ignorado)

**Interfaces:**
- Consumes: nombres de variables de `src/capuccino_vainilla/config.py` (`ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD`, `WOO_URL`, `WOO_CONSUMER_KEY`, `WOO_CONSUMER_SECRET`, `WOO_VERIFY_SSL`, `WEBHOOK_SECRET`, `WEBHOOK_PATH`, etc.).
- Produces: archivo plantilla que el operador copia a `.env.test` (cargado con `load_config(env_file=".env.test")`).

- [ ] **Step 1: Crear `.env.test.example`**

```bash
# ==============================================================================
#  ENTORNO DE PRUEBA — Validación end-to-end (NO es producción)
#  Copiá este archivo a ".env.test" y completá las credenciales.
#  La CLI lo usa con: load_config(env_file=".env.test")
# ==============================================================================

# --- ODOO: la COPIA de la productiva, nunca la real ---
ODOO_URL=https://odoo.gpinnacle.com
ODOO_DB=pinnacle_test
ODOO_USERNAME=integraciones@pinnacle.com
ODOO_PASSWORD=tu_api_key_de_odoo

# --- WOOCOMMERCE local (Docker) ---
WOO_URL=http://localhost:8080
WOO_CONSUMER_KEY=ck_completar_tras_task_4
WOO_CONSUMER_SECRET=cs_completar_tras_task_4
WOO_API_VERSION=wc/v3
WOO_VERIFY_SSL=false

# --- WEBHOOK (Flujo 2) ---
WEBHOOK_SECRET=secreto_de_prueba_largo_y_aleatorio
WEBHOOK_PATH=/webhooks/woocommerce/orders
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000

# --- Runtime ---
BATCH_SIZE=50
MAX_RETRIES=3
RETRY_DELAY=2
HTTP_TIMEOUT=30
LOG_LEVEL=DEBUG
LOG_FILE=sync-test.log
STATE_FILE=.sync_state.test.json
```

- [ ] **Step 2: Asegurar que `.env.test` esté ignorado por git**

Verificá que `.gitignore` ignore los `.env` reales pero no la plantilla. Si no existe la regla, agregá estas líneas a `.gitignore`:

```gitignore
.env
.env.*
!.env.example
!.env.test.example
```

- [ ] **Step 3: Verificar que git no trackea el `.env.test` real**

Run: `printf 'x\n' > .env.test && git check-ignore .env.test`
Expected: imprime `.env.test` (está ignorado). Después borralo: `rm .env.test`.

- [ ] **Step 4: Commit**

```bash
git add .env.test.example .gitignore
git commit -m "chore: add .env.test.example template for e2e validation"
```

---

### Task 3: Script de aprovisionamiento de WooCommerce (WP-CLI)

**Files:**
- Create: `scripts/woo-provision.sh`
- Create: `scripts/woo-create-apikey.php`

**Interfaces:**
- Consumes: servicios `woo` / `woo-cli` del perfil `woo` (Task 1).
- Produces: WordPress instalado, WooCommerce activado, permalinks "pretty" (requeridos por la REST API), y un par de claves REST `ck_…` / `cs_…` impresas por stdout.

- [ ] **Step 1: Crear `scripts/woo-create-apikey.php`**

Snippet PHP que crea una clave REST de WooCommerce con permisos read/write para el usuario admin (id 1) y la imprime. Se ejecuta con `wp eval-file`.

```php
<?php
// Crea una API key read_write de WooCommerce e imprime ck/cs por stdout.
$user_id = 1;
$consumer_key    = 'ck_' . wc_rand_hash();
$consumer_secret = 'cs_' . wc_rand_hash();

global $wpdb;
$wpdb->insert(
    $wpdb->prefix . 'woocommerce_api_keys',
    array(
        'user_id'         => $user_id,
        'description'     => 'capuccino-vainilla e2e test',
        'permissions'     => 'read_write',
        'consumer_key'    => wc_api_hash( $consumer_key ),
        'consumer_secret' => $consumer_secret,
        'truncated_key'   => substr( $consumer_key, -7 ),
    ),
    array( '%d', '%s', '%s', '%s', '%s', '%s' )
);

echo $consumer_key . "\n";
echo $consumer_secret . "\n";
```

- [ ] **Step 2: Crear `scripts/woo-provision.sh`**

Script idempotente que instala el core, activa WooCommerce y fija permalinks. Usa `docker compose run --rm woo-cli`.

```bash
#!/usr/bin/env bash
# Aprovisiona el WooCommerce de prueba. Requiere el stack levantado:
#   docker compose --profile woo up -d woo-db woo
set -euo pipefail

WP="docker compose --profile woo run --rm -T woo-cli"

echo "==> Esperando a que WordPress acepte WP-CLI..."
until $WP db check >/dev/null 2>&1; do sleep 3; done

echo "==> Instalando el core de WordPress (idempotente)..."
$WP core install \
  --url="http://localhost:8080" \
  --title="Capuccino Vainilla TEST" \
  --admin_user="admin" \
  --admin_password="admin12345" \
  --admin_email="admin@example.com" \
  --skip-email || true

echo "==> Instalando y activando WooCommerce..."
$WP plugin install woocommerce --activate

echo "==> Fijando permalinks 'pretty' (requerido por la REST API)..."
$WP rewrite structure '/%postname%/' --hard
$WP rewrite flush --hard

echo "==> Generando una API key REST (read_write)..."
$WP eval-file /var/www/html/woo-create-apikey.php

echo "==> Listo. Copiá el ck_/cs_ de arriba a tu .env.test (WOO_CONSUMER_KEY / WOO_CONSUMER_SECRET)."
```

> Nota: `woo-cli` comparte el volumen `woo-data` montado en `/var/www/html`, así que el
> `.php` debe quedar accesible ahí. El Step 3 lo copia al volumen antes de ejecutarlo.

- [ ] **Step 3: Copiar el snippet al volumen de Woo y correr el aprovisionamiento**

```bash
# Copiar el .php dentro del contenedor woo (al docroot compartido)
docker compose --profile woo cp scripts/woo-create-apikey.php woo:/var/www/html/woo-create-apikey.php
# Ejecutar el aprovisionamiento
bash scripts/woo-provision.sh
```

Expected: termina imprimiendo dos líneas, una `ck_...` y otra `cs_...`.

- [ ] **Step 4: Verificar que la REST API de Woo responde y autentica**

Reemplazá `CK`/`CS` por las claves recién generadas:

Run: `curl -s -u CK:CS "http://localhost:8080/wp-json/wc/v3/products" -w "\nHTTP %{http_code}\n"`
Expected: `HTTP 200` y un array JSON `[]` (Woo arranca sin productos).

- [ ] **Step 5: Commit**

```bash
git add scripts/woo-provision.sh scripts/woo-create-apikey.php
git commit -m "chore: add WooCommerce provisioning scripts (WP-CLI)"
```

---

### Task 4: Exponer `--env-file` global en la CLI

**Files:**
- Modify: `src/capuccino_vainilla/cli.py` (parser global + `main`)
- Test: `tests/test_cli.py` (crear)

**Interfaces:**
- Consumes: `load_config(env_file: str | None = None)` de `config.py` (ya existe).
- Produces: opción global `--env-file PATH` (antes del subcomando) que se pasa a
  `load_config(env_file=...)`. Sin el flag, `env_file` es `None` (comportamiento actual).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_cli.py
from capuccino_vainilla.cli import main
from capuccino_vainilla.config import ConfigError


def test_env_file_flag_se_pasa_a_load_config(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")  # corta el flujo apenas capturamos

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    rc = main(["--env-file", ".env.test", "sync-catalog"])

    assert captured["env_file"] == ".env.test"
    assert rc == 2  # main mapea ConfigError -> 2


def test_sin_env_file_se_usa_none(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    main(["sync-catalog"])

    assert captured["env_file"] is None
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `--env-file` es un argumento no reconocido (argparse sale con código 2 / SystemExit), o `env_file` no se captura.

- [ ] **Step 3: Implementar el cambio mínimo**

En `_build_parser()`, agregar la opción global **antes** de `parser.add_subparsers(...)`:

```python
    parser.add_argument(
        "--env-file",
        default=None,
        help="Ruta a un .env específico (ej. .env.test). Default: busca .env.",
    )
```

En `main()`, reemplazar la carga de config:

```python
    try:
        config = load_config(env_file=args.env_file)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (los dos tests).

- [ ] **Step 5: Verificar que no rompí el resto y el tipado**

Run: `make check` (ruff + mypy + pytest)
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/capuccino_vainilla/cli.py tests/test_cli.py
git commit -m "feat: add global --env-file option to CLI"
```

---

### Task 5: Runbook ejecutable de validación end-to-end

**Files:**
- Create: `docs/runbooks/2026-06-18-validacion-end-to-end.md`

**Interfaces:**
- Consumes: Task 1 (stack Docker), Task 2 (`.env.test`), Task 3 (claves REST), Task 4 (`--env-file`), y la CLI existente (`sync-catalog`, `serve`, `viewer`).
- Produces: checklist de 11 pasos con criterios de aceptación; es el artefacto que se ejecuta para el go/no-go.

- [ ] **Step 1: Crear el runbook**

````markdown
# Runbook — Validación end-to-end Odoo ⇄ WooCommerce (2026-06-18)

Ejecutar en orden. **Si un paso falla, frenar ahí** y diagnosticar antes de seguir.
Todos los comandos de la CLI usan el `.env.test` con el flag global `--env-file`
(implementado en la Task 4): `capuccino-vainilla --env-file .env.test <comando>`.

## Pre-requisitos
- [ ] Copia de Odoo `pinnacle_test` creada y accesible.
- [ ] `.env.test` completado (copiado de `.env.test.example`).
- [ ] **GATE DE SEGURIDAD:** leer en voz alta `ODOO_DB` del `.env.test` → debe decir `pinnacle_test`.

## Paso 0 — Levantar entorno
- [ ] `docker compose --profile woo up -d woo-db woo`
- [ ] `bash scripts/woo-provision.sh` y copiar `ck_/cs_` al `.env.test`.
- Criterio: `curl -u CK:CS http://localhost:8080/wp-json/wc/v3/products` → `200` + `[]`.

## Paso 1 — Conectividad
- [ ] `capuccino-vainilla --env-file .env.test viewer` → abrir http://127.0.0.1:8050
- Criterio: ambos paneles (Odoo copia y Woo) en **verde**.

## Paso 2 — Flujo 1 acotado
- [ ] `capuccino-vainilla --env-file .env.test sync-catalog --limit 5 --full`
- Criterio: reporte 5 OK / 0 errores; en Woo aparecen 5 productos con precio, stock,
  descripción y meta `_odoo_product_id`.

## Paso 3 — Inspección de muestra
- [ ] Revisar en Woo ~5 productos testigo (cross-sell, atributos, tildes/ñ, stock 0).
- Criterio: cross-sell visible, atributos globales creados (filtros), encoding OK, stock 0 reflejado.

## Paso 4 — Flujo 1 completo
- [ ] `capuccino-vainilla --env-file .env.test sync-catalog --full`
- Criterio: conteo en Woo ≈ catálogo de Odoo; 0 errores fatales (skips logueados y revisados).

## Paso 5 — Incremental (idempotencia)
- [ ] `capuccino-vainilla --env-file .env.test sync-catalog`  (sin cambios en Odoo)
- Criterio: no se duplican productos; el reporte indica 0/pocos cambios.

## Paso 6 — Incremental con cambio
- [ ] Cambiar 1 precio en la copia de Odoo → `capuccino-vainilla --env-file .env.test sync-catalog`
- Criterio: solo ese producto se actualiza en Woo; precio nuevo reflejado.

## Paso 7 — Webhook arriba
- [ ] `capuccino-vainilla --env-file .env.test serve`
- [ ] En Woo: Ajustes → Avanzado → Webhooks → crear `Order created`,
      URL `http://host.docker.internal:8000/webhooks/woocommerce/orders`, secret = `WEBHOOK_SECRET`.
- Criterio: `curl http://localhost:8000/health` → `200`.

## Paso 8 — Flujo 2 (pedido OK)
- [ ] Crear un pedido de prueba en Woo (cliente ficticio, email `test+webhook@example.com`).
- Criterio: en la copia de Odoo aparece el `sale.order` con cliente y línea correctos;
  la entrega del webhook figura `201` en Woo.

## Paso 9 — Flujo 2 (firma inválida)
- [ ] `curl -X POST http://localhost:8000/webhooks/woocommerce/orders -H "X-WC-Webhook-Signature: malo" -d '{}'`
- Criterio: responde `401`; no se crea nada en Odoo.

## Paso 10 — Flujo 2 (pedido no mapeable)
- [ ] Crear un pedido en Woo con un SKU inexistente en Odoo.
- Criterio: responde `422`; se loguea; el servidor no crashea.

## Limpieza
- [ ] En la copia de Odoo: borrar `sale.order` y cliente de prueba (o descartar `pinnacle_test`).
- [ ] `docker compose --profile woo down -v`
````

- [ ] **Step 2: Verificar que los comandos del runbook coinciden con la CLI real**

Run: `capuccino-vainilla --help`
Expected: aparecen `sync-catalog`, `serve`, `viewer` y la opción global `--env-file` (de la Task 4).

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/2026-06-18-validacion-end-to-end.md
git commit -m "docs: add end-to-end validation runbook"
```

---

## Notas de cierre

- **Integración futura (no incluida):** sincronización Odoo→Woo en tiempo real (Automated
  Action en Odoo + endpoint `/webhooks/odoo/products` en el conector). Ver
  `docs/superpowers/specs/2026-06-18-testing-end-to-end-odoo-woo-design.md`, sección 7.
- **Fallback de la API key (Task 3):** si `wp eval-file` fallara en tu versión de WooCommerce,
  generá la clave manualmente en WooCommerce → Ajustes → Avanzado → REST API → "Añadir clave"
  (permisos Lectura/Escritura) y copiá `ck_/cs_` al `.env.test`.
