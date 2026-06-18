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
- [ ] `curl -X POST http://localhost:8000/webhooks/woocommerce/orders -H "X-WC-Webhook-Signature: malo" -H "Content-Type: application/json" -d '{}'`
- Criterio: responde `401`; no se crea nada en Odoo.

## Paso 10 — Flujo 2 (pedido no mapeable)
- [ ] Crear un pedido en Woo con un SKU inexistente en Odoo.
- Criterio: responde `422`; se loguea; el servidor no crashea.

## Limpieza
- [ ] En la copia de Odoo: borrar `sale.order` y cliente de prueba (o descartar `pinnacle_test`).
- [ ] `docker compose --profile woo down -v`
