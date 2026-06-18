# Odoo local en Docker + seed de productos — Diseño

**Fecha:** 2026-06-18
**Estado:** Aprobado (diseño) — pendiente revisión del spec
**Contexto:** Conector Capuccino Vainilla (Odoo ⇄ WooCommerce)

## Problema

Hoy los tests del conector pueden terminar apuntando al **Odoo de producción** de la empresa
(`capuccino-vainilla.odoo.com`, Odoo **16 Enterprise**, SaaS). El flujo de importación de pedidos
(`order_import.py`) **escribe** en Odoo: crea `sale.order` y `res.partner`. Correrlo contra
producción ensuciaría ventas y clientes reales. Necesitamos un entorno aislado.

El flujo de catálogo (`catalog_sync.py`) en cambio **solo lee** de Odoo (`product.template`,
`product.attribute.value`); nunca escribe.

## Objetivo

Levantar un **Odoo local en Docker** y poblarlo con una **copia fiel de los productos** del Odoo
real (incluyendo atributos y ventas cruzadas), para validar ambos flujos del conector sin riesgo
sobre producción. El Odoo real solo se toca en **modo lectura**, una vez, para copiar productos.

### No-objetivos (YAGNI)

- **No** copiar la base completa de Odoo (contabilidad, usuarios, facturas). Es data sensible,
  innecesaria para testear, y un dump Enterprise no restaura en una imagen Community.
- **No** sincronizar productos de forma continua origen→local; es una copia puntual y repetible.

## Decisiones tomadas

| Decisión | Elección | Motivo |
|----------|----------|--------|
| Método de copia | Script seed vía XML-RPC | Reusa `OdooClient`; repetible; copia catálogo completo |
| Alcance de copia | Producto + atributos + cross-sells | Permite ejercitar la sync de catálogo al 100% |
| Versión local | `odoo:16` (Community) | Coincide con el major del real (16 Enterprise) |
| Origen vs destino | Conexiones separadas; origen solo-lectura | Garantía de no escribir en producción |

## Arquitectura

### 1. Infraestructura Docker — nuevo profile `odoo`

Se agrega al `docker-compose.yml` (mismo patrón que el profile `woo`). No se levanta con `up`
salvo `--profile odoo`.

- **`odoo-db`**: `postgres:15`, volumen `odoo-db-data`, healthcheck (`pg_isready`).
- **`odoo`**: imagen `odoo:16`, `ports: 8069:8069`, `depends_on: odoo-db (healthy)`,
  volúmenes `odoo-data:/var/lib/odoo` y addons. Variables `HOST`, `USER`, `PASSWORD` apuntando a
  `odoo-db`.

> **Nota (descopado en la implementación):** originalmente el diseño preveía verificar con una
> llamada `version()` que el major del Odoo local coincidiera con el real. No se implementó: la
> coincidencia se garantiza por elección de imagen (`odoo:16` = Odoo 16 del real) y queda como
> verificación manual. Pendiente de implementar si se quiere una salvaguarda automática.

### 2. Configuración: credenciales origen vs destino

El seed usa **dos conexiones**:

- **ORIGEN** = Odoo real → usado **exclusivamente con métodos de lectura** (`search_read`, `read`).
  El script nunca invoca `create`/`write` sobre esta conexión. Recomendado: usuario/API key de
  solo lectura en Odoo.
- **DESTINO** = Odoo local Docker → acá se crea todo.

Nuevo archivo **`.env.seed`** (gitignored) con dos bloques de variables: `ODOO_SRC_*`
(URL/DB/USER/PASSWORD del real) y `ODOO_DST_*` (del local). El `.env` normal del conector pasa a
apuntar al **local** (`ODOO_URL=http://localhost:8069`), de modo que los tests de escritura nunca
toquen producción.

### 3. Script seed — `scripts/seed_odoo.py` (comando `seed-odoo`)

Reusa `OdooClient`. Copia en **tres pasadas** por el remapeo de IDs entre instancias:

1. **Atributos**: lee `product.attribute` + `product.attribute.value` del origen, los recrea en
   destino y construye un mapa `id_origen → id_destino`. Idempotencia por `name`.
2. **Productos**: lee `product.template` con los campos del catálogo
   (`name`, `default_code`, `list_price`, `description_sale`, `qty_available`, `attribute_line_ids`),
   recrea cada uno con `attribute_line_ids` remapeados. Idempotencia por `default_code` (SKU):
   si ya existe en destino, se actualiza en vez de duplicar. Productos sin SKU se omiten con warning.
3. **Cross-sells**: segunda pasada sobre `optional_product_ids`, ya con todos los templates creados,
   para linkear las ventas cruzadas (referencian otros templates, por eso van al final).

Al terminar imprime un reporte: copiados / actualizados / omitidos / fallidos.

### 4. Seguridad y aislamiento

- Conexión origen **read-only por contrato** (solo se le pasan métodos de lectura) y, a ser posible,
  read-only por permisos en Odoo.
- `.env.seed` con credenciales reales **nunca** al repositorio (entra en `.gitignore`).
- **Banner de confirmación**: el script muestra a qué URL va a escribir y **aborta si el destino no
  parece local** (heurística sobre host/puerto), evitando apuntarle a producción por error.

### 5. Testing (TDD)

Tests unitarios con `OdooClient` mockeado:

- Origen devuelve registros fake; destino captura los `create`/`write`.
- Se valida el **remapeo de IDs** de atributos (línea de atributo en destino usa id nuevo).
- **Idempotencia** por SKU: segunda corrida no duplica, actualiza.
- **Garantía de seguridad** (test explícito): la conexión origen **nunca recibe** `create`/`write`.
- Cross-sells se linkean recién en la tercera pasada.

## Flujo de uso

```bash
# 1. Levantar Odoo local
docker compose --profile odoo up -d
# 2. (primera vez) crear/inicializar la base de Odoo desde la UI o por parámetro
# 3. Copiar productos del real al local (lee real, escribe local)
seed-odoo --env .env.seed
# 4. Correr la sync de catálogo (local -> Woo de prueba)
docker compose run --rm sync
```

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Apuntar el seed a producción como destino | Banner + aborto si el destino no es local |
| Desfasaje de campos entre Community y Enterprise 16 | Solo se copian modelos de producto, idénticos en ambos |
| IDs de atributos distintos entre instancias | Remapeo explícito en pasada 1 |
| Cross-sells apuntando a templates aún no creados | Linkeo en tercera pasada, post-creación |
