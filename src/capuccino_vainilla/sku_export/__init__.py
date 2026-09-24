"""Exportación de la lista blanca de SKUs desde la planilla de catálogo curado.

Convierte una columna de una planilla .xlsx (ej. "REF ODOO" en la lista de
productos GPinnacle) en el archivo de texto que consume
``RuntimeConfig.sku_allowlist`` / ``SYNC_SKU_ALLOWLIST_FILE``.
"""
