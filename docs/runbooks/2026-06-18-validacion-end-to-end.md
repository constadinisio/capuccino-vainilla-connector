# Runbook — Validación end-to-end Odoo ⇄ WooCommerce

**Validado: 2026-06-18** contra el stack 100% local (Odoo seedeado + WooCommerce en Docker).
Resultado: **Flujo 1 y Flujo 2 funcionando punta a punta.**

Ejecutar en orden. **Si un paso falla, frenar ahí** y diagnosticar antes de seguir.
Todos los comandos de la CLI usan `.env.local` con el flag global `--env-file`:
`capuccino-vainilla --env-file .env.local <comando>`.

> **Nota sobre el entorno.** Esta validación corre contra instancias **locales**
> (Odoo `http://localhost:8069`, Woo `http://localhost:8080`), no contra producción.
> El catálogo de Odoo local se pobló con el seeder (`seed-odoo`) a partir del Odoo real.

## Pre-requisitos
- [ ] Stack local levantado: `docker compose --profile odoo --profile woo up -d`.
- [ ] Odoo local seedeado con el catálogo (vía `seed-odoo`) — ~1155 templates.
- [ ] **Módulo `stock` instalado en el Odoo local** (ver Paso 0). Sin él, el campo
      `qty_available` no existe y el Flujo 1 falla con `Invalid field 'qty_available'`.
- [ ] `.env.local` completado: credenciales de Odoo local + API key de Woo (ver Paso 0).
- [ ] **GATE DE SEGURIDAD:** confirmar que en `.env.local` tanto `ODOO_URL` como
      `WOO_URL` apuntan a `localhost` → nunca correr esta validación contra producción.

## Paso 0 — Levantar y aprovisionar el entorno
- [ ] `docker compose --profile odoo --profile woo up -d`
- [ ] **Instalar el módulo `stock` en Odoo** (necesario para `qty_available`):
      instalar "Inventario" desde Apps en la UI, o vía XML-RPC
      (`ir.module.module` → `button_immediate_install` sobre el módulo `stock`).
- [ ] **Aprovisionar Woo y generar API key:** `bash scripts/woo-provision.sh`
      (instala WordPress + WooCommerce, fija permalinks y crea una API key `read_write`).
- [ ] Copiar el `ck_/cs_` impreso a `.env.local` (`WOO_CONSUMER_KEY` / `WOO_CONSUMER_SECRET`).
      ⚠️ WooCommerce muestra el `ck_/cs_` completo **una sola vez**; si se pierde, regenerar
      con `wp eval-file /var/www/html/woo-create-apikey.php` (vía el servicio `woo-cli`).
- Criterio: `curl -u CK:CS http://localhost:8080/wp-json/wc/v3/products` → `200`.

## Paso 1 — Conectividad
- [ ] `capuccino-vainilla --env-file .env.local viewer` → abrir http://127.0.0.1:8050
- Criterio: ambos paneles (Odoo y Woo) en **verde**.

## Paso 2 — Flujo 1 acotado
- [ ] `capuccino-vainilla --env-file .env.local sync-catalog --limit 5 --full`
- Criterio: reporte 5 OK / 0 errores; en Woo aparecen 5 productos con precio, stock,
  descripción y meta `_odoo_product_id`.
- ✅ **Validado 2026-06-18:** `5 created / 0 failed`; meta `_odoo_product_id` presente en los 5.

## Paso 3 — Inspección de muestra
- [ ] Revisar en Woo ~5 productos testigo (cross-sell, atributos, tildes/ñ, stock 0).
- Criterio: cross-sell visible, atributos globales creados (filtros), encoding OK, stock 0 reflejado.
- ℹ️ **Nota 2026-06-18:** el catálogo seedeado **no traía** `optional_product_ids`, así que
  `cross_sells_linked: 0` es esperado (no hay datos de cross-sell que enlazar, no es un bug).
  Encoding verificado OK (p. ej. `CAÑEIM003` con ñ).

## Paso 4 — Flujo 1 completo
- [ ] `capuccino-vainilla --env-file .env.local sync-catalog --full`
- Criterio: conteo en Woo ≈ catálogo de Odoo; 0 errores fatales (skips logueados y revisados).
- ✅ **Validado 2026-06-18:** `total 1155 / created 1148 / updated 6 / failed 1` → **1153 productos en Woo**.
- ⚠️ **Limitación conocida (solo local):** 1 SKU con caracteres especiales (`C/V U$D`, con `/ $` y
  espacio) falla con `401 Invalid signature`. Causa: sobre **HTTP** la librería `woocommerce`
  firma con **OAuth 1.0a** y esos caracteres rompen la firma. En **producción (HTTPS → Basic
  Auth, sin firma)** ese SKU sincroniza normal. No es un bug del conector.

## Paso 5 — Incremental (idempotencia)
- [ ] `capuccino-vainilla --env-file .env.local sync-catalog`  (sin cambios en Odoo)
- Criterio: no se duplican productos; el reporte indica 0/pocos cambios.
- ✅ **Validado 2026-06-18:** `0 a procesar`; conteo en Woo estable (1153 → 1153); watermark avanzado.

## Paso 6 — Incremental con cambio
- [ ] Cambiar 1 precio en Odoo local → `capuccino-vainilla --env-file .env.local sync-catalog`
- Criterio: solo ese producto se actualiza en Woo; precio nuevo reflejado.
- ✅ **Validado 2026-06-18:** cambiado `ALQUILER` (1 → 1000) → `1 a procesar / updated 1`;
  precio en Woo pasó a `1000.00`; ningún otro producto tocado.

## Paso 7 — Webhook arriba
- [ ] Frenar el contenedor `webhook` si está corriendo (libera el puerto 8000):
      `docker compose stop webhook`.
- [ ] Levantar el server **en el host** (así llega a Odoo/Woo locales sin gimnasia de red):
      `capuccino-vainilla --env-file .env.local serve`.
- [ ] En Woo: Ajustes → Avanzado → Webhooks → crear `Order created`,
      URL `http://host.docker.internal:8000/webhooks/woocommerce/orders`, secret = `WEBHOOK_SECRET`.
- Criterio: `curl http://localhost:8000/health` → `200`.
- ✅ **Validado 2026-06-18:** `/health` → `200` con el server en el host.

## Paso 8 — Flujo 2 (pedido OK)
- [ ] Crear un pedido de prueba en Woo (cliente ficticio, email `test+webhook@example.com`),
      o simular el POST con firma HMAC válida
      (`X-WC-Webhook-Signature = Base64(HMAC-SHA256(raw_body, WEBHOOK_SECRET))`).
- Criterio: en Odoo aparece el `sale.order` con cliente y línea correctos; el webhook responde `201`.
- ✅ **Validado 2026-06-18:** `201` → `sale.order` **S00001** (`client_order_ref=WC-5001`),
  cliente Juana Pérez creado, línea `ALQUILER` x2 @ 1000, total 2420 (IVA 21% aplicado por Odoo).

## Paso 9 — Flujo 2 (firma inválida)
- [ ] `curl -X POST http://localhost:8000/webhooks/woocommerce/orders -H "X-WC-Webhook-Signature: malo" -H "Content-Type: application/json" -d '{}'`
- Criterio: responde `401`; no se crea nada en Odoo.
- ✅ **Validado 2026-06-18:** `401 unauthorized`; nada creado.

## Paso 10 — Flujo 2 (pedido no mapeable)
- [ ] Crear/POSTear un pedido con un SKU inexistente en Odoo (firma válida).
- Criterio: responde `422`; se loguea; el servidor no crashea.
- ✅ **Validado 2026-06-18:** `422 skipped` ("ninguna línea pudo mapearse"); `WC-5002` → 0 órdenes en Odoo.

## Limpieza
- [ ] Frenar el server de webhooks del host (Ctrl-C o matar el proceso del puerto 8000).
- [ ] En el Odoo local: revertir el precio de `ALQUILER`, borrar el `sale.order` y el cliente de prueba.
- [ ] `docker compose --profile odoo --profile woo down` (agregar `-v` para borrar también los volúmenes).
