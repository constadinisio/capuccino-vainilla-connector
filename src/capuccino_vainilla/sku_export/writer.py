"""Escritura del archivo de lista blanca en el formato que lee ``config.py``."""

from __future__ import annotations


def write_allowlist(skus: frozenset[str], output_path: str, *, source_path: str) -> int:
    """Escribe ``skus`` ordenados, uno por línea, con un encabezado de trazabilidad.

    El formato coincide con lo que espera ``SYNC_SKU_ALLOWLIST_FILE`` (líneas
    vacías y las que empiezan con '#' se ignoran al leerlo). Devuelve la
    cantidad de SKUs escritos.
    """
    ordered = sorted(skus)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Generado por export-sku-allowlist desde: {source_path}\n")
        fh.write(f"# Total: {len(ordered)} SKUs\n")
        for sku in ordered:
            fh.write(f"{sku}\n")
    return len(ordered)
