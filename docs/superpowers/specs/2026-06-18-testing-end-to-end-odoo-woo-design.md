# Diseño — Validación end-to-end del conector Odoo ⇄ WooCommerce

- **Fecha:** 2026-06-18
- **Proyecto:** Capuccino Vainilla — Conector Odoo ⇄ WooCommerce (Pinnacle)
- **Estado:** aprobado para escribir plan de implementación
- **Enfoque elegido:** B — *closed-loop guionado con criterios de aceptación*

---

## 1. Contexto y objetivo

El conector ya está implementado (dos flujos, arquitectura en capas, tests unitarios
con *fakes* y CI). Lo que falta es una **validación de integración / end-to-end contra
instancias reales** antes de pasar a producción.

**Objetivo único:** confirmar que el sistema funciona al 100% contra las APIs reales
(conexión, autenticación, mapeo de campos, creación de productos y pedidos, y los
caminos de error) **antes de entrar en producción**. Es un *go/no-go* de pre-producción.

Los tests unitarios validan la *lógica* con *fakes*; esta validación valida los
**contratos reales** con XML-RPC de Odoo y la REST API de WooCommerce.

---

## 2. Alcance

**Dentro del alcance:**
- Levantar un WooCommerce de prueba local (Docker, descartable).
- Probar contra una **copia** de la base de datos productiva de Odoo (`pinnacle_test`).
- Validar Flujo 1 (catálogo Odoo→Woo): completo, incremental e idempotencia.
- Validar Flujo 2 (pedidos Woo→Odoo): happy path y caminos de error (firma inválida,
  pedido no mapeable).

**Fuera del alcance (etapas futuras):**
- Pruebas de performance / carga bajo estrés.
- Automatización de la validación en CI (sería el "Enfoque C").
- Sincronización Odoo→Woo en tiempo real (ver sección 7 — integración futura).

---

## 3. Arquitectura del entorno de prueba

El **conector y el webhook corren en el host (Windows)**; **solo WooCommerce vive en
Docker**. Odoo es remoto (la copia de la productiva).

```
┌─────────────── HOST (Windows) ──────────────────────┐      ┌──────────── INTERNET ───────────┐
│                                                      │      │                                  │
│  CLI / conector  ──(REST)──►  WooCommerce (Docker)   │      │  Odoo (copia: pinnacle_test)     │
│  (sync-catalog,               localhost:8080         │      │  https://odoo.gpinnacle.com      │
│   import-order)   ◄─(XML-RPC)───────────────────────────────►  (XML-RPC)                       │
│                                                      │      │                                  │
│  Webhook server   ◄─(HTTP)──  Woo container          │      └──────────────────────────────────┘
│  localhost:8000               (host.docker.internal) │
└──────────────────────────────────────────────────────┘
```

**Stack Docker para Woo** (se suma al `docker-compose.yml` actual bajo un **perfil aparte**
—p. ej. `--profile woo`— para no mezclarlo con los servicios existentes):
- `wordpress` con WooCommerce auto-instalado (vía WP-CLI) → expuesto en `localhost:8080`.
- `mysql` como base de datos de WordPress.
- (Opcional) contenedor `wp-cli` para automatizar instalación y carga inicial.

**Configuración — `.env.test` separado del `.env` real** (evita correr un test apuntando
sin querer a producción; la CLI ya soporta `load_config(env_file=...)`):
- `WOO_URL=http://localhost:8080`
- `WOO_VERIFY_SSL=false`  ← el Woo local es HTTP sin certificado.
- `ODOO_URL=https://odoo.gpinnacle.com`
- `ODOO_DB=pinnacle_test`  ← **la copia, nunca la productiva.**
- `WEBHOOK_SECRET=<secreto de prueba>` y el webhook de Woo apuntando a
  `http://host.docker.internal:8000/webhooks/woocommerce/orders`.

---

## 4. Estrategia de datos de prueba

- **Universo de prueba (Flujo 1):** el **catálogo real completo** de la copia de Odoo.
  Es lectura pura sobre Odoo y escribe en un Woo descartable → es el test más fiel y sin
  riesgo. No se cargan productos a mano en Woo: se pueblan al correr el Flujo 1.
- **Muestra de inspección detallada:** ~5 productos del catálogo real que representen los
  casos límite, para verificarlos con lupa en Woo:
  1. Producto simple con precio + stock (caso base).
  2. Producto con stock 0.
  3. Producto con cross-sell / accesorios (`optional_product_ids`).
  4. Producto con atributos (p. ej. color/tamaño) → atributos globales en Woo.
  5. Producto con descripción rica y caracteres especiales (tildes, ñ) → encoding.
- **Crear productos testigo solo si falta un caso** en el catálogo real (excepción, no regla).
- **Datos creados para el Flujo 2:** 1 pedido de prueba en Woo con un cliente ficticio
  identificable (email tipo `test+webhook@…`, referencia reconocible) para poder limpiarlo
  después. Ese pedido escribe en la **copia** de Odoo.

---

## 5. Runbook de validación (pasos por riesgo creciente)

Cada paso tiene un criterio de aceptación verificable. **Si un paso falla, se frena ahí.**
Los pasos 1–6 son lectura sobre Odoo (seguros); el riesgo de escritura arranca en el paso 8.

| # | Paso | Comando / acción | Criterio de aceptación |
|---|------|------------------|------------------------|
| 0 | Levantar entorno | `docker compose --profile woo up -d` + instalar Woo (WP-CLI) + generar API keys | Woo responde en `localhost:8080`; admin accesible |
| 1 | Conectividad | `capuccino-vainilla viewer` (o health check) | Ambos paneles en verde: Odoo (copia) y Woo conectan |
| 2 | Flujo 1 acotado | `sync-catalog --limit 5 --full` | Reporte 5 OK / 0 errores; en Woo aparecen los 5 con precio, stock, descripción y meta `_odoo_product_id` |
| 3 | Inspección de muestra | revisar los ~5 productos testigo en Woo | Cross-sell visible, atributos globales creados, tildes/ñ OK, stock 0 reflejado |
| 4 | Flujo 1 completo | `sync-catalog --full` | Conteo en Woo ≈ catálogo de Odoo; 0 errores fatales (skips controlados se loguean y revisan) |
| 5 | Incremental (idempotencia) | `sync-catalog` otra vez, sin cambios | No se duplican productos; 0 o pocos cambios. Valida `STATE_FILE` y match por SKU |
| 6 | Incremental con cambio | cambiar 1 precio en Odoo → `sync-catalog` | Solo ese producto se actualiza en Woo; precio nuevo reflejado |
| 7 | Webhook arriba | `capuccino-vainilla serve` + crear webhook en Woo (`Order created`, URL `host.docker.internal:8000`, secret) | `serve` levanta; `/health` responde 200 |
| 8 | Flujo 2 — pedido OK | crear pedido de prueba en Woo (cliente `test+webhook@…`) | En la copia de Odoo aparece el `sale.order` con cliente y línea correctos; webhook devolvió `201` |
| 9 | Flujo 2 — firma inválida | POST con firma incorrecta (curl) | Devuelve `401`; no crea nada en Odoo. Valida el HMAC |
| 10 | Flujo 2 — pedido no mapeable | pedido con SKU inexistente | Devuelve `422` (no reintentar); se loguea; no crashea |

Los pasos 9–10 son los que separan "anduvo la demo" de "listo para producción": prueban
los caminos de error, no solo el happy path.

---

## 6. Seguridad y limpieza

**Gate de seguridad (antes de escribir):**
- Confirmar que `ODOO_DB` del `.env.test` apunta a `pinnacle_test` (la copia) y **nunca** a
  la productiva. Chequeo manual obligatorio antes del paso 8.
- Pasos 1–6 son lectura → seguros incluso ante un error de apuntado. El riesgo real arranca
  en el paso 8 (primera escritura en Odoo).

**Aislamiento de datos:**
- Pedido y cliente de prueba con marca identificable (`test+webhook@…`, referencia reconocible).
- Woo es descartable: `docker compose --profile woo down -v` borra todo.

**Limpieza al terminar:**
- En la copia de Odoo: borrar el/los `sale.order` y el cliente de prueba creados, o descartar
  directamente la copia `pinnacle_test`.
- Woo: `docker compose --profile woo down -v`.

---

## 7. Integración futura — Sincronización Odoo→Woo en tiempo real

> **No se diseña en detalle en este documento.** Queda anotado como próxima integración,
> con su propio ciclo brainstorm → spec → plan.

**Motivación:** que el catálogo en Woo esté *siempre actualizado* sin ejecutar `sync-catalog`
a mano ni depender solo de corridas programadas.

**Estado actual:**
- Flujo 2 (pedidos Woo→Odoo) **ya es automático** (event-driven vía webhook de Woo).
- Flujo 1 (catálogo Odoo→Woo) es **batch incremental por comando**: hoy requiere que alguien
  o un scheduler lo dispare.

**Viabilidad:** el Odoo de Pinnacle (`odoo.gpinnacle.com`, dominio propio) **no es Odoo Online
SaaS**, por lo que admite módulos custom y server actions → el push en tiempo real es viable
(Odoo.sh u on-premise).

**Forma propuesta (a diseñar):** simétrica al Flujo 2.
1. Automated Action en Odoo sobre `product.template` (al crear/actualizar).
2. Server action que hace un `POST` firmado a un endpoint nuevo del conector
   (`/webhooks/odoo/products`) con el id del producto.
3. El servidor `serve` recibe y sincroniza ese producto a Woo al instante.
4. Firma con secreto compartido (mismo patrón HMAC que el webhook de Woo).

**Asteriscos a resolver en su diseño:**
- **Stock:** cambia vía `stock.quant`/`stock.move`, no por escritura de `product.template`.
  Capturarlo en tiempo real exige triggers en esos modelos. Patrón habitual: precio/datos en
  tiempo real + stock con polling corto como red de seguridad.
- **Módulo custom en Odoo:** el `POST` HTTP saliente desde el entorno Python restringido de
  Odoo probablemente requiera un módulo chico (no solo una server action de UI).
- Confirmar versión de Odoo y si es Odoo.sh u on-premise (afecta el despliegue del módulo).
