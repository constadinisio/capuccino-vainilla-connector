# Guía — Montar el entorno de prueba (test local) desde 0

> **Objetivo:** levantar un **Odoo** y un **WooCommerce** falsos en tu propia PC con Docker,
> y validar los **dos flujos** del conector **sin tocar nada de producción**.
>
> Cada paso trae una **✅ Verificación**: confirmala antes de pasar al siguiente.
> **Si un paso falla, frená ahí** y diagnosticá antes de seguir.

**Idea clave:** la instalación del conector es **una sola**. Lo único que distingue "test"
de "producción" es **qué archivo `.env` se usa**. En test usamos `.env.local` (todo apuntando a
`localhost`); en producción, `.env` (instancias reales).

---

## Índice

- [Pre-requisitos](#pre-requisitos)
- [Paso 0 — Preparar la terminal](#paso-0--preparar-la-terminal)
- [Paso 1 — Levantar Odoo + WooCommerce locales](#paso-1--levantar-odoo--woocommerce-locales)
- [Paso 2 — Configurar Odoo (base + módulo Inventario)](#paso-2--configurar-odoo-base--módulo-inventario)
- [Paso 3 — Aprovisionar WooCommerce y sacar las claves API](#paso-3--aprovisionar-woocommerce-y-sacar-las-claves-api)
- [Paso 4 — Poblar Odoo local con el catálogo (seeder)](#paso-4--poblar-odoo-local-con-el-catálogo-seeder)
- [Paso 5 — Armar el `.env.local`](#paso-5--armar-el-envlocal)
- [Paso 6 — Verificar conexión (visor)](#paso-6--verificar-conexión-visor)
- [Paso 7 — Flujo 1: catálogo Odoo → Woo](#paso-7--flujo-1-catálogo-odoo--woo)
- [Paso 8 — Flujo 2: pedido Woo → Odoo (webhook)](#paso-8--flujo-2-pedido-woo--odoo-webhook)
- [Paso 9 — Apagar todo](#paso-9--apagar-todo)
- [Resumen de comandos](#resumen-de-comandos)
- [Problemas comunes (troubleshooting)](#problemas-comunes-troubleshooting)

---

## Pre-requisitos

| Requisito | Para qué |
|---|---|
| **Python 3.10+** (recomendado 3.11+) | Ejecutar el conector. |
| **Docker Desktop** (Compose v2) | Levantar Odoo 16 + WooCommerce locales. En Windows habilita WSL2 solo. |
| **Git Bash** | Correr `scripts/woo-provision.sh` (viene con Git). |
| **Conector instalado** | `pip install -e ".[dev]"` ya ejecutado en un `.venv`. |

> 🔒 **Gate de seguridad:** este entorno corre 100% contra `localhost`. Nunca apuntes el
> `.env.local` a instancias reales.

---

## Paso 0 — Preparar la terminal

1. Abrí **Docker Desktop** y esperá a que diga **running** (ballena verde). Si no está corriendo, todo lo de Docker falla.
2. Abrí **PowerShell** en la carpeta del proyecto.
3. Activá el entorno de Python:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```

> Si PowerShell te frena con un error de *execution policy*, corré una vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` y reintentá.

**✅ Verificación:** aparece `(.venv)` al inicio de la línea y `capuccino-vainilla --help` lista los comandos.

> Si el `.venv` no existe: `python -m venv .venv`, activarlo, y `pip install -e ".[dev]"`.

---

## Paso 1 — Levantar Odoo + WooCommerce locales

```powershell
docker compose --profile odoo --profile woo up -d
```

La primera vez tarda (descarga Odoo 16, WordPress, Postgres y MariaDB). Esperá 1–2 minutos.

**✅ Verificación:**
```powershell
docker compose ps
```
Los servicios `odoo`, `odoo-db`, `woo`, `woo-db` deben estar en `running` / `healthy`.

- Odoo → http://localhost:8069
- WooCommerce → http://localhost:8080

---

## Paso 2 — Configurar Odoo (base + módulo Inventario)

1. Entrá a http://localhost:8069. La primera vez muestra el **gestor de base de datos**:
   completá **nombre de la base**, **email** y **password** del admin. **Anotá esos datos**
   (van al `.env.local`).
2. Adentro de Odoo, andá a **Apps** e instalá **Inventario** (módulo `stock`).

> ⚠️ **Obligatorio.** Sin el módulo `stock`, el campo `qty_available` no existe y el **Flujo 1
> falla** con `Invalid field 'qty_available'`. Es el tropezón más común.

**✅ Verificación:** aparece el menú **Inventario** en la barra superior de Odoo.

---

## Paso 3 — Aprovisionar WooCommerce y sacar las claves API

Instala WordPress + WooCommerce, fija permalinks y crea una API key de lectura/escritura.
Corré con **Git Bash** (no PowerShell):

```bash
bash scripts/woo-provision.sh
```

Al terminar imprime un par `ck_.../cs_...`. **Copialos ya** — WooCommerce los muestra **una sola vez**.

- Admin de Woo: usuario `admin` / password `admin12345`.
- Si perdés las claves, regeneralas con:
  ```powershell
  docker compose run --rm woo-cli wp eval-file /var/www/html/woo-create-apikey.php
  ```

**✅ Verificación** (reemplazá `CK`/`CS`):
```bash
curl -u CK:CS http://localhost:8080/wp-json/wc/v3/products
```
Debe responder `200` (una lista vacía `[]` está perfecta: todavía no hay productos).

---

## Paso 4 — Poblar Odoo local con el catálogo (seeder)

Copia el catálogo del Odoo **real** (solo lectura) hacia tu Odoo **local**, para tener productos que sincronizar.

```powershell
copy .env.seed.example .env.seed
```
Editá `.env.seed`: **origen** = Odoo real (credenciales de solo lectura); **destino** = Odoo local
(`http://localhost:8069`, la base del Paso 2). Después:

```powershell
seed-odoo
```

> 🔒 Guarda de seguridad: el origen se trata como **solo lectura** y el destino **debe ser local**;
> si el destino no es local, el seeder se niega a correr.

**✅ Verificación:** en Odoo → Productos ves el catálogo cargado (~1155 plantillas en la validación previa).

> Sin acceso al Odoo real, podés saltear este paso y cargar a mano 3–4 productos en Odoo.
> Lo importante: que tengan **SKU** (referencia interna) y stock.

---

## Paso 5 — Armar el `.env.local`

```powershell
copy .env.test.example .env.local
```

Editá `.env.local` y completá:

- **WooCommerce:** pegá el `ck_/cs_` del Paso 3 en `WOO_CONSUMER_KEY` / `WOO_CONSUMER_SECRET`.
  Dejá `WOO_URL=http://localhost:8080` y `WOO_VERIFY_SSL=false`.
- **Odoo:** `ODOO_URL=http://localhost:8069`, con la base, usuario y password del Paso 2.
- **Webhook:** poné un `WEBHOOK_SECRET` cualquiera largo (lo reusás en el Paso 8).

> ⚠️ **Gate de seguridad:** confirmá que **`ODOO_URL` y `WOO_URL` apunten a `localhost`**.

---

## Paso 6 — Verificar conexión (visor)

```powershell
capuccino-vainilla --env-file .env.local viewer
```
Abrí http://127.0.0.1:8050.

**✅ Verificación:** los dos paneles (Odoo y WooCommerce) en **verde**. Si alguno está en rojo,
muestra el error de conexión ahí mismo → revisá el `.env.local`. Cortá con `Ctrl+C`.

---

## Paso 7 — Flujo 1: catálogo Odoo → Woo

Empezá acotado para validar rápido:

```powershell
capuccino-vainilla --env-file .env.local sync-catalog --limit 5 --full
```
**✅ Verificación:** reporte `5 created / 0 failed`; en Woo aparecen 5 productos con precio,
stock, descripción y el meta `_odoo_product_id`.

Catálogo completo:
```powershell
capuccino-vainilla --env-file .env.local sync-catalog --full
```

Idempotencia (correrlo de nuevo sin cambios no debe duplicar nada):
```powershell
capuccino-vainilla --env-file .env.local sync-catalog
```
**✅ Verificación:** reporta `0 a procesar` y el conteo en Woo queda estable.

---

## Paso 8 — Flujo 2: pedido Woo → Odoo (webhook)

1. Si el contenedor `webhook` está corriendo, frenalo para liberar el puerto 8000:
   ```powershell
   docker compose stop webhook
   ```
2. Levantá el server **en el host** (llega a Odoo/Woo locales sin gimnasia de red):
   ```powershell
   capuccino-vainilla --env-file .env.local serve
   ```
   **✅ Verificación:** http://localhost:8000/health responde `200`.
3. En Woo → **Ajustes → Avanzado → Webhooks**, creá uno:
   - **Tema:** `Order created`
   - **URL:** `http://host.docker.internal:8000/webhooks/woocommerce/orders`
   - **Secreto:** el mismo valor de `WEBHOOK_SECRET` en `.env.local`.
4. Creá un pedido de prueba en Woo (cliente ficticio).

**✅ Verificación:** en Odoo aparece el `sale.order` con cliente y línea correctos; el webhook
respondió `201`.

**Casos de error esperados** (robustez del Flujo 2):
- Firma inválida → `401`, no se crea nada.
- Pedido con SKU inexistente en Odoo → `422`, se loguea, el server no crashea.

---

## Paso 9 — Apagar todo

```powershell
# Cortá el server de webhooks con Ctrl+C, después:
docker compose --profile odoo --profile woo down
#   agregá -v si querés borrar también los datos (Odoo y Woo quedan vacíos)
```

---

## Resumen de comandos

| Qué | Comando |
|---|---|
| Levantar entorno | `docker compose --profile odoo --profile woo up -d` |
| Ver estado de contenedores | `docker compose ps` |
| Aprovisionar Woo | `bash scripts/woo-provision.sh` |
| Poblar Odoo | `seed-odoo` |
| Ver estado de conexión | `capuccino-vainilla --env-file .env.local viewer` |
| Flujo 1 (acotado) | `capuccino-vainilla --env-file .env.local sync-catalog --limit 5 --full` |
| Flujo 1 (completo) | `capuccino-vainilla --env-file .env.local sync-catalog --full` |
| Flujo 2 (webhook) | `capuccino-vainilla --env-file .env.local serve` |
| Apagar | `docker compose --profile odoo --profile woo down` |

---

## Problemas comunes (troubleshooting)

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Invalid field 'qty_available'` en Flujo 1 | Falta el módulo `stock` en Odoo | Instalar **Inventario** desde Apps (Paso 2). |
| `Activate.ps1` no se puede ejecutar | Execution policy de Windows | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. |
| Paneles del visor en rojo | Credenciales/URLs mal en `.env.local` | Revisar `ODOO_URL`/`WOO_URL` (deben ser `localhost`) y claves. |
| `curl` a Woo no da `200` | Permalinks o API key | Re-correr `woo-provision.sh`; regenerar API key con `woo-cli`. |
| Perdí el `ck_/cs_` | Woo los muestra una sola vez | `docker compose run --rm woo-cli wp eval-file /var/www/html/woo-create-apikey.php`. |
| El webhook no llega a Odoo | URL del webhook | Usar `http://host.docker.internal:8000/...` y correr `serve` en el host. |
| Puerto 8000 ocupado | Contenedor `webhook` corriendo | `docker compose stop webhook` antes de `serve`. |
| Docker no levanta nada | Docker Desktop apagado | Abrir Docker Desktop y esperar la ballena verde. |

---

> 📚 **Referencia:** el runbook validado paso a paso está en
> [`docs/runbooks/2026-06-18-validacion-end-to-end.md`](runbooks/2026-06-18-validacion-end-to-end.md),
> con los 10 checks y los resultados esperados de la validación del 2026-06-18.
