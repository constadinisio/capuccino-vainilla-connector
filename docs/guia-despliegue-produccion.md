# Guía — Despliegue a producción desde 0

> **Objetivo:** poner el conector a correr **solo, en las dos direcciones**, contra el
> **Odoo real** y la **tienda WooCommerce real**, sin intervención manual.
>
> Una vez configurado: el **`watcher`** mantiene el catálogo al día (Odoo → Woo) y el
> **`webhook`** ingresa los pedidos (Woo → Odoo). El visor y la importación manual quedan
> como respaldo/diagnóstico.
>
> Cada paso trae una **✅ Verificación**. **Si un paso falla, frená ahí** antes de seguir.

**Diferencia con el entorno de test:** la instalación del conector es **la misma**. Lo único
que cambia es el archivo de entorno (**`.env`** en producción, en vez de `.env.local`) y que
acá **Docker solo corre el conector** — Odoo y WooCommerce ya existen, son los reales.

> 🚨 **Esto opera sobre datos reales.** Un error de configuración puede crear/editar productos
> o pedidos en la tienda en vivo. Revisá cada paso con cuidado, especialmente el `.env`.

---

## Índice

- [Pre-requisitos](#pre-requisitos)
- [Paso 0 — Preparar el servidor](#paso-0--preparar-el-servidor)
- [Paso 1 — Credenciales de Odoo y WooCommerce](#paso-1--credenciales-de-odoo-y-woocommerce)
- [Paso 2 — Armar el `.env` productivo](#paso-2--armar-el-env-productivo)
- [Paso 3 — Levantar el conector (Docker)](#paso-3--levantar-el-conector-docker)
- [Paso 4 — Exponer el webhook con HTTPS](#paso-4--exponer-el-webhook-con-https)
- [Paso 5 — Configurar el webhook en WooCommerce](#paso-5--configurar-el-webhook-en-woocommerce)
- [Paso 6 — Cron real de WordPress](#paso-6--cron-real-de-wordpress)
- [Paso 7 — Validación end-to-end en producción](#paso-7--validación-end-to-end-en-producción)
- [Operación y mantenimiento](#operación-y-mantenimiento)
- [Resumen de comandos](#resumen-de-comandos)
- [Problemas comunes (troubleshooting)](#problemas-comunes-troubleshooting)

---

## Pre-requisitos

| Requisito | Para qué |
|---|---|
| **Servidor siempre encendido** (VPS/on-prem) | Hospedar el conector 24/7. Linux recomendado. |
| **Docker + Compose v2** | Correr los servicios `watcher` y `webhook`. |
| **Dominio + HTTPS** | URL pública para que WooCommerce entregue los webhooks. |
| **Odoo Enterprise real** | URL, base, usuario y **API Key** (XML-RPC habilitado). |
| **WooCommerce real** | Claves REST `ck_/cs_` de **Lectura/Escritura** y acceso de admin. |
| **Git** | Clonar el repositorio en el servidor. |

> 🔑 En Odoo usá una **API Key** (Ajustes → Usuarios → Seguridad de la cuenta), **no** el
> password de la cuenta.

---

## Paso 0 — Preparar el servidor

1. Conectate al servidor (SSH) y verificá Docker:
   ```bash
   docker --version
   docker compose version
   ```
2. Cloná el repositorio y entrá a la carpeta:
   ```bash
   git clone https://github.com/constadinisio/capuccino-vainilla-connector.git
   cd capuccino-vainilla-connector
   ```

**✅ Verificación:** `docker compose version` responde con Compose v2 y el repo quedó clonado.

---

## Paso 1 — Credenciales de Odoo y WooCommerce

Antes de tocar el `.env`, tené a mano:

**Odoo:**
- `ODOO_URL` (ej. `https://capuccino-vainilla.odoo.com`)
- `ODOO_DB` (nombre de la base)
- `ODOO_USERNAME` (ej. `integraciones@pinnacle.com`)
- **API Key** → Ajustes → Usuarios → tu usuario → Seguridad de la cuenta → *Nueva API Key*.

**WooCommerce:**
- `WOO_URL` real con **https** (ej. `https://tienda.capuccinovainilla.com`)
- Claves REST → **WooCommerce → Ajustes → Avanzado → REST API → Añadir clave**, con permiso
  **Lectura/Escritura**. Copiá `ck_...` y `cs_...`.

**✅ Verificación rápida de Woo** (desde el servidor, reemplazá `CK`/`CS` y la URL):
```bash
curl -u CK:CS https://tienda.capuccinovainilla.com/wp-json/wc/v3/products
```
Debe responder `200`.

---

## Paso 2 — Armar el `.env` productivo

```bash
cp .env.example .env
```

Editá `.env` con los datos reales:

```ini
# --- Odoo (real) ---
ODOO_URL=https://capuccino-vainilla.odoo.com
ODOO_DB=capuccino_vainilla
ODOO_USERNAME=integraciones@pinnacle.com
ODOO_PASSWORD=tu_api_key_de_odoo          # API Key, no el password

# --- WooCommerce (real) ---
WOO_URL=https://tienda.capuccinovainilla.com
WOO_CONSUMER_KEY=ck_xxxxxxxxxxxxxxxxxxxx
WOO_CONSUMER_SECRET=cs_xxxxxxxxxxxxxxxxxxxx
WOO_VERIFY_SSL=true                        # SIEMPRE true en producción

# --- Webhook ---
WEBHOOK_SECRET=<secreto-largo-y-aleatorio>
WEBHOOK_PATH=/webhooks/woocommerce/orders
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
```

> 🔐 Generá un `WEBHOOK_SECRET` fuerte y **guardalo** (lo reusás en el Paso 5):
> ```bash
> openssl rand -hex 32
> ```
> (En PowerShell: `python -c "import secrets; print(secrets.token_hex(32))"`.)

**Checklist del `.env` productivo:**
- [ ] `ODOO_URL` y `WOO_URL` apuntan a las instancias **reales** (no `localhost`).
- [ ] `ODOO_PASSWORD` es una **API Key**.
- [ ] `WOO_VERIFY_SSL=true`.
- [ ] `WEBHOOK_SECRET` largo y aleatorio.
- [ ] El archivo `.env` **no** se versiona (ya está en `.gitignore`).

---

## Paso 3 — Levantar el conector (Docker)

Levantá los dos servicios de producción:

```bash
docker compose up -d watcher webhook
```

- **`watcher`** → sincroniza el catálogo de forma continua (Flujo 1). En el primer arranque
  reconcilia todo el catálogo (`WATCH_INITIAL_FULL=true`), después va incremental cada
  `WATCH_INTERVAL` segundos.
- **`webhook`** → escucha los pedidos de Woo en el puerto `8000` (Flujo 2).

Ambos traen `restart: unless-stopped`: si el servidor se reinicia, levantan solos.

**✅ Verificación:**
```bash
docker compose ps          # webhook y watcher en 'running'/'healthy'
curl http://localhost:8000/health   # -> 200
docker compose logs -f watcher      # ver el primer ciclo de sincronización
```

---

## Paso 4 — Exponer el webhook con HTTPS

WooCommerce necesita entregar los webhooks a una **URL pública con HTTPS**. El contenedor
`webhook` escucha en el puerto `8000` del servidor; poné un **reverse proxy** adelante que
termine TLS y reenvíe a ese puerto.

**Ejemplo orientativo con Caddy** (HTTPS automático con Let's Encrypt):
```caddy
conector.tu-dominio.com {
    reverse_proxy localhost:8000
}
```

**Alternativa con Nginx** (esquema):
```nginx
server {
    server_name conector.tu-dominio.com;
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
    # ... certificados TLS (certbot) ...
}
```

> ℹ️ El reverse proxy y los certificados son **infraestructura del servidor**, no parte del
> repo. Usá la herramienta que ya tengas (Caddy, Nginx + certbot, Traefik, etc.).

**✅ Verificación** (desde afuera del servidor):
```bash
curl https://conector.tu-dominio.com/health   # -> 200, con candado TLS válido
```

---

## Paso 5 — Configurar el webhook en WooCommerce

En **WooCommerce → Ajustes → Avanzado → Webhooks → Añadir webhook**:

| Campo | Valor |
|---|---|
| **Nombre** | `Conector Odoo — Order created` |
| **Estado** | Activo |
| **Tema** | `Order created` (Pedido creado) |
| **URL de entrega** | `https://conector.tu-dominio.com/webhooks/woocommerce/orders` |
| **Secreto** | el **mismo** valor de `WEBHOOK_SECRET` del `.env` |
| **Versión de API** | WP REST API v3 |

El endpoint valida la firma `X-WC-Webhook-Signature` (HMAC-SHA256) antes de procesar.

**Códigos de respuesta esperados:**
- `201` → orden creada en Odoo.
- `401` → firma inválida (no se procesa).
- `422` → pedido no mapeable (no reintentar).
- `502` → error contra Odoo (WooCommerce reintenta).

**✅ Verificación:** usá el botón de WooCommerce para reenviar/probar el webhook, o creá un
pedido de prueba (ver Paso 7). En el log del webhook debe verse la entrega.

---

## Paso 6 — Cron real de WordPress

En una tienda con tráfico, conviene desactivar el cron "por visita" de WordPress y usar uno
del sistema, para que la entrega de webhooks sea confiable.

En `wp-config.php`:
```php
define('DISABLE_WP_CRON', true);
```

Y un cron del sistema (en el servidor de la tienda):
```cron
* * * * * curl -s https://tu-tienda/wp-cron.php >/dev/null
```

**✅ Verificación:** los pedidos nuevos disparan el webhook sin demoras notorias.

---

## Paso 7 — Validación end-to-end en producción

> Hacelo en una ventana de bajo tráfico y, si es posible, con un producto/pedido de prueba
> que después puedas limpiar.

1. **Flujo 1 (catálogo):** cambiá un dato menor de un producto en Odoo (ej. la descripción) y
   esperá un ciclo del `watcher`.
   **✅** El cambio se refleja en Woo; en los logs del `watcher` aparece ese producto como actualizado.

2. **Flujo 2 (pedido):** generá un pedido de prueba en la tienda (cliente ficticio).
   **✅** El webhook responde `201` y en Odoo aparece el `sale.order` con cliente y línea correctos.

3. **Limpieza:** revertí el cambio del producto y cancelá/borrá el pedido y el cliente de prueba.

---

## Operación y mantenimiento

- **Ver estado:** `docker compose ps`
- **Ver logs en vivo:** `docker compose logs -f webhook` / `docker compose logs -f watcher`
- **Reiniciar un servicio:** `docker compose restart watcher`
- **Actualizar el conector:**
  ```bash
  git pull
  docker compose up -d --build watcher webhook
  ```
- **Sincronización manual puntual** (bajo demanda, sin esperar al watcher):
  ```bash
  docker compose run --rm sync
  ```
- **Diagnóstico visual** (opcional, contra las instancias reales):
  ```bash
  capuccino-vainilla viewer        # http://127.0.0.1:8050 — requiere el paquete instalado en el host
  ```
- **Estado incremental:** el watcher persiste su snapshot (`WATCH_STATE_FILE`) y la
  sincronización su watermark (`STATE_FILE`). No los borres salvo que quieras forzar un
  full-resync.
- **Logs:** rotan solos (`LOG_FILE`). Revisalos periódicamente buscando `ERROR`/skips.

---

## Resumen de comandos

| Qué | Comando |
|---|---|
| Levantar conector | `docker compose up -d watcher webhook` |
| Ver estado | `docker compose ps` |
| Health del webhook | `curl http://localhost:8000/health` |
| Logs del watcher | `docker compose logs -f watcher` |
| Sync manual puntual | `docker compose run --rm sync` |
| Actualizar y redeployar | `git pull && docker compose up -d --build watcher webhook` |
| Frenar todo | `docker compose down` |

---

## Problemas comunes (troubleshooting)

| Síntoma | Causa probable | Solución |
|---|---|---|
| Webhook responde `401` siempre | `WEBHOOK_SECRET` distinto entre `.env` y Woo | Igualar el secreto en ambos lados (Paso 5). |
| WooCommerce no entrega webhooks | URL no pública / sin HTTPS válido | Verificar reverse proxy y certificado (Paso 4). |
| Pedidos quedan en `422` | SKU del pedido no existe en Odoo | Asegurar que el producto esté sincronizado con su SKU. |
| Reintentos `502` | Odoo caído o credenciales mal | Revisar `ODOO_*` y disponibilidad de Odoo; ver logs. |
| `Invalid field 'qty_available'` | Falta el módulo `stock` en Odoo | Instalar **Inventario** en el Odoo real. |
| Errores SSL al hablar con Woo | `WOO_VERIFY_SSL` o certificado | En producción debe ser `true` con un certificado válido. |
| El watcher no toma cambios de stock | Producto **Consumible** en Odoo | Solo los **Almacenable** (`product`) reportan stock real. |
| Tras reiniciar, no levanta | — | `restart: unless-stopped` debería relevantarlo; si no, `docker compose up -d`. |

---

> 📚 **Referencias:**
> - Entorno de prueba (para validar antes de tocar producción):
>   [`docs/guia-prueba-test-local.md`](guia-prueba-test-local.md).
> - Runbook de validación end-to-end:
>   [`docs/runbooks/2026-06-18-validacion-end-to-end.md`](runbooks/2026-06-18-validacion-end-to-end.md).
