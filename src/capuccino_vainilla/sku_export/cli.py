"""Entrypoint `export-sku-allowlist`: planilla .xlsx -> archivo de SKUs.

Uso:
    export-sku-allowlist --input "LISTA DE PRODUCTOS - GPINNACLE - 250826 - CON STOCK.xlsx"
    export-sku-allowlist --input planilla.xlsx --output sku_allowlist.txt --column "REF ODOO"

El archivo resultante es el que después apunta `SYNC_SKU_ALLOWLIST_FILE` en el
`.env`, para que `sync-catalog` / `watch` / el visor se acoten a esos SKUs en
vez de todo el catálogo vendible de Odoo.
"""

from __future__ import annotations

import argparse
import sys

from ..exceptions import ConnectorError
from .writer import write_allowlist
from .xlsx_reader import extract_skus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="export-sku-allowlist",
        description="Genera el archivo de SKUs autorizados a partir de una planilla .xlsx.",
    )
    parser.add_argument("--input", required=True, help="Ruta a la planilla .xlsx de origen.")
    parser.add_argument("--output", default="sku_allowlist.txt",
                        help="Ruta del archivo a escribir (default: sku_allowlist.txt).")
    parser.add_argument("--column", default="REF ODOO",
                        help="Encabezado de la columna con el SKU/Referencia interna de Odoo "
                             "(default: 'REF ODOO').")
    args = parser.parse_args(argv)

    try:
        skus = extract_skus(args.input, column_name=args.column)
        count = write_allowlist(skus, args.output, source_path=args.input)
    except ConnectorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{count} SKUs escritos en '{args.output}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
